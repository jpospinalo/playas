"""Pruebas de alcance, fallback y validación del analizador de consultas."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import rag.core.query_enricher as query_enricher
from rag.core.prompts import AGENT_SYSTEM, ENRICHER_HUMAN_BODY, ENRICHER_SYSTEM
from rag.core.query_enricher import EnrichedQuery, _fallback, _parse_json_response


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué permisos exige DIMAR para pescar desde una playa?",
        "¿Puede un hotel impedir el acceso público a una playa?",
        "¿Qué procedimiento se requiere para una concesión en terreno de bajamar?",
        "¿Qué jurisprudencia regula el turismo en una zona costera?",
        "¿Quién tiene derecho a usar las aguas marítimas cercanas a la playa?",
    ],
)
def test_scope_fallback_accepts_domain_questions(question: str) -> None:
    result = _fallback(question)
    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]


@pytest.mark.parametrize(
    "question",
    [
        "¿Cuál es la capital de Francia?",
        "Dame una receta para cocinar pescado.",
        "Explícame cómo programar una API en Python.",
        "Recomiéndame hoteles para pasar vacaciones.",
    ],
)
def test_scope_fallback_rejects_unrelated_questions(question: str) -> None:
    assert _fallback(question).route == "out_of_scope"


def test_related_but_ambiguous_question_requests_clarification() -> None:
    result = _fallback("¿Qué permiso necesito para operar un negocio turístico?")
    assert result.route == "needs_clarification"


def test_follow_up_inherits_coastal_scope_from_history() -> None:
    result = _fallback(
        "¿Y quién tiene ese derecho?",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?\nAsistente: Respuesta previa.",
    )
    assert result.route == "in_scope"


def test_explicit_off_topic_question_does_not_inherit_old_domain_history() -> None:
    result = _fallback(
        "¿Y cuál es la capital de Francia?",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )
    assert result.route == "out_of_scope"


def test_unrelated_question_without_known_pattern_does_not_inherit_scope() -> None:
    result = _fallback(
        "Escribe un poema sobre la luna.",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )
    assert result.route == "out_of_scope"


def test_invalid_structured_output_is_not_accepted_as_enrichment() -> None:
    result = _parse_json_response(
        '{"expanded_query":"capital de Francia DIMAR","legal_concepts":["inventado"]}',
        "¿Cuál es la capital de Francia?",
    )
    assert result.route == "out_of_scope"
    assert result.expanded_query == "¿Cuál es la capital de Francia?"


def test_obvious_unrelated_question_cannot_be_forced_into_scope() -> None:
    result = _parse_json_response(
        """{
            "route": "in_scope",
            "standalone_question": "¿Cuál es la capital de Francia?",
            "expanded_query": "capital de Francia DIMAR playas",
            "doc_types": ["normativa"]
        }""",
        "¿Cuál es la capital de Francia?",
    )
    assert result.route == "out_of_scope"
    assert result.doc_types == []


def test_arbitrary_question_cannot_be_forced_into_scope_by_model() -> None:
    result = _parse_json_response(
        """{
            "route": "in_scope",
            "standalone_question": "Escribe un poema sobre la luna",
            "expanded_query": "playas poema luna",
            "doc_types": ["normativa"]
        }""",
        "Escribe un poema sobre la luna",
    )
    assert result.route == "out_of_scope"


def test_analysis_prompt_injects_question_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        query_enricher,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    prompt = query_enricher._build_prompt()
    messages = prompt.format_messages(
        history="Usuario: pregunta anterior sobre una playa",
        question="¿Y cuál es el plazo?",
    )
    rendered = "\n".join(str(message.content) for message in messages)
    assert "pregunta anterior sobre una playa" in rendered
    assert "¿Y cuál es el plazo?" in rendered
    assert "{history}" not in rendered
    assert "{question}" not in rendered


def test_prompts_do_not_assign_an_atlas_identity() -> None:
    assert "ATLAS" not in AGENT_SYSTEM
    assert "ATLAS" not in ENRICHER_SYSTEM
    assert "ATLAS" not in ENRICHER_HUMAN_BODY


def test_enriched_query_normalizes_doc_types_and_word_limit() -> None:
    result = EnrichedQuery(
        route="in_scope",
        standalone_question="¿Qué norma aplica a una playa?",
        expanded_query=" ".join(f"término{index}" for index in range(60)),
        doc_types=["normativa", "normativa"],
    )
    assert len(result.expanded_query.split()) == 45
    assert result.doc_types == ["normativa"]
