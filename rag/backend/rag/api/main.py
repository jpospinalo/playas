"""FastAPI application para el sistema RAG de jurisprudencia de playas.

Expone estos endpoints sobre el agente LangGraph:
  GET  /api/health          — liveness check
  GET  /api/ready            — readiness check (T2.5; ver docstring de `ready()`)
  POST /api/query           — respuesta completa (JSON)
  POST /api/query/stream    — streaming SSE con tokens del LLM

Run with:
    uv run uvicorn rag.api.main:app --reload --port 8080
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.rate_limit import backpressure, get_query_user
from rag.api.routes.admin import router as admin_router
from rag.api.routes.auth import router as auth_router
from rag.api.routes.conversations import router as conversations_router
from rag.api.routes.feedback import router as feedback_router
from rag.api.schemas import QueryRequest, QueryResponse, SourceFragment, SourceGroup
from rag.config import CONTEXT_LIMIT_TOKENS
from rag.core.agent import extract_answer_from_state as _extract_answer_from_state
from rag.core.observability import ActiveQueryTracker, log_retained_conversations
from rag.core.retriever import bm25_index_is_empty, init_retrievers
from rag.core.tools import sanitize_replacement_chars

# T2.5: timeout corto por defecto para el chequeo de base de datos en
# /api/ready — una base de datos colgada no debe bloquear el readiness probe
# indefinidamente. Como constante de módulo para que las pruebas puedan
# ejercer el timeout real sin esperarlo (pasando un valor pequeño explícito
# a `_check_database_ready`).
READY_DB_TIMEOUT_SECONDS = 2.0

# ── Singleton del grafo ─────────────────────────────────────────────────────

_graph: Any = None
logger = logging.getLogger(__name__)

# T3.1: gauge de consultas en curso, sin contenido de negocio (ver
# rag.core.observability). Un único proceso, un único tracker de módulo.
ACTIVE_QUERIES = ActiveQueryTracker()

# T3.5: lock por conversación (ver rag.api.conversation_lock) — serializa
# turnos concurrentes sobre el MISMO thread_id, demostrado necesario por un
# test de interleaving real. No serializa entre conversaciones distintas.
CONVERSATION_LOCKS = ConversationLockRegistry()


def get_graph() -> Any:
    if _graph is None:
        raise RuntimeError("El grafo no ha sido compilado. Verifica el lifespan de la app.")
    return _graph


# ── Lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-calienta los componentes costosos al arrancar:
    - Tablas de la base de datos (create_all idempotente)
    - Conexión HTTP a Chroma (singleton)
    - Índice BM25 completo (construido una sola vez desde el corpus de Chroma)
    - Vectorstore LangChain-Chroma (singleton)
    - Grafo LangGraph compilado (singleton con MemorySaver)
    """
    import asyncio

    from rag.api.database import init_db
    from rag.core.agent import build_graph

    global _graph
    await init_db()
    await asyncio.to_thread(init_retrievers)
    _graph = build_graph()
    yield


# ── App ────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="RAG Playas API",
    description=(
        "Sistema de consulta de jurisprudencia y normatividad colombiana relacionada con playas"
    ),
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(conversations_router)
app.include_router(feedback_router)
app.include_router(admin_router)


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_answer(answer: str) -> str:
    """Elimina sufijos de citación que algunos LLMs añaden al final."""
    patterns = [
        r"\s*\(fuente:[^)]+\)\s*$",
        r"\s*\((?:doc|chunk)[^)]*\)\s*$",
    ]
    for p in patterns:
        answer = re.sub(p, "", answer)
    return answer.strip()


# Campos de metadata que pertenecen al documento (no al fragmento). El resto
# de claves se considera específico del chunk y viaja en SourceFragment.metadata.
_DOC_LEVEL_META_KEYS = (
    "doc_type",
    "norma",
    "tipo_norma",
    "anio",
    "title",
    "book_title",
    "Archivo",
    "No",
    "Corporación",
    "Radicado",
    "Magistrado ponente",
    "Tema principal",
    "Partes procesales",
    "RELACIÓN PLAYAS",
    "TEMATICA",
)


