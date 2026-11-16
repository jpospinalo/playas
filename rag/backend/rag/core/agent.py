"""Grafo determinista para análisis, recuperación y generación jurídica.

El LLM ya no decide si debe consultar el corpus. Primero se analiza el alcance de
la pregunta y solo las consultas jurídicas dentro del dominio pasan por una única
recuperación. Esto evita respuestas generales sin fuentes y hace que el uso de la
consulta enriquecida sea verificable.
"""

from __future__ import annotations

import asyncio
import logging
import re
from functools import partial
from pathlib import Path
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

from ..config import (
    CONTEXT_BUDGET_WARNING_CHARS,
    LEGAL_RESOLUTION_PROVENANCE_PATH,
    LEGAL_RESOLUTION_PROVENANCE_SHA256,
)
from .legal_resolution import (
    DocketEvidence,
    Resolution,
    ResolutionIndex,
    has_docket_intent,
    load_provenance,
    matches_answer_attribution,
    requires_operative_proof,
)
from .llm_factory import get_active_provider, get_generation_llm
from .observability import (
    log_citation_format_error,
    log_context_budget_warning,
    log_full_context_size,
    stage_timer,
)
from .prompts import AGENT_FALLBACK_HUMAN_TEMPLATE, AGENT_SYSTEM
from .query_enricher import EnrichedQuery, QueryRoute, enrich_query_async
from .retriever import HybridEnsembleRetriever, bm25_documents, get_ensemble_retriever
from .tools import build_context_block


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    question: str
    standalone_question: str | None
    enriched_query: str | None
    query_route: QueryRoute | None
    sources: list[Document]
    doc_types: NotRequired[list[str] | None]
    requested_doc_types: NotRequired[list[str] | None]
    verified_docket: NotRequired[str | None]
    verified_instance: NotRequired[str | None]
    documentary_answer: NotRequired[str | None]
    k: NotRequired[int]
    k_candidates: NotRequired[int]


BASE_INSTRUCTIONS = AGENT_SYSTEM
logger = logging.getLogger(__name__)

PROMPT_WITH_SYSTEM = ChatPromptTemplate.from_messages(
    [("system", BASE_INSTRUCTIONS), ("human", AGENT_FALLBACK_HUMAN_TEMPLATE)]
)
PROMPT_NO_SYSTEM = ChatPromptTemplate.from_messages(
    [("human", "INSTRUCCIONES:\n{instructions}\n\n" + AGENT_FALLBACK_HUMAN_TEMPLATE)]
)

_CITATION_RE = re.compile(r"\[doc(\d+)\]", re.IGNORECASE)
_MAX_ANALYSIS_HISTORY_CHARS = 4000

# Respuestas sin recuperación. Las cuatro guían al usuario en vez de limitarse
# a describir el ámbito en abstracto: quien no sabe cómo preguntar no sale de
# una descripción de alcance, pero sí sale de un ejemplo concreto y de los tres
# datos que de verdad hacen falta para buscar en el corpus. Los ejemplos tienen
# la forma de las consultas reales del ground truth (lugar + actividad +
# autoridad), y los lugares nombrados existen en el corpus.

_EJEMPLOS_CONSULTA = (
    "- «Un hotel con concesión cerró el paso a la playa frente a mi casa en El Rodadero, "
    "¿puede hacerlo?»\n"
    "- «¿Qué exige DIMAR para operar motos acuáticas en una playa de Santa Marta?»\n"
    "- «La Alcaldía autorizó un concierto en la playa, ¿qué requisitos debía cumplir?»"
)

_DATOS_QUE_FALTAN = (
    "- **Dónde**: la playa, el municipio o el distrito (El Rodadero, Taganga, Cartagena, "
    "Turbo…).\n"
    "- **Qué actividad o trámite**: acceso, ocupación, construcción, concesión, permiso, "
    "sanción, deslinde, evento.\n"
    "- **Quién intervino**: DIMAR, la alcaldía, la autoridad ambiental, un juez."
)

