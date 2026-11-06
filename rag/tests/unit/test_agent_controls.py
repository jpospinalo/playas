"""Controles deterministas del grafo RAG."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from rag.core.agent import (
    _compose_generation_question,
    _conversation_response,
    _history_for_analysis,
    _retrieval_queries,
    _validate_citations,
    route_after_analysis,
)


def test_citations_must_exist_in_retrieved_documents() -> None:
    assert _validate_citations("Regla aplicable [doc1][doc3].", 3)
    assert not _validate_citations("Regla sin fuente.", 3)
    assert not _validate_citations("Cita inexistente [doc4].", 3)
    assert not _validate_citations("Cita inválida [doc0].", 3)


def test_history_excludes_only_current_repeated_question() -> None:
    messages = [
        HumanMessage(content="¿Puede cerrarse una playa?"),
        AIMessage(content="Respuesta anterior [doc1]."),
        HumanMessage(content="¿Puede cerrarse una playa?"),
    ]
    history = _history_for_analysis(messages, "¿Puede cerrarse una playa?")
    assert history.count("¿Puede cerrarse una playa?") == 1
    assert "Respuesta anterior" in history


def test_only_in_scope_queries_reach_retrieval() -> None:
    assert route_after_analysis({"query_route": "in_scope"}) == "retrieve"
    assert route_after_analysis({"query_route": "out_of_scope"}) == "respond"
    assert route_after_analysis({"query_route": "conversation"}) == "respond"
    assert route_after_analysis({"query_route": "needs_clarification"}) == "respond"


def test_original_question_is_preserved_in_retrieval_and_generation() -> None:
    state = {
        "question": "¿Y cuál es el plazo?",
        "standalone_question": "¿Cuál es el plazo del permiso de ocupación de una playa?",
        "enriched_query": "plazo permiso ocupación playa",
    }
    retrieval_queries = _retrieval_queries(state)
    generation_question = _compose_generation_question(state)
    assert retrieval_queries[0] == "¿Y cuál es el plazo?"
    assert "¿Cuál es el plazo del permiso de ocupación de una playa?" in retrieval_queries
    assert "plazo permiso ocupación playa" in retrieval_queries
    assert "Pregunta original: ¿Y cuál es el plazo?" in generation_question
    assert "Reformulación contextual" in generation_question


def test_social_responses_do_not_present_an_assistant_identity() -> None:
    saludo = _conversation_response("Hola")
    assert saludo.startswith("Hola.")
    assert "ATLAS" not in saludo and "soy " not in saludo.casefold()
    assert _conversation_response("Gracias") == "Con gusto."
    assert "ATLAS" not in _conversation_response("¿Qué puedes hacer?")
