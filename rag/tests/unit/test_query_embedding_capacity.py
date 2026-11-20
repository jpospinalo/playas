"""The product query embedder frees its real HTTP pool after interruption.

Only the network is simulated. The first HTTP/1.1 body never completes;
neither the assertion path nor fixture cleanup supplies its missing bytes.
The product singleton remains present and rejects accidental legacy use.
"""

from __future__ import annotations

import asyncio
import json
from functools import partial
from types import SimpleNamespace

import httpcore
import httpx
import pytest
import requests
from fastapi import HTTPException
from langchain_core.messages import AIMessage
from langchain_core.retrievers import BaseRetriever
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from starlette.responses import StreamingResponse
from starlette.types import Message

from rag.api import main
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.schemas import QueryRequest, QueryResponse
from rag.core import embeddings as candidate
from rag.core import retriever
from rag.core.agent import AgentState
from rag.core.chroma_query import ChromaQuery
from rag.core.observability import ActiveQueryTracker

_USER = {"sub": "embedding-capacity-offline"}
_FIRST = "Primera consulta sintética sobre playas."
_SECOND = "Segunda consulta sintética sobre playas."
_VECTOR = [0.5, 0.75]
_BODY = "Pasaje sintético para verificar la cita y su origen."
_ANSWER = f"{_BODY} [doc1]"
_CHUNK_ID = "fragment-second"
_SOURCE = "norma-sintetica.pdf"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _EmptyRetriever(BaseRetriever):
    def _get_relevant_documents(self, query, *, run_manager):
        return []

    async def _aget_relevant_documents(self, query, *, run_manager):
        return []


class _Wire(httpcore.AsyncNetworkStream):
    def __init__(self, response: bytes, *, stall: bool = False, read_timeout: bool = False) -> None:
        self.response = response
        self.stall = stall
        self.reading = asyncio.Event()
        self.closed = asyncio.Event()
        self.written = bytearray()
        self.read_timeout = read_timeout
        self.fail_read = asyncio.Event()

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if not self.stall or not self.response:
            self.reading.set()
        if self.stall and not self.response:
            if self.read_timeout:
                await self.fail_read.wait()
                raise httpcore.ReadTimeout("Synthetic embedding body read timeout")
            await asyncio.Future()
            raise AssertionError("The original embedding body must never complete")
        data, self.response = self.response[:max_bytes], self.response[max_bytes:]
        return data

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        self.written.extend(buffer)

    async def aclose(self) -> None:
        self.closed.set()

    def payload(self) -> dict:
        headers, body = bytes(self.written).split(b"\r\n\r\n", 1)
        assert headers.startswith(b"POST /api/embeddings HTTP/1.1\r\n")
        return json.loads(body)


class _Network(httpcore.AsyncNetworkBackend):
    def __init__(self, *, read_timeout: bool = False) -> None:
        self.first = _Wire(
            b"HTTP/1.1 200 OK\r\nContent-Length: 30\r\n\r\n{",
            stall=True,
            read_timeout=read_timeout,
        )
        body = json.dumps({"embedding": _VECTOR}).encode()
        self.second = _Wire(
            f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
        )
        self.connections = 0

    async def connect_tcp(self, host: str, port: int, **kwargs: object) -> _Wire:
        assert (host, port) == ("ollama.offline.invalid", 80)
        self.connections += 1
        assert self.connections <= 2, "No retry or third embedding connection is allowed"
        return self.first if self.connections == 1 else self.second


async def _observe(task: asyncio.Task, seconds: float = 2.0) -> None:
    done, _ = await asyncio.wait({task}, timeout=seconds)
    assert task in done, "The observer expired without completing the API task"


