"""Equivalencia del adaptador BM25 interno con el ranking histórico."""

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from rag.core.retriever import BM25Retriever, _tokenize_bm25


def test_internal_bm25_preserves_tokenization_and_ranking() -> None:
    docs = [
        Document(page_content="acceso público a la playa", metadata={"id": "1"}),
        Document(page_content="permiso de pesca artesanal", metadata={"id": "2"}),
        Document(page_content="restricción de acceso costero", metadata={"id": "3"}),
    ]
    vectorizer = BM25Okapi([_tokenize_bm25(doc.page_content) for doc in docs])
    retriever = BM25Retriever(vectorizer=vectorizer, docs=docs, k=2)

    expected = vectorizer.get_top_n("acceso playa".split(), docs, n=2)
    result = retriever.invoke("acceso playa")

    assert result == expected
    assert [doc.metadata["id"] for doc in result] == ["1", "3"]
