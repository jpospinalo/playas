"""A01/B04: persistence contracts with independent sessions and real SQLite writes.

The barriers retain initial reads before either writer proceeds; they do not
replace inserts, commits or constraint errors. This characterizes stale ORM
state and ID collisions offline, not PostgreSQL isolation or performance.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError
from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rag.api.models import Base, Conversation, Message, User
from rag.api.routes.conversations import (
    AddMessageRequest,
    MessageOut,
    _is_message_primary_key_conflict,
    add_message,
    list_messages,
)

_USER = {"sub": "writer-a"}
_CONVERSATION = "conversation-a"
_SOURCES = [
    {
        "source": "synthetic.pdf",
        "title": "Synthetic decision",
        "doc_type": "jurisprudencia",
        "metadata": {"Radicado": "synthetic-only"},
        "fragments": [{"index": 1, "content": "Quoted evidence.", "metadata": {"tag": "kept"}}],
    }
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def message_database(
    tmp_path: Path,
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'message-writes.sqlite'}",
        connect_args={"timeout": 1},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all(
                [
                    User(id="writer-a", email="a@example.invalid", password_hash="synthetic"),
                    User(id="writer-b", email="b@example.invalid", password_hash="synthetic"),
                    Conversation(id=_CONVERSATION, user_id="writer-a", thread_id="thread-a"),
                    Conversation(id="other-a", user_id="writer-a", thread_id="thread-other-a"),
                    Conversation(id="other-b", user_id="writer-b", thread_id="thread-other-b"),
                ]
            )
            await session.commit()
        yield engine, factory
    finally:
        await engine.dispose()


class _TwoReaderBarrier:
    def __init__(self) -> None:
        self.arrivals = 0
        self.ready = asyncio.Event()

    async def wait(self) -> None:
        self.arrivals += 1
        if self.arrivals == 2:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=3)


class _SynchronizedReadSession(AsyncSession):
    """Hold each session's first real conversation/message read at a barrier."""

    def __init__(self, *args: Any, barriers: dict[type, _TwoReaderBarrier], **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._barriers = barriers
        self._arrived: set[type] = set()

    async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
        value = await super().get(entity, ident, **kwargs)
        if entity in self._barriers and entity not in self._arrived:
            self._arrived.add(entity)
            await self._barriers[entity].wait()
        return value


def _payload(message_id: str = "shared-id", **changes: Any) -> AddMessageRequest:
    values = {"message_id": message_id, "role": "assistant", "text": "Answer.", "sources": _SOURCES}
    return AddMessageRequest(**(values | changes))


async def _race(
    engine: AsyncEngine, left: AddMessageRequest, right: AddMessageRequest
) -> list[MessageOut | BaseException]:
    barriers = {Conversation: _TwoReaderBarrier(), Message: _TwoReaderBarrier()}
    factory = async_sessionmaker(
        engine, class_=_SynchronizedReadSession, expire_on_commit=False, barriers=barriers
    )

    async def write(payload: AddMessageRequest) -> MessageOut:
        async with factory() as session:
            return await add_message(_CONVERSATION, payload, _USER, session)

    return list(
        await asyncio.wait_for(
            asyncio.gather(write(left), write(right), return_exceptions=True), timeout=10
        )
    )


async def _stored_state(factory: async_sessionmaker[AsyncSession]) -> tuple[int, list[Message]]:
    async with factory() as session:
        conversation = await session.get(Conversation, _CONVERSATION)
        assert conversation is not None
        rows = await session.execute(
            select(Message).where(Message.conversation_id == _CONVERSATION).order_by(Message.id)
        )
        return conversation.message_count, list(rows.scalars())


@pytest.mark.anyio
async def test_independent_writers_increment_for_both_distinct_messages(message_database) -> None:
    engine, factory = message_database
    results = await _race(engine, _payload("message-a"), _payload("message-b"))

    assert all(isinstance(result, MessageOut) for result in results), results
    count, messages = await _stored_state(factory)
    assert count == len(messages) == 2
    assert [message.id for message in messages] == ["message-a", "message-b"]
    assert all(message.sources == results[0].sources for message in messages)


@pytest.mark.anyio
async def test_concurrent_identical_id_and_payload_replay_without_double_increment(
    message_database,
) -> None:
    engine, factory = message_database
    results = await _race(engine, _payload(), _payload())

    assert all(isinstance(result, MessageOut) for result in results), results
    assert results[0].model_dump(exclude={"created_at"}) == results[1].model_dump(
        exclude={"created_at"}
    )
    # SQLite drops timezone information on reload; compare the same UTC instant.
    assert datetime.fromisoformat(results[0].created_at).replace(
        tzinfo=UTC
    ) == datetime.fromisoformat(results[1].created_at).replace(tzinfo=UTC)
    count, messages = await _stored_state(factory)
    assert count == len(messages) == 1
    assert messages[0].sources == results[0].sources


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes", [{"text": "Different answer."}, {"role": "user"}, {"sources": None}]
)
async def test_concurrent_id_collision_rejects_changed_text_role_or_sources(
    message_database, changes
) -> None:
    engine, factory = message_database
    results = await _race(engine, _payload(), _payload(**changes))

    successes = [result for result in results if isinstance(result, MessageOut)]
    failures = [result for result in results if isinstance(result, BaseException)]
    assert len(successes) == len(failures) == 1, results
    assert isinstance(failures[0], HTTPException), results
    assert failures[0].status_code == 409
    count, messages = await _stored_state(factory)
    assert count == len(messages) == 1
    assert (messages[0].role, messages[0].text, messages[0].sources) == (
        successes[0].role,
        successes[0].text,
        successes[0].sources,
    )