async def _read_sse(
    response: StreamingResponse,
    disconnected: asyncio.Event,
    send_started: asyncio.Event | None = None,
) -> list[str]:
    frames: list[bytes] = []

    async def receive() -> Message:
        await disconnected.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body":
            body = message.get("body", b"")
            if send_started is not None:
                assert json.loads(body.removeprefix(b"data: "))["type"] == "status"
                send_started.set()
                await asyncio.Future()
            frames.append(body)

    await response({"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send)
    return [
        line.removeprefix("data: ")
        for line in b"".join(frames).decode().splitlines()
        if line.startswith("data: ")
    ]


async def _call(endpoint: str, question: str) -> QueryResponse | list[str]:
    request = QueryRequest(question=question)
    if endpoint == "json":
        return await main.query(request, _USER)
    return await _read_sse(await main.query_stream(request, _USER), asyncio.Event())


def _verify_answer(result: QueryResponse | list[str]) -> None:
    if isinstance(result, QueryResponse):
        assert result.answer == _ANSWER
        sources = [group.model_dump() for group in result.sources]
    else:
        token, sources_event, done = result
        assert json.loads(token) == {"type": "token", "content": _ANSWER}
        assert done == "[DONE]"
        sources = json.loads(sources_event)["sources"]
    assert len(sources) == 1
    assert sources[0]["source"] == _SOURCE
    assert sources[0]["doc_type"] == "normativa"
    (fragment,) = sources[0]["fragments"]
    assert fragment["index"] == 1
    assert fragment["content"] == _BODY
    assert fragment["metadata"]["chunk_id"] == _CHUNK_ID


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "interruption"),
    [
        ("json", "timeout"),
        ("sse", "timeout"),
        ("json", "cancel"),
        ("sse", "disconnect"),
        ("sse", "disconnect_progress_send"),
        ("json", "read_timeout"),
        ("sse", "read_timeout"),
    ],
)
async def test_embedding_interruption_releases_same_http_pool_before_rescue(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, interruption: str
) -> None:
    network = _Network(read_timeout=interruption == "read_timeout")
    transport = httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=1), trust_env=False)
    # Test-only network injection; HTTPX/httpcore own the actual one-slot pool.
    transport._pool._network_backend = network
    limiter = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    locks = ConversationLockRegistry()
    tracker = ActiveQueryTracker()
    monkeypatch.setattr(main, "backpressure", limiter)
    monkeypatch.setattr(main, "CONVERSATION_LOCKS", locks)
    monkeypatch.setattr(main, "ACTIVE_QUERIES", tracker)
    monkeypatch.setattr(
        main, "QUERY_TOTAL_TIMEOUT_SECONDS", 1.0 if interruption == "timeout" else 8.0
    )
    monkeypatch.setattr(
        main, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", 1.0 if interruption == "timeout" else 8.0
    )
    monkeypatch.setattr(candidate, "OLLAMA_BASE_URL", "http://ollama.offline.invalid")
    monkeypatch.setattr(candidate, "OLLAMA_EMBEDDING_MODEL", "fixture-embedding-model")

    def reject_sync_http(*args, **kwargs):
        raise AssertionError("The query helper must not use Requests")

    async def reject_legacy_embedding(*args, **kwargs):
        raise AssertionError("The REST query must use its injected async embedder")

    legacy_embeddings = retriever.EMBEDDINGS
    monkeypatch.setattr(legacy_embeddings, "aembed_query", reject_legacy_embedding)
    monkeypatch.setattr(requests.sessions.Session, "post", reject_sync_http)
    monkeypatch.setattr(
        retriever,
        "_get_chroma_vectorstore",
        lambda: SimpleNamespace(as_retriever=lambda **kwargs: _EmptyRetriever()),
    )
    monkeypatch.setattr(retriever, "get_bm25_retriever", lambda **kwargs: _EmptyRetriever())
    rest_vectors: list[list[float]] = []
    generated: list[str] = []

    def chroma_response(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.host == "chroma.offline.invalid"
        vector = json.loads(request.content)["query_embeddings"][0]
        rest_vectors.append(vector)
        assert vector == _VECTOR
        return httpx.Response(
            200,
            json={
                "ids": [["chroma-second"]],
                "documents": [[_BODY]],
                "metadatas": [
                    [{"chunk_id": _CHUNK_ID, "source": _SOURCE, "doc_type": "normativa"}]
                ],
                "distances": [[0.1]],
            },
        )

    async with (
        httpx.AsyncClient(transport=transport, timeout=30.0) as ollama_client,
        httpx.AsyncClient(transport=httpx.MockTransport(chroma_response)) as chroma_client,
    ):
        # Exercise the product dependency injection without replacing EMBEDDINGS.
        query = ChromaQuery(chroma_client, "http://chroma.offline.invalid/query", 1.0)
        hybrid = retriever.get_ensemble_retriever(
            k=1,
            k_candidates=1,
            chroma_query=query,
            query_embedder=partial(candidate.embed_query_async, ollama_client),
        )
        assert retriever.EMBEDDINGS is legacy_embeddings
        send_started = asyncio.Event() if interruption == "disconnect_progress_send" else None

        async def retrieve(state: AgentState) -> dict:
            if send_started is not None and state["question"] == _FIRST:
                get_stream_writer()({"type": "status", "stage": "retrieving"})
            return {"sources": await hybrid.ainvoke(state["question"]), "query_route": "in_scope"}

        async def answer(state: AgentState) -> dict:
            generated.append(state["question"])
            assert len(state["sources"]) == 1
            return {"messages": [AIMessage(content=_ANSWER)]}

        graph = (
            StateGraph(AgentState)
            .add_node("retrieve", retrieve)
            .add_node("answer", answer)
            .add_edge(START, "retrieve")
            .add_edge("retrieve", "answer")
            .add_edge("answer", END)
            .compile(checkpointer=MemorySaver())
        )
        monkeypatch.setattr(main, "_graph", graph)
        disconnected = asyncio.Event()
        response = None
        second = None
        if endpoint == "json":
            first = asyncio.create_task(_call(endpoint, _FIRST))
        else:
            response = await main.query_stream(QueryRequest(question=_FIRST), _USER)
            first = asyncio.create_task(_read_sse(response, disconnected, send_started))
        try:
            await asyncio.wait_for(network.first.reading.wait(), 2)
            if send_started is not None:
                await asyncio.wait_for(send_started.wait(), 2)
            assert network.first.payload() == {"model": "fixture-embedding-model", "prompt": _FIRST}
            assert limiter.in_flight == tracker.count == 1
            assert len(locks._entries) == 1 and graph.checkpointer.storage
            if interruption == "cancel":
                first.cancel()
            elif interruption.startswith("disconnect"):
                disconnected.set()
            elif interruption == "read_timeout":
                # The public HTTP transport maps this to HTTPX ReadTimeout.
                # It must retain the legacy API error, not become a 504.
                network.first.fail_read.set()
            await _observe(first)
            if interruption == "cancel":
                assert first.cancelled()
            elif interruption.startswith("disconnect"):
                assert first.result() == []
            elif endpoint == "json":
                error = first.exception()
                expected_status = 500 if interruption == "read_timeout" else 504
                assert isinstance(error, HTTPException) and error.status_code == expected_status
            else:
                (frame,) = first.result()
                event = json.loads(frame)
                assert event["type"] == "error"
                if interruption == "read_timeout":
                    assert event["detail"] == "No fue posible procesar la consulta."

            # The response is still incomplete; observing closure must not rescue it.
            await asyncio.wait_for(network.first.closed.wait(), 2)
            assert network.first.stall and not network.first.response
            assert limiter.in_flight == tracker.count == 0 and not locks._entries
            assert not graph.checkpointer.storage and not rest_vectors and not generated

            monkeypatch.setattr(main, "QUERY_TOTAL_TIMEOUT_SECONDS", 3.0)
            monkeypatch.setattr(main, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", 3.0)
            second = asyncio.create_task(_call(endpoint, _SECOND))
            await _observe(second)
            _verify_answer(second.result())
            assert network.connections == 2 and network.second.reading.is_set()
            assert network.second.payload() == {
                "model": "fixture-embedding-model",
                "prompt": _SECOND,
            }
            assert rest_vectors == [_VECTOR] and generated == [_SECOND]
            assert limiter.in_flight == tracker.count == 0 and not locks._entries
            assert not graph.checkpointer.storage
            await asyncio.sleep(0)
            assert rest_vectors == [_VECTOR] and generated == [_SECOND]
            assert retriever.EMBEDDINGS is legacy_embeddings
        finally:
            tasks = [task for task in (first, second) if task is not None]
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if response is not None:
                await response.body_iterator.aclose()
