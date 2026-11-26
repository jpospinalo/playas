"""A02: one message rating per user, with real temporary SQLite transactions.

Independent sessions synchronize only the initial duplicate SELECT. No INSERT,
commit, uniqueness violation or rollback is replaced with a successful double.
These tests do not demonstrate PostgreSQL concurrency.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from asyncpg.exceptions import ForeignKeyViolationError, UniqueViolationError
from fastapi import HTTPException
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.dialects.postgresql.asyncpg import AsyncAdapt_asyncpg_dbapi
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import rag.api.routes.feedback as feedback_module
from rag.api.models import Base, Conversation, Message, MessageFeedback, User
from rag.api.routes.feedback import _is_message_feedback_pair_conflict, submit_message_feedback
from rag.api.schemas import MessageFeedbackRequest, MessageFeedbackResponse

_USER = {"sub": "rating-user-a", "email": "a@example.invalid"}
_CONVERSATION = "rating-conversation"
_MESSAGE = "assistant-one"
_INDEX = "uq_message_feedback_user_message"
_LEGACY_DDL = """
CREATE TABLE message_feedback (
    id VARCHAR NOT NULL PRIMARY KEY,
    user_id VARCHAR NOT NULL REFERENCES users(id),
    user_email VARCHAR NOT NULL,
    conversation_id VARCHAR NOT NULL,
    message_id VARCHAR NOT NULL,
    ratings JSON NOT NULL,
    expected_answer TEXT,
    created_at DATETIME NOT NULL
)
"""


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def feedback_database(
    tmp_path: Path, request: pytest.FixtureRequest
) -> AsyncIterator[tuple[AsyncEngine, async_sessionmaker[AsyncSession]]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'feedback.sqlite'}", connect_args={"timeout": 1}
    )

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection: Any, record: Any) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            if getattr(request, "param", False):
                # Build the historical schema first. Do not remove an index from
                # a current protected table or mutate the model's metadata.
                await connection.execute(text(_LEGACY_DDL))
                await connection.execute(
                    text(
                        "CREATE INDEX ix_message_feedback_message_id "
                        "ON message_feedback(message_id)"
                    )
                )
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all(
                [
                    User(id=_USER["sub"], email=_USER["email"], password_hash="synthetic"),
                    User(id="rating-user-b", email="b@example.invalid", password_hash="synthetic"),
                ]
            )
            await session.flush()
            session.add(
                Conversation(id=_CONVERSATION, user_id=_USER["sub"], thread_id="rating-thread")
            )
            await session.flush()
            session.add_all(
                Message(id=ident, conversation_id=_CONVERSATION, role="assistant", text=ident)
                for ident in (_MESSAGE, "assistant-two")
            )
            await session.commit()
        yield engine, factory
    finally:
        await engine.dispose()


def _request(**changes: Any) -> MessageFeedbackRequest:
    fields = {
        "conversation_id": _CONVERSATION,
        "message_id": _MESSAGE,
        "ratings": {"pertinence": 4, "accuracy": 5},
        "expected_answer": "Keep this original note.",
    }
    return MessageFeedbackRequest(**(fields | changes))


def _record(ident: str, payload: MessageFeedbackRequest, **changes: Any) -> MessageFeedback:
    fields = {
        "id": ident,
        "user_id": _USER["sub"],
        "user_email": _USER["email"],
        "conversation_id": payload.conversation_id,
        "message_id": payload.message_id,
        "ratings": payload.ratings.model_dump(),
        "expected_answer": payload.expected_answer,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    return MessageFeedback(**(fields | changes))


async def _snapshot(factory: async_sessionmaker[AsyncSession]) -> list[dict]:
    async with factory() as session:
        rows = await session.execute(
            MessageFeedback.__table__.select().order_by(MessageFeedback.id)
        )
        return [dict(row) for row in rows.mappings()]


def _selects_feedback(statement: Any) -> bool:
    return bool(
        getattr(statement, "is_select", False)
        and any(
            getattr(table, "name", None) == "message_feedback"
            for table in statement.get_final_froms()
        )
    )


async def _race(
    engine: AsyncEngine, requests: list[MessageFeedbackRequest]
) -> list[MessageFeedbackResponse | Exception]:
    readers = 0
    ready = asyncio.Event()

    class SynchronizedSession(AsyncSession):
        held = False

        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal readers
            result = await super().execute(statement, *args, **kwargs)
            if not self.held and _selects_feedback(statement):
                self.held = True
                readers += 1
                if readers == 2:
                    ready.set()
                await asyncio.wait_for(ready.wait(), timeout=3)
            return result

    factory = async_sessionmaker(engine, class_=SynchronizedSession, expire_on_commit=False)

    async def write(payload: MessageFeedbackRequest) -> MessageFeedbackResponse | Exception:
        async with factory() as session:
            try:
                outcome = await submit_message_feedback(payload, _USER, session)
            except Exception as exc:
                outcome = exc
            # A handled collision must leave this same session usable, not failed.
            assert await session.scalar(select(func.count()).select_from(MessageFeedback)) >= 1
            return outcome

    return list(await asyncio.wait_for(asyncio.gather(*(write(p) for p in requests)), timeout=10))


@pytest.mark.anyio
async def test_current_schema_has_the_named_unique_user_message_index(feedback_database) -> None:
    engine, _ = feedback_database
    async with engine.connect() as connection:
        indexes = await connection.run_sync(lambda c: inspect(c).get_indexes("message_feedback"))
    matches = [index for index in indexes if index["name"] == _INDEX]
    assert len(matches) == 1
    assert matches[0]["unique"]
    assert matches[0]["column_names"] == ["user_id", "message_id"]
    assert matches[0].get("dialect_options", {}).get("sqlite_where") is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "different_payload", [False, True], ids=["same-payload", "changed-payload"]
)
async def test_concurrent_same_pair_has_one_winner_and_one_409(
    feedback_database, different_payload: bool
) -> None:
    engine, factory = feedback_database
    requests = [
        _request(),
        _request(ratings={"pertinence": 1, "accuracy": 2}, expected_answer="Another note.")
        if different_payload
        else _request(),
    ]
    outcomes = await _race(engine, requests)
    winners = [
        (result, payload)
        for result, payload in zip(outcomes, requests, strict=True)
        if isinstance(result, MessageFeedbackResponse)
    ]
    failures = [result for result in outcomes if isinstance(result, Exception)]
    assert len(winners) == len(failures) == 1, outcomes
    assert isinstance(failures[0], HTTPException), outcomes
    assert failures[0].status_code == 409
    winner, payload = winners[0]
    before = await _snapshot(factory)
    assert len(before) == 1 and before[0]["id"] == winner.id
    assert before[0]["ratings"] == payload.ratings.model_dump()
    assert before[0]["expected_answer"] == payload.expected_answer
    assert before[0]["user_id"] == _USER["sub"]
    assert before[0]["user_email"] == _USER["email"]
    async with factory() as session:
        with pytest.raises(HTTPException) as error:
            await submit_message_feedback(_request(), _USER, session)
        assert error.value.status_code == 409
    assert await _snapshot(factory) == before


@pytest.mark.anyio
async def test_sequential_duplicate_is_409_even_with_identical_payload(feedback_database) -> None:
    _, factory = feedback_database
    async with factory() as session:
        first = await submit_message_feedback(_request(), _USER, session)
    before = await _snapshot(factory)
    async with factory() as session:
        with pytest.raises(HTTPException) as error:
            await submit_message_feedback(_request(), _USER, session)
        assert error.value.status_code == 409
    assert before[0]["id"] == first.id
    assert await _snapshot(factory) == before


@pytest.mark.anyio
async def test_distinct_message_pairs_both_save(feedback_database) -> None:
    engine, factory = feedback_database
    outcomes = await _race(engine, [_request(), _request(message_id="assistant-two")])
    assert all(isinstance(result, MessageFeedbackResponse) for result in outcomes), outcomes
    rows = await _snapshot(factory)
    assert len(rows) == 2
    assert {row["message_id"] for row in rows} == {_MESSAGE, "assistant-two"}


@pytest.mark.anyio
async def test_unique_pair_does_not_prohibit_another_user_at_schema_level(
    feedback_database,
) -> None:
    """Schema identity is a pair; API authorization remains a separate requirement."""
    _, factory = feedback_database
    async with factory() as session:
        session.add_all(
            [
                _record("rating-a", _request()),
                _record("rating-b", _request(), user_id="rating-user-b"),
            ]
        )
        await session.commit()
    rows = await _snapshot(factory)
    assert len(rows) == 2 and {row["user_id"] for row in rows} == {_USER["sub"], "rating-user-b"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "feedback_database", [True], indirect=True, ids=["legacy-without-unique-index"]
)
async def test_legacy_duplicate_rows_return_409_without_choosing_or_mutating_a_row(
    feedback_database,
) -> None:
    engine, factory = feedback_database
    async with factory() as session:
        session.add_all([_record("legacy-a", _request()), _record("legacy-b", _request())])
        await session.commit()
    before = await _snapshot(factory)
    async with engine.connect() as connection:
        indexes = await connection.run_sync(lambda c: inspect(c).get_indexes("message_feedback"))
    assert all(index["name"] != _INDEX for index in indexes)
    async with factory() as session:
        with pytest.raises(HTTPException) as error:
            await submit_message_feedback(_request(), _USER, session)
        assert error.value.status_code == 409
    assert await _snapshot(factory) == before


@pytest.mark.anyio
async def test_feedback_primary_key_collision_is_not_a_duplicate_pair_409(
    feedback_database, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, factory = feedback_database
    async with factory() as session:
        session.add(_record("fixed-rating-id", _request()))
        await session.commit()
    before = await _snapshot(factory)
    monkeypatch.setattr(feedback_module, "uuid", SimpleNamespace(uuid4=lambda: "fixed-rating-id"))
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await submit_message_feedback(_request(message_id="assistant-two"), _USER, session)
        await session.rollback()
    assert await _snapshot(factory) == before


@pytest.mark.anyio
async def test_another_constraint_is_not_hidden_when_a_competitor_created_the_pair(
    feedback_database,
) -> None:
    engine, factory = feedback_database

    class CompetingInsertSession(AsyncSession):
        interposed = False

        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            result = await super().execute(statement, *args, **kwargs)
            if not self.interposed and _selects_feedback(statement):
                self.interposed = True
                async with factory() as competitor:
                    competitor.add(_record("competitor-rating", _request()))
                    await competitor.commit()
                async with engine.begin() as connection:
                    await connection.execute(
                        text(
                            "CREATE TRIGGER reject_rating BEFORE INSERT ON message_feedback "
                            "BEGIN SELECT RAISE(ABORT, 'unrelated_storage_constraint'); END"
                        )
                    )
            return result

    interposed_factory = async_sessionmaker(
        engine, class_=CompetingInsertSession, expire_on_commit=False
    )
    async with interposed_factory() as session:
        with pytest.raises(IntegrityError, match="unrelated_storage_constraint"):
            await submit_message_feedback(_request(), _USER, session)
        await session.rollback()
    rows = await _snapshot(factory)
    assert len(rows) == 1 and rows[0]["id"] == "competitor-rating"
    assert rows[0]["ratings"] == _request().ratings.model_dump()
    assert rows[0]["expected_answer"] == _request().expected_answer


@pytest.mark.parametrize(
    ("driver_error_type", "table_name", "constraint_name", "include_cause", "expected"),
    [
        (UniqueViolationError, "message_feedback", _INDEX, True, True),
        (UniqueViolationError, "message_feedback", "message_feedback_pkey", True, False),
        (UniqueViolationError, "message_feedback", "another_unique_index", True, False),
        (UniqueViolationError, "other_table", _INDEX, True, False),
        (ForeignKeyViolationError, "message_feedback", _INDEX, True, False),
        (UniqueViolationError, "message_feedback", _INDEX, False, False),
    ],
    ids=["canonical-pair", "primary-key", "other-index", "other-table", "foreign-key", "no-cause"],
)
def test_asyncpg_pair_conflict_diagnostics_without_a_database_connection(
    driver_error_type, table_name: str, constraint_name: str, include_cause: bool, expected: bool
) -> None:
    """Installed diagnostic types are injected, not PostgreSQL execution evidence."""
    diagnostic = driver_error_type("Synthetic server diagnostic")
    diagnostic.table_name = table_name
    diagnostic.constraint_name = constraint_name
    translated = AsyncAdapt_asyncpg_dbapi.IntegrityError("Synthetic adapter diagnostic")
    translated.sqlstate = diagnostic.sqlstate
    if include_cause:
        translated.__cause__ = diagnostic
    error = IntegrityError("INSERT INTO message_feedback (...) VALUES (...)", {}, translated)

    assert _is_message_feedback_pair_conflict(error) is expected


def test_missing_driver_diagnostic_is_not_a_pair_conflict() -> None:
    error = IntegrityError("INSERT INTO message_feedback (...) VALUES (...)", {}, None)

    assert _is_message_feedback_pair_conflict(error) is False


@pytest.mark.anyio
@pytest.mark.parametrize("changed_target", ["conversation-owner", "message-role"])
async def test_pair_collision_revalidates_changed_target_after_real_rollback(
    feedback_database, changed_target: str
) -> None:
    engine, factory = feedback_database
    winner_before: list[dict] = []

    class TargetChangesAfterRollbackSession(AsyncSession):
        interposed = False
        changed = False

        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            nonlocal winner_before
            result = await super().execute(statement, *args, **kwargs)
            if not self.interposed and _selects_feedback(statement):
                self.interposed = True
                async with factory() as competitor:
                    competitor.add(_record("retained-winner", _request()))
                    await competitor.commit()
                winner_before = await _snapshot(factory)
            return result

        async def rollback(self) -> None:
            await super().rollback()
            if self.interposed and not self.changed:
                self.changed = True
                async with factory() as competitor:
                    if changed_target == "conversation-owner":
                        conversation = await competitor.get(Conversation, _CONVERSATION)
                        assert conversation is not None
                        conversation.user_id = "rating-user-b"
                    else:
                        message = await competitor.get(Message, _MESSAGE)
                        assert message is not None
                        message.role = "user"
                    await competitor.commit()

    interposed_factory = async_sessionmaker(
        engine, class_=TargetChangesAfterRollbackSession, expire_on_commit=False
    )
    async with interposed_factory() as session:
        with pytest.raises(HTTPException) as error:
            await submit_message_feedback(_request(), _USER, session)
        assert error.value.status_code == 404
        assert session.changed
    assert len(winner_before) == 1 and winner_before[0]["id"] == "retained-winner"
    assert await _snapshot(factory) == winner_before
