"""Validación del contrato de consultas."""

import pytest
from pydantic import ValidationError

from rag.api.schemas import QueryRequest


def test_query_contract_accepts_current_message_and_valid_types() -> None:
    request = QueryRequest(
        question="  ¿Quién puede usar una playa?  ",
        doc_types=["normativa", "jurisprudencia"],
        conversation_id="conversation-id",
        current_message_id="message-id",
    )
    assert request.question == "¿Quién puede usar una playa?"


@pytest.mark.parametrize(
    "payload",
    [
        {"question": "   "},
        {"question": "válida", "doc_types": ["otro"]},
        {"question": "válida", "doc_types": ["normativa", "normativa"]},
        {"question": "válida", "k": 8, "k_candidates": 4},
        {"question": "válida", "current_message_id": "message-id"},
        {"question": "x" * 4001},
        # A3.5 — thread_id/conversation_id/current_message_id (con
        # conversation_id, requisito de current_message_id) deben rechazar
        # el string vacío: None sigue siendo válido, "" ya no lo es.
        {"question": "válida", "thread_id": ""},
        {"question": "válida", "conversation_id": "", "current_message_id": "m"},
        {"question": "válida", "conversation_id": "c", "current_message_id": ""},
    ],
)
def test_query_contract_rejects_invalid_payloads(payload: dict) -> None:
    with pytest.raises(ValidationError):
        QueryRequest(**payload)


# ── A3.5 — min_length=1 en IDs opcionales ───────────────────────────────────
#
# `None` sigue siendo válido para los tres (cada uno es opcional); solo el
# string vacío ("") pasa a rechazarse. `conversation_id` conserva la
# precedencia actual sobre `thread_id` cuando ambos llegan (ver
# `query_support._make_config`) — este punto no cambia esa lógica, solo la
# documenta en el schema.


def test_query_contract_accepts_none_for_all_optional_id_fields() -> None:
    request = QueryRequest(question="válida")
    assert request.thread_id is None
    assert request.conversation_id is None
    assert request.current_message_id is None


def test_query_contract_accepts_non_empty_optional_id_fields() -> None:
    request = QueryRequest(
        question="válida",
        thread_id="guest-thread-1",
        conversation_id="conv-1",
        current_message_id="msg-1",
    )
    assert request.thread_id == "guest-thread-1"
    assert request.conversation_id == "conv-1"
    assert request.current_message_id == "msg-1"


@pytest.mark.parametrize("field", ["thread_id", "conversation_id"])
def test_query_contract_rejects_empty_string_id_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        QueryRequest(question="válida", **{field: ""})
