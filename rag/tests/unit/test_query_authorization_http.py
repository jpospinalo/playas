"""C02: real HTTP dependencies, JWT, SQL ownership and checkpoint isolation.

ASGI stays in memory without the service-starting lifespan. Only provider,
retrieval and analysis calls are synthetic; the application graph is real.
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import httpx
import jwt
import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag.api.database as database_module
import rag.api.main as main_module
import rag.api.rate_limit as rate_limit_module
import rag.core.agent as agent_module
from rag.api.auth import create_access_token
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.database import get_session
from rag.api.models import Base, Conversation, Message, User
from rag.api.query_support import _make_config
from rag.api.rate_limit import ConcurrencyBackpressure, SlidingWindowRateLimiter
from rag.core.domain_scope import EnrichedQuery
from rag.core.observability import ActiveQueryTracker

_SECRET = "synthetic-query-authorization-secret-with-sufficient-entropy"
_THREAD = "same-client-thread"
_PRIVATE = {"owner": "PRIVATE_OWNER_752", "other": "PRIVATE_OTHER_619"}
_ROLES = {"owner": "user", "other": "user", "admin": "admin"}
_PATHS = ("/api/query", "/api/query/stream")
_ANSWER = "El uso de las playas está sujeto a las autoridades competentes [doc1]."
_DOCUMENT = "El uso de las playas está sujeto a las autoridades competentes."
_WAIT = 5.0


def _question(marker: str) -> str:
    return f"¿Qué autoridad regula el uso de las playas? {marker}"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class _QueryAPI:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    graph: Any
    checkpoint_read: AsyncMock
    analysis: list[tuple[str, str]] = field(default_factory=list)
    retrieval: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)

    def headers(self, actor: str) -> dict[str, str]:
        token = create_access_token(actor, f"{actor}@example.invalid", _ROLES.get(actor, "user"))
        return {"Authorization": f"Bearer {token}"}

    async def post(
        self, path: str, actor: str, body: dict, *, headers: dict | None = None
    ) -> httpx.Response:
        return await asyncio.wait_for(
            self.client.post(
                path, json=body, headers=self.headers(actor) if headers is None else headers
            ),
            timeout=_WAIT,
        )

    def reset_calls(self) -> None:
        self.analysis.clear()
        self.retrieval.clear()
        self.prompts.clear()
        self.checkpoint_read.reset_mock()

    def checkpoint_snapshot(self) -> dict:
        return copy.deepcopy(
            {
                "storage": self.graph.checkpointer.storage,
                "writes": self.graph.checkpointer.writes,
                "blobs": self.graph.checkpointer.blobs,
            }
        )

    async def sql_snapshot(self) -> dict:
        snapshot = {}
        async with self.sessions() as session:
            for model in (User, Conversation, Message):
                rows = (await session.execute(select(model).order_by(model.id))).scalars().all()
                snapshot[model.__tablename__] = [
                    {column.name: getattr(row, column.name) for column in model.__table__.columns}
                    for row in rows
                ]
        return snapshot


@pytest.fixture
async def query_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_QueryAPI]:
    monkeypatch.setenv("JWT_SECRET_KEY", _SECRET)
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'query-authorization.sqlite'}",
        connect_args={"timeout": 1},
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    analysis: list[tuple[str, str]] = []
    retrieval: list[str] = []
    prompts: list[str] = []

    async def analyze(question: str, history: str) -> EnrichedQuery:
        analysis.append((question, history))
        return EnrichedQuery(
            route="in_scope",
            standalone_question=question,
            expanded_query=question,
            doc_types=["normativa"],
        )

    async def retrieve(question: str) -> list[Document]:
        retrieval.append(question)
        return [
            Document(
                page_content=_DOCUMENT,
                metadata={
                    "source": "public-synthetic.md",
                    "chunk_id": "public-synthetic-1",
                    "doc_type": "normativa",
                },
            )
        ]

    async def generate(prompt: Any) -> AIMessage:
        prompts.append("\n".join(str(message.content) for message in prompt.to_messages()))
        return AIMessage(content=_ANSWER)

    monkeypatch.setattr(agent_module, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    monkeypatch.setattr(
        agent_module, "get_ensemble_retriever", lambda **_kwargs: RunnableLambda(retrieve)
    )
    monkeypatch.setattr(agent_module, "get_generation_llm", lambda: RunnableLambda(generate))
    monkeypatch.setattr(
        agent_module, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    graph = agent_module.build_graph()
    checkpoint_read = AsyncMock(wraps=graph.aget_state)
    monkeypatch.setattr(graph, "aget_state", checkpoint_read)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", ConversationLockRegistry())
    monkeypatch.setattr(main_module, "ACTIVE_QUERIES", ActiveQueryTracker())
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="enforce", max_concurrent=2)
    )
    monkeypatch.setattr(
        rate_limit_module, "query_rate_limiter", SlidingWindowRateLimiter(mode="off")
    )
    monkeypatch.setattr(database_module, "async_session_factory", sessions)

    async def local_session() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    # Remove possible unrelated test overrides temporarily, never bypass auth.
    monkeypatch.setattr(main_module.app, "dependency_overrides", {get_session: local_session})
    now = datetime(2026, 1, 1, tzinfo=UTC)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all(
                [
                    User(
                        id=actor,
                        email=f"{actor}@example.invalid",
                        password_hash="synthetic-only",
                        role=role,
                    )
                    for actor, role in _ROLES.items()
                ]
            )
            session.add_all(
                [
                    Conversation(id=f"conv-{actor}", user_id=actor, thread_id=_THREAD)
                    for actor in _ROLES
                ]
            )
            session.add(
                Conversation(id="conv-sibling", user_id="owner", thread_id="sibling-thread")
            )
            for actor in _PRIVATE:
                session.add_all(
                    [
                        Message(
                            id=f"history-{actor}",
                            conversation_id=f"conv-{actor}",
                            role="user",
                            text=_question(_PRIVATE[actor]),
                            created_at=now,
                        ),
                        Message(
                            id=f"assistant-{actor}",
                            conversation_id=f"conv-{actor}",
                            role="assistant",
                            text=_ANSWER,
                            created_at=now + timedelta(seconds=1),
                        ),
                    ]
                )
            session.add_all(
                [
                    Message(
                        id="current-owner",
                        conversation_id="conv-owner",
                        role="user",
                        text=_question("CURRENT_OWNER_225"),
                        created_at=now + timedelta(seconds=2),
                    ),
                    Message(
                        id="current-sibling",
                        conversation_id="conv-sibling",
                        role="user",
                        text=_question("CURRENT_OWNER_225"),
                        created_at=now + timedelta(seconds=2),
                    ),
                    Message(
                        id="current-assistant",
                        conversation_id="conv-owner",
                        role="assistant",
                        text=_question("CURRENT_OWNER_225"),
                        created_at=now + timedelta(seconds=3),
                    ),
                ]
            )
            await session.commit()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main_module.app), base_url="http://query.test"
        ) as client:
            yield _QueryAPI(client, sessions, graph, checkpoint_read, analysis, retrieval, prompts)
    finally:
        await engine.dispose()


def _answer(response: httpx.Response) -> dict:
    assert response.status_code == 200, response.text
    if response.headers["content-type"].startswith("application/json"):
        result = response.json()
    else:
        assert response.headers["content-type"].startswith("text/event-stream")
        payloads = [
            line.removeprefix("data: ")
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert payloads[-1] == "[DONE]"
        assert payloads.count("[DONE]") == 1
        events = [json.loads(payload) for payload in payloads[:-1]]
        assert not any(event["type"] == "error" for event in events)
        sources = [event for event in events if event["type"] == "sources"]
        assert len(sources) == 1
        result = {
            **sources[0],
            "answer": "".join(event["content"] for event in events if event["type"] == "token"),
        }
    assert result["answer"] == _ANSWER
    assert result["query_route"] == "in_scope"
    assert len(result["sources"]) == 1
    group = result["sources"][0]
    assert group["source"] == "public-synthetic.md"
    assert len(group["fragments"]) == 1
    assert group["fragments"][0]["index"] == 1
    assert group["fragments"][0]["content"] == _DOCUMENT
    return result


async def _assert_rejection(
    api: _QueryAPI, response: httpx.Response, status: int, sql_before: dict, memory_before: dict
) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert set(response.json()) == {"detail"}
    assert isinstance(response.json()["detail"], str)
    assert "data:" not in response.text
    assert all(marker not in response.text for marker in _PRIVATE.values())
    assert not api.analysis and not api.retrieval and not api.prompts
    api.checkpoint_read.assert_not_awaited()
    assert await api.sql_snapshot() == sql_before
    assert api.checkpoint_snapshot() == memory_before
    assert main_module.ACTIVE_QUERIES.count == 0
    assert main_module.backpressure.in_flight == 0
    assert main_module.CONVERSATION_LOCKS._entries == {}


@pytest.mark.anyio
@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize("credential", ["missing", "bad-signature", "expired", "deleted"])
async def test_query_http_requires_a_live_authenticated_user(
    query_api: _QueryAPI, path: str, credential: str
) -> None:
    api = query_api
    headers: dict[str, str] = {}
    if credential == "deleted":
        headers = api.headers("deleted")
    elif credential in {"bad-signature", "expired"}:
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "owner",
                "email": "owner@example.invalid",
                "role": "user",
                "iat": now - timedelta(minutes=2),
                "exp": now - timedelta(minutes=1)
                if credential == "expired"
                else now + timedelta(minutes=1),
            },
            _SECRET if credential == "expired" else "different-synthetic-signing-secret",
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
    body = {"question": _question("AUTH_CONTROL"), "thread_id": _THREAD}
    sql_before, memory_before = await api.sql_snapshot(), api.checkpoint_snapshot()
    response = await api.post(path, "owner", body, headers=headers)
    await _assert_rejection(api, response, 401, sql_before, memory_before)


@pytest.mark.anyio
@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize("warm", [False, True], ids=["cold", "warm"])
@pytest.mark.parametrize("actor", ["other", "admin"])
async def test_foreign_conversation_is_rejected_even_with_a_warm_checkpoint_or_admin_role(
    query_api: _QueryAPI, path: str, warm: bool, actor: str
) -> None:
    api = query_api
    if warm:
        _answer(
            await api.post(
                path,
                "owner",
                {"question": _question("OWNER_WARMUP"), "conversation_id": "conv-owner"},
            )
        )
    api.reset_calls()
    sql_before, memory_before = await api.sql_snapshot(), api.checkpoint_snapshot()
    response = await api.post(
        path,
        actor,
        {
            "question": _question("FOREIGN_ATTEMPT"),
            "conversation_id": "conv-owner",
            "thread_id": _THREAD,
        },
    )
    await _assert_rejection(api, response, 404, sql_before, memory_before)


@pytest.mark.anyio
@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize("kind", ["missing", "sibling", "assistant", "text-mismatch"])
async def test_query_http_validates_current_message_inside_the_owned_conversation(
    query_api: _QueryAPI, path: str, kind: str
) -> None:
    api = query_api
    identities = {
        "missing": "missing-message",
        "sibling": "current-sibling",
        "assistant": "current-assistant",
        "text-mismatch": "current-owner",
    }
    body = {
        "question": _question("DISCORDANT_332" if kind == "text-mismatch" else "CURRENT_OWNER_225"),
        "conversation_id": "conv-owner",
        "current_message_id": identities[kind],
        "thread_id": _THREAD,
    }
    sql_before, memory_before = await api.sql_snapshot(), api.checkpoint_snapshot()
    response = await api.post(path, "owner", body)
    await _assert_rejection(api, response, 422, sql_before, memory_before)


@pytest.mark.anyio
@pytest.mark.parametrize("path", _PATHS)
@pytest.mark.parametrize(
    "persisted", [False, True], ids=["explicit-thread", "persisted-conversations"]
)
async def test_same_client_thread_is_isolated_for_two_users_in_cold_and_warm_turns(
    query_api: _QueryAPI, path: str, persisted: bool
) -> None:
    api = query_api
    sql_before = await api.sql_snapshot()
    turns = {"owner": [], "other": []}
    for number in (1, 2):
        for actor, foreign in (("owner", "other"), ("other", "owner")):
            marker = f"TURN_{actor.upper()}_{number}_798"
            question = _question(marker)
            body = {"question": question, "thread_id": _THREAD}
            if persisted:
                body["conversation_id"] = f"conv-{actor}"
            before_analysis = len(api.analysis)
            before_prompts = len(api.prompts)
            response = await api.post(path, actor, body)
            _answer(response)
            assert len(api.analysis) == before_analysis + 1
            assert len(api.prompts) == before_prompts + 1
            seen_question, history = api.analysis[-1]
            assert seen_question == question
            assert marker in api.prompts[-1]
            assert _PRIVATE[foreign] not in history + api.prompts[-1] + response.text
            assert all(old not in history + api.prompts[-1] for old in turns[foreign])
            if number == 1:
                if persisted:
                    assert _PRIVATE[actor] in history
                else:
                    assert history == ""
            else:
                assert turns[actor][0] in history
            turns[actor].append(marker)

    keys = []
    for actor, foreign in (("owner", "other"), ("other", "owner")):
        config = _make_config(actor, f"conv-{actor}" if persisted else None, _THREAD)
        keys.append(config["configurable"]["thread_id"])
        state = await asyncio.wait_for(api.graph.aget_state(config), timeout=_WAIT)
        history = "\n".join(str(message.content) for message in state.values["messages"])
        assert all(marker in history for marker in turns[actor])
        assert all(marker not in history for marker in turns[foreign])
        assert _PRIVATE[foreign] not in history
        if persisted:
            assert _PRIVATE[actor] in history
        else:
            assert _PRIVATE[actor] not in history
    assert keys[0] != keys[1]
    assert set(api.graph.checkpointer.storage) == set(keys)
    assert len(api.analysis) == len(api.retrieval) == len(api.prompts) == 4
    assert await api.sql_snapshot() == sql_before
    assert main_module.ACTIVE_QUERIES.count == 0
    assert main_module.backpressure.in_flight == 0
    assert main_module.CONVERSATION_LOCKS._entries == {}