@pytest.mark.anyio
async def test_other_users_conversation_is_not_writable_or_readable(message_database) -> None:
    _, factory = message_database
    async with factory() as session:
        with pytest.raises(HTTPException) as write_error:
            await add_message("other-b", _payload(), _USER, session)
        assert write_error.value.status_code == 404
        with pytest.raises(HTTPException) as read_error:
            await list_messages("other-b", _USER, session)
        assert read_error.value.status_code == 404
    count, messages = await _stored_state(factory)
    assert count == 0 and messages == []


@pytest.mark.anyio
@pytest.mark.parametrize("foreign_conversation", ["other-a", "other-b"])
async def test_racing_id_from_another_conversation_is_not_replayed(
    message_database, foreign_conversation
) -> None:
    """An actual competing insert wins the ID after the request's initial read."""
    engine, factory = message_database
    payload = _payload()

    class CompetingInsertSession(AsyncSession):
        inserted = False

        async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
            value = await super().get(entity, ident, **kwargs)
            if entity is Message and ident == payload.message_id and not self.inserted:
                assert value is None
                self.inserted = True
                async with factory() as competitor:
                    competitor.add(
                        Message(
                            id=payload.message_id,
                            conversation_id=foreign_conversation,
                            role=payload.role,
                            text=payload.text,
                            sources=[source.model_dump() for source in payload.sources or []],
                        )
                    )
                    await competitor.commit()
            return value

    race_factory = async_sessionmaker(engine, class_=CompetingInsertSession, expire_on_commit=False)
    async with race_factory() as session:
        with pytest.raises(HTTPException) as error:
            await add_message(_CONVERSATION, payload, _USER, session)
        assert error.value.status_code == 409
    count, messages = await _stored_state(factory)
    assert count == 0 and messages == []
    async with factory() as session:
        foreign = await session.get(Message, payload.message_id)
        assert foreign is not None and foreign.conversation_id == foreign_conversation


@pytest.mark.anyio
@pytest.mark.parametrize("competing_insert", [True, False], ids=["pk-rollback", "zero-row-update"])
async def test_owner_change_rejects_both_conflict_replay_and_initial_insert(
    message_database, competing_insert: bool
) -> None:
    """A controlled ownership change must not admit the previously authorized writer."""
    engine, factory = message_database
    payload = _payload()

    class OwnerChangesAfterReadSession(AsyncSession):
        changed = False

        async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
            value = await super().get(entity, ident, **kwargs)
            if entity is Message and ident == payload.message_id and not self.changed:
                assert value is None
                self.changed = True
                async with factory() as competitor:
                    conversation = await competitor.get(Conversation, _CONVERSATION)
                    assert conversation is not None
                    conversation.user_id = "writer-b"
                    if competing_insert:
                        competitor.add(
                            Message(
                                id=payload.message_id,
                                conversation_id=_CONVERSATION,
                                role=payload.role,
                                text=payload.text,
                                sources=[source.model_dump() for source in payload.sources or []],
                            )
                        )
                        conversation.message_count = 1
                    await competitor.commit()
            return value

    race_factory = async_sessionmaker(
        engine, class_=OwnerChangesAfterReadSession, expire_on_commit=False
    )
    async with race_factory() as session:
        with pytest.raises(HTTPException) as error:
            await add_message(_CONVERSATION, payload, _USER, session)
        assert error.value.status_code == 404
    count, messages = await _stored_state(factory)
    assert count == len(messages) == int(competing_insert)
    async with factory() as session:
        conversation = await session.get(Conversation, _CONVERSATION)
        assert conversation is not None and conversation.user_id == "writer-b"
        with pytest.raises(HTTPException) as error:
            await list_messages(_CONVERSATION, _USER, session)
        assert error.value.status_code == 404
        if competing_insert:
            assert messages[0].id == payload.message_id
            assert messages[0].text == payload.text
            assert messages[0].sources == [source.model_dump() for source in payload.sources or []]