_CONVERSATION_RESPONSE = (
    "Puedo responder consultas sobre jurisprudencia y normatividad colombiana relacionada con "
    "playas, zonas costeras y aguas marítimas, incluidos derechos, usos permitidos o prohibidos, "
    "pesca, turismo, permisos, concesiones, sanciones, autoridades y procedimientos vinculados "
    "con esos espacios.\n\n"
    "Por ejemplo:\n" + _EJEMPLOS_CONSULTA + "\n\n"
    "Cuéntame tu caso con el lugar y la actividad y busco la jurisprudencia y la normativa "
    "que apliquen."
)
_OUT_OF_SCOPE_RESPONSE = (
    "La consulta está fuera del ámbito jurídico y normativo relacionado con playas, zonas "
    "costeras, aguas marítimas y bienes de uso público en Colombia.\n\n"
    "Si tu caso sí tiene un lado costero, planteámelo así:\n" + _EJEMPLOS_CONSULTA
)
_CLARIFICATION_RESPONSE = (
    "Tu consulta puede estar dentro del ámbito, pero necesito un poco más de contexto para "
    "buscar en las normas y sentencias que apliquen.\n\n"
    "Dime cualquiera de estos tres y sigo:\n" + _DATOS_QUE_FALTAN + "\n\n"
    "Así se ven las consultas que puedo responder:\n" + _EJEMPLOS_CONSULTA
)
_NO_EVIDENCE_RESPONSE = (
    "**Situación:** evidencia insuficiente.\n\n"
    "**Motivo:** no se recuperaron fragmentos del corpus que permitan sustentar una respuesta "
    "jurídica verificable.\n\n"
    "**Cómo reformular:** añade cualquiera de estos tres datos y vuelvo a buscar:\n"
    + _DATOS_QUE_FALTAN
    + "\n\nTambién ayuda nombrar la norma, el expediente o el magistrado ponente si los conoces."
)
_INVALID_CITATIONS_RESPONSE = (
    "**Situación:** no fue posible producir una respuesta verificable.\n\n"
    "**Motivo:** la respuesta generada no quedó respaldada por citas válidas de los fragmentos "
    "recuperados. Para evitar presentar una conclusión jurídica sin fuente, no se muestra ese contenido."
)


_SALUDOS = (
    "hola",
    "buenos días",
    "buenos dias",
    "buenas tardes",
    "buenas noches",
    "buen día",
    "buen dia",
    "buenas",
)
_CORTESIAS = frozenset(
    "cómo como estás estas está esta qué que tal vas va todo bien buenas buenos días dias tardes".split()
)
_GREETING_RESPONSE = (
    "Hola. Cuéntame tu caso y busco las normas y sentencias que apliquen.\n\n"
    "Me ayuda saber:\n" + _DATOS_QUE_FALTAN + "\n\n"
    "Por ejemplo:\n" + _EJEMPLOS_CONSULTA
)


def _conversation_response(question: str) -> str:
    """Responde interacciones sociales sin presentar una identidad al usuario."""
    normalized = re.sub(r"[^a-záéíóúñü\s]", "", question.casefold()).strip()
    if "gracias" in normalized:
        return "Con gusto."
    if any(term in normalized for term in ("adiós", "adios", "hasta luego")):
        return "Hasta luego."
    for saludo in _SALUDOS:
        if normalized.startswith(saludo):
            # Un saludo seguido de un asunto («hola, tengo un problema con la
            # playa») ya es una consulta: se pide el dato que falta en vez de
            # obligar a repetirla. Un saludo solo, o con cortesías («hola,
            # ¿cómo estás?»), recibe la guía con ejemplos.
            resto = [w for w in normalized[len(saludo) :].split() if w not in _CORTESIAS]
            return _CLARIFICATION_RESPONSE if len(resto) >= 2 else _GREETING_RESPONSE
    return _CONVERSATION_RESPONSE


def _retrieval_queries(state: AgentState) -> list[str]:
    """Consultas a recuperar por separado: original, autosuficiente y enriquecida.

    Conserva el orden, recorta espacios, descarta vacías y deduplica. Si la
    pregunta original queda vacía, no se inventa ninguna consulta.
    """
    question = (state["question"] or "").strip()
    if not question:
        return []

    queries = [question]
    for candidate in (state.get("standalone_question"), state.get("enriched_query")):
        value = (candidate or "").strip()
        if value and value not in queries:
            queries.append(value)
    return queries


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


_SOLO_CITAS_RE = re.compile(r"^\s*(?:\[doc\d+\]\s*)+$", re.IGNORECASE)
_TITULO_RE = re.compile(r"^\s*\*\*[^*\n]+\*\*\s*$")


