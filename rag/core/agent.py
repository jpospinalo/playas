# rag/core/agent.py
"""Agente LangGraph para el pipeline RAG de jurisprudencia de playas.

Arquitectura:

  Providers con tool calling (OpenRouter, Gemini estándar):

    START → enrich_query → agent ⇆ tools → END

    El agente decide autónomamente si llama a `retrieve` según si la pregunta
    requiere jurisprudencia. El happy path para preguntas no jurídicas termina
    sin llamar tools. El happy path jurídico necesita 3 llamadas LLM:
    enrich + agent-sin-contexto (emite tool_call) + agent-post-retrieve.

  Providers sin tool calling (Gemma vía Google GenAI):

    START → enrich_query → retrieve_forced → generate → END

Optimizaciones:
  1. System prompt estable: BASE_INSTRUCTIONS no contiene partes dinámicas,
     habilitando prompt caching automático (Grok, OpenAI, etc.).
     Todo lo dinámico (enriched_query, contexto) va en el HumanMessage.
  2. Eventos custom de estado: cada nodo emite un evento "status" para que
     el frontend muestre progreso mientras se ejecuta.
"""

from __future__ import annotations

import asyncio
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
from .prompts import (
    AGENT_FALLBACK_HUMAN_TEMPLATE,
    AGENT_HUMAN_CITATION_REMINDER,
    AGENT_HUMAN_NO_CONTEXT_SUFFIX,
    AGENT_SYSTEM,
)
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
    # Sin reducer: overwrite. enrich_query_node lo resetea al inicio de cada turno;
    # la tool retrieve lo sobrescribe con los docs recuperados.
    sources: list[Document]


# ---------------------------------------------------------------------------
# Prompt del sistema (ESTABLE — habilita prompt caching)
# ---------------------------------------------------------------------------
#
# Definido en rag/core/prompts.py como AGENT_SYSTEM. Este alias local
# mantiene compatibilidad con el resto del módulo sin cambiar los nombres
# de uso interno.

BASE_INSTRUCTIONS = AGENT_SYSTEM


def _build_human_turn(
    question: str,
    enriched_query: str | None,
    context: str | None,
) -> str:
    """Construye el HumanMessage con toda la información dinámica del turno.

    - Sin contexto (primera llamada): expone enriched_query y pide al LLM que
      decida si hace retrieve. Mantiene el SystemMessage estable para caching.
    - Con contexto (post-retrieve): inyecta los docs y el recordatorio de citas.
    """
    parts: list[str] = []
    if enriched_query:
        parts.append(f"<enriched_query>\n{enriched_query}\n</enriched_query>")
    if context:
        parts.append(f"<context>\n{context}\n</context>")
        parts.append(f"<question>\n{question}\n</question>")
        parts.append(AGENT_HUMAN_CITATION_REMINDER)
    else:
        parts.append(f"<question>\n{question}\n</question>")
        parts.append(AGENT_HUMAN_NO_CONTEXT_SUFFIX)
    return "\n\n".join(parts)


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
# Nodos — grafo ReAct con retrieval condicional
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
    # Resetear sources al inicio de cada turno para no arrastrar docs de turnos anteriores.
    return {"enriched_query": enriched.expanded_query, "sources": []}


async def agent_node(state: AgentState) -> dict:
    """Nodo ReAct: LLM con tools.

    Primera llamada: sin contexto. El LLM decide si llama `retrieve` o responde
    directamente según si la pregunta requiere jurisprudencia.
    Llamadas posteriores (post-retrieve): hay docs en state["sources"], se
    inyectan en el human turn para responder con citas.
    """
    docs = state.get("sources") or []
    enriched_query = state.get("enriched_query")
    context = build_context_block(docs) if docs else None

    if context:
        _emit_status("generating", "Analizando las sentencias y redactando la respuesta…")
    else:
        _emit_status("generating", "Evaluando la consulta…")

    llm = get_generation_llm().bind_tools(ALL_TOOLS)  # type: ignore[union-attr]
    system_msg = SystemMessage(content=BASE_INSTRUCTIONS)
    human_turn = _build_human_turn(state["question"], enriched_query, context)

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
    """Grafo ReAct: enrich_query → agent ⇆ tools. El LLM decide cuándo recuperar."""
    return (
        StateGraph(AgentState)
        .add_node("enrich_query", enrich_query_node)
        .add_node("agent", agent_node)
        .add_node("tools", ToolNode(ALL_TOOLS, handle_tool_errors=True))
        .add_edge(START, "enrich_query")
        .add_edge("enrich_query", "agent")
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
