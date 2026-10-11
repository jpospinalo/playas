"""Clasificación del resultado del grafo, contador de tokens y reanudación
de la caché de generación (``evaluation/generation_cache.py``). Sin red."""

from __future__ import annotations

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from evaluation.generation_cache import (
    UsageTracker,
    classify_outcome,
    estimate_cost_usd,
    pending_cases,
)
from rag.core.agent import (
    _CLARIFICATION_RESPONSE,
    _INVALID_CITATIONS_RESPONSE,
    _NO_EVIDENCE_RESPONSE,
)


def test_ruta_distinta_de_in_scope_no_recupera() -> None:
    assert (
        classify_outcome("needs_clarification", _CLARIFICATION_RESPONSE)
        == "sin_recuperacion:needs_clarification"
    )


def test_respuesta_fija_sin_evidencia() -> None:
    assert classify_outcome("in_scope", _NO_EVIDENCE_RESPONSE) == "sin_evidencia"


def test_respuesta_fija_por_citas_invalidas() -> None:
    assert classify_outcome("in_scope", _INVALID_CITATIONS_RESPONSE) == "citas_invalidas"


def test_respuesta_generada() -> None:
    assert classify_outcome("in_scope", "Según [doc1], DIMAR…") == "respondida"


def _result(input_tokens: int, output_tokens: int) -> LLMResult:
    message = AIMessage(
        content="x",
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )
    return LLMResult(generations=[[ChatGeneration(message=message)]])


def test_el_contador_suma_tokens_de_todas_las_llamadas() -> None:
    tracker = UsageTracker()
    tracker.on_llm_end(_result(100, 20))
    tracker.on_llm_end(_result(50, 5))
    assert (tracker.input_tokens, tracker.output_tokens, tracker.calls) == (150, 25, 2)


def test_el_contador_tolera_respuestas_sin_uso_reportado() -> None:
    tracker = UsageTracker()
    tracker.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content="x"))]]))
    assert (tracker.input_tokens, tracker.output_tokens, tracker.calls) == (0, 0, 1)


def test_costo_estimado_con_precio_por_millon() -> None:
    assert estimate_cost_usd(1_000_000, 1_000_000, 0.05, 0.40) == 0.45


def test_reanudacion_omite_casos_ya_en_cache() -> None:
    cases = [{"id": "registro-002"}, {"id": "registro-003"}, {"id": "registro-004"}]
    assert pending_cases(cases, {"registro-003"}) == [
        {"id": "registro-002"},
        {"id": "registro-004"},
    ]
