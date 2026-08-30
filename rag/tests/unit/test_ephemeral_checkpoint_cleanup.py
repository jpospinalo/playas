"""A3.1/A3.2 — limpieza de checkpoints del `MemorySaver` del proceso.

Sin este cambio, dos rutas dejaban checkpoints huérfanos en
`MemorySaver.storage` (en proceso, sin persistencia, solo se libera al
reiniciar el servidor):

  A3.1 — una consulta sin `conversation_id` NI `thread_id` recibe un
  ``thread_id`` aleatorio de un solo uso (ver ``_make_config``) que
  ``QueryResponse``/los eventos SSE nunca devuelven al cliente: ese
  checkpoint es irrecuperable desde el primer instante. ``/api/query`` y
  ``/api/query/stream`` ahora lo borran en su `finally`
  (``_cleanup_ephemeral_checkpoint`` en ``api/main.py``) — pero SOLO en ese
  caso: una consulta con `thread_id` explícito (memoria multi-turno efímera
  pero intencional) o con `conversation_id` (persistida en la base de
  datos) debe conservar su checkpoint intacto.

  A3.2 — borrar una conversación (``DELETE /api/conversations/{id}``)
  borraba sus filas de la base de datos pero nunca su checkpoint en memoria
  del proceso, que quedaba huérfano para siempre.
  ``_cleanup_checkpoint_after_delete`` en ``routes/conversations.py`` lo
  borra también, sin que un fallo en esa limpieza pueda convertir un borrado
  ya confirmado en un error para el cliente.

Reutiliza los patrones ya establecidos en este suite: grafo real compilado
con enriquecimiento deshabilitado (mismo patrón que
``test_main_observability.py``), consultas que reciben el enrutamiento
determinista `out_of_scope`/`conversation` (misma pregunta que
``test_enrichment_llm_skip.py``/``test_main_observability.py``, así que no
hace falta mockear LLM ni retriever), y una base de datos SQLite real vía
``monkeypatch.setattr(database_module, "async_session_factory", ...)``
(mismo patrón que ``test_conversation_hydration.py``).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import rag.api.database as database_module
import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
from rag.api.models import Base, Conversation, User
from rag.api.query_support import _conversation_thread_id
from rag.api.schemas import QueryRequest

# Pregunta con enrutamiento determinista `out_of_scope` (familia #5 de
# `_is_deterministic_terminal`, ver A1.5) — el grafo responde sin llamar a
# ningún LLM ni al retriever, así que estas pruebas no necesitan mockear
# ninguno de los dos.
_OFF_TOPIC_QUESTION = "Dame una receta de cocina, por favor."

_USER = {"sub": "test-user"}

# Engines creados por _fresh_db_session_factory() en esta ejecución de
# pytest, pendientes de dispose() — mismo patrón que
# test_readiness_endpoint.py (A1.4) y los archivos de A2: sin esto, los
# hilos de fondo de aiosqlite pueden disparar "Event loop is closed" contra
# el event loop de una prueba posterior.
_pending_engines: list[AsyncEngine] = []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _dispose_test_db_engines() -> Iterator[None]:
    yield
    if not _pending_engines:
        return
    engines, _pending_engines[:] = list(_pending_engines), []

    async def _dispose_all() -> None:
        for engine in engines:
            await engine.dispose()

    asyncio.run(_dispose_all())


def _real_graph(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    return agent_module.build_graph()


async def _fresh_db_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


async def _consume_sse(response) -> None:
    """Agota un `_ResourceManagedStreamingResponse` sin necesitar su
    contenido — mismo helper mínimo que `test_query_stream_endpoint.py`,
    reducido a solo drenar (estas pruebas verifican el checkpointer, no el
    formato de los eventos)."""
    async for _chunk in response.body_iterator:
        pass


# ---------------------------------------------------------------------------
# A3.1 — /api/query
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_query_without_conversation_or_thread_id_leaves_no_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    await main_module.query(request, _USER)

    assert dict(graph.checkpointer.storage) == {}


@pytest.mark.anyio
async def test_query_with_explicit_thread_id_keeps_its_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memoria multi-turno efímera pero INTENCIONAL: el cliente puede volver
    a usar el mismo `thread_id` — A3.1 no debe borrarla."""
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION, thread_id="guest-thread-1")
    await main_module.query(request, _USER)

    expected_key = _conversation_thread_id("test-user", "guest-thread-1")
    assert expected_key in graph.checkpointer.storage


