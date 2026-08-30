"""Grafo determinista para análisis, recuperación y generación jurídica.

El LLM ya no decide si debe consultar el corpus. Primero se analiza el alcance de
la pregunta y solo las consultas jurídicas dentro del dominio pasan por una única
recuperación. Esto evita respuestas generales sin fuentes y hace que el uso de la
consulta enriquecida sea verificable.
"""

from __future__ import annotations

import re
from typing import Annotated, Any, NotRequired

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from ..config import CONTEXT_BUDGET_WARNING_CHARS
from .llm_factory import get_active_provider, get_generation_llm
from .observability import (
    log_citation_format_error,
    log_context_budget_warning,
    log_full_context_size,
    stage_timer,
)
from .prompts import AGENT_FALLBACK_HUMAN_TEMPLATE, AGENT_SYSTEM
from .query_enricher import EnrichedQuery, QueryRoute, enrich_query_async
from .retriever import get_ensemble_retriever
from .tools import build_context_block


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    standalone_question: str | None
    enriched_query: str | None
    query_route: QueryRoute | None
    sources: list[Document]
    doc_types: NotRequired[list[str] | None]
    k: NotRequired[int]
    k_candidates: NotRequired[int]


BASE_INSTRUCTIONS = AGENT_SYSTEM

PROMPT_WITH_SYSTEM = ChatPromptTemplate.from_messages(
    [("system", BASE_INSTRUCTIONS), ("human", AGENT_FALLBACK_HUMAN_TEMPLATE)]
)
PROMPT_NO_SYSTEM = ChatPromptTemplate.from_messages(
    [("human", "INSTRUCCIONES:\n{instructions}\n\n" + AGENT_FALLBACK_HUMAN_TEMPLATE)]
)

_CITATION_RE = re.compile(r"\[doc(\d+)\]", re.IGNORECASE)
_MAX_ANALYSIS_HISTORY_CHARS = 4000

_CONVERSATION_RESPONSE = (
    "Puedo responder consultas sobre jurisprudencia y normatividad colombiana relacionada con "
    "playas, zonas costeras y aguas marítimas, incluidos derechos, usos permitidos o prohibidos, "
    "pesca, turismo, permisos, concesiones, sanciones, autoridades y procedimientos vinculados "
    "con esos espacios."
)
_OUT_OF_SCOPE_RESPONSE = (
    "La consulta está fuera del ámbito jurídico y normativo relacionado con playas, zonas "
    "costeras, aguas marítimas y bienes de uso público en Colombia. Puedo responder sobre pesca, "
    "turismo, derechos, permisos y procedimientos cuando estén vinculados con esos espacios."
)
_CLARIFICATION_RESPONSE = (
    "La consulta podría estar dentro del ámbito, pero necesito que indiques su "
    "conexión con playas, zonas costeras, aguas marítimas o bienes de uso público. Por ejemplo, "
    "puedes precisar el lugar, la actividad, el permiso, la autoridad o el derecho que deseas revisar."
)
_NO_EVIDENCE_RESPONSE = (
    "**Situación:** evidencia insuficiente.\n\n"
    "**Motivo:** no se recuperaron fragmentos del corpus que permitan sustentar una respuesta "
    "jurídica verificable.\n\n"
    "**Cómo reformular:** precisa la actividad, autoridad, norma, procedimiento, lugar o derecho "
    "relacionado con la playa o zona costera."
)
_INVALID_CITATIONS_RESPONSE = (
    "**Situación:** no fue posible producir una respuesta verificable.\n\n"
    "**Motivo:** la respuesta generada no quedó respaldada por citas válidas de los fragmentos "
    "recuperados. Para evitar presentar una conclusión jurídica sin fuente, no se muestra ese contenido."
)


def _conversation_response(question: str) -> str:
    """Responde interacciones sociales sin presentar una identidad al usuario."""
    normalized = re.sub(r"[^a-záéíóúñü\s]", "", question.casefold()).strip()
    if "gracias" in normalized:
        return "Con gusto."
    if any(term in normalized for term in ("adiós", "adios", "hasta luego")):
        return "Hasta luego."
    if normalized.startswith(("hola", "buenos días", "buenas tardes", "buenas noches")):
        return "Hola. ¿Cuál es tu consulta?"
    return _CONVERSATION_RESPONSE