def _resolve_title(meta: dict) -> str:
    """Resuelve el título legible de un documento a partir de su metadata.

    Prioridad: ``title`` → ``book_title`` → stem del ``source`` (reemplazando
    ``_`` por espacios). Devuelve ``""`` si nada está disponible.
    """
    title = meta.get("title") or meta.get("book_title") or ""
    if title:
        return title
    source_path = meta.get("source", "")
    return Path(source_path).stem.replace("_", " ") if source_path else ""


def _truncate_content(text: str) -> str:
    """Trunca contenido de fragmento a 500 caracteres (para respuesta al frontend)."""
    content = (text or "").strip().replace("\n", " ")
    if len(content) > 500:
        content = content[:500] + "..."
    return content


def _docs_to_source_groups(docs: list[Document]) -> list[SourceGroup]:
    """Agrupa los documentos recuperados por archivo de origen.

    - Conserva el orden de recuperación (el primer fragmento determina la
      posición del grupo en la lista, lo que preserva "mejor score primero").
    - Asigna a cada fragmento un `index` global 1-based que coincide con los
      marcadores `[docN]` que `tools.build_context_block` inyecta en el prompt.
    - Separa los metadatos en nivel-documento (compartidos entre fragmentos del
      mismo archivo) y nivel-fragmento (sección, summary, keywords, entities).
    """
    groups: dict[str, SourceGroup] = {}
    order: list[str] = []

    for i, doc in enumerate(docs):
        # Parche temporal: limpiar U+FFFD antes de exponer al frontend.
        # Ver docs/INGEST_ENCODING_BUG.md.
        meta = sanitize_replacement_chars(dict(doc.metadata or {}))
        source = meta.get("source", "") or f"__unknown_{i}__"

        fragment_meta = {
            k: v for k, v in meta.items() if k not in (*_DOC_LEVEL_META_KEYS, "source")
        }
        fragment = SourceFragment(
            index=i + 1,
            content=_truncate_content(sanitize_replacement_chars(doc.page_content or "")),
            metadata=fragment_meta,
        )

        if source not in groups:
            doc_meta = {k: meta[k] for k in _DOC_LEVEL_META_KEYS if k in meta}
            groups[source] = SourceGroup(
                source=meta.get("source", ""),
                title=_resolve_title(meta),
                doc_type=meta.get("doc_type"),
                metadata=doc_meta,
                fragments=[fragment],
            )
            order.append(source)
        else:
            groups[source].fragments.append(fragment)

    return [groups[s] for s in order]


def _make_config(
    user_id: str,
    conversation_id: str | None,
    thread_id: str | None,
    recursion_limit: int = 10,
) -> dict:
    """Construye una clave de checkpoint aislada por usuario y conversación."""
    logical_id = conversation_id or thread_id or str(uuid.uuid4())
    tid = f"user:{user_id}:conversation:{logical_id}"
    return {
        "configurable": {"thread_id": tid},
        "recursion_limit": recursion_limit,
    }


def _estimate_context_tokens(messages: list) -> int:
    """Estimación rápida de tokens en el historial (~4 chars/token).

    Solo cuenta los mensajes acumulados en state (HumanMessages + AIMessages),
    no el system prompt ni los docs del turno actual, que son overhead fijo.
    """
    total_chars = 0
    for m in messages:
        content = m.content
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total_chars += len(part)
                elif isinstance(part, dict):
                    total_chars += len(str(part.get("text", "")))
    return total_chars // 4


def _build_graph_input(request: QueryRequest, messages: list) -> dict[str, Any]:
    """Construye en un solo lugar el contrato de entrada del grafo."""
    return {
        "question": request.question,
        "standalone_question": None,
        "enriched_query": None,
        "query_route": None,
        "messages": messages,
        "sources": [],
        "doc_types": request.doc_types,
        "k": request.k,
        "k_candidates": request.k_candidates,
    }