@pytest.mark.anyio
async def test_query_with_conversation_id_keeps_its_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conversación persistida en la base de datos: su checkpoint se limpia
    solo al borrar la conversación (A3.2), no en cada turno."""
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)

    session_factory = await _fresh_db_session_factory()
    async with session_factory() as session:
        session.add_all(
            [
                User(id="test-user", email="u@example.com", password_hash="hash", role="user"),
                Conversation(
                    id="conv-keep-1",
                    user_id="test-user",
                    thread_id="conv-keep-1-thread",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION, conversation_id="conv-keep-1")
    await main_module.query(request, _USER)

    expected_key = _conversation_thread_id("test-user", "conv-keep-1")
    assert expected_key in graph.checkpointer.storage


@pytest.mark.anyio
async def test_ephemeral_cleanup_does_not_break_a_failing_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un fallo dentro del grafo (nunca llegó a escribir un checkpoint) no
    debe impedir que `_cleanup_ephemeral_checkpoint` corra sin lanzar —
    `adelete_thread` es idempotente ante un thread que nunca existió."""
    from fastapi import HTTPException

    import rag.api.main as main_module

    class _BoomGraph:
        checkpointer = agent_module.build_graph().checkpointer

        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(main_module, "_graph", _BoomGraph())

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    with pytest.raises(HTTPException) as exc_info:
        await main_module.query(request, _USER)

    assert exc_info.value.status_code == 500
    assert dict(_BoomGraph.checkpointer.storage) == {}


# ---------------------------------------------------------------------------
# A3.1 — /api/query/stream
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stream_without_conversation_or_thread_id_leaves_no_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    response = await main_module.query_stream(request, _USER)
    await _consume_sse(response)

    assert dict(graph.checkpointer.storage) == {}


@pytest.mark.anyio
async def test_stream_with_explicit_thread_id_keeps_its_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION, thread_id="guest-thread-sse-1")
    response = await main_module.query_stream(request, _USER)
    await _consume_sse(response)

    expected_key = _conversation_thread_id("test-user", "guest-thread-sse-1")
    assert expected_key in graph.checkpointer.storage


# ---------------------------------------------------------------------------
# A3.2 — DELETE /api/conversations/{id}
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_deleting_a_conversation_also_removes_its_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module
    from rag.api.routes.conversations import delete_conversation

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)
    # C4 — delete_conversation ahora lee el grafo de `request.app.state.graph`
    # (poblado por el lifespan real en producción), no del import diferido
    # que existía antes. `raising=False`: en este entorno de pruebas el
    # lifespan nunca corrió, así que `app.state` puede no tener `graph` aún.
    monkeypatch.setattr(main_module.app.state, "graph", graph, raising=False)
    fake_request = Request(scope={"type": "http", "app": main_module.app, "headers": []})

    session_factory = await _fresh_db_session_factory()
    async with session_factory() as session:
        session.add_all(
            [
                User(id="test-user", email="u@example.com", password_hash="hash", role="user"),
                Conversation(
                    id="conv-to-delete",
                    user_id="test-user",
                    thread_id="conv-to-delete-thread",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    # Genera un turno real para que el checkpoint exista de verdad antes de
    # borrar la conversación — no basta con verificar el borrado de algo que
    # nunca se creó.
    request = QueryRequest(question=_OFF_TOPIC_QUESTION, conversation_id="conv-to-delete")
    await main_module.query(request, _USER)
    expected_key = _conversation_thread_id("test-user", "conv-to-delete")
    assert expected_key in graph.checkpointer.storage, "precondición: el checkpoint debía existir"

    async with session_factory() as session:
        await delete_conversation("conv-to-delete", fake_request, user=_USER, session=session)

    assert expected_key not in graph.checkpointer.storage

    async with session_factory() as session:
        assert await session.get(Conversation, "conv-to-delete") is None


@pytest.mark.anyio
async def test_conversation_delete_succeeds_even_if_checkpoint_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El grafo no disponible (v1.2/C3: `request.app.state.graph` ausente —
    p. ej. durante un fallo de arranque, antes de que el lifespan lo asigne
    — `_cleanup_checkpoint_after_delete` recibe `graph=None`) — u otro fallo
    cualquiera en la limpieza del checkpoint — nunca debe convertir un
    borrado de conversación ya confirmado en la base de datos en un error
    para el cliente."""
    from types import SimpleNamespace

    from rag.api.routes.conversations import delete_conversation

    # `request.app.state` sin atributo `graph` — `Request` sigue siendo
    # obligatorio (v1.2/C3), pero nada garantiza que el lifespan ya haya
    # poblado `app.state.graph` en el momento del borrado.
    fake_request_no_graph = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))

    session_factory = await _fresh_db_session_factory()
    async with session_factory() as session:
        session.add_all(
            [
                User(id="test-user", email="u@example.com", password_hash="hash", role="user"),
                Conversation(
                    id="conv-cleanup-fails",
                    user_id="test-user",
                    thread_id="conv-cleanup-fails-thread",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()

    async with session_factory() as session:
        # No debe lanzar, pese a que `app.state.graph` no está disponible.
        await delete_conversation(
            "conv-cleanup-fails", fake_request_no_graph, user=_USER, session=session
        )

    async with session_factory() as session:
        assert await session.get(Conversation, "conv-cleanup-fails") is None