def _compose_retrieval_query(state: AgentState) -> str:
    """Conserva la consulta original y añade reformulaciones sin duplicarlas."""
    candidates = (
        state["question"],
        state.get("standalone_question"),
        state.get("enriched_query"),
    )
    parts: list[str] = []
    for candidate in candidates:
        value = (candidate or "").strip()
        if value and value not in parts:
            parts.append(value)
    return "\n".join(parts)


def _compose_generation_question(state: AgentState) -> str:
    """Entrega al generador la pregunta exacta y su resolución contextual, si existe."""
    original = state["question"].strip()
    standalone = (state.get("standalone_question") or "").strip()
    if not standalone or standalone == original:
        return original
    return (
        f"Pregunta original: {original}\n"
        f"Reformulación contextual basada en el historial: {standalone}"
    )


def _get_fallback_prompt() -> ChatPromptTemplate:
    if not get_active_provider().supports_system_role:
        return PROMPT_NO_SYSTEM.partial(instructions=BASE_INSTRUCTIONS)
    return PROMPT_WITH_SYSTEM


def _emit_status(stage: str, message: str) -> None:
    try:
        writer = get_stream_writer()
        writer({"type": "status", "stage": stage, "message": message})
    except Exception:
        # Fuera de graph.astream no existe un writer; no es un error funcional.
        pass


def _history_for_analysis(messages: list[BaseMessage], question: str) -> str:
    """Serializa una ventana reciente, excluyendo solo el mensaje actual."""
    history = list(messages)
    if history and isinstance(history[-1], HumanMessage) and history[-1].content == question:
        history.pop()

    selected: list[str] = []
    used = 0
    for message in reversed(history):
        if not isinstance(message.content, str) or not message.content.strip():
            continue
        role = "Usuario" if isinstance(message, HumanMessage) else "Asistente"
        content = message.content.strip()
        remaining = _MAX_ANALYSIS_HISTORY_CHARS - used
        if remaining <= 0:
            break
        line = f"{role}: {content[:remaining]}"
        selected.append(line)
        used += len(line)
    return "\n".join(reversed(selected))


def extract_answer_from_state(state: dict) -> str:
    """Extrae el contenido del último ``AIMessage`` del state del grafo.

    Vive aquí, pública y tipada, en vez de en ``rag.api.main`` (de donde
    también la importa ``rag.core.generator`` — un adaptador pensado para
    uso offline, sin servidor; ver su docstring): así ninguna herramienta
    de ``core/`` termina forzando la carga completa de FastAPI, los routers
    y la base de datos solo por esta función pura, y tanto ``api.main``
    como ``core.generator`` la importan desde el mismo lugar sin duplicar
    la lógica ni depender uno del otro.
    """
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


def _validate_citations(answer: str, doc_count: int) -> bool:
    """Comprueba que una respuesta jurídica cite al menos un documento existente."""
    references = [int(value) for value in _CITATION_RE.findall(answer)]
    return bool(references) and all(1 <= value <= doc_count for value in references)


async def enrich_query_node(state: AgentState) -> dict:
    _emit_status("enriching", "Analizando el alcance y contexto de tu pregunta…")
    with stage_timer("enrich_query") as fields:
        history_context = _history_for_analysis(state["messages"], state["question"])
        analysis: EnrichedQuery = await enrich_query_async(state["question"], history_context)
        # `route` es un enum cerrado (QueryRoute), no texto libre de la
        # pregunta — seguro de loguear.
        fields["route"] = analysis.route

    requested_doc_types = state.get("doc_types")
    effective_doc_types = requested_doc_types or analysis.doc_types
    if analysis.route != "in_scope":
        effective_doc_types = []

    return {
        "query_route": analysis.route,
        "standalone_question": analysis.standalone_question,
        "enriched_query": analysis.expanded_query,
        "doc_types": effective_doc_types,
        "sources": [],
    }


def route_after_analysis(state: AgentState) -> str:
    return "retrieve" if state.get("query_route") == "in_scope" else "respond"


async def respond_without_retrieval_node(state: AgentState) -> dict:
    route = state.get("query_route")
    if route == "conversation":
        answer = _conversation_response(state["question"])
    elif route == "needs_clarification":
        answer = _CLARIFICATION_RESPONSE
    else:
        answer = _OUT_OF_SCOPE_RESPONSE
    return {"messages": [AIMessage(content=answer)], "sources": []}


