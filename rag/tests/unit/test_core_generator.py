"""T4.2 — rag.core.generator.generate_answer, adaptador para los scripts de
evaluación offline (evaluation/ragas_eval_*.py).

Esos scripts hacían ``from rag.core.generator import generate_answer``, un
módulo que ya no existía en el código actual (quedó huérfano tras la
migración del agente al único grafo determinista en ``rag.core.agent`` —
antes había un ``generator.py`` distinto). Este módulo restaura esa
referencia sin reimplementar retrieval ni generación: invoca el mismo grafo
real (``build_graph()``) que sirve ``/api/query``, con un ``thread_id``
efímero propio por llamada — nunca comparte memoria entre preguntas de
evaluación ni con conversaciones reales.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import rag.core.agent as agent_module
from rag.core.query_enricher import EnrichedQuery


def _mock_in_scope_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    doc_text: str = "fragmento de prueba",
    answer: str = "Respuesta [doc1].",
) -> None:
    async def analyze(question: str, history: str) -> EnrichedQuery:
        del question, history
        return EnrichedQuery(
            route="in_scope",
            standalone_question="reformulación",
            expanded_query="consulta jurídica costera",
            doc_types=["normativa"],
        )

    class FakeRetriever:
        def invoke(self, query: str) -> list[Document]:
            del query
            return [Document(page_content=doc_text, metadata={"chunk_id": "1"})]

        async def ainvoke(self, query: str) -> list[Document]:
            return self.invoke(query)

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: FakeRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module, "get_generation_llm", lambda: FakeListChatModel(responses=[answer])
    )


def test_generate_answer_returns_text_and_source_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rag.core.generator import generate_answer

    _mock_in_scope_pipeline(
        monkeypatch, doc_text="Contenido del fragmento.", answer="Respuesta con cita [doc1]."
    )

    answer, docs = generate_answer("¿Puede un hotel privatizar el acceso a una playa?")

    assert answer == "Respuesta con cita [doc1]."
    assert len(docs) == 1
    assert isinstance(docs[0], Document)
    assert docs[0].page_content == "Contenido del fragmento."


def test_generate_answer_returns_no_evidence_message_when_out_of_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rag.core.generator import generate_answer

    async def analyze(question: str, history: str) -> EnrichedQuery:
        del history
        return EnrichedQuery(
            route="out_of_scope",
            standalone_question=question,
            expanded_query=question,
            doc_types=[],
        )

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    monkeypatch.setattr(
        agent_module,
        "get_ensemble_retriever",
        lambda **kwargs: pytest.fail("No debía recuperar: la ruta es out_of_scope"),
    )

    answer, docs = generate_answer("¿Cuál es la capital de Francia?")

    assert docs == []
    assert answer.strip() != ""


def test_generate_answer_uses_an_independent_ephemeral_thread_id_per_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cada llamada es independiente: sin memoria compartida entre preguntas
    de evaluación distintas — evita fugas de contexto entre casos del set."""
    from rag.core.generator import generate_answer

    _mock_in_scope_pipeline(monkeypatch, doc_text="Fragmento A", answer="Respuesta [doc1].")
    generate_answer("Primera pregunta de evaluación")

    _mock_in_scope_pipeline(monkeypatch, doc_text="Fragmento B", answer="Otra respuesta [doc1].")
    answer2, docs2 = generate_answer("Segunda pregunta de evaluación, sin relación con la primera")

    assert len(docs2) == 1
    assert docs2[0].page_content == "Fragmento B"
    assert answer2 == "Otra respuesta [doc1]."