def _tidy_answer(answer: str) -> str:
    """Limpia defectos de formato de la respuesta generada sin tocar su contenido.

    - Quita las líneas que solo contienen marcadores ``[docN]``: no respaldan
      ninguna frase (algunos modelos «etiquetan» así una sección).
    - Quita los títulos de sección en negrita repetidos; el contenido que
      seguía al duplicado se conserva bajo el primero.
    - Colapsa las líneas en blanco consecutivas que dejan esas supresiones.
    """
    lineas: list[str] = []
    titulos: set[str] = set()
    for linea in answer.splitlines():
        if _SOLO_CITAS_RE.match(linea):
            continue
        if _TITULO_RE.match(linea):
            clave = linea.strip().casefold()
            if clave in titulos:
                continue
            titulos.add(clave)
        if not linea.strip() and (not lineas or not lineas[-1].strip()):
            continue
        lineas.append(linea)
    while lineas and not lineas[-1].strip():
        lineas.pop()
    return "\n".join(lineas)


def _validate_citations(answer: str, doc_count: int) -> bool:
    """Comprueba que una respuesta jurídica cite al menos un documento existente."""
    references = [int(value) for value in _CITATION_RE.findall(answer)]
    return bool(references) and all(1 <= value <= doc_count for value in references)


async def enrich_query_node(state: AgentState, *, capture_filter: bool = False) -> dict:
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

    update: dict[str, Any] = {
        "query_route": analysis.route,
        "standalone_question": analysis.standalone_question,
        "enriched_query": analysis.expanded_query,
        "doc_types": effective_doc_types,
        "sources": [],
    }
    if capture_filter:
        update.update(
            requested_doc_types=requested_doc_types,
            verified_docket=None,
            verified_instance=None,
            documentary_answer=None,
        )
    return update


def route_after_analysis(state: AgentState) -> str:
    return "retrieve" if state.get("query_route") == "in_scope" else "respond"


def _permits_jurisprudence(state: AgentState) -> bool:
    requested = state.get("requested_doc_types")
    return requested is None or "jurisprudencia" in requested


async def _resolve_documentary(state: AgentState, index: ResolutionIndex) -> Resolution | None:
    try:
        resolution = await asyncio.to_thread(
            index.resolve,
            state["question"],
            max_sources=min(max(int(state.get("k", 4)), 1), 8),
        )
        if resolution is not None and _validate_citations(
            resolution.answer, len(resolution.sources)
        ):
            return resolution
    except Exception as exc:
        logger.warning("legal_resolution_failed error_type=%s", type(exc).__name__)
    return None


async def respond_without_retrieval_node(
    state: AgentState, *, resolution_index: ResolutionIndex | None = None
) -> dict:
    route = state.get("query_route")
    if (
        route in {"out_of_scope", "needs_clarification"}
        and resolution_index is not None
        and _permits_jurisprudence(state)
        and has_docket_intent(state["question"])
    ):
        resolution = await _resolve_documentary(state, resolution_index)
        if resolution is not None:
            return {
                "messages": [AIMessage(content=resolution.answer)],
                "sources": resolution.presentation_sources(),
                "query_route": "in_scope",
                "doc_types": ["jurisprudencia"],
            }

    if route == "conversation":
        answer = _conversation_response(state["question"])
    elif route == "needs_clarification":
        answer = _CLARIFICATION_RESPONSE
    else:
        answer = _OUT_OF_SCOPE_RESPONSE
    return {"messages": [AIMessage(content=answer)], "sources": []}


