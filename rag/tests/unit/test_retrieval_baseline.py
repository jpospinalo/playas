"""Métricas deterministas de recuperación por documento esperado
(``evaluation/retrieval_baseline.py``). Sin red: solo funciones puras."""

from __future__ import annotations

import unicodedata

import pytest

from evaluation.retrieval_baseline import (
    doc_recall_at_k,
    first_relevant_rank,
    summarize_retrieval,
)

_A = "AP Felipe José Campo Fernández VS Corpamag y otros"
_B = "decreto-2324-de-1984"
_C = "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)"


def test_rango_del_primer_chunk_relevante_es_base_1() -> None:
    assert first_relevant_rank([_C, _C, _A, _B], [_A, _B]) == 3


def test_sin_documento_esperado_en_la_lista_el_rango_es_none() -> None:
    assert first_relevant_rank([_C, _C], [_A]) is None


def test_el_rango_ignora_la_forma_unicode_del_titulo() -> None:
    assert first_relevant_rank([unicodedata.normalize("NFD", _A)], [_A]) == 1


@pytest.mark.parametrize(
    ("k", "esperado"),
    [(1, 0.0), (2, 0.5), (4, 1.0)],
)
def test_recall_por_documento_cuenta_documentos_distintos_en_el_top_k(
    k: int, esperado: float
) -> None:
    recuperados = [_C, _A, _A, _B]
    assert doc_recall_at_k(recuperados, [_A, _B], k) == esperado


def test_resumen_agrupa_y_calcula_hit_y_mrr() -> None:
    filas = [
        {"tipo": "x", "rank": 1, "doc_recall_at_4": 1.0},
        {"tipo": "x", "rank": None, "doc_recall_at_4": 0.0},
        {"tipo": "y", "rank": 8, "doc_recall_at_4": 0.0},
    ]
    resumen = summarize_retrieval(filas, "tipo")
    assert resumen["x"] == {
        "n": 2,
        "hit_at_4": 0.5,
        "hit_at_20": 0.5,
        "mrr": 0.5,
        "doc_recall_at_4": 0.5,
    }
    assert resumen["y"]["hit_at_4"] == 0.0
    assert resumen["y"]["hit_at_20"] == 1.0
    assert resumen["y"]["mrr"] == pytest.approx(1 / 8)
