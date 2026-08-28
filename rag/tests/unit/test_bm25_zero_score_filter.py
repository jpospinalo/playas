"""T2.2 — BM25 sin señal: excluir puntajes exactamente cero.

Gate real de esta entrega (el banco de 21 preguntas en
``test_query_analysis.py`` no ejercita retrieval en absoluto — es un banco de
clasificación/enriquecimiento de consultas, no de recuperación; verificado
por inspección directa del archivo).

``BM25Retriever._get_relevant_documents()`` usaba ``rank_bm25``'s
``get_top_n()``, que internamente hace ``np.argsort(get_scores(query))[::-1]``
sin filtrar nada: con un corpus más pequeño que ``k``, o con documentos sin
ningún término en común con la consulta, ``get_top_n`` completa igual el
top-k con documentos de score EXACTAMENTE 0 —evidencia fabricada, sin ninguna
señal léxica real—, que además terminan compitiendo en la fusión RRF como si
fueran candidatos genuinos.

El fix reimplementa el mismo cálculo (``get_scores`` +
``np.argsort(scores)[::-1]``, el mismo algoritmo que ``get_top_n`` ya usaba
internamente) pero descarta los documentos con score == 0 antes de completar
el top-k. El orden de desempate ante scores iguales se preserva
deliberadamente igual a como lo produce ``np.argsort`` con quicksort (su
`kind` por defecto, NO estable) — el mismo comportamiento de siempre, ahora
solo con el filtro de score cero añadido. Ese orden de desempate es un
detalle de implementación de NumPy, no una garantía documentada por
``np.argsort``; la prueba de empates de este archivo queda pinneada a la
versión de NumPy fijada en ``uv.lock`` (2.4.6 al momento de esta entrega) y
debe revisarse si esa versión cambia.
"""

from __future__ import annotations

import numpy as np
import pytest
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from rag.core.retriever import BM25Retriever, _FilteredRetriever, _tokenize_bm25


def _bm25(docs: list[Document], k: int) -> BM25Retriever:
    corpus = [_tokenize_bm25(d.page_content) for d in docs]
    vectorizer = BM25Okapi(corpus)
    return BM25Retriever(vectorizer=vectorizer, docs=docs, k=k)


def _doc(identifier: str, text: str) -> Document:
    return Document(page_content=text, metadata={"id": identifier})


# ---------------------------------------------------------------------------
# Corpus controlado: k mayor que la cantidad de documentos con señal real
# ---------------------------------------------------------------------------


def test_zero_score_documents_are_excluded_even_when_k_exceeds_matches() -> None:
    docs = [
        _doc("acceso-1", "acceso público a la playa"),
        _doc("acceso-2", "restricción de acceso costero a la playa"),
        _doc("pesca", "permiso de pesca artesanal"),
        _doc("concesion", "trámite de concesión portuaria"),
        _doc("ambiental", "licencia ambiental para construcción"),
    ]
    retriever = _bm25(docs, k=5)  # k == tamaño del corpus completo

    results = retriever.invoke("acceso playa")

    ids = [d.metadata["id"] for d in results]
    # Solo los dos documentos con solapamiento léxico real; nunca los otros
    # tres, aunque k=5 "pediría" completar hasta cinco resultados.
    assert set(ids) == {"acceso-1", "acceso-2"}
    assert len(results) < 5


def test_returns_single_result_when_only_one_document_has_signal() -> None:
    docs = [
        _doc("match", "dominio público marítimo terrestre"),
        _doc("no-match-1", "requisitos de licencia de construcción"),
        _doc("no-match-2", "impuesto predial unificado"),
    ]
    retriever = _bm25(docs, k=10)

    results = retriever.invoke("dominio marítimo terrestre")

    assert [d.metadata["id"] for d in results] == ["match"]


