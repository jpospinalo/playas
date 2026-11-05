"""Construcción de la lista de consultas de recuperación del agente."""

from __future__ import annotations

from rag.core.agent import _retrieval_queries


def test_retrieval_queries_deduplicates_and_preserves_order() -> None:
    state = {
        "question": "  ¿Puede cerrarse el acceso?  ",
        "standalone_question": "¿Puede cerrarse el acceso?",
        "enriched_query": "hotel cierre acceso playa",
    }

    assert _retrieval_queries(state) == [
        "¿Puede cerrarse el acceso?",
        "hotel cierre acceso playa",
    ]


def test_retrieval_queries_discards_empty_optional_values() -> None:
    state = {
        "question": "pregunta",
        "standalone_question": "   ",
        "enriched_query": None,
    }

    assert _retrieval_queries(state) == ["pregunta"]


def test_retrieval_queries_returns_empty_when_question_is_blank() -> None:
    state = {
        "question": "   ",
        "standalone_question": "reformulación",
        "enriched_query": "consulta enriquecida",
    }

    assert _retrieval_queries(state) == []