async def retrieve_forced_node(state: AgentState) -> dict:
    _emit_status("retrieving", "Buscando evidencia en jurisprudencia y normatividad…")
    with stage_timer("retrieve_forced") as fields:
        query = _compose_retrieval_query(state)
        doc_types = state.get("doc_types") or None
        k = min(max(int(state.get("k", 4)), 1), 8)
        k_candidates = min(max(int(state.get("k_candidates", 8)), k), 20)

        retriever = get_ensemble_retriever(
            k=k,
            k_candidates=k_candidates,
            doc_types=doc_types,
        )
        # Una sola capa de concurrencia — ainvoke() orquesta BM25 y el
        # retriever vectorial internamente (asyncio.gather + to_thread, sin
        # ThreadPoolExecutor anidado). No se envuelve aquí en
        # asyncio.to_thread(retriever.invoke, ...).
        docs = await retriever.ainvoke(query)
        selected = docs[:k]
        # Conteo, no contenido: cuántos documentos, no cuáles ni su texto.
        fields["doc_count"] = len(selected)
    return {"sources": selected}


async def generate_node(state: AgentState) -> dict:
    _emit_status("generating", "Construyendo una respuesta respaldada por fuentes…")
    docs = state.get("sources") or []
    if not docs:
        return {"messages": [AIMessage(content=_NO_EVIDENCE_RESPONSE)]}

    with stage_timer("generate", doc_count=len(docs)):
        context = build_context_block(docs)
        prompt = _get_fallback_prompt()
        llm = get_generation_llm()
        chain = llm | StrOutputParser()
        question = _compose_generation_question(state)
        # Métrica interna de tamaño real del prompt de generación, solo
        # para logs — no afecta ni sustituye a `context_tokens` (campo
        # público, calculado en api/main.py a partir del historial en
        # `state["messages"]`). En vez de sumar `len()` de las piezas por
        # separado (subestimaría el tamaño real: ignora el texto literal
        # del template — las etiquetas <context>/<question>, el recordatorio
        # de citación, y en el caso sin system role el envoltorio
        # "INSTRUCCIONES:\n...\n\n"), se formatea el MISMO ChatPromptTemplate
        # que se le pasa al LLM y se cuentan los caracteres de los mensajes
        # ya formateados — el tamaño exacto de lo que efectivamente se
        # envía. Se formatea UNA sola vez: `prompt.ainvoke(...)` construye
        # el `PromptValue` que se usa tanto para medir `full_context_chars`
        # (vía `to_messages()`, templating local, sin red) como para invocar
        # al LLM directamente (`chain.ainvoke`, sin el `prompt` de vuelta en
        # el pipe) — evita formatear el mismo prompt dos veces: una aquí y
        # otra, de forma implícita, dentro del chain LCEL al incluir
        # `prompt | llm`.
        prompt_value = await prompt.ainvoke({"context": context, "question": question})
        full_context_chars = sum(len(str(m.content)) for m in prompt_value.to_messages())
        log_full_context_size(chars=full_context_chars)
        # A3.6 — presupuesto de contexto en modo observación: solo advierte,
        # no trunca ni fija max_tokens (ver CONTEXT_BUDGET_WARNING_CHARS).
        if full_context_chars > CONTEXT_BUDGET_WARNING_CHARS:
            log_context_budget_warning(
                chars=full_context_chars, doc_count=len(docs), stage="generate"
            )
        answer = str(await chain.ainvoke(prompt_value)).strip()

        if not _validate_citations(answer, len(docs)):
            log_citation_format_error(doc_count=len(docs))
            answer = _INVALID_CITATIONS_RESPONSE
    return {"messages": [AIMessage(content=answer)]}


def build_graph() -> Any:
    """Compila un único grafo determinista para todos los proveedores."""
    checkpointer = MemorySaver()
    return (
        StateGraph(AgentState)
        .add_node("enrich_query", enrich_query_node)
        .add_node("respond_without_retrieval", respond_without_retrieval_node)
        .add_node("retrieve_forced", retrieve_forced_node)
        .add_node("generate", generate_node)
        .add_edge(START, "enrich_query")
        .add_conditional_edges(
            "enrich_query",
            route_after_analysis,
            {"retrieve": "retrieve_forced", "respond": "respond_without_retrieval"},
        )
        .add_edge("respond_without_retrieval", END)
        .add_edge("retrieve_forced", "generate")
        .add_edge("generate", END)
        .compile(checkpointer=checkpointer)
    )
