# tests/unit/test_retriever_balance.py

from __future__ import annotations

from langchain_core.documents import Document

from rag.core.retriever import balance_by_doc_type


def _doc(idx: int, doc_type: str) -> Document:
    return Document(
        page_content=f"contenido-{idx}",
        metadata={"chunk_id": str(idx), "doc_type": doc_type},
    )


def test_quota_pulls_normativa_from_the_bottom() -> None:
    # Lista ordenada por relevancia: 4 jurisprudencia primero, normativa al fondo.
    docs = [
        _doc(0, "jurisprudencia"),
        _doc(1, "jurisprudencia"),
        _doc(2, "jurisprudencia"),
        _doc(3, "jurisprudencia"),
        _doc(4, "normativa"),
    ]

    result = balance_by_doc_type(docs, k=3, min_per_type={"normativa": 1})

    assert len(result) == 3
    doc_types = [d.metadata["doc_type"] for d in result]
    assert doc_types.count("normativa") >= 1
    # La normativa de menor rank entra; debe ser el chunk 4.
    assert any(d.metadata["chunk_id"] == "4" for d in result)


def test_quota_keeps_best_ranked_of_other_types() -> None:
    docs = [
        _doc(0, "jurisprudencia"),
        _doc(1, "jurisprudencia"),
        _doc(2, "normativa"),
    ]

    result = balance_by_doc_type(docs, k=2, min_per_type={"normativa": 1})

    assert len(result) == 2
    ids = {d.metadata["chunk_id"] for d in result}
    # Cuota de normativa (chunk 2) + mejor jurisprudencia (chunk 0).
    assert ids == {"0", "2"}


def test_no_min_per_type_returns_top_k_unchanged() -> None:
    docs = [_doc(i, "jurisprudencia") for i in range(5)]

    result = balance_by_doc_type(docs, k=3, min_per_type=None)

    assert result == docs[:3]
    assert [d.metadata["chunk_id"] for d in result] == ["0", "1", "2"]


def test_quota_ignored_when_type_absent() -> None:
    docs = [_doc(i, "jurisprudencia") for i in range(4)]

    result = balance_by_doc_type(docs, k=2, min_per_type={"normativa": 2})

    # No hay normativa disponible: simplemente devuelve top-k de lo que hay.
    assert len(result) == 2
    assert [d.metadata["chunk_id"] for d in result] == ["0", "1"]
