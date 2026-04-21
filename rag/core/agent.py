# rag/core/agent.py
"""Agente LangGraph para el pipeline RAG de jurisprudencia de playas.

Arquitectura:

  Providers con tool calling (OpenRouter, Gemini estándar):

    START → enrich_query → retrieve_prefetch → agent ⇆ tools → END

    El retrieve usa la consulta enriquecida (mejor recall). El agent recibe
    las sources ya inyectadas en el HumanMessage, por lo que en el caso
    feliz NO emite tool_calls y genera la respuesta en su primera llamada
    (una llamada LLM menos que el ReAct puro).

  Providers sin tool calling (Gemma vía Google GenAI):

    START → enrich_query → retrieve_forced → generate → END

Optimizaciones de latencia:
  1. Contexto pre-cargado: elimina la llamada LLM intermedia que solo
     emite tool_calls (de 3 llamadas LLM a 2 en el happy path).
  2. System prompt estable: el BASE_INSTRUCTIONS no contiene partes
     dinámicas, habilitando prompt caching automático (Grok, OpenAI, etc.).
     Todo lo dinámico (enriched_query, contexto) va en el HumanMessage final.
  3. Eventos custom de estado: cada nodo emite un evento "status" para que
     el frontend muestre progreso mientras se ejecuta.
"""

from __future__ import annotations

import asyncio
import operator
from typing import Annotated, Any

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from typing_extensions import TypedDict

from .llm_factory import get_active_provider, get_generation_llm
from .prompts import AGENT_FALLBACK_HUMAN_TEMPLATE, AGENT_HUMAN_CITATION_REMINDER, AGENT_SYSTEM
from .query_enricher import EnrichedQuery, enrich_query_async
from .retriever import get_ensemble_retriever
from .tools import ALL_TOOLS, build_context_block

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    enriched_query: str | None
    # Reducer operator.add: acumula docs entre prefetch + tool calls adicionales
    sources: Annotated[list[Document], operator.add]


# ---------------------------------------------------------------------------
# Prompt del sistema (ESTABLE — habilita prompt caching)
# ---------------------------------------------------------------------------
#
# Definido en rag/core/prompts.py como AGENT_SYSTEM. Este alias local
# mantiene compatibilidad con el resto del módulo sin cambiar los nombres
# de uso interno.

BASE_INSTRUCTIONS = AGENT_SYSTEM


def _build_human_turn(question: str, context: str) -> str:
    """Construye el HumanMessage con toda la información dinámica del turno.

    Mantener esto fuera del SystemMessage es lo que permite que Grok/OpenAI
    hagan cache-hit del prefijo (system) entre requests.
    """
    return (
        f"<context>\n{context}\n</context>\n\n"
        f"<question>\n{question}\n</question>\n\n"
        f"{AGENT_HUMAN_CITATION_REMINDER}"
    )


# Prompt del grafo fallback (providers sin tool calling) — importado desde prompts.py
_FALLBACK_HUMAN_TEMPLATE = AGENT_FALLBACK_HUMAN_TEMPLATE

PROMPT_WITH_SYSTEM = ChatPromptTemplate.from_messages(
    [("system", BASE_INSTRUCTIONS), ("human", _FALLBACK_HUMAN_TEMPLATE)]
)

PROMPT_NO_SYSTEM = ChatPromptTemplate.from_messages(
    [("human", "INSTRUCCIONES:\n{instructions}\n\n" + _FALLBACK_HUMAN_TEMPLATE)]
)


def _get_fallback_prompt() -> ChatPromptTemplate:
    if not get_active_provider().supports_system_role:
        return PROMPT_NO_SYSTEM.partial(instructions=BASE_INSTRUCTIONS)
    return PROMPT_WITH_SYSTEM


# ---------------------------------------------------------------------------
# Nodos — grafo ReAct con prefetch paralelo
# ---------------------------------------------------------------------------


def _emit_status(stage: str, message: str) -> None:
    """Emite un evento custom de estado consumible por el frontend vía SSE."""
    try:
        writer = get_stream_writer()
        writer({"type": "status", "stage": stage, "message": message})
    except Exception:
        # get_stream_writer solo está disponible dentro de graph.astream.
        # En invoke() o tests no hay writer; ignorar silenciosamente.
        pass


async def enrich_query_node(state: AgentState) -> dict:
    """Reescribe la pregunta del usuario para mejorar el recall del retriever."""
    _emit_status("enriching", "Reformulando la consulta…")
    enriched: EnrichedQuery = await enrich_query_async(state["question"])
    return {"enriched_query": enriched.expanded_query}


