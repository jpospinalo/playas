import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from ragas import SingleTurnSample
from ragas.metrics import NonLLMContextPrecisionWithReference, NonLLMContextRecall

spec = importlib.util.spec_from_file_location(
    "level0", Path(__file__).resolve().parents[3] / "evaluation/ragas/run_level0.py"
)
level0 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(level0)


def test_document_ranking_deduplicates_chunks():
    docs = [
        SimpleNamespace(metadata={"source": source}, page_content=text)
        for source, text in [("a.pdf", "nada"), ("a.pdf", "nada"), ("b.md", "la playa es pública")]
    ]
    case = {"evidence": [{"document_key": "b", "quote": "la playa es pública"}]}
    result = level0.ranks(docs, case, 4)
    assert result["document_mrr_at_k"] == 0.5
    assert result["passage_mrr_at_k"] == 1 / 3


def test_evidence_uses_nfc_and_whitespace():
    assert level0.canonical("pública\n   playa") == level0.canonical("pública playa")


def test_quote_from_another_source_is_not_a_passage_hit():
    docs = [SimpleNamespace(metadata={"source": "otra.pdf"}, page_content="CONSEJO DE ESTADO")]
    case = {"evidence": [{"document_key": "esperada", "quote": "CONSEJO DE ESTADO"}]}
    assert level0.ranks(docs, case, 4)["passage_hit_at_k"] == 0.0


def test_nonllm_ragas_runs_with_empty_keys_and_no_http(monkeypatch):
    import requests

    for name in ["OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]:
        monkeypatch.setenv(name, "")
    monkeypatch.setattr(
        requests.Session,
        "request",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("HTTP prohibido")),
    )
    sample = SingleTurnSample(
        retrieved_contexts=["Las playas son bienes públicos."],
        reference_contexts=["Las playas son bienes públicos."],
    )
    for metric in [NonLLMContextRecall(), NonLLMContextPrecisionWithReference()]:
        assert asyncio.run(metric.single_turn_ascore(sample)) == pytest.approx(1.0)
