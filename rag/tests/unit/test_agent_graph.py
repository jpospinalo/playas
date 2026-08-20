"""Pruebas del enrutamiento completo del grafo sin servicios externos."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

import rag.core.agent as agent_module
from rag.core.query_enricher import EnrichedQuery


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _state(question: str) -> dict:
    return {
        "question": question,
        "standalone_question": None,
        "enriched_query": None,
        "query_route": None,
        "messages": [HumanMessage(content=question)],
        "sources": [],
        "doc_types": None,
        "k": 2,
        "k_candidates": 5,
    }


@pytest.mark.anyio
async def test_out_of_scope_route_does_not_retrieve(monkeypatch: pytest.MonkeyPatch) -> None:
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
        lambda **kwargs: pytest.fail(f"No debía recuperar: {kwargs}"),
    )

    result = await agent_module.build_graph().ainvoke(
        _state("¿Cuál es la capital de Francia?"),
        config={"configurable": {"thread_id": "off-scope"}},
    )

    assert result["query_route"] == "out_of_scope"
    assert result["sources"] == []
    assert "fuera del ámbito jurídico" in result["messages"][-1].content


@pytest.mark.anyio
async def test_in_scope_route_uses_enrichment_limits_k_and_validates_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def analyze(question: str, history: str) -> EnrichedQuery:
        del question, history
        return EnrichedQuery(
            route="in_scope",
            standalone_question="¿Puede un hotel cerrar el acceso a una playa?",
            expanded_query="hotel acceso público playa cierre derecho uso",
            doc_types=["jurisprudencia", "normativa"],
        )

    captured: dict = {}

    class FakeRetriever:
        def invoke(self, query: str) -> list[Document]:
            captured["query"] = query
            return [
                Document(page_content=f"fragmento {index}", metadata={"chunk_id": str(index)})
                for index in range(4)
            ]

    def make_retriever(**kwargs):
        captured.update(kwargs)
        return FakeRetriever()

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["El acceso no puede cerrarse [doc1]."]),
    )

    result = await agent_module.build_graph().ainvoke(
        _state("¿Puede cerrarse?"),
        config={"configurable": {"thread_id": "in-scope"}},
    )

    assert captured == {
        "k": 2,
        "k_candidates": 5,
        "doc_types": ["jurisprudencia", "normativa"],
        "query": (
            "¿Puede cerrarse?\n"
            "¿Puede un hotel cerrar el acceso a una playa?\n"
            "hotel acceso público playa cierre derecho uso"
        ),
    }
    assert len(result["sources"]) == 2
    assert result["messages"][-1].content == "El acceso no puede cerrarse [doc1]."


@pytest.mark.anyio
async def test_stream_values_exposes_the_validated_final_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def analyze(question: str, history: str) -> EnrichedQuery:
        del history
        return EnrichedQuery(
            route="out_of_scope",
            standalone_question=question,
            expanded_query=question,
            doc_types=[],
        )

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    final_values: dict = {}
    modes: list[str] = []
    async for mode, payload in agent_module.build_graph().astream(
        _state("¿Cuál es la capital de Francia?"),
        config={"configurable": {"thread_id": "stream-values"}},
        stream_mode=["values", "custom"],
    ):
        modes.append(mode)
        if mode == "values":
            final_values = payload

    assert "custom" in modes
    assert final_values["query_route"] == "out_of_scope"
    assert "fuera del ámbito jurídico" in final_values["messages"][-1].content
