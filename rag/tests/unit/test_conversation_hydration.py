"""Aislamiento y reconstrucción del historial de consultas."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import rag.api.database as database_module
import rag.core.agent as agent_module
from rag.api import main as main_module
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.main import _get_initial_messages, _make_config
from rag.api.models import Base, Conversation, Message, User
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.routes.conversations import AddMessageRequest, add_message
from rag.api.schemas import QueryRequest
from rag.core.query_enricher import EnrichedQuery


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

    now = datetime(2026, 1, 1, tzinfo=UTC)
    question = "¿Y cuál es el plazo?"
    async with session_factory() as session:
        session.add_all(
            [
                User(id="user-1", email="u1@example.com", password_hash="hash", role="user"),
                User(id="user-2", email="u2@example.com", password_hash="hash", role="user"),
                Conversation(id="conv-1", user_id="user-1", thread_id="thread-1"),
                Conversation(id="conv-2", user_id="user-1", thread_id="thread-2"),
                Message(
                    id="future-user",
                    conversation_id="conv-1",
                    role="user",
                    text="Pregunta posterior",
                    created_at=now + timedelta(seconds=1),
                ),
                Message(
                    id="previous-user",
                    conversation_id="conv-1",
                    role="user",
                    text="Pregunta anterior",
                    created_at=now - timedelta(seconds=2),
                ),
                Message(
                    id="other-user",
                    conversation_id="conv-2",
                    role="user",
                    text="Pregunta de otra conversación",
                    created_at=now - timedelta(seconds=2),
                ),
                Message(
                    id="previous-ai",
                    conversation_id="conv-1",
                    role="assistant",
                    text="Respuesta anterior [doc1]",
                    created_at=now - timedelta(seconds=1),
                ),
                Message(
                    id="current-user",
                    conversation_id="conv-1",
                    role="user",
                    text=question,
                    created_at=now,
                ),
                Message(
                    id="before-current",
                    conversation_id="conv-1",
                    role="user",
                    text=question,
                    created_at=now,
                ),
                Message(
                    id="same-time-later",
                    conversation_id="conv-1",
                    role="user",
                    text="Otra pregunta con la misma fecha",
                    created_at=now,
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
        question,
        "user-1",
        "current-user",
    )

    assert [(type(message), message.content) for message in messages] == [
        (HumanMessage, "Pregunta anterior"),
        (AIMessage, "Respuesta anterior [doc1]"),
        (HumanMessage, question),
        (HumanMessage, question),
    ]

    legacy = await _get_initial_messages(graph, config, "conv-1", "Nueva pregunta", "user-1")
    assert len(legacy) == 7
    assert [message.content for message in legacy[-2:]] == ["Pregunta posterior", "Nueva pregunta"]

    with pytest.raises(HTTPException) as error:
        await _get_initial_messages(
            graph,
            _make_config("user-2", "conv-1", "thread-1"),
            "conv-1",
            question,
            "user-2",
            "current-user",
        )
    assert error.value.status_code == 404
    await engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["json", "sse"])
async def test_two_tabs_and_restart_use_the_expected_history(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)
    monkeypatch.setattr(agent_module, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="off", max_concurrent=2)
    )

    first_entered = asyncio.Event()
    second_reserved = asyncio.Event()
    release_first = asyncio.Event()
    histories: dict[str, str] = {}
    locks = ConversationLockRegistry()
    reserve = locks._reserve

    async def observe_reserve(key: str):
        entry = await reserve(key)
        if entry.waiters == 2:
            second_reserved.set()
        return entry

    monkeypatch.setattr(locks, "_reserve", observe_reserve)
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)

    async def analyze(question: str, history: str) -> EnrichedQuery:
        histories[question] = history
        if question == "Pregunta A":
            first_entered.set()
            await release_first.wait()
        return EnrichedQuery(
            route="needs_clarification" if question == "Pregunta B" else "out_of_scope",
            standalone_question=question,
            expanded_query=question,
            doc_types=[],
        )

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)

    now = datetime(2026, 1, 1, tzinfo=UTC)

    def message(ident: str, text: str, offset: int, role: str = "user") -> Message:
        return Message(
            id=ident,
            conversation_id="shared",
            role=role,
            text=text,
            created_at=now + timedelta(seconds=offset),
        )

    async def query(label: str, tab: str) -> str:
        request = QueryRequest(
            question=f"Pregunta {label}",
            conversation_id="shared",
            thread_id=tab,
            current_message_id=label,
        )
        user = {"sub": "user-1"}
        if endpoint == "json":
            return (await main_module.query(request, user)).answer
        stream = await main_module.query_stream(request, user)
        frames = [frame.removeprefix("data: ").strip() async for frame in stream.body_iterator]
        assert frames[-1] == "[DONE]"
        events = [json.loads(frame) for frame in frames[:-1]]
        return "".join(event["content"] for event in events if event["type"] == "token")

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add_all(
                [
                    User(id="user-1", email="u1@example.com", password_hash="hash", role="user"),
                    Conversation(id="shared", user_id="user-1", thread_id="stored-thread"),
                    message("A", "Pregunta A", 0),
                    message("B", "Pregunta B", 1),
                ]
            )
            await session.commit()

        graph = agent_module.build_graph()
        monkeypatch.setattr(main_module, "_graph", graph)
        async with asyncio.timeout(5), asyncio.TaskGroup() as tasks:
            first = tasks.create_task(query("A", "tab-a"))
            await first_entered.wait()
            second = tasks.create_task(query("B", "tab-b"))
            await second_reserved.wait()
            assert "Pregunta B" not in histories
            release_first.set()

        answer_a, answer_b = first.result(), second.result()
        assert answer_a != answer_b
        assert histories == {
            "Pregunta A": "",
            "Pregunta B": f"Usuario: Pregunta A\nAsistente: {answer_a}",
        }
        state = await graph.aget_state(_make_config("user-1", "shared", "tab-b"))
        assert [(type(msg), msg.content) for msg in state.values["messages"]] == [
            (HumanMessage, "Pregunta A"),
            (AIMessage, answer_a),
            (HumanMessage, "Pregunta B"),
            (AIMessage, answer_b),
        ]

        async with session_factory() as session:
            session.add_all(
                [
                    message("reply-a", answer_a, 2, "assistant"),
                    message("reply-b", answer_b, 3, "assistant"),
                    message("C", "Pregunta C", 4),
                    message("D", "Pregunta D", 5),
                ]
            )
            await session.commit()

        monkeypatch.setattr(main_module, "_graph", agent_module.build_graph())
        await query("C", "tab-a")
        assert histories["Pregunta C"] == (
            f"Usuario: Pregunta A\nUsuario: Pregunta B\nAsistente: {answer_a}\nAsistente: {answer_b}"
        )
    finally:
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
