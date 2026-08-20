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
    ],
)
def test_query_contract_rejects_invalid_payloads(payload: dict) -> None:
    with pytest.raises(ValidationError):
        QueryRequest(**payload)