# ── Hydration ──────────────────────────────────────────────────────────────


async def _get_initial_messages(
    graph,
    config: dict,
    conversation_id: str | None,
    question: str,
    user_id: str,
    current_message_id: str | None = None,
) -> list:
    """Devuelve los mensajes iniciales para invocar el agente.

    - Si MemorySaver tiene estado: solo añade la nueva pregunta (continuación normal).
    - Si no hay estado y hay conversation_id: carga el historial desde la base de datos
      e inyecta el contexto completo (útil tras reinicio del servidor).
    - Si no hay estado ni conversation_id: comienza conversación nueva.
    """
    if not conversation_id:
        if current_message_id:
            raise HTTPException(
                status_code=422,
                detail="current_message_id requiere conversation_id.",
            )
        return [HumanMessage(content=question)]

    from sqlalchemy import select

    from rag.api.database import async_session_factory
    from rag.api.models import Conversation, Message

    async with async_session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")

        if current_message_id:
            current_message = await session.get(Message, current_message_id)
            if (
                current_message is None
                or current_message.conversation_id != conversation_id
                or current_message.role != "user"
                or current_message.text.strip() != question.strip()
            ):
                raise HTTPException(
                    status_code=422,
                    detail="El mensaje actual no coincide con la conversación y la pregunta.",
                )

        state = await graph.aget_state(config)
        has_checkpoint = bool((state.values if hasattr(state, "values") else {}).get("messages"))
        if has_checkpoint:
            return [HumanMessage(content=question)]

        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        msgs = result.scalars().all()

    history: list = []
    for msg in msgs:
        if msg.id == current_message_id:
            continue
        if msg.role == "user":
            history.append(HumanMessage(content=msg.text))
        else:
            history.append(AIMessage(content=msg.text))

    return history + [HumanMessage(content=question)]


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


async def _check_database_ready(timeout: float = READY_DB_TIMEOUT_SECONDS) -> bool:
    """Verifica que la base de datos responda una consulta trivial dentro
    de ``timeout`` segundos.

    Solo para uso interno de ``/api/ready``: cualquier fallo (timeout,
    conexión rechazada, credenciales inválidas, lo que sea) se colapsa a
    ``False`` sin propagar la excepción ni su mensaje — no debe filtrarse
    ningún detalle de infraestructura (host, credenciales) a quien consulta
    el endpoint.
    """
    from sqlalchemy import text

    from rag.api.database import async_session_factory

    async def _ping() -> None:
        async with async_session_factory() as session:
            await session.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(_ping(), timeout=timeout)
    except Exception:
        return False
    return True


@app.get("/api/ready")
async def ready() -> JSONResponse:
    """Readiness check (T2.5): a diferencia de ``/api/health`` (liveness,
    siempre ``{"status": "ok"}`` si el proceso responde), este endpoint
    verifica que las dependencias necesarias para atender una consulta estén
    realmente disponibles:

    - ``graph_compiled``  — el grafo LangGraph ya terminó de compilarse en
      el lifespan de arranque.
    - ``index_not_empty`` — el índice BM25 se inicializó con un corpus no
      vacío. Se apoya en ``retriever.bm25_index_is_empty()`` (expuesta desde
      T2.1 justo con este propósito), pero SOLO se evalúa cuando el grafo ya
      compiló: ``bm25_index_is_empty()`` devuelve ``False`` tanto si el
      índice tiene contenido como si aún no se inicializó (ver su
      docstring), así que evaluarla antes de que el lifespan termine
      reportaría un falso "no vacío".
    - ``database``        — una consulta trivial a la base de datos responde
      dentro de un timeout corto (no bloquea el probe si la base está
      caída/colgada).

    No invoca ningún LLM ni el grafo (nunca llama a ``graph.ainvoke`` /
    ``graph.astream``). No expone detalles de infraestructura ni mensajes de
    excepción: solo booleanos por chequeo. Devuelve 200 si todos los
    chequeos pasan, 503 si falta alguno.
    """
    graph_compiled = _graph is not None
    checks = {
        "graph_compiled": graph_compiled,
        "index_not_empty": graph_compiled and not bm25_index_is_empty(),
        "database": await _check_database_ready(),
    }
    is_ready = all(checks.values())
    return JSONResponse(
        status_code=200 if is_ready else 503,
        content={"status": "ready" if is_ready else "not_ready", "checks": checks},
    )


