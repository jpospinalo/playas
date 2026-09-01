"""FastAPI application para el sistema RAG de jurisprudencia de playas.

Expone estos endpoints sobre el agente LangGraph:
  GET  /api/health          — liveness check
  GET  /api/ready            — readiness check (ver docstring de `ready()`)
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
from rag.config import (
    CONTEXT_LIMIT_TOKENS,
    QUERY_STREAM_STAGE_TIMEOUT_SECONDS,
    QUERY_TOTAL_TIMEOUT_SECONDS,
)
from rag.core.agent import extract_answer_from_state as _extract_answer_from_state
from rag.core.observability import ActiveQueryTracker, log_retained_conversations
from rag.core.retriever import bm25_index_is_empty, close_retrievers, init_retrievers

# Timeout corto por defecto para el chequeo de base de datos en /api/ready
# — una base de datos colgada no debe bloquear el readiness probe
# indefinidamente. Como constante de módulo para que las pruebas puedan
# ejercer el timeout real sin esperarlo (pasando un valor pequeño explícito
# a `_check_database_ready`).
READY_DB_TIMEOUT_SECONDS = 2.0

# ── Singleton del grafo ─────────────────────────────────────────────────────

_graph: Any = None
logger = logging.getLogger(__name__)

# Gauge de consultas en curso, sin contenido de negocio (ver
# rag.core.observability). Un único proceso, un único tracker de módulo.
ACTIVE_QUERIES = ActiveQueryTracker()

# Lock por conversación (ver rag.api.conversation_lock) — serializa turnos
# concurrentes sobre el MISMO thread_id, demostrado necesario por un test
# de interleaving real. No serializa entre conversaciones distintas.
CONVERSATION_LOCKS = ConversationLockRegistry()


def get_graph() -> Any:
    if _graph is None:
        raise RuntimeError("El grafo no ha sido compilado. Verifica el lifespan de la app.")
    return _graph


def _is_ephemeral_query(request: QueryRequest) -> bool:
    """``True`` si el checkpoint de esta consulta es basura de un solo uso.

    ``_make_config`` genera un ``thread_id`` aleatorio cuando ni
    ``conversation_id`` ni ``thread_id`` vienen en la request (ver su
    docstring): ese identificador nunca se devuelve al cliente en
    ``QueryResponse``/eventos SSE, así que ninguna solicitud futura puede
    volver a referenciarlo — a diferencia de una conversación con
    ``conversation_id`` (persistida en la base de datos, limpiada al
    borrarla — A3.2) o con ``thread_id`` explícito (memoria multi-turno
    efímera pero intencional: el cliente SÍ puede volver a usarlo). Sin este
    chequeo, cada consulta de una sola vez sin memoria deja un checkpoint
    huérfano en ``MemorySaver.storage`` para siempre — una fuga de memoria
    del proceso sin ningún ciclo de vida que la limite.
    """
    return request.conversation_id is None and request.thread_id is None


async def _cleanup_ephemeral_checkpoint(graph: Any, request: QueryRequest, thread_id: str) -> None:
    """Borra el checkpoint de una consulta efímera (ver ``_is_ephemeral_query``).

    Se llama siempre desde un ``finally`` — éxito, error de negocio o
    cancelación — porque en los tres casos el checkpoint es igualmente
    irrecuperable para el cliente. ``adelete_thread`` es idempotente (no-op
    si el thread nunca llegó a escribir un checkpoint), así que es seguro
    llamarlo incluso si la consulta falló antes de invocar el grafo.

    C2 — un fallo de ``adelete_thread`` (backend del checkpointer caído,
    error interno de LangGraph, lo que sea) se captura y se registra aquí
    mismo, sin dejarlo propagar: antes, al no tener manejo propio, esta
    función se invocaba dentro de un ``finally`` plano en ambos endpoints —
    una excepción aquí reemplazaba en silencio (semántica de Python) el
    valor de retorno o la excepción original que ese ``finally`` estaba
    terminando de propagar, descartando una respuesta ya exitosa o
    sustituyendo el error real por uno de limpieza sin relación. Solo se
    captura ``Exception``: ``asyncio.CancelledError`` hereda de
    ``BaseException`` en Python 3.8+, así que una cancelación real sigue
    propagándose sin que este ``except`` la intercepte ni la silencie.

    v1.2/C2 — el warning NO usa ``exc_info=True``: el mensaje de la
    excepción (o su traceback formateado) puede contener, sin que este
    código lo controle, cualquier valor que el backend del checkpointer
    haya decidido incluir — potencialmente el propio ``thread_id`` u otro
    identificador interno, si ese backend los interpola en su excepción. En
    vez de arriesgarse a filtrar eso al log, se registra únicamente un
    evento fijo más el nombre de la clase de la excepción
    (``type(exc).__name__``, nunca su mensaje) — suficiente señal operativa
    para saber que la limpieza falló y de qué tipo de error se trató, sin
    exponer ``thread_id``, contenido de negocio (pregunta/respuesta) ni
    ningún dato interpolado por una dependencia externa.
    """
    if not _is_ephemeral_query(request):
        return
    try:
        await graph.checkpointer.adelete_thread(thread_id)
    except Exception as exc:
        logger.warning("ephemeral_checkpoint_cleanup_failed error_type=%s", type(exc).__name__)


# ── Lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-calienta los componentes costosos al arrancar:
    - Tablas de la base de datos (create_all idempotente)
    - Conexión HTTP a Chroma (singleton)
    - Índice BM25 completo (construido una sola vez desde el corpus de Chroma)
    - Vectorstore LangChain-Chroma (singleton)
    - Grafo LangGraph compilado (singleton con MemorySaver)

    C3 — el ``try`` cubre TODO el arranque (``init_db``, ``init_retrievers``,
    ``build_graph``), no solo el bloque ``yield``: un fallo en cualquiera de
    los tres pasos de arranque llega igual al ``finally`` de abajo y libera
    lo que ya alcanzó a abrirse, en vez de dejarlo huérfano. ``_graph`` (el
    singleton de módulo, leído por ``get_graph()``) y ``app.state.graph``
    (leído por rutas que reciben ``Request``, p. ej. la limpieza de
    checkpoint en ``routes/conversations.py`` — C4) se asignan juntos al
    mismo objeto compilado y se resetean juntos a ``None`` al salir, en
    cualquier camino (apagado limpio, fallo de arranque, o excepción durante
    el cuerpo del servidor) — nunca queda uno de los dos apuntando a un
    grafo ya cerrado mientras el otro es ``None``.

    Al salir, libera lo que este lifespan dejó abierto: la sesión HTTP del
    cliente de embeddings y los singletons de retriever
    (``close_retrievers()``), y el engine SQLAlchemy (``engine.dispose()``,
    que cierra el pool de conexiones a la base de datos). Estas dos
    liberaciones están en su propio ``try/finally`` anidado para que un
    fallo de ``close_retrievers()`` nunca impida que ``engine.dispose()``
    se ejecute.
    """
    import asyncio

    from rag.api.database import engine, init_db
    from rag.core.agent import build_graph

    global _graph
    try:
        await init_db()
        await asyncio.to_thread(init_retrievers)
        _graph = build_graph()
        app.state.graph = _graph
        yield
    finally:
        _graph = None
        app.state.graph = None
        try:
            close_retrievers()
        finally:
            await engine.dispose()


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

    # El lock de conversación se adquiere PRIMERO, y el slot de
    # backpressure DESPUÉS, justo antes del trabajo que consume recursos:
    # en el orden inverso, una segunda solicitud de una conversación que ya
    # tiene un turno en curso reservaría un slot global de backpressure
    # solo para quedarse esperando el lock de SU conversación — sin hacer
    # ningún trabajo real — restándole capacidad a conversaciones
    # independientes. Con este orden, esperar el lock nunca consume un
    # slot; si backpressure rechaza con 503 una vez adquirido el lock, la
    # salida de este `async with` lo libera de inmediato (sin código
    # especial: es la propagación normal de la excepción). Mismo orden en
    # /api/query/stream — evita tanto la falta de equidad como un futuro
    # deadlock por orden inconsistente entre los dos endpoints.
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
                    final_state = await asyncio.wait_for(
                        graph.ainvoke(
                            _build_graph_input(request, initial_messages),
                            config=config,
                        ),
                        timeout=QUERY_TOTAL_TIMEOUT_SECONDS,
                    )
                except TimeoutError as exc:
                    # Corte CONTROLADO (504) antes de que el ALB/Nginx
                    # delante de este servicio corten la conexión por
                    # inactividad a los 300s (A3.3) — sin este timeout, el
                    # cliente vería la conexión morir sin ninguna respuesta.
                    logger.warning(
                        "query_total_timeout timeout_seconds=%.1f",
                        QUERY_TOTAL_TIMEOUT_SECONDS,
                    )
                    raise HTTPException(
                        status_code=504,
                        detail="La consulta superó el tiempo máximo permitido.",
                    ) from exc
                except Exception as exc:
                    if isinstance(exc, HTTPException):
                        raise
                    logger.exception("Error procesando una consulta RAG")
                    raise HTTPException(
                        status_code=500,
                        detail="No fue posible procesar la consulta.",
                    ) from exc
                finally:
                    # Limpieza ANTES del log de retención, para que ese conteo
                    # ya refleje el estado sin la basura de un solo uso (A3.1).
                    await _cleanup_ephemeral_checkpoint(graph, request, thread_id)
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
    ejecutarse y su `finally` nunca se alcanza. Esta subclase cierra el
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


