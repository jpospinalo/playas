"""El borrado coordina SQL y checkpoints con los turnos JSON y SSE activos."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

import rag.api.database as database_module
from rag.api import main as main_module
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.models import Base, Conversation, User
from rag.api.query_support import _conversation_thread_id
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.routes import conversations as conversations_module
from rag.api.routes.conversations import delete_conversation
from rag.api.schemas import QueryRequest
from rag.core.agent import AgentState

_USER = {"sub": "user-1"}
_ANSWER = "Respuesta respaldada [doc1]."
_CONTENT = "Pasaje sintético que respalda la respuesta."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@asynccontextmanager
async def _environment(
    monkeypatch: pytest.MonkeyPatch, conversations: dict[str, str]
) -> AsyncIterator[SimpleNamespace]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    entered = asyncio.Event()
    release = asyncio.Event()
    locks = ConversationLockRegistry()

    async def respond(state: AgentState) -> dict:
        if state["question"] == "Consulta pausada":
            entered.set()
            await release.wait()
        return {
            "messages": [AIMessage(content=_ANSWER)],
            "sources": [
                Document(
                    page_content=_CONTENT,
                    metadata={"source": "sintetico.pdf", "chunk_id": "synthetic-1"},
                )
            ],
        }

    graph = (
        StateGraph(AgentState)
        .add_node("respond", respond)
        .add_edge(START, "respond")
        .add_edge("respond", END)
        .compile(checkpointer=MemorySaver())
    )
    app = SimpleNamespace(state=SimpleNamespace(graph=graph, conversation_locks=locks))
    request = Request({"type": "http", "app": app})
    monkeypatch.setattr(database_module, "async_session_factory", sessions)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="enforce", max_concurrent=2)
    )
    tasks: list[asyncio.Task] = []
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                User(id="user-1", email="u1@example.com", password_hash="hash", role="user")
            )
            session.add_all(
                Conversation(id=ident, user_id="user-1", thread_id=legacy)
                for ident, legacy in conversations.items()
            )
            await session.commit()
        yield SimpleNamespace(
            sessions=sessions,
            graph=graph,
            locks=locks,
            request=request,
            entered=entered,
            release=release,
            tasks=tasks,
        )
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await engine.dispose()


def _task(env: SimpleNamespace, coroutine) -> asyncio.Task:
    task = asyncio.create_task(coroutine)
    env.tasks.append(task)
    return task


async def _query(
    endpoint: str,
    conversation_id: str | None,
    question: str = "Consulta independiente",
    thread_id: str | None = None,
) -> tuple[str, list[dict]]:
    request = QueryRequest(question=question, conversation_id=conversation_id, thread_id=thread_id)
    if endpoint == "json":
        result = await main_module.query(request, _USER)
        return result.answer, [source.model_dump() for source in result.sources]
    response = await main_module.query_stream(request, _USER)
    frames = [frame.removeprefix("data: ").strip() async for frame in response.body_iterator]
    assert frames[-1] == "[DONE]"
    events = [json.loads(frame) for frame in frames[:-1]]
    assert not any(event["type"] == "error" for event in events)
    answer = "".join(event["content"] for event in events if event["type"] == "token")
    sources = next(event["sources"] for event in events if event["type"] == "sources")
    return answer, sources


async def _delete(env: SimpleNamespace, conversation_id: str) -> None:
    async with env.sessions() as session:
        await delete_conversation(conversation_id, env.request, user=_USER, session=session)


def _assert_answer(result: tuple[str, list[dict]]) -> None:
    answer, sources = result
    assert answer == _ANSWER
    assert sources[0]["fragments"][0]["index"] == 1
    assert sources[0]["fragments"][0]["content"] == _CONTENT


async def _assert_deleted(env: SimpleNamespace, conversation_id: str, legacy: str) -> None:
    async with env.sessions() as session:
        assert await session.get(Conversation, conversation_id) is None
    keys = {
        _conversation_thread_id("user-1", conversation_id),
        _conversation_thread_id("user-1", legacy),
    }
    saver = env.graph.checkpointer
    assert not keys.intersection(saver.storage)
    assert not any(key[0] in keys for key in saver.writes)
    assert not any(key[0] in keys for key in saver.blobs)


async def _wait_for_delete_reservation(
    env: SimpleNamespace, deleting: asyncio.Task, reserved: asyncio.Event
) -> None:
    reservation = _task(env, reserved.wait())
    done, _ = await asyncio.wait(
        {deleting, reservation}, timeout=3, return_when=asyncio.FIRST_COMPLETED
    )
    assert done, "El borrado no reservó el bloqueo ni terminó dentro del plazo de control"
    assert deleting not in done, "DELETE terminó mientras una consulta conservaba el bloqueo"
    assert reserved.is_set()


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["json", "sse"])
@pytest.mark.parametrize(
    ("legacy", "use_legacy"), [("shared", False), ("legacy-thread", False), ("legacy-thread", True)]
)
async def test_delete_waits_for_inflight_query_and_releases_both_checkpoints(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, legacy: str, use_legacy: bool
) -> None:
    async with _environment(monkeypatch, {"shared": legacy, "other": "other-thread"}) as env:
        for logical_id in {"shared", legacy}:
            _assert_answer(await _query(endpoint, None, thread_id=logical_id))
        active_key = _conversation_thread_id("user-1", legacy if use_legacy else "shared")
        delete_reserved = asyncio.Event()
        reserve = env.locks._reserve

        async def observe_reserve(key: str):
            entry = await reserve(key)
            if key == active_key and entry.waiters == 2:
                delete_reserved.set()
            return entry

        monkeypatch.setattr(env.locks, "_reserve", observe_reserve)
        querying = _task(
            env,
            _query(
                endpoint,
                None if use_legacy else "shared",
                "Consulta pausada",
                legacy if use_legacy else None,
            ),
        )
        await asyncio.wait_for(env.entered.wait(), 3)
        deleting = _task(env, _delete(env, "shared"))
        await _wait_for_delete_reservation(env, deleting, delete_reserved)

        _assert_answer(await asyncio.wait_for(_query(endpoint, "other"), 3))
        async with env.sessions() as session:
            assert await session.get(Conversation, "shared") is not None
        env.release.set()
        _assert_answer(await asyncio.wait_for(querying, 3))
        assert await asyncio.wait_for(deleting, 3) is None
        await _assert_deleted(env, "shared", legacy)
        assert _conversation_thread_id("user-1", "other") in env.graph.checkpointer.storage
        assert env.locks._entries == {}


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["json", "sse"])
async def test_query_queued_after_delete_observes_the_missing_conversation(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    async with _environment(monkeypatch, {"shared": "legacy-thread"}) as env:
        key = _conversation_thread_id("user-1", "shared")
        delete_reserved = asyncio.Event()
        query_reserved = asyncio.Event()
        reserve = env.locks._reserve

        async def observe_reserve(thread_id: str):
            entry = await reserve(thread_id)
            if thread_id == key and entry.waiters == 2:
                delete_reserved.set()
            if thread_id == key and entry.waiters == 3:
                query_reserved.set()
            return entry

        monkeypatch.setattr(env.locks, "_reserve", observe_reserve)
        querying = _task(env, _query(endpoint, "shared", "Consulta pausada"))
        await asyncio.wait_for(env.entered.wait(), 3)
        deleting = _task(env, _delete(env, "shared"))
        await _wait_for_delete_reservation(env, deleting, delete_reserved)
        following = _task(env, _query(endpoint, "shared", "Consulta posterior"))
        await asyncio.wait_for(query_reserved.wait(), 3)
        env.release.set()
        _assert_answer(await asyncio.wait_for(querying, 3))
        assert await asyncio.wait_for(deleting, 3) is None
        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(following, 3)
        assert error.value.status_code == 404
        await _assert_deleted(env, "shared", "legacy-thread")
        assert env.locks._entries == {}


@pytest.mark.anyio
async def test_simultaneous_deletes_recheck_preloaded_sql_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _environment(monkeypatch, {"shared": "legacy-thread"}) as env:
        prepared = 0
        both_prepared = asyncio.Event()

        async def erase_with_preloaded_conversation() -> int:
            nonlocal prepared
            async with env.sessions() as session:
                cached = await session.get(Conversation, "shared")
                assert cached is not None
                prepared += 1
                if prepared == 2:
                    both_prepared.set()
                await both_prepared.wait()
                try:
                    await delete_conversation("shared", env.request, user=_USER, session=session)
                except HTTPException as error:
                    return error.status_code
                return 204

        first = _task(env, erase_with_preloaded_conversation())
        second = _task(env, erase_with_preloaded_conversation())
        result = await asyncio.wait_for(asyncio.gather(first, second), 3)
        assert sorted(result) == [204, 404]
        await _assert_deleted(env, "shared", "legacy-thread")
        assert env.locks._entries == {}


@pytest.mark.anyio
async def test_crossed_legacy_aliases_reserve_locks_in_the_same_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with _environment(monkeypatch, {"a": "b", "b": "a"}) as env:
        reservations: dict[asyncio.Task, list[str]] = {}
        reserve = env.locks._reserve

        async def observe_reserve(key: str):
            reservations.setdefault(asyncio.current_task(), []).append(key)
            return await reserve(key)

        monkeypatch.setattr(env.locks, "_reserve", observe_reserve)
        first = _task(env, _delete(env, "a"))
        second = _task(env, _delete(env, "b"))
        assert await asyncio.wait_for(asyncio.gather(first, second), 3) == [None, None]
        expected = sorted(
            {_conversation_thread_id("user-1", "a"), _conversation_thread_id("user-1", "b")}
        )
        assert reservations[first] == expected
        assert reservations[second] == expected
        await _assert_deleted(env, "a", "b")
        await _assert_deleted(env, "b", "a")
        assert env.locks._entries == {}


@pytest.mark.anyio
async def test_cancelled_delete_releases_the_first_alias_and_the_waiting_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = "a-legacy-thread"
    async with _environment(monkeypatch, {"shared": legacy}) as env:
        _assert_answer(await _query("json", None, thread_id=legacy))
        key = _conversation_thread_id("user-1", "shared")
        historical_key = _conversation_thread_id("user-1", legacy)
        delete_reserved = asyncio.Event()
        reserve = env.locks._reserve

        async def observe_reserve(thread_id: str):
            entry = await reserve(thread_id)
            if thread_id == key and entry.waiters == 2:
                delete_reserved.set()
            return entry

        monkeypatch.setattr(env.locks, "_reserve", observe_reserve)
        querying = _task(env, _query("json", "shared", "Consulta pausada"))
        await asyncio.wait_for(env.entered.wait(), 3)
        deleting = _task(env, _delete(env, "shared"))
        await _wait_for_delete_reservation(env, deleting, delete_reserved)
        deleting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(deleting, 3)
        assert set(env.locks._entries) == {key}
        assert env.locks._entries[key].waiters == 1
        assert historical_key in env.graph.checkpointer.storage
        async with env.sessions() as session:
            assert await session.get(Conversation, "shared") is not None
        env.release.set()
        _assert_answer(await asyncio.wait_for(querying, 3))
        _assert_answer(await asyncio.wait_for(_query("json", "shared"), 3))
        assert env.locks._entries == {}


@pytest.mark.anyio
@pytest.mark.parametrize("endpoint", ["json", "sse"])
async def test_busy_delete_returns_conflict_without_late_deletion_and_can_be_retried(
    monkeypatch: pytest.MonkeyPatch, endpoint: str
) -> None:
    monkeypatch.setattr(conversations_module, "_DELETE_LOCK_TIMEOUT_SECONDS", 0.01, raising=False)
    legacy = "a-legacy-thread"
    async with _environment(monkeypatch, {"shared": legacy}) as env:
        _assert_answer(await _query(endpoint, None, thread_id=legacy))
        key = _conversation_thread_id("user-1", "shared")
        historical_key = _conversation_thread_id("user-1", legacy)
        querying = _task(env, _query(endpoint, "shared", "Consulta pausada"))
        await asyncio.wait_for(env.entered.wait(), 3)

        with pytest.raises(HTTPException) as error:
            await asyncio.wait_for(_delete(env, "shared"), 1)
        assert error.value.status_code == 409
        assert error.value.detail == (
            "La conversación está en uso. Espera a que termine la operación e inténtalo de nuevo."
        )
        assert not querying.done()
        async with env.sessions() as session:
            assert await session.get(Conversation, "shared") is not None
        saver = env.graph.checkpointer
        for retained_key in (key, historical_key):
            assert retained_key in saver.storage
            assert any(item[0] == retained_key for item in saver.writes)
            assert any(item[0] == retained_key for item in saver.blobs)
        assert set(env.locks._entries) == {key}
        assert env.locks._entries[key].waiters == 1

        env.release.set()
        _assert_answer(await asyncio.wait_for(querying, 3))
        assert await asyncio.wait_for(_delete(env, "shared"), 3) is None
        await _assert_deleted(env, "shared", legacy)
        assert env.locks._entries == {}