async def retrieve_forced_node(
    state: AgentState,
    *,
    verify_docket: bool = False,
    resolution_index: ResolutionIndex | None = None,
) -> dict:
    evidence: DocketEvidence | None = None
    if verify_docket and _permits_jurisprudence(state):
        question = state["question"]
        if has_docket_intent(question):
            if resolution_index is None:
                return {"sources": []}
            evidence = resolution_index.docket_evidence(question)
            if evidence is None:
                return {"sources": []}
            resolution = await _resolve_documentary(state, resolution_index)
            if resolution is not None:
                return {
                    "sources": resolution.presentation_sources(),
                    "documentary_answer": resolution.answer,
                }
        if requires_operative_proof(question):
            return {"sources": []}
    _emit_status("retrieving", "Buscando evidencia en jurisprudencia y normatividad…")
    with stage_timer("retrieve_forced") as fields:
        doc_types = state.get("doc_types") or None
        k = min(max(int(state.get("k", 4)), 1), 8)
        k_candidates = min(max(int(state.get("k_candidates", 8)), k), 20)

        retriever = get_ensemble_retriever(
            k=k_candidates if evidence else k,
            k_candidates=k_candidates,
            doc_types=["jurisprudencia"] if evidence else doc_types,
        )
        # Una sola capa de concurrencia: ni afuse_queries() ni ainvoke() se
        # envuelven en asyncio.to_thread(retriever.invoke, ...).
        queries = _retrieval_queries(state)
        if evidence:
            # Radicado verificado: una consulta compuesta basta para traer los
            # fragmentos de esa sentencia; evidence filtra los verificados.
            # Aquí se buscan VARIOS fragmentos de una misma sentencia, así que
            # se quita el tope de un fragmento por sentencia (sobre una copia).
            if isinstance(retriever, HybridEnsembleRetriever):
                retriever = retriever.model_copy(update={"fragmentos_por_sentencia": None})
            docs = await retriever.ainvoke("\n".join(queries))
            selected, documentary_answer = evidence.select_for_question(state["question"], docs, k)
        else:
            # Resto de preguntas: original, autosuficiente y enriquecida se
            # recuperan por separado y se fusionan (afuse_queries).
            docs = await retriever.afuse_queries(queries)
            selected, documentary_answer = docs[:k], None
        # Conteo, no contenido: cuántos documentos, no cuáles ni su texto.
        fields["doc_count"] = len(selected)
    if verify_docket:
        if documentary_answer is not None and not _validate_citations(
            documentary_answer, len(selected)
        ):
            return {"sources": []}
        return {
            "sources": selected,
            "verified_docket": evidence.docket if evidence else None,
            "verified_instance": evidence.instance if evidence else None,
            "documentary_answer": documentary_answer,
        }
    return {"sources": selected}


async def generate_node(state: AgentState) -> dict:
    if answer := state.get("documentary_answer"):
        return {"messages": [AIMessage(content=answer)]}
    _emit_status("generating", "Construyendo una respuesta respaldada por fuentes…")
    docs = state.get("sources") or []
    if not docs:
        return {"messages": [AIMessage(content=_NO_EVIDENCE_RESPONSE)]}

    with stage_timer("generate", doc_count=len(docs)):
        docket, instance = state.get("verified_docket"), state.get("verified_instance")
        context = build_context_block(docs, include_source_identifiers=not (docket and instance))
        prompt = _get_fallback_prompt()
        llm = get_generation_llm()
        chain = llm | StrOutputParser()
        question = _compose_generation_question(state)
        if docket and instance:
            question += (
                f"\nAtribución documental verificada: radicado {docket}, {instance}. "
                "Identifica esta providencia con esos datos."
            )
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
        answer = _tidy_answer(str(await chain.ainvoke(prompt_value)).strip())

        if docket and instance and not matches_answer_attribution(answer, docket, instance):
            return {"messages": [AIMessage(content=_INVALID_CITATIONS_RESPONSE)], "sources": []}
        if not _validate_citations(answer, len(docs)):
            log_citation_format_error(doc_count=len(docs))
            if docket and instance:
                return {"messages": [AIMessage(content=_INVALID_CITATIONS_RESPONSE)], "sources": []}
            answer = _INVALID_CITATIONS_RESPONSE
    return {"messages": [AIMessage(content=answer)]}


def build_graph() -> Any:
    """Compila un único grafo determinista para todos los proveedores."""
    checkpointer = MemorySaver()
    verify_docket = LEGAL_RESOLUTION_PROVENANCE_PATH is not None
    resolution_index = None
    if LEGAL_RESOLUTION_PROVENANCE_PATH:
        try:
            provenance = load_provenance(
                Path(LEGAL_RESOLUTION_PROVENANCE_PATH), LEGAL_RESOLUTION_PROVENANCE_SHA256
            )
            index = ResolutionIndex(bm25_documents(), provenance)
            if index.snapshot_verified:
                resolution_index = index
                logger.info("legal_resolution_snapshot_verified records=%d", len(provenance))
            else:
                logger.warning("legal_resolution_snapshot_unverified")
        except (OSError, ValueError) as exc:
            logger.warning(
                "legal_resolution_provenance_unavailable error_type=%s", type(exc).__name__
            )
    return (
        StateGraph(AgentState)
        .add_node("enrich_query", partial(enrich_query_node, capture_filter=verify_docket))
        .add_node(
            "respond_without_retrieval",
            partial(respond_without_retrieval_node, resolution_index=resolution_index),
        )
        .add_node(
            "retrieve_forced",
            partial(
                retrieve_forced_node, verify_docket=verify_docket, resolution_index=resolution_index
            ),
        )
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
