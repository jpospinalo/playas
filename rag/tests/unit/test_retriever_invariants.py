"""A1.6 — chequeos de invariantes internos del retriever híbrido.

Tres puntos donde una entrada estructuralmente inconsistente se aceptaba
antes en silencio, truncando datos sin ningún aviso:

  1. ``HybridEnsembleRetriever(retrievers=..., weights=...)`` con listas de
     longitud distinta: ``zip(all_results, self.weights, strict=False)`` en
     ``_fuse()`` truncaba a la más corta, descartando candidatos o pesos.
  2. ``HybridEnsembleRetriever._fuse()`` invocado directamente con
     ``all_results`` de longitud distinta a ``self.weights`` — el mismo
     problema, por si algún caller futuro invoca ``_fuse()`` sin pasar por
     el constructor (que ya lo habría rechazado).
  3. ``load_all_docs_from_chroma()``: ``ids``/``documents``/``metadatas`` son
     tres listas paralelas de la misma respuesta de Chroma;
     ``zip(..., strict=False)`` truncaba a la más corta ante una respuesta
     corrupta o parcial.

Ahora los tres casos fallan explícitamente en vez de truncar. Ninguna de
estas pruebas cambia el resultado de una configuración válida: la fusión RRF
sobre entradas consistentes debe seguir produciendo exactamente el mismo
ranking (formula, pesos, filtros, número de candidatos y orden intactos) —
ver ``test_hybrid_fusion_with_valid_config_ranks_identically_to_before``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

import rag.core.retriever as retriever_module
from rag.core.retriever import HybridEnsembleRetriever, load_all_docs_from_chroma


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


def _doc(identifier: str) -> Document:
    return Document(page_content=identifier, metadata={"chunk_id": identifier})


# ---------------------------------------------------------------------------
# 1. Construcción: número de retrievers debe coincidir con número de pesos
# ---------------------------------------------------------------------------


def test_construction_rejects_more_weights_than_retrievers() -> None:
    with pytest.raises(ValueError, match="retrievers.*no coincide.*pesos|no coincide"):
        HybridEnsembleRetriever(
            retrievers=[_StaticRetriever(docs=[])],
            weights=[0.5, 0.5],
        )


def test_construction_rejects_more_retrievers_than_weights() -> None:
    with pytest.raises(ValueError, match="no coincide"):
        HybridEnsembleRetriever(
            retrievers=[_StaticRetriever(docs=[]), _StaticRetriever(docs=[])],
            weights=[1.0],
        )


def test_construction_accepts_matching_counts_of_any_size() -> None:
    """No se limita a exactamente 2 — cualquier conteo igual es válido."""
    retriever = HybridEnsembleRetriever(
        retrievers=[_StaticRetriever(docs=[]) for _ in range(3)],
        weights=[0.2, 0.3, 0.5],
    )
    assert len(retriever.retrievers) == len(retriever.weights) == 3


# ---------------------------------------------------------------------------
# 2. _fuse(): all_results debe coincidir en longitud con self.weights
# ---------------------------------------------------------------------------


def test_fuse_rejects_all_results_shorter_than_weights() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[_StaticRetriever(docs=[]), _StaticRetriever(docs=[])],
        weights=[0.5, 0.5],
    )
    with pytest.raises(ValueError, match="no coincide"):
        retriever._fuse([[_doc("a")]])  # una sola lista, dos pesos


def test_fuse_rejects_all_results_longer_than_weights() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[_StaticRetriever(docs=[]), _StaticRetriever(docs=[])],
        weights=[0.5, 0.5],
    )
    with pytest.raises(ValueError, match="no coincide"):
        retriever._fuse([[_doc("a")], [_doc("b")], [_doc("c")]])


# ---------------------------------------------------------------------------
# Sin regresión: una configuración válida produce EXACTAMENTE el mismo
# ranking que antes de este chequeo (fórmula, pesos, filtro, candidatos y
# orden intactos).
# ---------------------------------------------------------------------------


def test_hybrid_fusion_with_valid_config_ranks_identically_to_before() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(docs=[_doc("a"), _doc("b"), _doc("c")]),
            _StaticRetriever(docs=[_doc("b"), _doc("d")]),
        ],
        weights=[0.3, 0.7],
        c=160,
        max_results=4,
    )
    result_sync = retriever.invoke("consulta")
    result_ids_sync = [d.metadata["chunk_id"] for d in result_sync]

    # Cálculo manual de RRF ponderado con c=160, para el mismo par de listas,
    # como referencia independiente de la implementación.
    def _rrf_score(rank: int, weight: float, c: int = 160) -> float:
        return weight / (rank + c)

    expected_scores = {
        "a": _rrf_score(1, 0.3),
        "b": _rrf_score(2, 0.3) + _rrf_score(1, 0.7),
        "c": _rrf_score(3, 0.3),
        "d": _rrf_score(2, 0.7),
    }
    expected_order = sorted(expected_scores, key=lambda k: expected_scores[k], reverse=True)

    assert result_ids_sync == expected_order


@pytest.mark.anyio
async def test_hybrid_fusion_async_matches_sync_for_valid_config() -> None:
    def _make_retriever() -> HybridEnsembleRetriever:
        return HybridEnsembleRetriever(
            retrievers=[
                _StaticRetriever(docs=[_doc("a"), _doc("b"), _doc("c")]),
                _StaticRetriever(docs=[_doc("b"), _doc("d")]),
            ],
            weights=[0.3, 0.7],
        )

    sync_result = _make_retriever().invoke("consulta")
    async_result = await _make_retriever().ainvoke("consulta")

    assert [d.metadata["chunk_id"] for d in sync_result] == [
        d.metadata["chunk_id"] for d in async_result
    ]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# 3. load_all_docs_from_chroma(): ids/documents/metadatas deben coincidir
# ---------------------------------------------------------------------------


def _mock_chroma_client(get_return: dict[str, Any]) -> MagicMock:
    collection = MagicMock()
    collection.get.return_value = get_return
    client = MagicMock()
    client.get_collection.return_value = collection
    return client


def test_load_docs_raises_when_documents_shorter_than_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "_get_chroma_client",
        lambda: _mock_chroma_client(
            {
                "ids": ["1", "2", "3"],
                "documents": ["texto uno", "texto dos"],
                "metadatas": [{}, {}, {}],
            }
        ),
    )
    with pytest.raises(RuntimeError, match="[Ll]ongitudes inconsistentes"):
        load_all_docs_from_chroma()


def test_load_docs_raises_when_metadatas_shorter_than_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "_get_chroma_client",
        lambda: _mock_chroma_client(
            {"ids": ["1", "2"], "documents": ["texto uno", "texto dos"], "metadatas": [{}]}
        ),
    )
    with pytest.raises(RuntimeError, match="[Ll]ongitudes inconsistentes"):
        load_all_docs_from_chroma()


def test_load_docs_error_message_reports_the_three_lengths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        retriever_module,
        "_get_chroma_client",
        lambda: _mock_chroma_client(
            {"ids": ["1", "2", "3"], "documents": ["a"], "metadatas": [{}, {}]}
        ),
    )
    with pytest.raises(RuntimeError, match=r"ids=3.*documents=1.*metadatas=2"):
        load_all_docs_from_chroma()


def test_load_docs_succeeds_with_consistent_lengths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        retriever_module,
        "_get_chroma_client",
        lambda: _mock_chroma_client(
            {
                "ids": ["1", "2"],
                "documents": ["acceso a la playa", "permiso de pesca"],
                "metadatas": [{"doc_type": "normativa"}, {"doc_type": "jurisprudencia"}],
            }
        ),
    )

    docs = load_all_docs_from_chroma()

    assert [d.page_content for d in docs] == ["acceso a la playa", "permiso de pesca"]
    assert docs[0].metadata["id"] == "1"
    assert docs[1].metadata["doc_type"] == "jurisprudencia"


def test_load_docs_succeeds_with_empty_consistent_lengths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """0 == 0 == 0 es consistente — colección vacía, no un error estructural."""
    monkeypatch.setattr(
        retriever_module,
        "_get_chroma_client",
        lambda: _mock_chroma_client({"ids": [], "documents": [], "metadatas": []}),
    )

    assert load_all_docs_from_chroma() == []


def test_load_docs_still_skips_empty_text_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Comportamiento preexistente (documentos con texto vacío se descartan)
    no cambia por el nuevo chequeo de longitudes."""
    monkeypatch.setattr(
        retriever_module,
        "_get_chroma_client",
        lambda: _mock_chroma_client(
            {
                "ids": ["1", "2"],
                "documents": ["", "texto real"],
                "metadatas": [{}, {}],
            }
        ),
    )

    docs = load_all_docs_from_chroma()

    assert len(docs) == 1
    assert docs[0].page_content == "texto real"
