"""Multiconsulta en ``HybridEnsembleRetriever.afuse_queries``.

Estos tests usan recuperadores falsos en memoria (sin Chroma, sin Ollama y
sin red) y fijan la configuración validada offline: RRF con ``c=2``, peso
léxico 0.8 y peso vectorial 0.2. El caso central es el que fallaba con
``c=160``: un documento que BM25 pone en el puesto 1 debe poder competir con
candidatos vectoriales de ranks bajos, y además debe recuperarse por separado
con cada reformulación de la consulta.
"""

from __future__ import annotations

import inspect
from collections import Counter

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag.core.retriever import (
    BM25_WEIGHT,
    RRF_C,
    VECTOR_WEIGHT,
    HybridEnsembleRetriever,
    get_ensemble_retriever,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _doc(identifier: str, text: str | None = None) -> Document:
    return Document(
        page_content=identifier if text is None else text,
        metadata={"chunk_id": identifier},
    )


class _RecordingRetriever(BaseRetriever):
    """Devuelve una lista fija por consulta y registra las consultas recibidas."""

    docs_by_query: dict[str, list[Document]] = Field(default_factory=dict)
    default_docs: list[Document] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del run_manager
        self.calls.append(query)
        return list(self.docs_by_query.get(query, self.default_docs))


def _ids(docs: list[Document]) -> list[str]:
    return [str(d.metadata["chunk_id"]) for d in docs]


def _make(docs_by_query: dict[str, list[Document]], *, max_results: int = 4):
    lexical = _RecordingRetriever(docs_by_query=docs_by_query)
    vector = _RecordingRetriever(docs_by_query=docs_by_query)
    retriever = HybridEnsembleRetriever(
        retrievers=[lexical, vector],
        weights=[BM25_WEIGHT, VECTOR_WEIGHT],
        c=RRF_C,
        max_results=max_results,
    )
    return retriever, lexical, vector


# ---------------------------------------------------------------------------
# 1. Cada sub-recuperador recibe cada consulta una sola vez
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_each_subretriever_is_called_once_per_distinct_query() -> None:
    q1 = "¿Puede cerrarse el acceso a una playa?"
    q2 = "hotel cierre acceso público playa"
    retriever, lexical, vector = _make({q1: [_doc("a")], q2: [_doc("b")]})

    await retriever.afuse_queries([q1, q2])

    assert len(lexical.calls) == len(vector.calls) == 2
    assert Counter(lexical.calls) == Counter({q1: 1, q2: 1})
    assert Counter(vector.calls) == Counter({q1: 1, q2: 1})


# ---------------------------------------------------------------------------
# 2. Un rank 1 léxico sobrevive a candidatos vectoriales de ranks bajos
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_lexical_rank_one_document_enters_final_result() -> None:
    q1 = "consulta original"
    q2 = "consulta reformulada"
    target = _doc("normativa-esperada")
    vector_q1 = [_doc(f"v{i}") for i in range(1, 9)]
    vector_q2 = [_doc(f"w{i}") for i in range(1, 9)]

    retriever = HybridEnsembleRetriever(
        retrievers=[
            _RecordingRetriever(docs_by_query={q1: [target], q2: []}),
            _RecordingRetriever(docs_by_query={q1: vector_q1, q2: vector_q2}),
        ],
        weights=[BM25_WEIGHT, VECTOR_WEIGHT],
        c=RRF_C,
        max_results=4,
    )

    result = await retriever.afuse_queries([q1, q2])

    assert "normativa-esperada" in _ids(result)


# ---------------------------------------------------------------------------
# 3. Duplicados y consultas vacías no generan llamadas extra
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_duplicates_and_blank_queries_do_not_generate_extra_calls() -> None:
    retriever, lexical, vector = _make({})

    await retriever.afuse_queries(["consulta", " consulta ", "", "   ", "otra"])

    assert len(lexical.calls) == len(vector.calls) == 2
    assert Counter(lexical.calls) == Counter({"consulta": 1, "otra": 1})
    assert Counter(vector.calls) == Counter({"consulta": 1, "otra": 1})


# ---------------------------------------------------------------------------
# 4. Sin consultas válidas no se invoca a ningún sub-recuperador
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_empty_query_list_returns_empty_without_calling_subretrievers() -> None:
    retriever, lexical, vector = _make({})

    assert await retriever.afuse_queries([]) == []
    assert await retriever.afuse_queries(["", "   "]) == []
    assert lexical.calls == []
    assert vector.calls == []


# ---------------------------------------------------------------------------
# 5. Se respeta max_results
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_afuse_queries_respects_max_results() -> None:
    q = "consulta"
    retriever, _, _ = _make({q: [_doc(f"d{i}") for i in range(6)]}, max_results=2)

    result = await retriever.afuse_queries([q])

    assert len(result) == 2


# ---------------------------------------------------------------------------
# 6. Una sola consulta conserva el orden de la ruta existente
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_single_query_afuse_matches_existing_single_query_route() -> None:
    q = "consulta"
    lexical_docs = [_doc("a"), _doc("b"), _doc("c")]
    vector_docs = [_doc("b"), _doc("d")]

    def make_retriever() -> HybridEnsembleRetriever:
        return HybridEnsembleRetriever(
            retrievers=[
                _RecordingRetriever(default_docs=lexical_docs),
                _RecordingRetriever(default_docs=vector_docs),
            ],
            weights=[BM25_WEIGHT, VECTOR_WEIGHT],
            max_results=4,
        )

    sync_ids = _ids(make_retriever().invoke(q))
    async_ids = _ids(await make_retriever().ainvoke(q))
    afuse_ids = _ids(await make_retriever().afuse_queries([q]))

    assert afuse_ids == sync_ids == async_ids


# ---------------------------------------------------------------------------
# 7. El filtro de contenido posterior a la fusión sigue vigente
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_structural_document_without_alphanumeric_content_is_excluded() -> None:
    q = "consulta"
    retriever, _, _ = _make(
        {
            q: [
                _doc("junk", "--- ___ ..."),
                _doc("valid", "Prohíbese pescar en la playa."),
            ]
        }
    )

    result = await retriever.afuse_queries([q])

    assert _ids(result) == ["valid"]


# ---------------------------------------------------------------------------
# 9. Aritmética de la fusión: rank 1 léxico (0.8/3) > rank 4 vectorial (0.2/6)
# ---------------------------------------------------------------------------


def test_documented_constants_are_the_ones_used_by_the_default_retriever() -> None:
    assert (RRF_C, BM25_WEIGHT, VECTOR_WEIGHT) == (2, 0.8, 0.2)
    assert HybridEnsembleRetriever.model_fields["c"].default == RRF_C
    defaults = {
        name: parameter.default
        for name, parameter in inspect.signature(get_ensemble_retriever).parameters.items()
    }
    assert defaults["bm25_weight"] == BM25_WEIGHT
    assert defaults["vector_weight"] == VECTOR_WEIGHT


@pytest.mark.anyio
async def test_lexical_rank_one_outscores_vector_rank_four_with_c_two() -> None:
    q = "consulta"
    lexical_doc = _doc("lexico-rank1")
    vector_docs = [_doc(f"vector-rank{i}") for i in range(1, 6)]

    retriever = HybridEnsembleRetriever(
        retrievers=[
            _RecordingRetriever(default_docs=[lexical_doc]),
            _RecordingRetriever(default_docs=vector_docs),
        ],
        weights=[BM25_WEIGHT, VECTOR_WEIGHT],
        c=RRF_C,
        max_results=5,
    )

    result = _ids(await retriever.afuse_queries([q]))

    # Referencia analítica independiente: 0.8/(1+2) ≈ 0.267 frente a
    # 0.2/(4+2) ≈ 0.033. El documento léxico debe quedar por delante.
    assert BM25_WEIGHT / (1 + RRF_C) > VECTOR_WEIGHT / (4 + RRF_C)
    assert result[0] == "lexico-rank1"
    assert result.index("lexico-rank1") < result.index("vector-rank4")