@app.post(
    "/api/query/stream",
    # Corrige SOLO la documentación OpenAPI de esta ruta — sin
    # `response_model`/anotación de retorno, FastAPI declararía por
    # defecto el 200 como `application/json` con un schema vacío (`{}`),
    # aunque en tiempo de ejecución esta ruta siempre responde con
    # `media_type="text/event-stream"` (ver `_ResourceManagedStreamingResponse`
    # más abajo). `response_class=StreamingResponse` es solo una pista para
    # que FastAPI genere el 200 por defecto sin el `application/json` vacío
    # de su fallback habitual — la función igual retorna directamente su
    # propia `_ResourceManagedStreamingResponse` (subclase de
    # `StreamingResponse`), así que el comportamiento real no cambia.
    # `responses` amplía esa entrada 200 con el media type real; no pisa el
    # 422 que FastAPI ya agrega por el body validado.
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Successful Response",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
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

    # El lock de conversación y el slot de backpressure se adquieren aquí
    # (antes de la hidratación) y se liberan al final de
    # event_generator() — deliberadamente NO se resuelve todo antes del
    # StreamingResponse, porque _get_initial_messages() debe poder seguir
    # lanzando su HTTPException (404/422, o 503 de backpressure) ANTES de
    # que exista el StreamingResponse; solo necesitan cubrir desde aquí
    # hasta que termine el streaming. Ambos recursos se registran en el
    # mismo AsyncExitStack (hold() es un context manager async como
    # backpressure.slot()) — se entra en un scope y se cierra en otro, y
    # aclose() los libera en orden inverso ante cualquier salida (éxito,
    # excepción o cancelación), sin necesidad de llevar la cuenta manual de
    # qué se adquirió.
    #
    # Lock PRIMERO, backpressure DESPUÉS — mismo orden que /api/query, y
    # por el mismo motivo: esperar el lock de conversación no debe
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
                # Timeout POR ETAPA (A3.3), no total: se mide el tiempo ENTRE
                # eventos consecutivos del grafo (`__anext__()` en vez de
                # `async for` directo), no la duración completa del stream —
                # los eventos `status` intermedios pueden mantener viva una
                # consulta más larga que QUERY_STREAM_STAGE_TIMEOUT_SECONDS
                # legítimamente. Si el grafo se queda sin producir NINGÚN
                # evento nuevo durante ese tiempo, se asume una etapa colgada.
                stream_iterator = graph.astream(
                    _build_graph_input(request, initial_messages),
                    config=config,
                    stream_mode=["values", "custom"],
                ).__aiter__()
                while True:
                    try:
                        mode, payload = await asyncio.wait_for(
                            stream_iterator.__anext__(),
                            timeout=QUERY_STREAM_STAGE_TIMEOUT_SECONDS,
                        )
                    except StopAsyncIteration:
                        break
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

            except TimeoutError:
                # Corte CONTROLADO antes de que el ALB/Nginx delante de este
                # servicio corten la conexión por inactividad a los 300s
                # (A3.3) — la etapa actual del grafo no produjo ningún
                # evento nuevo dentro del timeout configurado.
                logger.warning(
                    "query_stream_stage_timeout timeout_seconds=%.1f",
                    QUERY_STREAM_STAGE_TIMEOUT_SECONDS,
                )
                event = json.dumps(
                    {
                        "type": "error",
                        "detail": "La consulta superó el tiempo máximo de espera de una etapa.",
                    }
                )
                yield f"data: {event}\n\n"
            except Exception:
                logger.exception("Error durante una consulta RAG por streaming")
                event = json.dumps(
                    {"type": "error", "detail": "No fue posible procesar la consulta."}
                )
                yield f"data: {event}\n\n"
            finally:
                # C2 — try/finally anidado: resource_stack.aclose() (libera
                # el lock de conversación y el slot de backpressure) debe
                # ejecutarse pase lo que pase en el bloque interior, incluso
                # si log_retained_conversations() llegara a lanzar (la
                # limpieza del checkpoint ya no puede — ver
                # _cleanup_ephemeral_checkpoint, que captura Exception
                # internamente). Con el finally plano anterior, una
                # excepción en cualquiera de las dos líneas de arriba habría
                # impedido que esta última corriera, dejando el lock/slot
                # sin liberar.
                try:
                    # Limpieza ANTES del log de retención, misma razón que en
                    # /api/query — ver _cleanup_ephemeral_checkpoint (A3.1).
                    await _cleanup_ephemeral_checkpoint(graph, request, thread_id)
                    log_retained_conversations(graph.checkpointer)
                finally:
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
