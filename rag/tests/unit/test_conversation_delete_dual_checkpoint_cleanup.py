"""C4 — borrar una conversación limpia AMBAS claves de checkpoint posibles,
sin depender de un import diferido hacia ``api/main.py``.

Antes de esta corrección, ``_cleanup_checkpoint_after_delete`` solo conocía
UNA clave de checkpoint: la derivada de ``conversation_id``
(``_conversation_thread_id(user_id, conversation_id)``). Pero
``_make_config`` en ``query_support.py`` deriva el ``thread_id`` real del
checkpointer con ``logical_id = conversation_id or thread_id or uuid4()`` —
si los primeros turnos de una conversación se hicieron ANTES de que existiera
su fila ``Conversation`` (con ``request.thread_id`` explícito, sin
``conversation_id`` todavía), esos turnos escribieron su checkpoint bajo la
clave derivada de ``conv.thread_id``, no de ``conversation_id``. Una
conversación así deja DOS checkpoints huérfanos al borrarla si solo se limpia
uno.

La corrección también reemplaza el import diferido ``from rag.api.main
import get_graph`` (que existía únicamente para romper el ciclo de
importación con ``api/main.py``, que importa este router) por
``request.app.state.graph`` — ``Request`` es un tipo especial inyectado por
FastAPI, excluido automáticamente del schema de OpenAPI.

Usa un grafo/checkpointer falsos (no el real de LangGraph) para poder
controlar con precisión qué clave falla y verificar el orden de intentos —
grafo real + checkpointer real ya se cubre en
``test_ephemeral_checkpoint_cleanup.py``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from rag.api.models import Base, Conversation, User
from rag.api.query_support import _conversation_thread_id
from rag.api.routes import conversations as conversations_module
from rag.api.routes.conversations import delete_conversation

_USER = {"sub": "test-user"}

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


async def _fresh_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


async def _seed_conversation(
    session_factory: async_sessionmaker, *, conversation_id: str, thread_id: str
) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                User(id="test-user", email="u@example.com", password_hash="hash", role="user"),
                Conversation(
                    id=conversation_id,
                    user_id="test-user",
                    thread_id=thread_id,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()


class _FakeCheckpointer:
    """``adelete_thread`` con control fino: registra cada intento (en orden)
    y falla solo para las claves listadas en ``fail_for`` — el resto de
    fallos sigue intentándose de todas formas."""

    def __init__(self, fail_for: frozenset[str] = frozenset()) -> None:
        self.deleted: list[str] = []
        self._fail_for = fail_for

    async def adelete_thread(self, thread_id: str) -> None:
        self.deleted.append(thread_id)
        if thread_id in self._fail_for:
            raise RuntimeError(f"fallo simulado borrando {thread_id!r}")


def _fake_request(graph: object | None) -> SimpleNamespace:
    """Sustituto mínimo de ``Request`` — lo único que ``delete_conversation``
    lee de él es ``request.app.state.graph`` (vía ``getattr`` con default)."""
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=graph)))


# ---------------------------------------------------------------------------
# Ambas claves se borran cuando son distintas.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_deletes_both_the_conversation_id_and_the_legacy_thread_id_keys() -> None:
    checkpointer = _FakeCheckpointer()
    graph = SimpleNamespace(checkpointer=checkpointer)
    session_factory = await _fresh_session_factory()
    await _seed_conversation(
        session_factory, conversation_id="conv-dual-1", thread_id="legacy-thread-dual-1"
    )

    async with session_factory() as session:
        await delete_conversation("conv-dual-1", _fake_request(graph), user=_USER, session=session)

    expected_conversation_id_key = _conversation_thread_id("test-user", "conv-dual-1")
    expected_legacy_key = _conversation_thread_id("test-user", "legacy-thread-dual-1")
    assert set(checkpointer.deleted) == {expected_conversation_id_key, expected_legacy_key}


@pytest.mark.anyio
async def test_equal_identifiers_are_deleted_only_once() -> None:
    """Cuando `conversation_id` y `conv.thread_id` coinciden (mismo valor),
    ambas claves derivadas son idénticas — el `set` interno debe deduplicar
    en vez de borrar dos veces la misma clave."""
    checkpointer = _FakeCheckpointer()
    graph = SimpleNamespace(checkpointer=checkpointer)
    session_factory = await _fresh_session_factory()
    await _seed_conversation(
        session_factory, conversation_id="conv-same-id", thread_id="conv-same-id"
    )

    async with session_factory() as session:
        await delete_conversation("conv-same-id", _fake_request(graph), user=_USER, session=session)

    assert len(checkpointer.deleted) == 1
    assert checkpointer.deleted == [_conversation_thread_id("test-user", "conv-same-id")]


# ---------------------------------------------------------------------------
# El fallo de una clave no impide intentar la otra; ninguno de los dos
# altera el 204 ni revive la conversación ya borrada.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_one_key_failing_does_not_prevent_attempting_the_other() -> None:
    conversation_id_key = _conversation_thread_id("test-user", "conv-dual-2")
    checkpointer = _FakeCheckpointer(fail_for=frozenset({conversation_id_key}))
    graph = SimpleNamespace(checkpointer=checkpointer)
    session_factory = await _fresh_session_factory()
    await _seed_conversation(
        session_factory, conversation_id="conv-dual-2", thread_id="legacy-thread-dual-2"
    )

    async with session_factory() as session:
        # No debe lanzar, pese a que una de las dos claves falla.
        await delete_conversation("conv-dual-2", _fake_request(graph), user=_USER, session=session)

    legacy_key = _conversation_thread_id("test-user", "legacy-thread-dual-2")
    assert set(checkpointer.deleted) == {conversation_id_key, legacy_key}, (
        "ambas claves debían intentarse pese a que una falló"
    )

    async with session_factory() as session:
        assert await session.get(Conversation, "conv-dual-2") is None


@pytest.mark.anyio
async def test_both_keys_failing_does_not_alter_the_204_or_revive_the_conversation() -> None:
    checkpointer = _FakeCheckpointer(
        fail_for=frozenset(
            {
                _conversation_thread_id("test-user", "conv-dual-3"),
                _conversation_thread_id("test-user", "legacy-thread-dual-3"),
            }
        )
    )
    graph = SimpleNamespace(checkpointer=checkpointer)
    session_factory = await _fresh_session_factory()
    await _seed_conversation(
        session_factory, conversation_id="conv-dual-3", thread_id="legacy-thread-dual-3"
    )

    async with session_factory() as session:
        # No debe lanzar, pese a que AMBAS claves fallan.
        result = await delete_conversation(
            "conv-dual-3", _fake_request(graph), user=_USER, session=session
        )

    assert result is None  # 204 No Content: el handler no devuelve cuerpo

    async with session_factory() as session:
        assert await session.get(Conversation, "conv-dual-3") is None


@pytest.mark.anyio
async def test_missing_app_state_graph_does_not_alter_the_204() -> None:
    """`request.app.state.graph` ausente (arranque aún no terminó) — la
    limpieza se omite con un log, pero el borrado ya confirmado en la base
    de datos no se ve afectado. Desde v1.2/C3, `request` en sí ya no es
    opcional (FastAPI siempre lo inyecta); lo que puede faltar es solo el
    atributo `graph` de su `app.state`, cubierto por `_fake_request(None)`."""
    session_factory = await _fresh_session_factory()
    await _seed_conversation(
        session_factory, conversation_id="conv-no-graph", thread_id="legacy-thread-no-graph"
    )

    async with session_factory() as session:
        result = await delete_conversation(
            "conv-no-graph", _fake_request(None), user=_USER, session=session
        )

    assert result is None

    async with session_factory() as session:
        assert await session.get(Conversation, "conv-no-graph") is None


# ---------------------------------------------------------------------------
# v1.2/C2 — el warning de limpieza no incluye thread_id ni contenido de
# negocio (mismo requisito que en `_cleanup_ephemeral_checkpoint`, aplicado
# aquí a `_cleanup_checkpoint_after_delete`).
# ---------------------------------------------------------------------------

_SENTINEL_THREAD_ID = "THREAD-ID-PRIVADO-123"
_SENTINEL_BUSINESS_CONTENT = "CONTENIDO-NEGOCIO-PRIVADO-456"


class _SentinelLeakingCheckpointer:
    """Falla con una excepción cuyo mensaje contiene sentinelas — si el log
    los mostrara, sería prueba directa de una fuga de contenido interno."""

    async def adelete_thread(self, thread_id: str) -> None:
        raise RuntimeError(
            f"fallo del checkpointer para thread_id={_SENTINEL_THREAD_ID} "
            f"al procesar '{_SENTINEL_BUSINESS_CONTENT}'"
        )


@pytest.mark.anyio
async def test_cleanup_after_delete_warning_carries_no_sentinel_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import logging

    graph = SimpleNamespace(checkpointer=_SentinelLeakingCheckpointer())
    session_factory = await _fresh_session_factory()
    await _seed_conversation(
        session_factory, conversation_id="conv-log-privacy", thread_id="legacy-thread-log-privacy"
    )

    with caplog.at_level(logging.WARNING, logger="rag.api.routes.conversations"):
        async with session_factory() as session:
            # No debe lanzar, pese a que ambas claves fallan.
            result = await delete_conversation(
                "conv-log-privacy", _fake_request(graph), user=_USER, session=session
            )

    assert result is None

    async with session_factory() as session:
        assert await session.get(Conversation, "conv-log-privacy") is None

    warnings = [r for r in caplog.records if r.name == "rag.api.routes.conversations"]
    assert len(warnings) >= 1
    for record in warnings:
        assert record.exc_info is None
    assert _SENTINEL_THREAD_ID not in caplog.text
    assert _SENTINEL_BUSINESS_CONTENT not in caplog.text
    # El evento fijo (con, como mucho, el nombre de la clase) sí aparece.
    assert (
        "checkpoint_cleanup_failed_after_conversation_delete error_type=RuntimeError" in caplog.text
    )


# ---------------------------------------------------------------------------
# v1.2/C3 — `Request` no aparece en el schema de OpenAPI para este endpoint.
# ---------------------------------------------------------------------------


def test_request_parameter_is_not_in_the_openapi_schema() -> None:
    from rag.api.main import app

    schema = app.openapi()
    delete_op = schema["paths"]["/api/conversations/{conversation_id}"]["delete"]
    param_names = {p["name"] for p in delete_op.get("parameters", [])}
    assert "request" not in param_names


# ---------------------------------------------------------------------------
# Sin import cruzado hacia api/main.py.
# ---------------------------------------------------------------------------


def test_conversations_router_does_not_import_rag_api_main() -> None:
    """C4 elimina el import diferido `from rag.api.main import get_graph`
    que existía para romper el ciclo con `api/main.py` (que importa este
    router). Verificado contra el módulo ya importado, no solo por texto:
    ninguno de sus objetos de código (incluidos los de funciones anidadas)
    debe mencionar `rag.api.main` como nombre importado."""
    import dis

    with open(conversations_module.__file__, encoding="utf-8") as f:
        source = f.read()
    assert "rag.api.main" not in source
    assert "from rag.api.main" not in source

    # Chequeo adicional a nivel de bytecode del propio módulo (no del texto
    # fuente) para las funciones definidas en él, por si algún import
    # cruzado se coló de forma menos obvia que un `from ... import` literal.
    for attr_name in dir(conversations_module):
        attr = getattr(conversations_module, attr_name)
        code = getattr(attr, "__code__", None)
        if code is None:
            continue
        for instruction in dis.get_instructions(code):
            if instruction.opname == "IMPORT_NAME":
                assert instruction.argval != "rag.api.main"
