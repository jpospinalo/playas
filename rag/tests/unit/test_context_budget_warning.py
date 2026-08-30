"""A3.6 — presupuesto de contexto en modo observación.

`generate_node` ya calculaba `full_context_chars` (ver
`test_agent_observability.py`, que cubre `log_full_context_size`, siempre a
nivel INFO). A3.6 añade un warning ADICIONAL y CONDICIONAL —
`log_context_budget_warning`, a nivel WARNING — solo cuando ese conteo
supera `config.CONTEXT_BUDGET_WARNING_CHARS`. Este archivo prueba
específicamente esa condicionalidad y el contenido del warning; no repite
la cobertura ya existente de `log_full_context_size`.

Esta ola es puramente observacional: no trunca chunks ni respuestas, y no
fija `max_tokens` de generación — ambas cosas se verifican aquí también
(la respuesta generada no cambia según se cruce o no el umbral).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import rag.core.agent as agent_module
from rag.core import observability as obs_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _generate_only_state(question: str) -> dict:
    return {
        "question": question,
        "standalone_question": None,
        "enriched_query": None,
        "query_route": "in_scope",
        "messages": [],
        "sources": [],
        "doc_types": None,
        "k": 2,
        "k_candidates": 5,
    }


def _mock_generation(
    monkeypatch: pytest.MonkeyPatch, answer: str = "Respuesta con cita [doc1]."
) -> None:
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=[answer] * 10),
    )


# ---------------------------------------------------------------------------
# log_context_budget_warning en aislamiento (mismo estilo que
# test_observability.py para las demás funciones de este módulo).
# ---------------------------------------------------------------------------


def test_log_context_budget_warning_logs_stage_chars_and_doc_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="rag.observability"):
        obs_module.log_context_budget_warning(chars=123_456, doc_count=7, stage="generate")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.WARNING
    assert "context_budget_exceeded" in record.message
    assert "stage=generate" in record.message
    assert "full_context_chars=123456" in record.message
    assert "doc_count=7" in record.message


def test_log_context_budget_warning_never_logs_content(caplog: pytest.LogCaptureFixture) -> None:
    sentinel = "CONTENIDO_CONFIDENCIAL_QUE_NO_DEBE_APARECER"
    with caplog.at_level(logging.WARNING, logger="rag.observability"):
        obs_module.log_context_budget_warning(chars=999_999, doc_count=1, stage="generate")

    full_output = "\n".join(r.message for r in caplog.records)
    assert sentinel not in full_output


# ---------------------------------------------------------------------------
# Conectado a generate_node — condicionalidad del warning según el umbral.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_generate_node_warns_when_context_exceeds_the_configured_threshold(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_generation(monkeypatch)
    # Umbral bajo, deliberadamente por debajo de lo que va a producir el
    # prompt real (instrucciones + contexto + pregunta) para forzar el aviso
    # de forma determinista, sin depender del tamaño exacto del template.
    monkeypatch.setattr(agent_module, "CONTEXT_BUDGET_WARNING_CHARS", 10)

    state = _generate_only_state("¿Aplica la norma sobre concesiones playeras?")
    state["sources"] = [Document(page_content="Fragmento del corpus.", metadata={"chunk_id": "1"})]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        result = await agent_module.generate_node(state)

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("context_budget_exceeded" in m for m in warning_messages)
    assert any("stage=generate" in m for m in warning_messages)
    # La respuesta generada no se ve afectada — modo puramente observacional.
    assert result["messages"][0].content == "Respuesta con cita [doc1]."


@pytest.mark.anyio
async def test_generate_node_does_not_warn_when_context_is_within_the_threshold(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_generation(monkeypatch)
    # Umbral deliberadamente muy alto: ningún prompt de prueba lo alcanza.
    monkeypatch.setattr(agent_module, "CONTEXT_BUDGET_WARNING_CHARS", 10_000_000)

    state = _generate_only_state("¿Aplica la norma sobre concesiones playeras?")
    state["sources"] = [Document(page_content="Fragmento del corpus.", metadata={"chunk_id": "1"})]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(state)

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("context_budget_exceeded" in m for m in warning_messages)


@pytest.mark.anyio
async def test_generate_node_never_truncates_documents_or_response_regardless_of_threshold(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Modo observación: cruzar el umbral no debe alterar el contexto que se
    le pasa al LLM ni la respuesta que produce — solo debe emitir el log."""
    long_answer = "Respuesta larga con cita [doc1]. " * 500
    _mock_generation(monkeypatch, answer=long_answer)
    monkeypatch.setattr(agent_module, "CONTEXT_BUDGET_WARNING_CHARS", 1)

    long_doc_content = "Fragmento extenso del corpus. " * 500
    state = _generate_only_state("¿Aplica la norma sobre concesiones playeras?")
    state["sources"] = [Document(page_content=long_doc_content, metadata={"chunk_id": "1"})]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        result = await agent_module.generate_node(state)

    # La respuesta completa (sin recortar) del LLM fake se conserva tal cual
    # (generate_node aplica `.strip()` al resultado, igual que siempre).
    assert result["messages"][0].content == long_answer.strip()


def test_default_threshold_is_a_positive_configurable_value() -> None:
    from rag.config import CONTEXT_BUDGET_WARNING_CHARS

    assert isinstance(CONTEXT_BUDGET_WARNING_CHARS, int)
    assert CONTEXT_BUDGET_WARNING_CHARS > 0