def test_no_lexical_overlap_at_all_returns_empty_list() -> None:
    docs = [
        _doc("a", "concesión de playa"),
        _doc("b", "permiso de pesca"),
    ]
    retriever = _bm25(docs, k=5)

    results = retriever.invoke("xilofono marciano inexistente")

    assert results == []


# ---------------------------------------------------------------------------
# Cuando SÍ hay señal en todos los documentos, el comportamiento no cambia
# frente al histórico get_top_n (mismo cálculo, sin nada que filtrar).
# ---------------------------------------------------------------------------


def test_matches_historical_get_top_n_ranking_when_no_zero_scores() -> None:
    docs = [
        _doc("1", "acceso público a la playa"),
        _doc("2", "permiso de pesca artesanal en la playa"),
        _doc("3", "restricción de acceso costero"),
    ]
    corpus = [_tokenize_bm25(d.page_content) for d in docs]
    vectorizer = BM25Okapi(corpus)
    retriever = BM25Retriever(vectorizer=vectorizer, docs=docs, k=2)

    expected = vectorizer.get_top_n(_tokenize_bm25("acceso playa"), docs, n=2)
    result = retriever.invoke("acceso playa")

    assert result == expected


def test_respects_k_when_more_documents_have_signal_than_k() -> None:
    docs = [_doc(str(i), f"playa fragmento {i} sobre acceso a la playa") for i in range(10)]
    retriever = _bm25(docs, k=3)

    results = retriever.invoke("playa acceso")

    assert len(results) == 3


# ---------------------------------------------------------------------------
# Orden de desempate: reproduce np.argsort(scores)[::-1] tal cual (quicksort,
# no estable), igual que hacía rank_bm25.get_top_n internamente.
# ---------------------------------------------------------------------------


def test_tie_order_matches_raw_numpy_argsort_convention() -> None:
    # Todos los documentos son textualmente idénticos: scores BM25 idénticos
    # para cualquier consulta que matchee, forzando un empate real.
    docs = [_doc(str(i), "playa acceso playa acceso") for i in range(8)]
    vectorizer = BM25Okapi([_tokenize_bm25(d.page_content) for d in docs])
    retriever = BM25Retriever(vectorizer=vectorizer, docs=docs, k=8)

    scores = vectorizer.get_scores(_tokenize_bm25("playa acceso"))
    expected_order = np.argsort(scores)[::-1]
    expected_ids = [docs[i].metadata["id"] for i in expected_order if scores[i] != 0]

    result = retriever.invoke("playa acceso")
    result_ids = [d.metadata["id"] for d in result]

    assert result_ids == expected_ids


# ---------------------------------------------------------------------------
# Los tipos devueltos siguen siendo list[Document] a través de
# _FilteredRetriever (BM25 no soporta filtro nativo de doc_type).
# ---------------------------------------------------------------------------


def test_filtered_retriever_still_receives_list_of_documents_after_zero_filter() -> None:
    docs = [
        Document(page_content="acceso a la playa", metadata={"id": "1", "doc_type": "normativa"}),
        Document(
            page_content="acceso a la playa jurisprudencial",
            metadata={"id": "2", "doc_type": "jurisprudencia"},
        ),
        Document(
            page_content="tema sin relación alguna", metadata={"id": "3", "doc_type": "normativa"}
        ),
    ]
    bm25 = _bm25(docs, k=5)
    filtered = _FilteredRetriever(inner=bm25, doc_types=["normativa"])

    results = filtered.invoke("acceso playa")

    assert all(isinstance(d, Document) for d in results)
    assert [d.metadata["id"] for d in results] == ["1"]


@pytest.mark.parametrize("k", [1, 2, 3, 50])
def test_never_returns_more_than_k_regardless_of_zero_filtering(k: int) -> None:
    docs = [_doc(str(i), "playa acceso costero") for i in range(20)]
    retriever = _bm25(docs, k=k)

    results = retriever.invoke("playa acceso")

    assert len(results) <= k
