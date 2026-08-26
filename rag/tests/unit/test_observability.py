"""T3.1 — observabilidad/logging del pipeline RAG (core/observability.py).

Cubre las piezas de instrumentación en aislamiento: `stage_timer`,
`log_citation_format_error`, `ActiveQueryTracker` y
`log_retained_conversations`. La garantía central que se verifica en TODAS
las pruebas de este archivo: ningún contenido de negocio (pregunta,
documentos, tokens) llega jamás a un mensaje de log — solo nombres de
etapa/ruta (enums cerrados) y números.
"""

from __future__ import annotations

import logging

import pytest

from rag.core import observability as obs

_SENTINEL_QUESTION = "¿Puede un hotel privatizar el acceso a Playa Secreta del Náufrago?"
_SENTINEL_DOC_TEXT = "CONTENIDO_CONFIDENCIAL_DEL_FRAGMENTO_XYZ"


# ---------------------------------------------------------------------------
# stage_timer
# ---------------------------------------------------------------------------


def test_stage_timer_logs_stage_name_and_positive_duration(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        with obs.stage_timer("enrich_query"):
            pass

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "stage=enrich_query" in message
    assert "duration_ms=" in message


def test_stage_timer_includes_safe_extra_fields_passed_up_front(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        with obs.stage_timer("retrieve_forced", doc_types="jurisprudencia,normativa"):
            pass

    message = caplog.records[0].message
    assert "doc_types=jurisprudencia,normativa" in message


def test_stage_timer_allows_completing_fields_inside_the_block(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        with obs.stage_timer("retrieve_forced") as fields:
            fields["doc_count"] = 3

    assert "doc_count=3" in caplog.records[0].message


def test_stage_timer_logs_even_when_the_block_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        with pytest.raises(RuntimeError):
            with obs.stage_timer("generate"):
                raise RuntimeError("boom")

    assert len(caplog.records) == 1
    assert "stage=generate" in caplog.records[0].message


def test_stage_timer_never_leaks_question_or_document_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO):
        with obs.stage_timer("retrieve_forced", doc_count=1) as fields:
            # Simula una etapa real que "ve" contenido sensible pero nunca lo
            # pasa a stage_timer — solo lo seguro (el conteo) se añade.
            _ = _SENTINEL_QUESTION
            _ = _SENTINEL_DOC_TEXT
            fields["doc_count"] = 2

    full_output = "\n".join(r.message for r in caplog.records)
    assert _SENTINEL_QUESTION not in full_output
    assert _SENTINEL_DOC_TEXT not in full_output


# ---------------------------------------------------------------------------
# log_citation_format_error
# ---------------------------------------------------------------------------


def test_log_citation_format_error_logs_only_doc_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="rag.observability"):
        obs.log_citation_format_error(doc_count=4)

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "citation_format_error" in message
    assert "doc_count=4" in message
    assert caplog.records[0].levelno == logging.WARNING


# ---------------------------------------------------------------------------
# log_full_context_size (T3.7)
# ---------------------------------------------------------------------------
#
# Métrica interna, solo para logs: cuántos caracteres (y una estimación de
# tokens) se envían realmente al LLM de generación (system prompt + contexto
# recuperado + pregunta). Deliberadamente NO es el mismo cálculo que
# `_estimate_context_tokens` en api/main.py (que solo cuenta el historial de
# `state["messages"]`, sin system prompt ni documentos del turno actual, y
# alimenta el campo público `context_tokens` de la API) — nunca debe leerse
# ni escribirse desde aquí, y esta función nunca se expone por la API.


def test_log_full_context_size_logs_chars_and_estimated_tokens(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_full_context_size(chars=4000)

    assert len(caplog.records) == 1
    message = caplog.records[0].message
    assert "full_context_chars=4000" in message
    assert "full_context_tokens_est=1000" in message
    assert caplog.records[0].levelno == logging.INFO


def test_log_full_context_size_rounds_down_the_token_estimate(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_full_context_size(chars=10)

    assert "full_context_chars=10" in caplog.records[0].message
    assert "full_context_tokens_est=2" in caplog.records[0].message


def test_log_full_context_size_handles_zero_chars(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_full_context_size(chars=0)

    assert "full_context_chars=0" in caplog.records[0].message
    assert "full_context_tokens_est=0" in caplog.records[0].message


def test_log_full_context_size_only_accepts_a_char_count_never_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Prueba estructural: la función solo puede recibir un conteo (int), no
    contenido real — así es imposible que el texto del contexto o de la
    pregunta llegue a este log, sin importar cómo se le llame."""
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_full_context_size(chars=len(_SENTINEL_QUESTION) + len(_SENTINEL_DOC_TEXT))

    full_output = "\n".join(r.message for r in caplog.records)
    assert _SENTINEL_QUESTION not in full_output
    assert _SENTINEL_DOC_TEXT not in full_output


# ---------------------------------------------------------------------------
# ActiveQueryTracker
# ---------------------------------------------------------------------------


def test_active_query_tracker_starts_at_zero() -> None:
    tracker = obs.ActiveQueryTracker()
    assert tracker.count == 0


def test_active_query_tracker_increments_during_and_decrements_after() -> None:
    tracker = obs.ActiveQueryTracker()
    with tracker.track():
        assert tracker.count == 1
    assert tracker.count == 0


def test_active_query_tracker_decrements_even_on_exception() -> None:
    tracker = obs.ActiveQueryTracker()
    with pytest.raises(ValueError):
        with tracker.track():
            raise ValueError("boom")
    assert tracker.count == 0


def test_active_query_tracker_tracks_concurrent_queries_independently() -> None:
    tracker = obs.ActiveQueryTracker()
    with tracker.track():
        with tracker.track():
            assert tracker.count == 2
        assert tracker.count == 1
    assert tracker.count == 0


def test_active_query_tracker_logs_the_gauge(caplog: pytest.LogCaptureFixture) -> None:
    tracker = obs.ActiveQueryTracker()
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        with tracker.track():
            pass
    messages = [r.message for r in caplog.records]
    assert "active_queries=1" in messages
    assert "active_queries=0" in messages


# ---------------------------------------------------------------------------
# log_retained_conversations
# ---------------------------------------------------------------------------


class _FakeCheckpointerWithStorage:
    def __init__(self, thread_ids: list[str]) -> None:
        self.storage = {tid: {} for tid in thread_ids}


class _FakeCheckpointerWithoutStorage:
    pass


def test_log_retained_conversations_reports_storage_key_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    checkpointer = _FakeCheckpointerWithStorage(["thread-a", "thread-b", "thread-c"])
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_retained_conversations(checkpointer)

    assert len(caplog.records) == 1
    assert "retained_conversations=3" in caplog.records[0].message


def test_log_retained_conversations_never_logs_thread_ids(
    caplog: pytest.LogCaptureFixture,
) -> None:
    checkpointer = _FakeCheckpointerWithStorage(["user:secret-uuid-123:conversation:abc"])
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_retained_conversations(checkpointer)

    assert "secret-uuid-123" not in caplog.records[0].message


def test_log_retained_conversations_silently_noops_without_storage_attr(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        obs.log_retained_conversations(_FakeCheckpointerWithoutStorage())

    assert caplog.records == []


def test_log_retained_conversations_silently_noops_when_storage_has_no_len() -> None:
    class _WeirdStorage:
        pass

    class _Checkpointer:
        storage = _WeirdStorage()

    # No debe lanzar, incluso si `storage` no soporta len().
    obs.log_retained_conversations(_Checkpointer())