@app.post("/api/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    user: dict = Depends(get_query_user),
) -> QueryResponse:
    """Consulta jurídica completa (respuesta JSON).

    Ejecuta el agente LangGraph hasta completar el ciclo enrich → retrieve → generate.
    Soporta memoria multi-turno si se proporciona `thread_id`.
    """
    graph = get_graph()
    config = _make_config(user["sub"], request.conversation_id, request.thread_id)
    thread_id = config["configurable"]["thread_id"]

    # C4: el lock de conversación se adquiere PRIMERO, y el slot de
    # backpressure DESPUÉS, justo antes del trabajo que consume recursos.
    # Antes era al revés: una segunda solicitud de una conversación que ya
    # tiene un turno en curso reservaba un slot global de backpressure solo
    # para quedarse esperando el lock de SU conversación — sin hacer ningún
    # trabajo real — restándole capacidad a conversaciones independientes.
    # Con este orden, esperar el lock nunca consume un slot; si backpressure
    # rechaza con 503 una vez adquirido el lock, la salida de este `async
    # with` lo libera de inmediato (sin código especial: es la propagación
    # normal de la excepción). Mismo orden en /api/query/stream — evita
    # tanto la falta de equidad como un futuro deadlock por orden
    # inconsistente entre los dos endpoints.
    async with CONVERSATION_LOCKS.hold(thread_id):
        async with backpressure.slot():
            with ACTIVE_QUERIES.track():
                try:
                    initial_messages = await _get_initial_messages(
                        graph,
                        config,
                        request.conversation_id,
                        request.question,
                        user["sub"],
                        request.current_message_id,
                    )
                    final_state = await graph.ainvoke(
                        _build_graph_input(request, initial_messages),
                        config=config,
                    )
                except Exception as exc:
                    if isinstance(exc, HTTPException):
                        raise
                    logger.exception("Error procesando una consulta RAG")
                    raise HTTPException(
                        status_code=500,
                        detail="No fue posible procesar la consulta.",
                    ) from exc
                finally:
                    # Estado de retención DESPUÉS de esta consulta (incluye la
                    # conversación que se acaba de procesar, si es nueva).
                    log_retained_conversations(graph.checkpointer)

    answer_raw = _extract_answer_from_state(final_state)
    if not answer_raw:
        answer_raw = "No se encontraron fragmentos relevantes en la base de conocimiento."

    sources = final_state.get("sources") or []
    enriched_query = final_state.get("enriched_query")
    context_tokens = _estimate_context_tokens(final_state.get("messages", []))

    return QueryResponse(
        answer=_clean_answer(answer_raw),
        sources=_docs_to_source_groups(sources),
        enriched_query=enriched_query,
        query_route=final_state.get("query_route"),
        context_tokens=context_tokens,
        context_limit=CONTEXT_LIMIT_TOKENS,
    )


