"""Asynchronous REST v2 query for an already resolved Chroma collection."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from chromadb.api.types import (
    IncludeMetadataDocumentsDistances,
    Where,
    convert_np_embeddings_to_list,
    deserialize_metadata,
    normalize_embeddings,
    validate_embeddings,
)
from langchain_core.documents import Document


class ChromaQueryTimeout(TimeoutError):
    """The local Chroma query exceeded its HTTP deadline."""


@dataclass(frozen=True, slots=True)
class ChromaQuery:
    """Bind the client, collection endpoint and deadline for the API graph."""

    client: httpx.AsyncClient
    collection_url: str
    timeout: float

    async def search(
        self, embedding: list[float], *, k: int, where: Where | None
    ) -> list[Document]:
        return await query_chroma(
            self.client, self.collection_url, embedding, k=k, where=where, timeout=self.timeout
        )


async def query_chroma(
    client: httpx.AsyncClient,
    collection_url: str,
    embedding: list[float],
    *,
    k: int,
    where: Where | None,
    timeout: float,
) -> list[Document]:
    """Query the collection endpoint using the caller's async HTTP client."""
    # The synchronous SDK converts Python vectors to float32 before serialization.
    embeddings = normalize_embeddings(embedding)
    assert embeddings is not None
    payload = {
        "ids": None,
        "query_embeddings": convert_np_embeddings_to_list(validate_embeddings(embeddings)),
        "n_results": k,
        "where": where,
        "where_document": None,
        "include": IncludeMetadataDocumentsDistances,
    }
    try:
        async with asyncio.timeout(timeout):
            response = await client.post(collection_url, json=payload)
    except (TimeoutError, httpx.TimeoutException) as exc:
        raise ChromaQueryTimeout("La consulta a Chroma superó el tiempo máximo permitido.") from exc

    response.raise_for_status()
    results = response.json()
    # LangChain keeps the backend rank and skips only rows with a null body here.
    return [
        Document(page_content=text, id=ident, metadata=deserialize_metadata(metadata) or {})
        for text, metadata, ident, _ in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["ids"][0],
            results["distances"][0],
            strict=False,
        )
        if text is not None
    ]
