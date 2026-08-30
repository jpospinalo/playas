"""C1.1 — Pruebas del diagnóstico reproducible de RRF (``evaluation/rrf_diagnostic.py``).

Estas pruebas no ejercitan producción: verifican que el propio diagnóstico de
Ola C sea correcto y determinista, ya que el reporte que produce se usa como
evidencia (informe RRF, sección 14 del plan). Confirman tres cosas:

1. Los pesos/``c`` que el diagnóstico lee son exactamente los de producción
   (``get_ensemble_retriever`` / ``HybridEnsembleRetriever``) — si alguna vez
   cambiaran, el diagnóstico los seguiría automáticamente en vez de quedar
   desincronizado con un valor hardcodeado aparte.
2. Cada escenario sintético produce el orden y los scores que la fórmula RRF
   ponderada predice manualmente (misma referencia analítica independiente
   que ya usa ``tests/unit/test_retriever_invariants.py``).
3. La conclusión central del diagnóstico — que un candidato exclusivo de BM25
   no compite con los vectoriales dentro del rango realista de
   ``k_candidates`` (4-20) — se sostiene con la configuración real leída.
"""

from __future__ import annotations

import inspect

from evaluation.rrf_diagnostic import (
    BM25_WEIGHT,
    RRF_C,
    VECTOR_WEIGHT,
    _rrf_score,
    bm25_exclusive_vs_vector_sweep,
    scenario_exclusive_bm25_candidate,
    scenario_exclusive_vector_candidates,
    scenario_final_ranking_mixed,
    scenario_shared_candidate,
)
from rag.core.retriever import HybridEnsembleRetriever, get_ensemble_retriever


def test_weights_and_c_match_production_defaults_exactly() -> None:
    """El diagnóstico lee la configuración real; no la hardcodea por separado."""
    sig = inspect.signature(get_ensemble_retriever)
    assert BM25_WEIGHT == sig.parameters["bm25_weight"].default
    assert VECTOR_WEIGHT == sig.parameters["vector_weight"].default
    assert RRF_C == HybridEnsembleRetriever.model_fields["c"].default


def test_exclusive_bm25_candidate_wins_when_nothing_competes() -> None:
    result = scenario_exclusive_bm25_candidate()
    assert result["orden_resultante"] == ["bm25_excl"]
    assert result["score_bm25_excl_rank1"] == _rrf_score(1, BM25_WEIGHT)


def test_exclusive_vector_candidates_preserve_their_rank_order() -> None:
    result = scenario_exclusive_vector_candidates()
    assert result["orden_resultante"] == ["v1", "v2", "v3"]
    # Los scores deben ser estrictamente decrecientes con el rank.
    scores = result["scores"]
    assert scores["v1"] > scores["v2"] > scores["v3"]


def test_shared_candidate_accumulates_both_contributions_and_wins() -> None:
    result = scenario_shared_candidate()
    scores = result["scores"]
    # El compartido debe valer más que la suma de cualquiera de los dos
    # candidatos exclusivos por separado — es la propiedad que RRF pondera.
    assert scores["shared"] == _rrf_score(1, BM25_WEIGHT) + _rrf_score(2, VECTOR_WEIGHT)
    assert scores["shared"] > scores["vector_only"]
    assert scores["shared"] > scores["bm25_only"]
    assert result["orden_resultante"][0] == "shared"


def test_mixed_scenario_order_matches_manual_rrf_calculation() -> None:
    """Réplica exacta del escenario ya validado en
    ``test_retriever_invariants.py::test_hybrid_fusion_with_valid_config_ranks_identically_to_before``,
    pero ejercitando el diagnóstico de Ola C en vez del retriever directamente."""
    result = scenario_final_ranking_mixed()
    assert result["orden_resultante"] == result["orden_esperado_por_score"]
    assert result["orden_resultante"] == ["b", "d", "a", "c"]


def test_bm25_exclusive_never_beats_vector_within_realistic_k_range() -> None:
    """La afirmación central de C1.1: si la búsqueda vectorial entrega al
    menos k candidatos (k entre 4 y 20 — rango real de ``k_candidates``),
    un candidato exclusivo de BM25 en su mejor rank posible (1) no compite
    con ellos."""
    result = bm25_exclusive_vs_vector_sweep()
    assert result["bm25_compite_en_algun_k_del_rango"] is False
    for row in result["filas"]:
        assert row["bm25_excl_supera_al_ultimo_vectorial"] is False
        # El candidato BM25 debe terminar siempre después de todos los k
        # candidatos vectoriales (posición k+1, el último lugar posible).
        assert row["posicion_final_bm25_excl"] == row["k"] + 1


def test_crossover_k_is_far_outside_the_realistic_range() -> None:
    """El punto de cruce analítico (a partir de qué k un vectorial en su
    peor rank empezaría a perder frente al mejor caso de BM25) debe quedar
    muy por fuera del rango realista de k_candidates (4-20) para que la
    conclusión del diagnóstico sea válida con los parámetros actuales."""
    result = bm25_exclusive_vs_vector_sweep()
    assert result["k_de_cruce_analitico"] > 20 * 10  # amplio margen de sobra
    # Y coincide con la fórmula cerrada: peso_bm25/(1+c) == peso_vector/(k+c)
    k = result["k_de_cruce_analitico"]
    expected_score_at_crossover = VECTOR_WEIGHT / (k + RRF_C)
    assert abs(expected_score_at_crossover - _rrf_score(1, BM25_WEIGHT)) < 1e-9


def test_sweep_covers_the_documented_realistic_k_candidates_range() -> None:
    result = bm25_exclusive_vs_vector_sweep()
    assert result["rango_k_evaluado"] == [4, 20]
    assert [row["k"] for row in result["filas"]] == list(range(4, 21))
