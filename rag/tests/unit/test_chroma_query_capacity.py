"""El mismo pool HTTP/1.1 recupera su única conexión tras interrumpir Chroma."""

from __future__ import annotations

import asyncio
import json

import httpcore
import httpx
import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from starlette.responses import StreamingResponse
from starlette.types import Message

from rag.api import main
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.schemas import QueryRequest, QueryResponse
from rag.core.agent import AgentState
from rag.core.chroma_query import ChromaQuery

_USER = {"sub": "pool-offline"}
_QUERY_URL = "http://chroma.invalid/api/v2/tenants/demo/databases/demo/collections/id/query"
_ANSWER = "Respuesta completa [doc1]."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Wire(httpcore.AsyncNetworkStream):
    def __init__(self, response: bytes, *, stall: bool = False) -> None:
        self.response = response
        self.stall = stall
        self.reading = asyncio.Event()
        self.closed = asyncio.Event()

    async def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        if not self.stall or not self.response:
            self.reading.set()
        if self.stall and not self.response:
            await asyncio.Future()
            raise AssertionError("La primera conexión nunca termina de responder")
        data, self.response = self.response[:max_bytes], self.response[max_bytes:]
        return data

    async def write(self, buffer: bytes, timeout: float | None = None) -> None:
        pass

    async def aclose(self) -> None:
        self.closed.set()


class _Network(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.first = _Wire(b"HTTP/1.1 200 OK\r\nContent-Length: 30\r\n\r\n{", stall=True)
        body = json.dumps(
            {
                "ids": [["chroma-id"]],
                "documents": [["Pasaje recuperado"]],
                "metadatas": [[{"chunk_id": "fragmento", "source": "norma.pdf"}]],
                "distances": [[0.25]],
            }
        ).encode()
        self.second = _Wire(
            f"HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
        )
        self.connections = 0

    async def connect_tcp(self, host: str, port: int, **kwargs: object) -> _Wire:
        assert (host, port) == ("chroma.invalid", 80)
        self.connections += 1
        assert self.connections <= 2
        return self.first if self.connections == 1 else self.second


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


async def _call(endpoint: str, disconnected: asyncio.Event) -> QueryResponse | list[str]:
    request = QueryRequest(question="Consulta de prueba")
    if endpoint == "json":
        return await main.query(request, _USER)
    return await _read_sse(await main.query_stream(request, _USER), disconnected)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("endpoint", "interruption"),
    [
        ("json", "timeout"),
        ("sse", "timeout"),
        ("json", "cancel"),
        ("sse", "cancel"),
        ("sse", "cancel_progress_send"),
    ],
)
async def test_chroma_interruption_releases_http_pool_and_api_resources(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, interruption: str
) -> None:
    network = _Network()
    transport = httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=1), trust_env=False)
    # Sustituimos solo la red. HTTPX y el pool HTTP/1.1 real hacen el cierre.
    transport._pool._network_backend = network
    limiter = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    locks = ConversationLockRegistry()
    monkeypatch.setattr(main, "backpressure", limiter)
    monkeypatch.setattr(main, "CONVERSATION_LOCKS", locks)
    monkeypatch.setattr(main, "QUERY_TOTAL_TIMEOUT_SECONDS", 10.0)
    monkeypatch.setattr(main, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", 10.0)

    async with httpx.AsyncClient(transport=transport, timeout=10.0) as client:
        chroma = ChromaQuery(client, _QUERY_URL, 0.3 if interruption == "timeout" else 8.0)
        send_started = asyncio.Event() if interruption == "cancel_progress_send" else None

        async def search(state: AgentState) -> dict:
            if send_started is not None and not send_started.is_set():
                get_stream_writer()({"type": "status", "stage": "retrieving"})
            docs = await chroma.search([0.1, 0.2], k=4, where=None)
            return {"messages": [AIMessage(content=_ANSWER)], "sources": docs}

        graph = (
            StateGraph(AgentState)
            .add_node("search", search)
            .add_edge(START, "search")
            .add_edge("search", END)
            .compile(checkpointer=MemorySaver())
        )
        monkeypatch.setattr(main, "_graph", graph)
        disconnected = asyncio.Event()
        response = None
        if send_started is None:
            first = asyncio.create_task(_call(endpoint, disconnected))
        else:
            # Conservar la respuesta impide que el GC cierre el iterador por la API.
            response = await main.query_stream(QueryRequest(question="Consulta de prueba"), _USER)
            first = asyncio.create_task(_read_sse(response, disconnected, send_started))
        try:
            await asyncio.wait_for(network.first.reading.wait(), 2)
            if send_started is not None:
                await asyncio.wait_for(send_started.wait(), 2)
            assert limiter.in_flight == 1
            assert len(locks._entries) == 1
            assert graph.checkpointer.storage

            if interruption == "cancel" and endpoint == "json":
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(first, 2)
            elif interruption in ("cancel", "cancel_progress_send"):
                disconnected.set()
                assert await asyncio.wait_for(first, 2) == []
            elif endpoint == "json":
                with pytest.raises(HTTPException) as error:
                    await asyncio.wait_for(first, 2)
                assert error.value.status_code == 504
            else:
                result = await asyncio.wait_for(first, 2)
                assert isinstance(result, list)
                (event,) = [json.loads(frame) for frame in result]
                assert event["type"] == "error"
                assert event["detail"]

            await asyncio.wait_for(network.first.closed.wait(), 2)
            assert limiter.in_flight == 0
            assert locks._entries == {}
            assert main.ACTIVE_QUERIES.count == 0
            assert not graph.checkpointer.storage

            # La primera lectura nunca recibe el resto del cuerpo. La nueva consulta debe
            # llegar a Chroma con el mismo cliente, pool y límite de un cupo.
            second = await asyncio.wait_for(_call(endpoint, asyncio.Event()), 2)
            assert network.connections == 2
            assert network.second.reading.is_set()
            if isinstance(second, QueryResponse):
                assert second.answer == _ANSWER
                sources = [group.model_dump() for group in second.sources]
            else:
                token, sources_event, done = second
                assert json.loads(token) == {"type": "token", "content": _ANSWER}
                assert done == "[DONE]"
                sources = json.loads(sources_event)["sources"]
            assert sources[0]["fragments"][0]["content"] == "Pasaje recuperado"
            assert limiter.in_flight == 0
            assert locks._entries == {}
            assert not graph.checkpointer.storage
        finally:
            if not first.done():
                first.cancel()
            await asyncio.gather(first, return_exceptions=True)
            if response is not None:
                await response.body_iterator.aclose()
