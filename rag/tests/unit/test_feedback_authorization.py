"""Matriz pública acotada de feedback con JWT y SQLite sintéticos.

Usa las rutas y dependencias de autorización reales. ASGITransport no inicia
el lifespan RAG; sólo se sustituye get_session por sesiones SQL temporales.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag.api.auth import create_access_token
from rag.api.database import get_session
from rag.api.main import app
from rag.api.models import Base, Conversation, Feedback, Message, MessageFeedback, User

_SECRET = "synthetic-feedback-authorization-secret-with-enough-entropy"
_POSTS = ("/api/feedback", "/api/feedback/message")
_GETS = ("/api/admin/feedback", "/api/admin/message-feedback")
_ROLES = {
    "owner": "user",
    "other": "user",
    "admin": "admin",
    "super": "super-admin",
    "demoted": "user",
}
_CONVERSATION_RATINGS = {"tone": 4, "length": 3, "usability": 5, "overall": 4}
_MESSAGE_RATINGS = {"pertinence": 5, "accuracy": 4}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@dataclass
class _FeedbackAPI:
    client: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]

    def headers(self, actor: str, *, role: str | None = None) -> dict[str, str]:
        token = create_access_token(
            actor, f"{actor}@example.test", role or _ROLES.get(actor, "user")
        )
        return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def feedback_api(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_FeedbackAPI]:
    monkeypatch.setenv("JWT_SECRET_KEY", _SECRET)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add_all(
                [
                    User(
                        id=actor,
                        email=f"{actor}@example.test",
                        password_hash="synthetic",
                        role=role,
                    )
                    for actor, role in _ROLES.items()
                ]
            )
            session.add_all(
                [
                    Conversation(
                        id=f"conv-{actor}",
                        user_id=actor,
                        thread_id=f"thread-{actor}",
                        title=f"Chat {actor}",
                    )
                    for actor in ("owner", "other", "admin")
                ]
            )
            session.add(
                Conversation(id="conv-sibling", user_id="owner", thread_id="thread-sibling")
            )
            session.add_all(
                [
                    Message(
                        id=f"msg-{actor}",
                        conversation_id=f"conv-{actor}",
                        role="assistant",
                        text=f"Answer {actor}",
                    )
                    for actor in ("owner", "other", "admin")
                ]
            )
            session.add_all(
                [
                    Message(
                        id="msg-user", conversation_id="conv-owner", role="user", text="Question"
                    ),
                    Message(
                        id="msg-sibling",
                        conversation_id="conv-sibling",
                        role="assistant",
                        text="Sibling answer",
                    ),
                    Message(
                        id="msg-rated",
                        conversation_id="conv-owner",
                        role="assistant",
                        text="Rated answer",
                    ),
                ]
            )
            session.add_all(
                [
                    Feedback(
                        id=f"feedback-{actor}",
                        user_id=actor,
                        user_email=f"{actor}@example.test",
                        ratings=dict(_CONVERSATION_RATINGS),
                        conversation_id=f"conv-{actor}",
                        conversation_title=f"Chat {actor}",
                    )
                    for actor in ("owner", "other")
                ]
            )
            session.add_all(
                [
                    MessageFeedback(
                        id="message-feedback-owner",
                        user_id="owner",
                        user_email="owner@example.test",
                        conversation_id="conv-owner",
                        message_id="msg-rated",
                        ratings=dict(_MESSAGE_RATINGS),
                    ),
                    MessageFeedback(
                        id="message-feedback-other",
                        user_id="other",
                        user_email="other@example.test",
                        conversation_id="conv-other",
                        message_id="msg-other",
                        ratings=dict(_MESSAGE_RATINGS),
                    ),
                ]
            )
            await session.commit()

        async def test_session() -> AsyncIterator[AsyncSession]:
            async with sessions() as session:
                yield session

        monkeypatch.setitem(app.dependency_overrides, get_session, test_session)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://feedback.test"
        ) as client:
            yield _FeedbackAPI(client, sessions)
    finally:
        await engine.dispose()


def _payload(path: str, actor: str = "owner") -> dict:
    if path == "/api/feedback":
        return {
            "conversation_id": f"conv-{actor}",
            "ratings": dict(_CONVERSATION_RATINGS),
            "comment": "Synthetic comment",
        }
    return {
        "conversation_id": f"conv-{actor}",
        "message_id": f"msg-{actor}",
        "ratings": dict(_MESSAGE_RATINGS),
        "expected_answer": "Synthetic expected answer",
    }


async def _snapshot(api: _FeedbackAPI) -> dict[str, list[dict]]:
    snapshot = {}
    async with api.sessions() as session:
        for model in (Feedback, MessageFeedback):
            rows = (await session.execute(select(model).order_by(model.id))).scalars().all()
            snapshot[model.__tablename__] = [
                {column.name: getattr(row, column.name) for column in model.__table__.columns}
                for row in rows
            ]
    return snapshot


@pytest.mark.anyio
@pytest.mark.parametrize("path", (*_POSTS, *_GETS))
@pytest.mark.parametrize("credential", ["missing", "invalid", "expired", "deleted"])
async def test_feedback_routes_require_a_live_authenticated_user(
    feedback_api: _FeedbackAPI, path: str, credential: str
) -> None:
    api = feedback_api
    before = await _snapshot(api)
    headers: dict[str, str] = {}
    if credential == "invalid":
        headers = {"Authorization": "Bearer invalid.synthetic.token"}
    elif credential == "deleted":
        headers = api.headers("deleted")
    elif credential == "expired":
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "owner",
                "email": "owner@example.test",
                "role": "user",
                "iat": now - timedelta(minutes=2),
                "exp": now - timedelta(minutes=1),
            },
            _SECRET,
            algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
    response = (
        await api.client.post(path, json=_payload(path), headers=headers)
        if path in _POSTS
        else await api.client.get(path, headers=headers)
    )
    assert response.status_code == 401, response.text
    assert await _snapshot(api) == before


@pytest.mark.anyio
@pytest.mark.parametrize("path", _POSTS)
@pytest.mark.parametrize("actor", ["owner", "admin"])
async def test_feedback_creation_uses_the_authenticated_owner(
    feedback_api: _FeedbackAPI, path: str, actor: str
) -> None:
    api = feedback_api
    response = await api.client.post(path, json=_payload(path, actor), headers=api.headers(actor))
    assert response.status_code == 201, response.text
    model = Feedback if path == "/api/feedback" else MessageFeedback
    async with api.sessions() as session:
        stored = await session.get(model, response.json()["id"])
        assert stored is not None
        assert stored.user_id == actor
        assert stored.user_email == f"{actor}@example.test"
        assert stored.conversation_id == f"conv-{actor}"


@pytest.mark.anyio
@pytest.mark.parametrize("path", _POSTS)
@pytest.mark.parametrize("actor", ["owner", "admin"])
@pytest.mark.parametrize("conversation_id", ["conv-other", "missing"])
async def test_foreign_or_missing_conversation_is_404_even_for_admin(
    feedback_api: _FeedbackAPI, path: str, actor: str, conversation_id: str
) -> None:
    api = feedback_api
    before = await _snapshot(api)
    body = {**_payload(path, actor), "conversation_id": conversation_id}
    response = await api.client.post(path, json=body, headers=api.headers(actor))
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Conversación no encontrada."
    assert await _snapshot(api) == before


@pytest.mark.anyio
@pytest.mark.parametrize("message_id", ["missing", "msg-other", "msg-sibling", "msg-user"])
async def test_message_feedback_requires_an_assistant_message_in_the_same_conversation(
    feedback_api: _FeedbackAPI, message_id: str
) -> None:
    api = feedback_api
    before = await _snapshot(api)
    body = {**_payload("/api/feedback/message"), "message_id": message_id}
    response = await api.client.post(
        "/api/feedback/message", json=body, headers=api.headers("owner")
    )
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Mensaje no encontrado."
    assert await _snapshot(api) == before


@pytest.mark.anyio
@pytest.mark.parametrize("same_payload", [True, False])
async def test_duplicate_message_feedback_is_409_without_replay_or_editing(
    feedback_api: _FeedbackAPI, same_payload: bool
) -> None:
    api = feedback_api
    body = _payload("/api/feedback/message")
    first = await api.client.post("/api/feedback/message", json=body, headers=api.headers("owner"))
    assert first.status_code == 201, first.text
    before = await _snapshot(api)
    if not same_payload:
        body = {**body, "ratings": {"pertinence": 1, "accuracy": 2}, "expected_answer": "Different"}
    repeated = await api.client.post(
        "/api/feedback/message", json=body, headers=api.headers("owner")
    )
    assert repeated.status_code == 409, repeated.text
    assert repeated.json()["detail"] == "Ya existe feedback para este mensaje."
    assert await _snapshot(api) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "field", "value"),
    [
        ("/api/feedback", "overall", 0),
        ("/api/feedback", "tone", 6),
        ("/api/feedback", "comment", "x" * 501),
        ("/api/feedback/message", "accuracy", 0),
        ("/api/feedback/message", "pertinence", 6),
        ("/api/feedback/message", "expected_answer", "x" * 1001),
        ("/api/feedback/message", "message_id", ""),
    ],
)
async def test_invalid_ratings_lengths_and_message_identity_remain_422(
    feedback_api: _FeedbackAPI, path: str, field: str, value: int | str
) -> None:
    api = feedback_api
    before = await _snapshot(api)
    body = _payload(path)
    if field in body["ratings"]:
        body["ratings"][field] = value
    else:
        body[field] = value
    response = await api.client.post(path, json=body, headers=api.headers("owner"))
    assert response.status_code == 422, response.text
    assert await _snapshot(api) == before


@pytest.mark.anyio
@pytest.mark.parametrize("path", _POSTS)
async def test_extra_identity_fields_do_not_override_the_authenticated_user(
    feedback_api: _FeedbackAPI, path: str
) -> None:
    api = feedback_api
    body = {
        **_payload(path),
        "user_id": "other",
        "user_email": "other@example.test",
        "email": "other@example.test",
    }
    body["ratings"] = {key: str(value) for key, value in body["ratings"].items()}
    response = await api.client.post(path, json=body, headers=api.headers("owner"))
    assert response.status_code == 201, response.text
    model = Feedback if path == "/api/feedback" else MessageFeedback
    async with api.sessions() as session:
        stored = await session.get(model, response.json()["id"])
        assert stored is not None
        assert stored.user_id == "owner"
        assert stored.user_email == "owner@example.test"
        expected = _CONVERSATION_RATINGS if model is Feedback else _MESSAGE_RATINGS
        assert stored.ratings == expected


@pytest.mark.anyio
@pytest.mark.parametrize("conversation_id", [None, "conv-owner"])
async def test_general_feedback_without_conversation_and_repeated_conversation_ratings_are_allowed(
    feedback_api: _FeedbackAPI, conversation_id: str | None
) -> None:
    api = feedback_api
    body = {"ratings": dict(_CONVERSATION_RATINGS), "conversation_id": conversation_id}
    responses = [
        await api.client.post("/api/feedback", json=body, headers=api.headers("owner"))
        for _ in range(2)
    ]
    assert [response.status_code for response in responses] == [201, 201]
    ids = [response.json()["id"] for response in responses]
    assert len(set(ids)) == 2
    async with api.sessions() as session:
        for feedback_id in ids:
            stored = await session.get(Feedback, feedback_id)
            assert stored is not None
            assert stored.conversation_id == conversation_id
            assert stored.user_id == "owner"


@pytest.mark.anyio
@pytest.mark.parametrize("path", _GETS)
@pytest.mark.parametrize("actor", ["owner", "demoted"])
async def test_regular_and_demoted_users_cannot_read_global_feedback(
    feedback_api: _FeedbackAPI, path: str, actor: str
) -> None:
    api = feedback_api
    before = await _snapshot(api)
    response = await api.client.get(
        path, headers=api.headers(actor, role="admin" if actor == "demoted" else "user")
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == "Acceso denegado."
    assert await _snapshot(api) == before


@pytest.mark.anyio
@pytest.mark.parametrize("path", _GETS)
@pytest.mark.parametrize("actor", ["admin", "super"])
async def test_current_administrative_roles_can_read_global_feedback(
    feedback_api: _FeedbackAPI, path: str, actor: str
) -> None:
    api = feedback_api
    before = await _snapshot(api)
    response = await api.client.get(path, headers=api.headers(actor))
    assert response.status_code == 200, response.text
    assert {item["userId"] for item in response.json()["items"]} == {"owner", "other"}
    assert response.json()["total"] == 2
    assert await _snapshot(api) == before
