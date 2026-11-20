"""Own the query-embedding HTTP client within one API lifespan and event loop.

The Ollama context and HTTPX client are real with a simulated public transport.
Database startup, Chroma context and graph compilation are replaced at their
boundaries. No SDK client, authentication service or model is contacted.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from rag.api import database, main
from rag.core import agent, embeddings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
def startup(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replace only resources outside the query-embedding lifecycle."""
    init_db = AsyncMock()
    dispose = AsyncMock()
    initialize = Mock()
    close_retrievers = Mock()
    build_graph = Mock(side_effect=lambda **kwargs: object())
    chroma_query = SimpleNamespace(
        client=SimpleNamespace(
            headers={"Authorization": "Bearer chroma-only", "X-Chroma-Key": "chroma-only"}
        )
    )

    @asynccontextmanager
    async def open_chroma():
        yield chroma_query

    monkeypatch.setattr(database, "init_db", init_db)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    monkeypatch.setattr(main, "init_retrievers", initialize)
    monkeypatch.setattr(main, "close_retrievers", close_retrievers)
    monkeypatch.setattr(main, "open_chroma_query", open_chroma)
    monkeypatch.setattr(agent, "build_graph", build_graph)
    monkeypatch.setattr(main, "_graph", None)
    monkeypatch.setattr(main.app.state, "graph", None, raising=False)
    monkeypatch.setattr(main.app.state, "conversation_locks", None, raising=False)
    return SimpleNamespace(
        init_db=init_db,
        dispose=dispose,
        initialize=initialize,
        close_retrievers=close_retrievers,
        build_graph=build_graph,
        chroma_query=chroma_query,
    )


@pytest.fixture
def ollama_http(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    actual_async_client = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "http://ollama.lifespan.invalid/api/embeddings"
        assert "authorization" not in request.headers
        assert "x-chroma-key" not in request.headers
        payload = json.loads(request.content)
        assert payload["model"] == "lifespan-model"
        requests.append(request)
        return httpx.Response(200, json={"embedding": [0.25, 2]})

    def make_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(respond)
        kwargs["trust_env"] = False
        client = actual_async_client(*args, **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(embeddings, "OLLAMA_BASE_URL", "http://ollama.lifespan.invalid")
    monkeypatch.setattr(embeddings, "OLLAMA_EMBEDDING_MODEL", "lifespan-model")
    monkeypatch.setattr(embeddings.httpx, "AsyncClient", make_client)
    return SimpleNamespace(clients=clients, requests=requests)


@pytest.mark.anyio
async def test_lifespan_reuses_one_embedding_client_without_chroma_headers(
    startup: SimpleNamespace, ollama_http: SimpleNamespace
) -> None:
    async with main.lifespan(main.app):
        assert len(ollama_http.clients) == 1
        client = ollama_http.clients[0]
        assert not client.is_closed
        kwargs = startup.build_graph.call_args.kwargs
        assert kwargs["chroma_query"] is startup.chroma_query
        embed_query = kwargs["query_embedder"]
        assert await embed_query("Primera consulta") == [0.25, 2.0]
        assert await embed_query("Segunda consulta") == [0.25, 2.0]
        assert len(ollama_http.clients) == 1
        assert [json.loads(request.content)["prompt"] for request in ollama_http.requests] == [
            "Primera consulta",
            "Segunda consulta",
        ]

    assert client.is_closed
    startup.build_graph.assert_called_once()
    startup.close_retrievers.assert_called_once()
    startup.dispose.assert_awaited_once()
    assert main._graph is None and main.app.state.graph is None


@pytest.mark.anyio
async def test_embedding_client_closes_if_graph_compilation_fails(
    startup: SimpleNamespace, ollama_http: SimpleNamespace
) -> None:
    startup.build_graph.side_effect = RuntimeError("Synthetic compilation failure")
    with pytest.raises(RuntimeError, match="Synthetic compilation failure"):
        async with main.lifespan(main.app):
            pytest.fail("Graph compilation must fail before serving requests")

    assert len(ollama_http.clients) == 1
    assert ollama_http.clients[0].is_closed
    assert ollama_http.requests == []
    startup.close_retrievers.assert_called_once()
    startup.dispose.assert_awaited_once()
    assert main._graph is None and main.app.state.graph is None


def test_embedding_lifespan_clients_are_distinct_across_event_loops(
    startup: SimpleNamespace, ollama_http: SimpleNamespace
) -> None:
    async def cycle() -> None:
        async with main.lifespan(main.app):
            assert not ollama_http.clients[-1].is_closed
            embed_query = startup.build_graph.call_args.kwargs["query_embedder"]
            assert await embed_query("Consulta de un ciclo") == [0.25, 2.0]
        assert ollama_http.clients[-1].is_closed
        assert main._graph is None and main.app.state.graph is None

    asyncio.run(cycle())
    asyncio.run(cycle())
    assert len(ollama_http.clients) == 2
    assert ollama_http.clients[0] is not ollama_http.clients[1]
    assert len(ollama_http.requests) == 2
    assert startup.dispose.await_count == 2
    assert startup.close_retrievers.call_count == 2


@pytest.mark.anyio
async def test_sdk_fallback_does_not_open_query_embedding_client(
    monkeypatch: pytest.MonkeyPatch, startup: SimpleNamespace, ollama_http: SimpleNamespace
) -> None:
    @asynccontextmanager
    async def legacy_chroma():
        # This is the public context boundary for the SDK-auth fallback.
        # The existing Chroma shutdown test verifies provider-based selection.
        yield None

    open_embeddings = Mock(side_effect=AssertionError("SDK fallback must not open Ollama HTTPX"))
    monkeypatch.setattr(main, "open_chroma_query", legacy_chroma)
    monkeypatch.setattr(main, "open_query_embeddings", open_embeddings)
    async with main.lifespan(main.app):
        kwargs = startup.build_graph.call_args.kwargs
        assert kwargs["chroma_query"] is None
        assert kwargs.get("query_embedder") is None

    open_embeddings.assert_not_called()
    assert ollama_http.clients == [] and ollama_http.requests == []
    startup.close_retrievers.assert_called_once()
    startup.dispose.assert_awaited_once()
    assert main._graph is None and main.app.state.graph is None
