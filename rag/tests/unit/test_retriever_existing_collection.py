"""The query retriever may open an existing collection, but never create one."""

from unittest.mock import Mock

import pytest
from chromadb.errors import NotFoundError

from rag.core import retriever


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    client = Mock(spec=["get_collection", "get_or_create_collection"])
    client.get_or_create_collection.side_effect = AssertionError(
        "Query startup must not create a collection"
    )
    monkeypatch.setattr(retriever, "_chroma_client", client)
    monkeypatch.setattr(retriever, "_chroma_vectorstore", None)
    monkeypatch.setattr(retriever, "CHROMA_COLLECTION_NAME", "gold-a-test")
    monkeypatch.setattr(retriever, "EMBEDDINGS", Mock(spec=["embed_query", "embed_documents"]))
    return client


def test_existing_collection_is_opened_once_without_creating_or_embedding(client: Mock) -> None:
    expected = {"ids": ["chunk-1"], "documents": ["Texto"], "metadatas": [{"id": "chunk-1"}]}
    client.get_collection.return_value.get.return_value = expected

    vectorstore = retriever._get_chroma_vectorstore()

    assert retriever._get_chroma_vectorstore() is vectorstore
    assert vectorstore.embeddings is retriever.EMBEDDINGS
    assert vectorstore.get(include=["documents", "metadatas"]) == expected
    client.get_collection.assert_called_once_with(name="gold-a-test")
    client.get_or_create_collection.assert_not_called()
    retriever.EMBEDDINGS.embed_query.assert_not_called()
    retriever.EMBEDDINGS.embed_documents.assert_not_called()


def test_missing_collection_fails_without_creating_or_publishing_vectorstore(client: Mock) -> None:
    client.get_collection.side_effect = NotFoundError("Missing configured collection")

    with pytest.raises(NotFoundError, match="Missing configured collection"):
        retriever._get_chroma_vectorstore()

    assert retriever._chroma_vectorstore is None
    client.get_collection.assert_called_once_with(name="gold-a-test")
    client.get_or_create_collection.assert_not_called()
    retriever.EMBEDDINGS.embed_query.assert_not_called()
    retriever.EMBEDDINGS.embed_documents.assert_not_called()
