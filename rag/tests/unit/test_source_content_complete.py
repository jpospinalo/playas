"""Public sources retain the selected body in JSON, SSE and stored messages.

All evidence is synthetic. TestClient runs without lifespan, so the real
handlers serialize a fake graph's result without starting Chroma or an LLM.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from langchain_core.messages import AIMessage

_PREFIX = "Antecedente ajeno al plazo. " * 24
_FACT = "La autoridad remitirá el informe dentro de diez días desde su aprobación."
_HTML = " Texto literal: <script>alert('documento')</script> y <b>sin HTML</b>."
_BODY = _PREFIX + "\n" + _FACT + _HTML
_PUBLIC_BODY = _PREFIX + " " + _FACT + _HTML
_USER = {"sub": "source-test-user"}


class _Graph:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.checkpointer = SimpleNamespace(storage={}, adelete_thread=AsyncMock())

    def _state(self) -> dict:
        return {
            "messages": [AIMessage(content="El plazo está documentado [doc1].")],
            "sources": self.documents,
            "query_route": "in_scope",
        }

    async def ainvoke(self, *args, **kwargs) -> dict:
        return self._state()

    async def astream(self, *args, **kwargs):
        yield "values", self._state()


@pytest.fixture
def source_api(monkeypatch: pytest.MonkeyPatch, tmp_path):
    # Set before deferred product imports; no real provenance is loaded.
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("LEGAL_RESOLUTION_PROVENANCE_PATH", "")
    monkeypatch.setenv("LEGAL_RESOLUTION_PROVENANCE_SHA256", "")
    import rag.api.main as main_module
    from rag.api.rate_limit import get_query_user

    documents = [
        Document(
            page_content=_BODY,
            metadata={
                "source": "norma.pdf",
                "title": "Norma de prueba",
                "doc_type": "normativa",
                "chunk_id": "norma-art-1",
                "id": "norma-art-1",
                "articulo": "1",
                "summary": "Plazo del informe.",
            },
        ),
        Document(
            page_content="Otra fuente independiente.",
            metadata={"source": "otra.pdf", "title": "Otra fuente", "chunk_id": "otra-1"},
        ),
        Document(
            page_content="Continuación de la norma.",
            metadata={"source": "norma.pdf", "title": "Norma de prueba", "chunk_id": "norma-2"},
        ),
    ]
    graph = _Graph(documents)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setitem(main_module.app.dependency_overrides, get_query_user, lambda: _USER)
    client = TestClient(main_module.app)  # No context manager: skip real startup.
    try:
        yield client, graph
    finally:
        client.close()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _public_response(client: TestClient, channel: str) -> dict:
    suffix = "/stream" if channel == "SSE" else ""
    response = client.post("/api/query" + suffix, json={"question": "¿Cuál es el plazo costero?"})
    assert response.status_code == 200, response.text
    if channel == "JSON":
        return response.json()
    assert response.text.rstrip().endswith("data: [DONE]")
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    assert not any(event.get("type") == "error" for event in events)
    return next(event for event in events if event.get("type") == "sources")


def _assert_complete_sources(sources: list[dict]) -> None:
    assert [group["source"] for group in sources] == ["norma.pdf", "otra.pdf"]
    assert [[part["index"] for part in group["fragments"]] for group in sources] == [[1, 3], [2]]
    fragment = sources[0]["fragments"][0]
    assert set(fragment) == {"index", "content", "metadata"}
    assert fragment["content"] == _PUBLIC_BODY
    assert _FACT in fragment["content"] and _HTML in fragment["content"]
    assert fragment["metadata"] == {
        "chunk_id": "norma-art-1",
        "id": "norma-art-1",
        "articulo": "1",
        "summary": "Plazo del informe.",
    }
    assert sources[0]["metadata"] == {"title": "Norma de prueba", "doc_type": "normativa"}
    assert sources[0]["fragments"][1]["metadata"] == {"chunk_id": "norma-2"}
    assert sources[1]["fragments"][0]["metadata"] == {"chunk_id": "otra-1"}


@pytest.mark.parametrize("channel", ["JSON", "SSE"])
def test_public_sources_keep_complete_body_identity_and_order(source_api, channel: str) -> None:
    client, graph = source_api
    assert _BODY.index(_FACT) > 500
    payload = _public_response(client, channel)
    _assert_complete_sources(payload["sources"])
    # HTML stays a string, and serialization must not rewrite the graph's evidence.
    assert graph.documents[0].page_content == _BODY
    assert graph.documents[0].metadata["chunk_id"] == "norma-art-1"


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
async def test_complete_sources_survive_persistence_and_reread(source_api, tmp_path, channel: str):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from rag.api.models import Base, Conversation, User
    from rag.api.routes.conversations import AddMessageRequest, add_message, list_messages

    client, _ = source_api
    sources = _public_response(client, channel)["sources"]
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "messages.db"))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all(
                [
                    User(id=_USER["sub"], email="source@example.invalid", password_hash="unused"),
                    Conversation(id="source-conv", user_id=_USER["sub"], thread_id="source-thread"),
                ]
            )
            await session.commit()
        payload = AddMessageRequest(role="assistant", text="Respuesta [doc1].", sources=sources)
        async with factory() as session:
            created = await add_message("source-conv", payload, _USER, session)
        async with factory() as session:
            messages = await list_messages("source-conv", _USER, session)
        assert len(messages) == 1
        assert messages[0].sources == created.sources == sources
        _assert_complete_sources(messages[0].sources)
    finally:
        await engine.dispose()


@pytest.mark.parametrize("channel", ["JSON", "SSE"])
def test_deliberate_legal_excerpt_is_not_expanded(source_api, channel: str) -> None:
    from rag.core.legal_resolution import Resolution

    client, graph = source_api
    original = graph.documents[0]
    excerpt = "[…] " + _FACT + " […]"
    assert len(excerpt) < 500
    resolution = Resolution("Orden [doc1].", (original,), (), (excerpt,))
    graph.documents = resolution.presentation_sources()
    fragment = _public_response(client, channel)["sources"][0]["fragments"][0]
    assert fragment["content"] == excerpt
    assert fragment["metadata"]["chunk_id"] == original.metadata["chunk_id"]
    assert _HTML not in fragment["content"]
    assert original.page_content == _BODY
