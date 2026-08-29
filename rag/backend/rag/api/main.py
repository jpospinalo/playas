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
from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.types import Receive, Scope, Send

from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.query_support import (
    _build_graph_input,
    _clean_answer,
    _docs_to_source_groups,
    _estimate_context_tokens,
    _get_initial_messages,
    _make_config,
)
from rag.api.rate_limit import backpressure, get_query_user
from rag.api.routes.admin import router as admin_router
from rag.api.routes.auth import router as auth_router
from rag.api.routes.conversations import router as conversations_router
from rag.api.routes.feedback import router as feedback_router
from rag.api.schemas import QueryRequest, QueryResponse
from rag.config import CONTEXT_LIMIT_TOKENS
from rag.core.agent import extract_answer_from_state as _extract_answer_from_state
from rag.core.observability import ActiveQueryTracker, log_retained_conversations
from rag.core.retriever import bm25_index_is_empty, init_retrievers

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

    C9 — alcance real, para que no se lea como más de lo que es: NINGUNO de
    los tres chequeos llama a ChromaDB ni a Ollama en el momento de la
    consulta. ``graph_compiled`` e ``index_not_empty`` reflejan el estado de
    la conexión a Chroma y del snapshot BM25 tomados una única vez durante
    el arranque (``lifespan``) — si Chroma u Ollama se caen DESPUÉS de que
    el proceso ya inició, este endpoint sigue reportando "ready" hasta que
    una consulta real falle. No se añade ningún ping periódico real a esos
    servicios (fuera de alcance de este plan de correcciones): esto es
    documentación de un comportamiento existente, no un cambio de
    comportamiento.
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


class _ResourceManagedStreamingResponse(StreamingResponse):
    """`StreamingResponse` que garantiza el cierre de `resource_stack` sin
    importar en qué punto del ciclo ASGI falle el envío.

    `AsyncExitStack.aclose()` YA se llama en el `finally` de
    `event_generator()` (§ abajo) — eso cubre toda salida que llegue a
    ejecutar el cuerpo del generador (éxito, excepción, cancelación tras el
    primer `__anext__`). El caso que ese `finally` no cubre es que el propio
    envío ASGI del `http.response.start` falle (p. ej. cliente ya
    desconectado): Starlette lanza esa excepción ANTES de iterar
    `body_iterator` por primera vez, así que el generador nunca llega a
    ejecutarse y su `finally` nunca se alcanza (H1). Esta subclase cierra el
    mismo `resource_stack` también en ese caso — `aclose()` de
    `AsyncExitStack` es seguro de llamar más de una vez (la segunda vez es
    no-op), así que no hay doble liberación."""

    def __init__(self, *args: Any, resource_stack: AsyncExitStack, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._resource_stack = resource_stack

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._resource_stack.aclose()


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

    return _ResourceManagedStreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
        resource_stack=resource_stack,
    )
