"""Protocol parity between the sync client and async helper in the same package."""

from __future__ import annotations

import json
from unittest.mock import Mock

import httpx
import pytest
import requests
from requests.adapters import BaseAdapter

from rag.core import embeddings as candidate

URL = "http://ollama.offline.invalid/api/embeddings"
MODEL = "fixture-embedding-model"
TEXT = "Texto sintético de consulta."


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    monkeypatch.setattr(candidate, "OLLAMA_BASE_URL", URL.removesuffix("/api/embeddings"))
    monkeypatch.setattr(candidate, "OLLAMA_EMBEDDING_MODEL", MODEL)


def response_for_sync(body: bytes, status: int = 200):
    response = requests.Response()
    response.status_code = status
    response.url = URL
    response.encoding = "utf-8"
    response._content = body
    return response


def call_sync(monkeypatch, body: bytes, status: int = 200):
    post = Mock(return_value=response_for_sync(body, status))
    with monkeypatch.context() as patcher:
        patcher.setattr(requests.Session, "post", post)
        client = candidate.OllamaEmbeddingClient()
        try:
            result = client.embed_one(TEXT)
            post.assert_called_once_with(URL, json={"model": MODEL, "prompt": TEXT}, timeout=30)
            return result
        finally:
            client.close()


@pytest.mark.anyio
@pytest.mark.parametrize("vector", [[1, 2.5], [True, False]])
async def test_valid_vector_payload_model_and_io_timeouts_match(monkeypatch, vector):
    body = json.dumps({"embedding": vector}).encode()
    sync_vector = call_sync(monkeypatch, body)
    observed = []

    def handler(request):
        observed.append(request)
        assert str(request.url) == URL and request.method == "POST"
        assert json.loads(request.content) == {"model": MODEL, "prompt": TEXT}
        assert request.extensions["timeout"] == dict.fromkeys(
            ("connect", "read", "write", "pool"), 30
        )
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await candidate.embed_query_async(client, TEXT)
    assert result == sync_vector == [float(value) for value in vector]
    assert len(observed) == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "data",
    [
        {},
        {"embedding": None},
        {"embedding": []},
        {"embedding": "1,2"},
        {"embedding": {"x": 1}},
        {"embedding": [1, "bad"]},
        [],
    ],
)
async def test_invalid_vector_preserves_legacy_error(monkeypatch, data):
    body = json.dumps(data).encode()
    with pytest.raises(RuntimeError) as old:
        call_sync(monkeypatch, body)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(RuntimeError) as new:
            await candidate.embed_query_async(client, TEXT)
    assert str(new.value) == str(old.value)


@pytest.mark.anyio
async def test_invalid_json_preserves_legacy_error(monkeypatch):
    body = b"{"
    with pytest.raises(RuntimeError) as old:
        call_sync(monkeypatch, body)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    ) as client:
        with pytest.raises(RuntimeError) as new:
            await candidate.embed_query_async(client, TEXT)
    assert str(new.value) == str(old.value)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [400, 503])
async def test_http_error_remains_an_error_without_timeout_conversion(monkeypatch, status):
    body = b'{"embedding":[1]}'
    with pytest.raises(requests.HTTPError):
        call_sync(monkeypatch, body, status)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body))
    ) as client:
        with pytest.raises(httpx.HTTPStatusError) as error:
            await candidate.embed_query_async(client, TEXT)
    assert error.value.response.status_code == status
    assert not isinstance(error.value, TimeoutError)


