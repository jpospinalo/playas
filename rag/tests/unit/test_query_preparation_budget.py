"""A03: preparation and graph deadlines, with real temporary SQLite sessions.

The clock begins after the conversation lock and capacity slot are acquired.
The first *graph event* includes values; this is not an ASGI-send or visible-frame
deadline. Delayed close demonstrates a logical budget, not a physical SQL SLA.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from anyio import CancelScope
from fastapi import HTTPException
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import rag.api.database as database_module
from rag.api import main as main_module
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.models import Base, Conversation, Message, User
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.schemas import QueryRequest

_BUDGET = 0.2
_USER = {"sub": "preparation-user"}
_CONVERSATION = "preparation-conversation"
_ANSWER = "Synthetic answer [doc1]."


@dataclass
class _SQLProbe:
    stage: str | None = None
    entered: asyncio.Event = field(default_factory=asyncio.Event)
    release: asyncio.Event = field(default_factory=asyncio.Event)
    closing: asyncio.Event = field(default_factory=asyncio.Event)
    close_release: asyncio.Event = field(default_factory=asyncio.Event)
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    close_tasks: list[asyncio.Task] = field(default_factory=list)
    cancelled: bool = False
    hold_close: bool = False

    async def pause(self) -> None:
        self.entered.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise


class _Graph:
    def __init__(self) -> None:
        self.hot = False
        self.invoke_calls = 0
        self.invoke_delay = 0.0
        self.invoke_cancelled = False
        self.stream_calls = 0
        self.stream_closed = asyncio.Event()
        self.stream_plan: list[tuple[float, str, dict]] = []
        self.checkpointer = SimpleNamespace(storage={})

    async def aget_state(self, config: dict) -> SimpleNamespace:
        del config
        return SimpleNamespace(
            values={"messages": [AIMessage(content="Previous")] if self.hot else []}
        )

    def _state(self) -> dict:
        return {
            "messages": [AIMessage(content=_ANSWER)],
            "sources": [Document(page_content="Evidence.", metadata={"source": "synthetic.pdf"})],
        }

    async def ainvoke(self, *args: Any, **kwargs: Any) -> dict:
        self.invoke_calls += 1
        try:
            await asyncio.sleep(self.invoke_delay)
        except asyncio.CancelledError:
            self.invoke_cancelled = True
            raise
        return self._state()

    def astream(self, *args: Any, **kwargs: Any) -> AsyncIterator:
        self.stream_calls += 1

        async def events() -> AsyncIterator:
            try:
                for delay, mode, payload in self.stream_plan:
                    await asyncio.sleep(delay)
                    yield mode, payload
                yield "values", self._state()
            finally:
                self.stream_closed.set()

        return events()


@dataclass
class _Environment:
    engine: AsyncEngine
    probe: _SQLProbe
    graph: _Graph
    locks: ConversationLockRegistry
    pressure: ConcurrencyBackpressure
    request: QueryRequest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def preparation_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[_Environment]:
    probe = _SQLProbe()
    graph = _Graph()
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'preparation.sqlite'}",
        pool_size=1,
        max_overflow=0,
    )

    class ProbedSession(AsyncSession):
        async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
            value = await super().get(entity, ident, **kwargs)
            if entity is Conversation and probe.stage == "conversation":
                await probe.pause()
            return value

        async def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            result = await super().execute(statement, *args, **kwargs)
            descriptions = getattr(statement, "column_descriptions", ())
            if probe.stage == "history" and any(d.get("entity") is Message for d in descriptions):
                await probe.pause()
            return result

        async def close(self) -> None:
            close_task = asyncio.current_task()
            if close_task is not None:
                probe.close_tasks.append(close_task)
            probe.closing.set()
            if probe.hold_close:
                await probe.close_release.wait()
            await super().close()
            probe.closed.set()

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            session.add_all(
                [
                    User(id=_USER["sub"], email="prep@example.invalid", password_hash="synthetic"),
                    Conversation(id=_CONVERSATION, user_id=_USER["sub"], thread_id="prep-thread"),
                    Message(
                        id="previous", conversation_id=_CONVERSATION, role="user", text="Prior"
                    ),
                ]
            )
            await session.commit()
        locks = ConversationLockRegistry()
        pressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
        monkeypatch.setattr(main_module, "_graph", graph)
        monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)
        monkeypatch.setattr(main_module, "backpressure", pressure)
        monkeypatch.setattr(main_module, "QUERY_TOTAL_TIMEOUT_SECONDS", _BUDGET)
        monkeypatch.setattr(main_module, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", _BUDGET)
        monkeypatch.setattr(
            database_module,
            "async_session_factory",
            async_sessionmaker(engine, class_=ProbedSession, expire_on_commit=False),
        )
        yield _Environment(
            engine,
            probe,
            graph,
            locks,
            pressure,
            QueryRequest(question="Synthetic question?", conversation_id=_CONVERSATION),
        )
    finally:
        probe.release.set()
        probe.close_release.set()
        await engine.dispose()


async def _events(response) -> list[dict]:
    events = []
    async for chunk in response.body_iterator:
        payload = (
            (chunk if isinstance(chunk, str) else chunk.decode()).removeprefix("data: ").strip()
        )
        if payload != "[DONE]":
            events.append(json.loads(payload))
    return events


async def _call(environment: _Environment, transport: str) -> Any:
    if transport == "json":
        return await main_module.query(environment.request, _USER)
    response = await main_module.query_stream(environment.request, _USER)
    return await _events(response)


async def _watchdog(awaitable: Awaitable, environment: _Environment) -> Any:
    """Bound red attempts externally without presenting that bound as a product 504."""
    task = asyncio.ensure_future(awaitable)
    try:
        done, _ = await asyncio.wait({task}, timeout=2)
        if not done:
            pytest.fail(
                "External watchdog expired: the product did not provide its controlled result"
            )
        return await task
    finally:
        if not task.done():
            environment.probe.release.set()
            environment.probe.close_release.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def _assert_reusable(environment: _Environment, transport: str) -> None:
    assert environment.probe.closed.is_set()
    assert environment.engine.pool.checkedout() == 0
    assert environment.locks._entries == {}
    assert environment.pressure.in_flight == 0
    environment.probe.stage = None
    environment.probe.hold_close = False
    environment.graph.invoke_delay = 0
    environment.graph.stream_plan = []
    result = await _watchdog(_call(environment, transport), environment)
    if transport == "json":
        assert result.answer == _ANSWER
    else:
        assert not any(event["type"] == "error" for event in result)
        assert "".join(event["content"] for event in result if event["type"] == "token") == _ANSWER
    assert environment.engine.pool.checkedout() == 0
    assert environment.locks._entries == {}
    assert environment.pressure.in_flight == 0


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["json", "sse"])
@pytest.mark.parametrize("hot", [False, True], ids=["cold-history", "hot-authorization"])
async def test_preparation_timeout_precedes_graph_and_releases_sql_capacity(
    preparation_environment: _Environment, transport: str, hot: bool
) -> None:
    environment = preparation_environment
    environment.graph.hot = hot
    environment.probe.stage = "conversation" if hot else "history"
    with pytest.raises(HTTPException) as error:
        await _watchdog(_call(environment, transport), environment)
    assert error.value.status_code == 504
    assert environment.probe.entered.is_set() and environment.probe.cancelled
    assert environment.graph.invoke_calls == environment.graph.stream_calls == 0
    await _assert_reusable(environment, transport)


def _delay_preparation(monkeypatch: pytest.MonkeyPatch, delay: float) -> None:
    original = main_module._get_initial_messages

    async def prepare(*args: Any, **kwargs: Any) -> list:
        messages = await original(*args, **kwargs)
        await asyncio.sleep(delay)
        return messages

    monkeypatch.setattr(main_module, "_get_initial_messages", prepare)


@pytest.mark.anyio
async def test_json_preparation_and_generation_share_one_budget(
    preparation_environment: _Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = preparation_environment
    _delay_preparation(monkeypatch, _BUDGET * 0.65)
    environment.graph.invoke_delay = _BUDGET * 0.65
    with pytest.raises(HTTPException) as error:
        await _watchdog(_call(environment, "json"), environment)
    assert error.value.status_code == 504
    assert environment.graph.invoke_calls == 1 and environment.graph.invoke_cancelled
    await _assert_reusable(environment, "json")


@pytest.mark.anyio
async def test_sse_first_graph_event_uses_only_the_remaining_preparation_budget(
    preparation_environment: _Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = preparation_environment
    _delay_preparation(monkeypatch, _BUDGET * 0.65)
    environment.graph.stream_plan = [(_BUDGET * 0.65, "values", {"messages": []})]
    events = await _watchdog(_call(environment, "sse"), environment)
    assert [event["type"] for event in events] == ["error"]
    assert environment.graph.stream_calls == 1 and environment.graph.stream_closed.is_set()
    await _assert_reusable(environment, "sse")


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["json", "sse"])
async def test_external_preparation_cancellation_is_not_converted_to_timeout(
    preparation_environment: _Environment, transport: str
) -> None:
    environment = preparation_environment
    environment.probe.stage = "conversation"
    task = asyncio.create_task(_call(environment, transport))
    try:
        await asyncio.wait_for(environment.probe.entered.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _watchdog(task, environment)
        assert environment.graph.invoke_calls == environment.graph.stream_calls == 0
        await _assert_reusable(environment, transport)
    finally:
        environment.probe.release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["json", "sse"])
async def test_slow_sql_close_is_awaited_before_capacity_is_reused(
    preparation_environment: _Environment, transport: str
) -> None:
    environment = preparation_environment
    environment.probe.stage = "conversation"
    environment.probe.hold_close = True
    task = asyncio.create_task(_call(environment, transport))
    try:
        # On an unbounded red implementation this wait itself expires; cleanup
        # releases the probe explicitly instead of abandoning a live SQL task.
        await asyncio.wait_for(environment.probe.closing.wait(), timeout=1)
        assert not task.done()
        assert environment.pressure.in_flight == 1
        assert environment.engine.pool.checkedout() == 1
        assert environment.locks._entries
        assert not environment.probe.closed.is_set()
        environment.probe.close_release.set()
        with pytest.raises(HTTPException) as error:
            await _watchdog(task, environment)
        assert error.value.status_code == 504
        await _assert_reusable(environment, transport)
    finally:
        environment.probe.release.set()
        environment.probe.close_release.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["json", "sse"])
@pytest.mark.parametrize("trigger", ["deadline", "external-cancellation"])
async def test_cancellation_during_sql_close_keeps_request_and_capacity_owned(
    preparation_environment: _Environment,
    transport: str,
    trigger: str,
) -> None:
    environment = preparation_environment
    environment.probe.stage = None
    environment.probe.hold_close = True
    task = asyncio.create_task(_call(environment, transport))
    try:
        await asyncio.wait_for(environment.probe.closing.wait(), timeout=1)
        assert environment.engine.pool.checkedout() == 1
        if trigger == "external-cancellation":
            task.cancel()
        # Keep the close active beyond the deadline too: external cancellation
        # must remain external even if that timer cancels the draining task again.
        done, _ = await asyncio.wait({task}, timeout=_BUDGET * 1.5)
        assert not done, {
            "premature_request_completion": task.done(),
            "connection_checked_out": environment.engine.pool.checkedout(),
            "capacity_in_flight": environment.pressure.in_flight,
            "close_completed": environment.probe.closed.is_set(),
        }
        assert environment.pressure.in_flight == 1
        assert environment.engine.pool.checkedout() == 1
        assert environment.locks._entries
        assert not environment.probe.closed.is_set()
        assert environment.graph.invoke_calls == environment.graph.stream_calls == 0
        environment.probe.close_release.set()
        if trigger == "deadline":
            with pytest.raises(HTTPException) as error:
                await _watchdog(task, environment)
            assert error.value.status_code == 504
        else:
            with pytest.raises(asyncio.CancelledError):
                await _watchdog(task, environment)
        await _assert_reusable(environment, transport)
    finally:
        environment.probe.release.set()
        environment.probe.close_release.set()
        # Drain the request and the shielded SQLAlchemy close even on red.
        done, _ = await asyncio.wait({task}, timeout=1)
        if not done:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.gather(*environment.probe.close_tasks, return_exceptions=True)


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["json", "sse"])
async def test_anyio_level_cancellation_during_close_does_not_spin_or_release_capacity(
    preparation_environment: _Environment,
    monkeypatch: pytest.MonkeyPatch,
    transport: str,
) -> None:
    environment = preparation_environment
    environment.probe.stage = None
    environment.probe.hold_close = True
    monkeypatch.setattr(main_module, "QUERY_TOTAL_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(main_module, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", 2)
    scope_holder: list[CancelScope] = []
    cancellation_seen = asyncio.Event()
    sentinel_start = asyncio.Event()
    sentinel_done = asyncio.Event()
    sentinel_ticks: list[int] = []

    async def request_in_scope() -> bool:
        with CancelScope() as scope:
            scope_holder.append(scope)
            try:
                await _call(environment, transport)
            except asyncio.CancelledError:
                cancellation_seen.set()
                raise
        # A scope suppresses its own cancellation: observe it here, not with
        # pytest.raises outside that scope.
        return scope.cancelled_caught

    async def sentinel() -> None:
        await sentinel_start.wait()
        for tick in range(12):
            sentinel_ticks.append(tick)
            await asyncio.sleep(0)
        sentinel_done.set()

    task = asyncio.create_task(request_in_scope())
    sentinel_task = asyncio.create_task(sentinel())
    try:
        await asyncio.wait_for(environment.probe.closing.wait(), timeout=1)
        assert environment.engine.pool.checkedout() == 1
        scope_holder[0].cancel()
        initial_cancellations = task.cancelling()
        sentinel_start.set()
        await asyncio.wait_for(sentinel_done.wait(), timeout=1)
        assert sentinel_ticks == list(range(12))
        assert not task.done()
        assert environment.pressure.in_flight == 1
        assert environment.engine.pool.checkedout() == 1
        assert environment.locks._entries
        assert not environment.probe.closed.is_set()
        # Level cancellation must not repeatedly interrupt the same drain while
        # unrelated tasks make progress. This is a delivery count, not a CPU benchmark.
        assert task.cancelling() - initial_cancellations <= 1
        environment.probe.close_release.set()
        assert await _watchdog(task, environment) is True
        assert cancellation_seen.is_set()
        assert environment.graph.invoke_calls == environment.graph.stream_calls == 0
        await _assert_reusable(environment, transport)
    finally:
        environment.probe.release.set()
        environment.probe.close_release.set()
        sentinel_start.set()
        done, _ = await asyncio.wait({task}, timeout=1)
        if not done:
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await asyncio.gather(*environment.probe.close_tasks, return_exceptions=True)
        await asyncio.gather(sentinel_task, return_exceptions=True)


@pytest.mark.anyio
async def test_sse_values_reset_the_stage_budget_and_progress_can_exceed_a_total_budget(
    preparation_environment: _Environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = preparation_environment
    _delay_preparation(monkeypatch, _BUDGET * 0.4)
    environment.graph.stream_plan = [(_BUDGET * 0.1, "values", {"messages": []})] + [
        (_BUDGET * 0.6, "custom", {"type": "status", "stage": f"stage-{index}"})
        for index in range(3)
    ]
    events = await _watchdog(_call(environment, "sse"), environment)
    assert len([event for event in events if event["type"] == "status"]) == 3
    assert not any(event["type"] == "error" for event in events)
    await _assert_reusable(environment, "sse")


@pytest.mark.anyio
async def test_expired_budget_during_asgi_start_does_not_start_a_graph_stream(
    preparation_environment: _Environment,
) -> None:
    environment = preparation_environment
    response = await _watchdog(main_module.query_stream(environment.request, _USER), environment)
    bodies: list[bytes] = []

    async def send(message: dict) -> None:
        if message["type"] == "http.response.start":
            await asyncio.sleep(_BUDGET * 1.2)
        elif message["type"] == "http.response.body":
            bodies.append(message.get("body", b""))

    async def receive() -> dict:
        return {"type": "http.request", "body": b"", "more_body": False}

    await _watchdog(
        response(
            {"type": "http", "asgi": {"spec_version": "2.4"}, "method": "POST", "headers": []},
            receive,
            send,
        ),
        environment,
    )
    events = [
        json.loads(frame.removeprefix("data: "))
        for frame in b"".join(bodies).decode().split("\n\n")
        if frame.startswith("data: ") and frame != "data: [DONE]"
    ]
    assert [event["type"] for event in events] == ["error"]
    assert environment.graph.stream_calls == 0
    await _assert_reusable(environment, "sse")
