"""Partes puras de la evaluación RAGAS sobre la v0.2
(``evaluation/ragas_v02.py``): precisión/cobertura/F1 a partir de conteos,
diagnóstico por caso, agregación y contador de uso. Sin red ni LLM."""

from __future__ import annotations

import pytest

from evaluation.ragas_v02 import (
    UsageCounter,
    aggregate_scores,
    diagnose,
    prf_from_counts,
)


def test_precision_cobertura_y_f1_desde_los_conteos() -> None:
    prf = prf_from_counts(tp=3, fp=1, fn=2)
    assert prf["precision"] == pytest.approx(0.75)
    assert prf["recall"] == pytest.approx(0.6)
    assert prf["f1"] == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))


def test_sin_afirmaciones_los_tres_valores_son_cero() -> None:
    assert prf_from_counts(tp=0, fp=0, fn=0) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


@pytest.mark.parametrize(
    ("scores", "esperado"),
    [
        ({"context_recall": 0.2, "faithfulness": 0.9, "factual_recall": 0.1}, "recuperacion"),
        ({"context_recall": 0.8, "faithfulness": 0.3, "factual_recall": 0.2}, "alucinacion"),
        (
            {"context_recall": 0.8, "faithfulness": 0.9, "factual_recall": 0.3},
            "incompleta_o_general",
        ),
        ({"context_recall": 0.8, "faithfulness": 0.9, "factual_recall": 0.7}, "correcta"),
        ({"context_recall": None, "faithfulness": 0.9, "factual_recall": 0.7}, "sin_datos"),
    ],
)
def test_diagnostico_sigue_la_tabla_del_documento(scores: dict, esperado: str) -> None:
    assert diagnose(scores) == esperado


def test_agregacion_promedia_ignorando_valores_faltantes() -> None:
    filas = [
        {"tipo": "a", "scores": {"faithfulness": 1.0, "context_recall": None}},
        {"tipo": "a", "scores": {"faithfulness": 0.5, "context_recall": 0.4}},
        {"tipo": "b", "scores": {"faithfulness": 0.0, "context_recall": 1.0}},
    ]
    resumen = aggregate_scores(filas, "tipo", ["faithfulness", "context_recall"])
    assert resumen["a"]["n"] == 2
    assert resumen["a"]["faithfulness"] == pytest.approx(0.75)
    assert resumen["a"]["context_recall"] == pytest.approx(0.4)
    assert resumen["b"]["context_recall"] == pytest.approx(1.0)


def test_metrica_sin_ningun_valor_queda_en_none() -> None:
    filas = [{"tipo": "a", "scores": {"faithfulness": None}}]
    assert aggregate_scores(filas, "tipo", ["faithfulness"])["a"]["faithfulness"] is None


def test_contador_de_uso_suma_respuestas_de_la_api() -> None:
    counter = UsageCounter()
    counter.add({"prompt_tokens": 1000, "completion_tokens": 400})
    counter.add({"prompt_tokens": 10, "completion_tokens": 5})
    counter.add(None)
    assert (counter.input_tokens, counter.output_tokens, counter.calls) == (1010, 405, 3)


def test_el_uso_se_atribuye_solo_al_caso_que_lo_genero() -> None:
    import asyncio

    from evaluation.ragas_v02 import case_usage, record_usage

    total = UsageCounter()

    async def caso(tokens: int) -> UsageCounter:
        async with case_usage() as propio:
            await asyncio.sleep(0)  # cede el turno: los casos se intercalan
            record_usage(total, {"prompt_tokens": tokens, "completion_tokens": 1})
            await asyncio.sleep(0)
            return propio

    async def ambos() -> list[UsageCounter]:
        return await asyncio.gather(caso(100), caso(7))

    a, b = asyncio.run(ambos())
    assert (a.input_tokens, b.input_tokens) == (100, 7)
    assert total.input_tokens == 107