@pytest.mark.anyio
@pytest.mark.parametrize("status", [302, 307])
async def test_final_redirect_without_location_is_not_a_new_http_error(monkeypatch, status):
    body = b'{"embedding":[1,2]}'
    expected = call_sync(monkeypatch, body, status)
    async with httpx.AsyncClient(
        follow_redirects=True,
        transport=httpx.MockTransport(lambda request: httpx.Response(status, content=body)),
    ) as client:
        assert await candidate.embed_query_async(client, TEXT) == expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("old_error", "new_error"),
    [
        (requests.ConnectionError, httpx.ConnectError),
        (requests.ConnectTimeout, httpx.ConnectTimeout),
    ],
)
async def test_connection_failure_preserves_the_legacy_public_error(
    monkeypatch, old_error, new_error
):
    with monkeypatch.context() as patcher:
        patcher.setattr(requests.Session, "post", Mock(side_effect=old_error("offline")))
        client = candidate.OllamaEmbeddingClient()
        try:
            with pytest.raises(RuntimeError) as old:
                client.embed_one(TEXT)
        finally:
            client.close()

    def handler(request):
        raise new_error("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError) as new:
            await candidate.embed_query_async(client, TEXT)
    assert str(new.value) == str(old.value)
    assert isinstance(new.value.__cause__, new_error)


@pytest.mark.anyio
async def test_read_timeout_does_not_become_the_api_timeout(monkeypatch):
    with monkeypatch.context() as patcher:
        patcher.setattr(requests.Session, "post", Mock(side_effect=requests.ReadTimeout("offline")))
        client = candidate.OllamaEmbeddingClient()
        try:
            with pytest.raises(requests.ReadTimeout) as old:
                client.embed_one(TEXT)
        finally:
            client.close()

    def handler(request):
        raise httpx.ReadTimeout("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ReadTimeout) as new:
            await candidate.embed_query_async(client, TEXT)
    assert not isinstance(old.value, TimeoutError)
    assert not isinstance(new.value, TimeoutError)


def mock_context_clients(monkeypatch, handler):
    original_client = httpx.AsyncClient
    clients = []

    def factory(**kwargs):
        assert kwargs == {"timeout": 30, "follow_redirects": True}
        client = original_client(**kwargs, transport=httpx.MockTransport(handler), trust_env=False)
        clients.append(client)
        return client

    monkeypatch.setattr(candidate.httpx, "AsyncClient", factory)
    return clients


@pytest.mark.anyio
async def test_owned_client_is_reused_inside_context_and_recreated_after_close(monkeypatch):
    requests_seen = []

    def handler(request):
        requests_seen.append(request)
        assert "authorization" not in request.headers
        assert "x-chroma-token" not in request.headers
        return httpx.Response(200, json={"embedding": [1.0]})

    clients = mock_context_clients(monkeypatch, handler)
    for _ in range(2):
        async with candidate.open_query_embeddings() as embed:
            assert await embed(TEXT) == [1.0]
            assert await embed(TEXT) == [1.0]
            assert not clients[-1].is_closed
        assert clients[-1].is_closed
    assert len(clients) == 2 and clients[0] is not clients[1]
    assert len(requests_seen) == 4


@pytest.mark.anyio
async def test_owned_client_closes_when_the_consumer_fails(monkeypatch):
    clients = mock_context_clients(
        monkeypatch, lambda request: httpx.Response(200, json={"embedding": [1]})
    )
    with pytest.raises(RuntimeError, match="consumer failure"):
        async with candidate.open_query_embeddings():
            raise RuntimeError("consumer failure")
    assert len(clients) == 1 and clients[0].is_closed


@pytest.mark.anyio
@pytest.mark.parametrize("status", [302, 307])
async def test_owned_client_follows_redirects_like_requests(monkeypatch, status):
    legacy_requests = []
    async_requests = []

    class RedirectAdapter(BaseAdapter):
        def send(self, request, **kwargs):
            legacy_requests.append((request.method, request.url))
            response = response_for_sync(b'{"embedding":[1]}')
            response.request = request
            response.url = request.url
            if request.url == URL:
                response.status_code = status
                response.headers["Location"] = "/redirected"
            return response

        def close(self):
            pass

    original_session = requests.Session

    def session_factory():
        session = original_session()
        session.trust_env = False
        session.mount("http://ollama.offline.invalid/", RedirectAdapter())
        return session

    with monkeypatch.context() as patcher:
        patcher.setattr(requests, "Session", session_factory)
        client = candidate.OllamaEmbeddingClient()
        try:
            expected = client.embed_one(TEXT)
        finally:
            client.close()

    def handler(request):
        async_requests.append((request.method, str(request.url)))
        if str(request.url) == URL:
            return httpx.Response(status, headers={"Location": "/redirected"})
        return httpx.Response(200, json={"embedding": [1]})

    clients = mock_context_clients(monkeypatch, handler)
    async with candidate.open_query_embeddings() as embed:
        assert await embed(TEXT) == expected
    assert async_requests == legacy_requests
    assert len(clients) == 1 and clients[0].is_closed
