from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from chromadb.api.fastapi import FastAPI
from chromadb.api.models.Collection import Collection
from chromadb.types import Collection as CollectionModel
from langchain_chroma import Chroma
from langchain_core.documents import Document

from rag.core.chroma_query import ChromaQueryTimeout, query_chroma
from rag.core.retriever import HybridEnsembleRetriever

_BASE_URL = "http://chroma.invalid:8000/api/v2"
_COLLECTION_ID = UUID("11111111-2222-4333-8444-555555555555")
_QUERY_URL = f"{_BASE_URL}/tenants/test-tenant/databases/test-db/collections/{_COLLECTION_ID}/query"
_EMBEDDING = [0.1, -0.123456789, 0.987654321]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "where", [None, {"doc_type": "normativa"}, {"doc_type": {"$in": ["a", "b"]}}]
)
async def test_rest_query_matches_sdk_request_and_documents(where):
    requests: list[tuple[str, str, dict]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url), json.loads(request.content)))
        return httpx.Response(
            200,
            json={
                "ids": [["first", "missing", "blank", "untyped"]],
                "documents": [["Pasaje", None, "", "Sin metadata"]],
                "metadatas": [
                    [{"chunk_id": "different", "tags": "[1]", "year": 2020}, {}, {}, None]
                ],
                "distances": [[0.7, 0.01, 0.1, 0.2]],
            },
        )

    # Use the actual SDK request and mapping against the same captured response.
    with httpx.Client(transport=httpx.MockTransport(respond)) as sdk_http:
        backend = object.__new__(FastAPI)
        backend._api_url = _BASE_URL
        backend._session = sdk_http
        model = CollectionModel(
            id=_COLLECTION_ID,
            name="test-collection",
            tenant="test-tenant",
            database="test-db",
            configuration_json={},
            serialized_schema=None,
            metadata=None,
            dimension=3,
        )
        collection = Collection(backend, model, embedding_function=None)
        store = Chroma(
            client=SimpleNamespace(get_collection=lambda name: collection),
            collection_name=model.name,
            embedding_function=SimpleNamespace(embed_query=lambda query: _EMBEDDING),
            create_collection_if_not_exists=False,
        )
        expected = store.similarity_search("Consulta", k=8, filter=where)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        actual = await query_chroma(client, _QUERY_URL, _EMBEDDING, k=8, where=where, timeout=1)

    assert requests[0] == requests[1]
    assert requests[1] == (
        "POST",
        _QUERY_URL,
        {
            "ids": None,
            "query_embeddings": [[0.10000000149011612, -0.12345679104328156, 0.9876543283462524]],
            "n_results": 8,
            "where": where,
            "where_document": None,
            "include": ["metadatas", "documents", "distances"],
        },
    )
    assert actual == expected
    assert [document.id for document in actual] == ["first", "blank", "untyped"]
    bm25 = [Document(id="lexical", page_content="Versión BM25", metadata={"chunk_id": "different"})]
    hybrid = HybridEnsembleRetriever(retrievers=[store.as_retriever()] * 2, weights=[0.3, 0.7])
    ranking = hybrid._fuse([bm25, actual])
    assert ranking == hybrid._fuse([bm25, expected])
    assert [document.id for document in ranking] == ["lexical", "untyped"]


@pytest.mark.anyio
async def test_rest_query_returns_empty_list_for_valid_empty_result():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert await query_chroma(client, _QUERY_URL, _EMBEDDING, k=8, where=None, timeout=1) == []


@pytest.mark.anyio
async def test_rest_query_maps_httpx_timeout_only():
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("demora simulada", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(ChromaQueryTimeout, match="superó el tiempo"):
            await query_chroma(client, _QUERY_URL, _EMBEDDING, k=8, where=None, timeout=1)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(503, text="fallo simulado"), httpx.HTTPStatusError),
        (httpx.Response(200, text="JSON inválido"), json.JSONDecodeError),
    ],
)
async def test_rest_query_preserves_non_timeout_errors(response, error):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)) as client:
        with pytest.raises(error):
            await query_chroma(client, _QUERY_URL, _EMBEDDING, k=8, where=None, timeout=1)
