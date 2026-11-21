"""Failure logs must not expose model output or conversation contents."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.exceptions import OutputParserException
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

import rag.core.query_enricher as enricher

QUESTION = "¿Qué permisos exige DIMAR para pescar desde una playa?"
HISTORY = "Usuario: consulta previa sobre la pesca en una playa."
SENTINEL = "CONTENIDO-SINTETICO-PRIVADO-NO-REGISTRAR"


def _failure(kind: str) -> Exception:
    if kind == "parser":
        return OutputParserException(SENTINEL, llm_output=SENTINEL)
    if kind == "validation":
        try:
            enricher.EnrichedQuery(
                route=SENTINEL,  # type: ignore[arg-type]
                standalone_question=QUESTION,
                expanded_query=QUESTION,
                doc_types=[],
            )
        except ValidationError as exc:
            return exc
        raise AssertionError("Invalid fixture unexpectedly validated")
    return RuntimeError(SENTINEL)


def _install_failure(monkeypatch: pytest.MonkeyPatch, failure: BaseException, kind: str) -> None:
    def invoke(_value):
        raise failure from ValueError(SENTINEL + "-CAUSE")

    async def ainvoke(_value):
        raise failure from ValueError(SENTINEL + "-CAUSE")

    runnable = RunnableLambda(invoke, afunc=ainvoke)
    monkeypatch.setattr(enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(
        enricher,
        "get_active_provider",
        invoke
        if kind == "provider"
        else lambda: SimpleNamespace(supports_system_role=True, supports_structured_output=True),
    )
    if kind == "provider":
        # The failure happens before a provider object exists.
        monkeypatch.setattr(enricher, "get_active_provider", lambda: invoke(None))
    monkeypatch.setattr(
        enricher,
        "get_enrichment_llm",
        lambda: SimpleNamespace(with_structured_output=lambda _schema: runnable),
    )


@pytest.mark.parametrize("kind", ["parser", "validation", "provider"])
@pytest.mark.parametrize("async_call", [False, True], ids=["sync", "async"])
def test_enrichment_errors_log_only_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    kind: str,
    async_call: bool,
) -> None:
    failure = _failure(kind)
    _install_failure(monkeypatch, failure, kind)
    with caplog.at_level("WARNING", logger="rag.core.query_enricher"):
        result = (
            asyncio.run(enricher.enrich_query_async(QUESTION, HISTORY))
            if async_call
            else enricher.enrich_query(QUESTION, HISTORY)
        )

    assert result == enricher._fallback(QUESTION, HISTORY)
    records = [r for r in caplog.records if r.name == "rag.core.query_enricher"]
    assert len(records) == 1
    assert SENTINEL not in caplog.text
    assert QUESTION not in caplog.text
    assert HISTORY not in caplog.text
    assert records[0].exc_info is None
    assert records[0].stack_info is None
    assert f"exception_class={type(failure).__name__}" in records[0].getMessage()
    assert "fallback_used=true" in records[0].getMessage()


def test_async_cancellation_propagates_without_fallback_or_failure_log(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _install_failure(monkeypatch, asyncio.CancelledError(), "parser")
    with caplog.at_level("WARNING", logger="rag.core.query_enricher"):
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(enricher.enrich_query_async(QUESTION, HISTORY))
    assert not [r for r in caplog.records if r.name == "rag.core.query_enricher"]