@pytest.mark.parametrize(
    ("driver_error_type", "table_name", "constraint_name", "include_cause", "expected"),
    [
        (UniqueViolationError, "messages", "messages_pkey", True, True),
        (UniqueViolationError, "messages", "messages_other_key", True, False),
        (UniqueViolationError, "other_table", "messages_pkey", True, False),
        (ForeignKeyViolationError, "messages", "messages_pkey", True, False),
        (UniqueViolationError, "messages", "messages_pkey", False, False),
    ],
    ids=["message-pk", "other-constraint", "other-table", "other-sqlstate", "missing-diagnostic"],
)
def test_postgresql_driver_diagnostic_classification_without_a_connection(
    driver_error_type, table_name: str, constraint_name: str, include_cause: bool, expected: bool
) -> None:
    """Inject installed driver diagnostic types, not a PostgreSQL execution result."""
    diagnostic = driver_error_type("Synthetic server diagnostic")
    diagnostic.table_name = table_name
    diagnostic.constraint_name = constraint_name
    # Mirrors the installed SQLAlchemy adapter's exception translation fields.
    translated = AsyncAdapt_asyncpg_dbapi.IntegrityError("Synthetic adapted exception")
    translated.sqlstate = diagnostic.sqlstate
    if include_cause:
        translated.__cause__ = diagnostic
    error = IntegrityError("INSERT INTO messages (...) VALUES (...)", {}, translated)

    assert _is_message_primary_key_conflict(error) is expected


def test_missing_database_diagnostic_is_not_an_id_collision() -> None:
    error = IntegrityError("INSERT INTO messages (...) VALUES (...)", {}, None)

    assert _is_message_primary_key_conflict(error) is False


@pytest.mark.anyio
async def test_storage_constraint_error_is_not_disguised_as_id_conflict(message_database) -> None:
    engine, factory = message_database
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TRIGGER reject_synthetic_message BEFORE INSERT ON messages "
                "WHEN NEW.id = 'storage-failure' "
                "BEGIN SELECT RAISE(ABORT, 'synthetic_storage_constraint'); END"
            )
        )
    async with factory() as session:
        with pytest.raises(IntegrityError, match="synthetic_storage_constraint"):
            await add_message(_CONVERSATION, _payload("storage-failure"), _USER, session)
        await session.rollback()
    count, messages = await _stored_state(factory)
    assert count == 0 and messages == []


@pytest.mark.anyio
async def test_other_constraint_is_not_hidden_even_when_the_message_id_now_exists(
    message_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, factory = message_database
    payload = _payload()
    async with factory() as session:
        original_get = session.get
        interposed = False

        async def read_before_competing_insert(entity: Any, ident: Any, **kwargs: Any) -> Any:
            nonlocal interposed
            value = await original_get(entity, ident, **kwargs)
            if entity is Message and ident == payload.message_id and not interposed:
                assert value is None
                interposed = True
                async with factory() as competitor:
                    competitor.add(
                        Message(
                            id=payload.message_id,
                            conversation_id=_CONVERSATION,
                            role=payload.role,
                            text=payload.text,
                            sources=[source.model_dump() for source in payload.sources or []],
                        )
                    )
                    conversation = await competitor.get(Conversation, _CONVERSATION)
                    assert conversation is not None
                    conversation.message_count = 1
                    await competitor.commit()
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "CREATE TRIGGER reject_after_competing_insert BEFORE INSERT "
                            "ON messages WHEN NEW.id = 'shared-id' "
                            "BEGIN SELECT RAISE(ABORT, 'unrelated_constraint'); END"
                        )
                    )
            return value

        monkeypatch.setattr(session, "get", read_before_competing_insert)
        with pytest.raises(IntegrityError, match="unrelated_constraint"):
            await add_message(_CONVERSATION, payload, _USER, session)
        await session.rollback()
    count, messages = await _stored_state(factory)
    assert count == len(messages) == 1
    assert messages[0].text == payload.text


@pytest.mark.anyio
async def test_messages_with_equal_timestamps_have_stable_id_order(message_database) -> None:
    _, factory = message_database
    timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    async with factory() as session:
        session.add_all(
            [
                Message(
                    id=ident,
                    conversation_id=_CONVERSATION,
                    role="user",
                    text=ident,
                    created_at=created_at,
                )
                for ident, created_at in (
                    ("z-last", timestamp),
                    ("a-first", timestamp),
                    ("earlier", timestamp - timedelta(seconds=1)),
                )
            ]
        )
        await session.commit()
    async with factory() as session:
        messages = await list_messages(_CONVERSATION, _USER, session)
        assert [message.id for message in messages] == ["earlier", "a-first", "z-last"]
        total = await session.scalar(select(func.count()).select_from(Message))
        assert total == len(messages) == 3