async def retrieve_prefetch_node(state: AgentState) -> dict:
    """Recupera jurisprudencia usando la consulta enriquecida.

    Se ejecuta después de enrich_query_node para aprovechar su reescritura
    (términos jurídicos, sinónimos, instituciones) y mejorar el recall del
    retriever híbrido BM25 + vector.
    """
    _emit_status("retrieving", "Buscando jurisprudencia relevante…")
    query = state.get("enriched_query") or state["question"]
    docs = await asyncio.to_thread(get_ensemble_retriever(k=8).invoke, query)
    return {"sources": docs}


async def agent_node(state: AgentState) -> dict:
    """Nodo ReAct: LLM con tools.

    En el happy path recibe contexto pre-cargado (sources) y responde sin
    llamar tools. Si el contexto es insuficiente, puede pedir retrieve
    con una query reformulada.
    """
    _emit_status("generating", "Analizando las sentencias y redactando la respuesta…")

    llm = get_generation_llm().bind_tools(ALL_TOOLS)  # type: ignore[union-attr]

    docs = state.get("sources") or []
    context = build_context_block(docs) if docs else "(No hay contexto pre-recuperado.)"

    # SystemMessage estable (cacheable) + HumanMessage con todo lo dinámico.
    system_msg = SystemMessage(content=BASE_INSTRUCTIONS)
    human_turn = _build_human_turn(state["question"], context)

    # Si ya hubo interacción previa (multi-turno), preservar el historial de
    # messages y añadir solo el nuevo HumanMessage con contexto.
    # Si es el primer turno, state["messages"] contiene solo el HumanMessage
    # original; lo reemplazamos por el enriquecido.
    prior_messages = [
        m
        for m in state["messages"]
        if not isinstance(m, HumanMessage) or m.content != state["question"]
    ]
    messages = [system_msg, *prior_messages, HumanMessage(content=human_turn)]

    response = await llm.ainvoke(messages)
    return {"messages": [response]}


# ---------------------------------------------------------------------------
# Nodos — grafo fallback determinista (providers sin tool calling)
# ---------------------------------------------------------------------------


async def retrieve_forced_node(state: AgentState) -> dict:
    _emit_status("retrieving", "Buscando jurisprudencia relevante…")
    query = state.get("enriched_query") or state["question"]
    docs = await asyncio.to_thread(get_ensemble_retriever(k=8).invoke, query)
    return {"sources": docs}


async def generate_node(state: AgentState) -> dict:
    _emit_status("generating", "Analizando las sentencias y redactando la respuesta…")
    docs = state.get("sources") or []
    context = build_context_block(docs)
    prompt = _get_fallback_prompt()
    llm = get_generation_llm()
    chain = prompt | llm | StrOutputParser()
    answer = await chain.ainvoke({"context": context, "question": state["question"]})
    return {"messages": [AIMessage(content=answer.strip())]}


# ---------------------------------------------------------------------------
# Factory del grafo
# ---------------------------------------------------------------------------


def build_graph() -> Any:
    """Compila y devuelve el StateGraph apropiado según el provider activo."""
    checkpointer = MemorySaver()
    if get_active_provider().supports_structured_output:
        return _build_react_graph(checkpointer)
    return _build_fallback_graph(checkpointer)


def _build_react_graph(checkpointer: MemorySaver) -> Any:
    """Grafo ReAct secuencial: enrich_query → retrieve_prefetch → agent ⇆ tools."""
    return (
        StateGraph(AgentState)
        .add_node("enrich_query", enrich_query_node)
        .add_node("retrieve_prefetch", retrieve_prefetch_node)
        .add_node("agent", agent_node)
        .add_node("tools", ToolNode(ALL_TOOLS, handle_tool_errors=True))
        .add_edge(START, "enrich_query")
        .add_edge("enrich_query", "retrieve_prefetch")
        .add_edge("retrieve_prefetch", "agent")
        .add_conditional_edges("agent", tools_condition, ["tools", END])
        .add_edge("tools", "agent")
        .compile(checkpointer=checkpointer)
    )


def _build_fallback_graph(checkpointer: MemorySaver) -> Any:
    """Grafo determinista para providers sin tool calling."""
    return (
        StateGraph(AgentState)
        .add_node("enrich_query", enrich_query_node)
        .add_node("retrieve_forced", retrieve_forced_node)
        .add_node("generate", generate_node)
        .add_edge(START, "enrich_query")
        .add_edge("enrich_query", "retrieve_forced")
        .add_edge("retrieve_forced", "generate")
        .add_edge("generate", END)
        .compile(checkpointer=checkpointer)
    )