@app.post("/api/query/stream")
async def query_stream(
    request: QueryRequest,
    user: dict = Depends(get_query_user),
):
    """Streaming SSE: emite estados y luego la respuesta validada en fragmentos.

    Formato de eventos SSE:
      data: {"type": "token",   "content": "<fragmento>"}
      data: {"type": "sources", "sources": [...], "enriched_query": "..."}
      data: [DONE]

    La respuesta se valida antes de exponerla para impedir citas inexistentes o
    conclusiones jurídicas sin respaldo. Al finalizar se envían las fuentes y
    la consulta enriquecida.
    """
    graph = get_graph()
    config = _make_config(user["sub"], request.conversation_id, request.thread_id)
    thread_id = config["configurable"]["thread_id"]

    # T3.6 + T3.5/C3: ambos se adquieren aquí (antes de la hidratación) y se
    # liberan al final de event_generator() — deliberadamente NO se resuelve
    # todo antes del StreamingResponse, porque _get_initial_messages() debe
    # poder seguir lanzando su HTTPException (404/422, o 503 de
    # backpressure) ANTES de que exista el StreamingResponse, igual que hoy;
    # solo necesitan cubrir desde aquí hasta que termine el streaming.
    # Ambos recursos se registran en el mismo AsyncExitStack (hold() es un
    # context manager async como backpressure.slot()) — se entra en un
    # scope y se cierra en otro, y aclose() los libera en orden inverso ante
    # cualquier salida (éxito, excepción o cancelación), sin necesidad de
    # llevar la cuenta manual de qué se adquirió.
    #
    # C4: lock PRIMERO, backpressure DESPUÉS — mismo orden que /api/query,
    # y por el mismo motivo: esperar el lock de conversación no debe
    # consumir un slot global. Si backpressure rechaza con 503 tras haber
    # adquirido el lock, el `except` de abajo cierra el stack (libera el
    # lock) antes de relanzar.
    resource_stack = AsyncExitStack()
    try:
        await resource_stack.enter_async_context(CONVERSATION_LOCKS.hold(thread_id))
        await resource_stack.enter_async_context(backpressure.slot())
    except BaseException:
        await resource_stack.aclose()
        raise
    try:
        initial_messages = await _get_initial_messages(
            graph,
            config,
            request.conversation_id,
            request.question,
            user["sub"],
            request.current_message_id,
        )
    except BaseException:
        await resource_stack.aclose()
        raise

    async def event_generator() -> AsyncGenerator[str, None]:
        with ACTIVE_QUERIES.track():
            try:
                # La generación se valida dentro del grafo antes de exponerla. Por eso
                # conservamos el último snapshot de este stream y emitimos su texto validado.
                values: dict[str, Any] = {}
                async for mode, payload in graph.astream(
                    _build_graph_input(request, initial_messages),
                    config=config,
                    stream_mode=["values", "custom"],
                ):
                    if mode == "custom":
                        # Eventos de estado emitidos por los nodos
                        if isinstance(payload, dict) and payload.get("type") == "status":
                            event = json.dumps(payload)
                            yield f"data: {event}\n\n"
                    elif mode == "values" and isinstance(payload, dict):
                        values = payload

                answer = _clean_answer(_extract_answer_from_state(values))
                if not answer:
                    answer = "No se encontraron fragmentos relevantes en la base de conocimiento."
                for start in range(0, len(answer), 120):
                    event = json.dumps({"type": "token", "content": answer[start : start + 120]})
                    yield f"data: {event}\n\n"

                sources_raw = values.get("sources") or []
                enriched_query = values.get("enriched_query")
                context_tokens = _estimate_context_tokens(values.get("messages", []))

                sources_payload = [g.model_dump() for g in _docs_to_source_groups(sources_raw)]
                event = json.dumps(
                    {
                        "type": "sources",
                        "sources": sources_payload,
                        "enriched_query": enriched_query,
                        "query_route": values.get("query_route"),
                        "context_tokens": context_tokens,
                        "context_limit": CONTEXT_LIMIT_TOKENS,
                    }
                )
                yield f"data: {event}\n\n"
                yield "data: [DONE]\n\n"

            except Exception:
                logger.exception("Error durante una consulta RAG por streaming")
                event = json.dumps(
                    {"type": "error", "detail": "No fue posible procesar la consulta."}
                )
                yield f"data: {event}\n\n"
            finally:
                # Estado de retención DESPUÉS de esta consulta (incluye la
                # conversación que se acaba de procesar, si es nueva).
                log_retained_conversations(graph.checkpointer)
                await resource_stack.aclose()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
