# tests/integration/test_full_pipeline.py
import pytest


@pytest.mark.integration
def test_rag_returns_answer():
    """End-to-end test: query → RAG chain → non-empty answer."""
    from src.backend.generator import generate_answer

    answer, docs = generate_answer("¿Quién es Pluto?", k=2, k_candidates=5)
    assert isinstance(answer, str)
    assert len(answer) > 0
    assert len(docs) > 0


@pytest.mark.integration
def test_retriever_returns_relevant_docs():
    from src.backend.retriever import get_ensemble_retriever

    retriever = get_ensemble_retriever()
    docs = retriever.invoke("El corazón delator")
    assert len(docs) > 0
    assert all(hasattr(d, "page_content") for d in docs)
