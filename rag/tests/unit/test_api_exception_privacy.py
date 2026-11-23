"""Errores externos no se vuelcan a los logs de las cuatro fronteras API.

Dobles de grafo/LLM y SQLite temporal: no servicios, contraseñas o corpus reales.
No certifica otros loggers, handlers o middleware fuera de estas rutas.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag.api.main as main_module
import rag.api.routes.auth as auth_module
import rag.api.routes.conversations as conversations_module
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.models import Base, User
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.schemas import QueryRequest
from rag.core.observability import ActiveQueryTracker

_PRIVATE_MESSAGE = "PRIVATE-EXTERNAL-MESSAGE-823"
_PRIVATE_CAUSE = "PRIVATE-CHAINED-CAUSE-614"
_PRIVATE_SQL = "SELECT PRIVATE_SQL_427 WHERE token = :secret"
_PRIVATE_PARAMETER = "PRIVATE-SQL-PARAMETER-590"
_PRIVATE_USER = "PRIVATE-USER-682"
_PRIVATE_QUESTION = "PRIVATE-QUESTION-437"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def sql_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


def _external_failure(kind: str) -> Exception:
    failure = (
        StatementError(
            _PRIVATE_MESSAGE,
            _PRIVATE_SQL,
            {"secret": _PRIVATE_PARAMETER},
            RuntimeError(_PRIVATE_PARAMETER),
        )
        if kind == "sql"
        else RuntimeError(_PRIVATE_MESSAGE, _PRIVATE_PARAMETER)
    )
    failure.__cause__ = ValueError(_PRIVATE_CAUSE)
    return failure


def _assert_safe_record(
    caplog: pytest.LogCaptureFixture,
    logger_name: str,
    event: str,
    failure: Exception,
    level: int,
) -> None:
    records = [record for record in caplog.records if record.name == logger_name]
    assert len(records) == 1, "El fallo debe conservar una señal operativa única."
    record = records[0]
    rendered = logging.Formatter("%(levelname)s %(name)s %(message)s").format(record)
    for secret in (
        _PRIVATE_MESSAGE,
        _PRIVATE_CAUSE,
        _PRIVATE_SQL,
        _PRIVATE_PARAMETER,
        _PRIVATE_USER,
        _PRIVATE_QUESTION,
    ):
        assert secret not in caplog.text
        assert secret not in rendered
        assert secret not in repr(record.args)
    assert record.exc_info is None
    assert record.exc_text is None
    assert record.stack_info is None
    assert record.levelno == level
    assert record.getMessage() == f"{event} error_type={type(failure).__name__}"
    assert record.args == (type(failure).__name__,)


class _FailingGraph:
    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.checkpointer = SimpleNamespace(storage={})

    async def ainvoke(self, *_args: object, **_kwargs: object) -> dict:
        raise self.failure

    async def astream(self, *_args: object, **_kwargs: object):
        yield "custom", {"type": "status", "stage": "retrieving"}
        raise self.failure


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["external", "sql"])
@pytest.mark.parametrize("transport", ["json", "sse"])
async def test_query_error_keeps_public_contract_without_logging_external_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kind: str,
    transport: str,
) -> None:
    failure = _external_failure(kind)
    locks = ConversationLockRegistry()
    capacity = ConcurrencyBackpressure(mode="observe", max_concurrent=1, scope="query")
    monkeypatch.setattr(main_module, "_graph", _FailingGraph(failure))
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)
    monkeypatch.setattr(main_module, "backpressure", capacity)
    monkeypatch.setattr(main_module, "ACTIVE_QUERIES", ActiveQueryTracker())
    request = QueryRequest(question=_PRIVATE_QUESTION, thread_id="privacy-test-thread")

    with caplog.at_level(logging.WARNING, logger=main_module.__name__):
        if transport == "json":
            with pytest.raises(HTTPException) as caught:
                await main_module.query(request, {"sub": _PRIVATE_USER})
            assert caught.value.status_code == 500
            assert caught.value.detail == "No fue posible procesar la consulta."
            event = "query_failed"
        else:
            response = await main_module.query_stream(request, {"sub": _PRIVATE_USER})
            chunks = [chunk async for chunk in response.body_iterator]
            text = "".join(chunk if isinstance(chunk, str) else chunk.decode() for chunk in chunks)
            events = [
                json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
            ]
            assert response.status_code == 200
            assert events[-1] == {"type": "error", "detail": "No fue posible procesar la consulta."}
            assert [item["type"] for item in events] == ["status", "error"]
            event = "query_stream_failed"

    assert main_module.ACTIVE_QUERIES.count == 0
    assert capacity.in_flight == 0
    assert locks._entries == {}
    _assert_safe_record(caplog, main_module.__name__, event, failure, logging.ERROR)


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["json", "sse"])
async def test_query_cancellation_is_not_logged_as_a_processing_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, transport: str
) -> None:
    monkeypatch.setattr(main_module, "_graph", _FailingGraph(asyncio.CancelledError()))
    request = QueryRequest(question=_PRIVATE_QUESTION, thread_id="privacy-cancel-thread")
    with caplog.at_level(logging.WARNING, logger=main_module.__name__):
        with pytest.raises(asyncio.CancelledError):
            if transport == "json":
                await main_module.query(request, {"sub": _PRIVATE_USER})
            else:
                response = await main_module.query_stream(request, {"sub": _PRIVATE_USER})
                _ = [chunk async for chunk in response.body_iterator]
    assert not [record for record in caplog.records if record.name == main_module.__name__]


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["external", "sql"])
async def test_title_failure_keeps_generic_500_and_does_not_commit_private_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    failure = _external_failure(kind)
    conversation = SimpleNamespace(
        id="privacy-conv", user_id=_PRIVATE_USER, title="Título anterior"
    )
    session = SimpleNamespace(get=AsyncMock(return_value=conversation), commit=AsyncMock())
    llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=failure))
    monkeypatch.setattr(
        conversations_module,
        "get_provider",
        lambda: SimpleNamespace(create_llm=lambda **_kwargs: llm),
    )

    with caplog.at_level(logging.WARNING, logger=conversations_module.__name__):
        with pytest.raises(HTTPException) as caught:
            await conversations_module.generate_title(
                conversations_module.GenerateTitleRequest(
                    first_message=_PRIVATE_QUESTION, conversation_id=conversation.id
                ),
                user={"sub": _PRIVATE_USER},
                session=session,
            )
    assert caught.value.status_code == 500
    assert caught.value.detail == "No fue posible generar el título."
    assert conversation.title == "Título anterior"
    session.commit.assert_not_awaited()
    _assert_safe_record(
        caplog,
        conversations_module.__name__,
        "conversation_title_generation_failed",
        failure,
        logging.ERROR,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["external", "sql"])
@pytest.mark.parametrize("phase", ["hash", "commit"])
async def test_rehash_failure_logs_only_type_and_keeps_rollback_and_valid_login(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    sql_factory: async_sessionmaker[AsyncSession],
    kind: str,
    phase: str,
) -> None:
    failure = _external_failure(kind)
    old_hash = "synthetic-legacy-hash"
    async with sql_factory() as seed:
        seed.add(
            User(
                id=_PRIVATE_USER, email="privacy@example.test", password_hash=old_hash, role="user"
            )
        )
        await seed.commit()
    monkeypatch.setattr(auth_module, "verify_password_async", AsyncMock(return_value=True))
    monkeypatch.setattr(auth_module, "needs_rehash", lambda _hash: True)
    monkeypatch.setattr(auth_module, "create_access_token", lambda *_args: "synthetic-jwt")
    monkeypatch.setattr(auth_module, "login_rate_limiter", SimpleNamespace(check=AsyncMock()))
    monkeypatch.setattr(
        auth_module,
        "hash_password_async",
        AsyncMock(side_effect=failure)
        if phase == "hash"
        else AsyncMock(return_value="synthetic-new-hash"),
    )
    async with sql_factory() as session:
        rollback = AsyncMock(wraps=session.rollback)
        monkeypatch.setattr(session, "rollback", rollback)
        if phase == "commit":
            monkeypatch.setattr(session, "commit", AsyncMock(side_effect=failure))
        with caplog.at_level(logging.WARNING, logger=auth_module.__name__):
            response = await auth_module.login(
                auth_module.LoginRequest(
                    email="privacy@example.test", password="synthetic-password"
                ),
                Request(scope={"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
                session=session,
            )
        rollback.assert_awaited_once()
    assert response.access_token == "synthetic-jwt"
    assert response.token_type == "bearer"
    assert response.user_id == _PRIVATE_USER
    assert response.email == "privacy@example.test"
    assert response.role == "user"
    async with sql_factory() as check:
        stored = await check.get(User, _PRIVATE_USER)
        assert stored is not None
        assert stored.password_hash == old_hash
    _assert_safe_record(
        caplog,
        auth_module.__name__,
        "opportunistic_password_rehash_failed",
        failure,
        logging.WARNING,
    )
