"""Filtro conservador post-fusión: descarta candidatos sin contenido
alfanumérico (basura estructural) sin tocar embeddings, BM25, pesos, k ni
el índice — opera solo sobre el resultado ya fusionado por RRF."""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag.core.retriever import HybridEnsembleRetriever, _has_retrievable_content


class _StaticRetriever(BaseRetriever):
    docs: list[Document]

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del query, run_manager
        return self.docs


def _doc(identifier: str, text: str) -> Document:
    return Document(page_content=text, metadata={"chunk_id": identifier})


def test_has_retrievable_content_rejects_purely_structural_text() -> None:
    assert _has_retrievable_content("---") is False
    assert _has_retrievable_content("   ") is False
    assert _has_retrievable_content("...___...") is False
    assert _has_retrievable_content("") is False


def test_has_retrievable_content_keeps_short_valid_legal_text() -> None:
    assert _has_retrievable_content("Prohíbese pescar.") is True
    assert _has_retrievable_content("Art. 4") is True


def test_structural_candidates_are_skipped_and_backfilled() -> None:
    """Un candidato puramente estructural mejor rankeado se descarta y se
    rellena con el siguiente candidato válido, sin reducir max_results."""
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(
                docs=[
                    _doc("junk-1", "---"),
                    _doc("valid-1", "Prohíbese pescar en la zona de playa."),
                    _doc("valid-2", "Artículo 4: definiciones."),
                ]
            ),
        ],
        weights=[1.0],
        max_results=2,
    )
    results = retriever.invoke("consulta")
    assert [d.metadata["chunk_id"] for d in results] == ["valid-1", "valid-2"]


def test_relative_order_among_valid_candidates_is_preserved() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(
                docs=[
                    _doc("valid-1", "Primero: contenido legítimo."),
                    _doc("junk", "____"),
                    _doc("valid-2", "Segundo: contenido legítimo."),
                    _doc("valid-3", "Tercero: contenido legítimo."),
                ]
            ),
        ],
        weights=[1.0],
        max_results=3,
    )
    results = retriever.invoke("consulta")
    assert [d.metadata["chunk_id"] for d in results] == ["valid-1", "valid-2", "valid-3"]


def test_never_exceeds_max_results_even_with_many_valid_candidates() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(docs=[_doc(f"v{i}", f"contenido válido {i}") for i in range(10)]),
        ],
        weights=[1.0],
        max_results=3,
    )
    results = retriever.invoke("consulta")
    assert len(results) == 3


def test_all_structural_input_yields_empty_result() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(
                docs=[_doc("junk-1", "---"), _doc("junk-2", "___"), _doc("junk-3", "   ")]
            ),
        ],
        weights=[1.0],
        max_results=4,
    )
    results = retriever.invoke("consulta")
    assert results == []
