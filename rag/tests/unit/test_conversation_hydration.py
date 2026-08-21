"""Aislamiento y reconstrucción del historial de consultas."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import rag.api.database as database_module
from rag.api.main import _get_initial_messages, _make_config
from rag.api.models import Base, Conversation, Message, User
from rag.api.routes.conversations import AddMessageRequest, add_message


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _GraphWithoutCheckpoint:
    async def aget_state(self, config: dict) -> SimpleNamespace:
        del config
        return SimpleNamespace(values={})


@pytest.mark.anyio
async def test_hydration_checks_owner_and_excludes_current_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                User(id="user-1", email="u1@example.com", password_hash="hash", role="user"),
                User(id="user-2", email="u2@example.com", password_hash="hash", role="user"),
                Conversation(id="conv-1", user_id="user-1", thread_id="thread-1"),
                Message(
                    id="previous-user",
                    conversation_id="conv-1",
                    role="user",
                    text="Pregunta anterior",
                ),
                Message(
                    id="previous-ai",
                    conversation_id="conv-1",
                    role="assistant",
                    text="Respuesta anterior [doc1]",
                ),
                Message(
                    id="current-user",
                    conversation_id="conv-1",
                    role="user",
                    text="¿Y cuál es el plazo?",
                ),
            ]
        )
        await session.commit()

    monkeypatch.setattr(database_module, "async_session_factory", session_factory)
    graph = _GraphWithoutCheckpoint()
    config = _make_config("user-1", "conv-1", "thread-1")

    messages = await _get_initial_messages(
        graph,
        config,
        "conv-1",
        "¿Y cuál es el plazo?",
        "user-1",
        "current-user",
    )

    assert [type(message) for message in messages] == [HumanMessage, AIMessage, HumanMessage]
    assert [message.content for message in messages].count("¿Y cuál es el plazo?") == 1

    with pytest.raises(HTTPException) as error:
        await _get_initial_messages(
            graph,
            _make_config("user-2", "conv-1", "thread-1"),
            "conv-1",
            "¿Y cuál es el plazo?",
            "user-2",
            "current-user",
        )
    assert error.value.status_code == 404
    await engine.dispose()


def test_checkpoint_keys_are_namespaced_by_user_and_conversation() -> None:
    first = _make_config("user-1", "conv-1", "same-thread")
    second = _make_config("user-2", "conv-1", "same-thread")
    third = _make_config("user-1", "conv-2", "same-thread")
    assert first["configurable"]["thread_id"] != second["configurable"]["thread_id"]
    assert first["configurable"]["thread_id"] != third["configurable"]["thread_id"]


@pytest.mark.anyio
async def test_message_persistence_is_idempotent_for_client_message_id() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        session.add_all(
            [
                User(id="user-1", email="u1@example.com", password_hash="hash", role="user"),
                Conversation(id="conv-1", user_id="user-1", thread_id="thread-1"),
            ]
        )
        await session.commit()
        payload = AddMessageRequest(
            message_id="client-message-1",
            role="user",
            text="¿Quién puede usar una playa?",
        )

        first = await add_message("conv-1", payload, {"sub": "user-1"}, session)
        second = await add_message("conv-1", payload, {"sub": "user-1"}, session)
        messages = (await session.execute(select(Message))).scalars().all()
        conversation = await session.get(Conversation, "conv-1")

    assert first.id == second.id == "client-message-1"
    assert len(messages) == 1
    assert conversation is not None and conversation.message_count == 1
    await engine.dispose()
