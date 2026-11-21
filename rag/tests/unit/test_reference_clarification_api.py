"""El referente desconocido se aclara antes de recuperar, en ambos canales."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from langchain_core.runnables import RunnableLambda

import rag.core.agent as agent_module
import rag.core.query_enricher as enricher_module
from rag.api.schemas import QueryRequest
from rag.core.domain_scope import EnrichedQuery


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _public_result(main_module, request: QueryRequest, channel: str):
    user = {"sub": "reference-contract-user"}
    if channel == "JSON":
        result = await main_module.query(request, user)
        return result.query_route, result.answer, result.sources
    response = await main_module.query_stream(request, user)
    events = []
    done = False
    async for block in response.body_iterator:
        text = block.decode() if isinstance(block, bytes) else block
        for line in text.splitlines():
            if not line.startswith("data: "):
                continue
            payload = line[6:].strip()
            if payload == "[DONE]":
                done = True
            else:
                events.append(json.loads(payload))
    assert done
    assert not any(event.get("type") == "error" for event in events)
    source_event = next(event for event in events if event.get("type") == "sources")
    answer = "".join(event["content"] for event in events if event.get("type") == "token")
    return source_event["query_route"], answer, source_event["sources"]


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize(
    ("question", "expected_route"),
    [
        ("¿Cuánto tiempo tiene esa entidad para ejecutar ese plan costero?", "needs_clarification"),
        ("¿Qué plazo hay para aplicar dicho plan de manejo de playas?", "needs_clarification"),
        ("Dame una receta para cocinar pescado en la playa.", "out_of_scope"),
    ],
)
async def test_unidentified_plan_stops_before_retrieval_in_json_and_sse(
    monkeypatch: pytest.MonkeyPatch, channel: str, question: str, expected_route: str
) -> None:
    import rag.api.main as main_module

    monkeypatch.setattr(enricher_module, "ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(agent_module, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
    monkeypatch.setattr(
        agent_module,
        "get_ensemble_retriever",
        lambda **kwargs: pytest.fail("No se debe buscar un referente desconocido o asunto ajeno"),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: pytest.fail("La aclaración no debe inventar una respuesta mediante el generador"),
    )
    monkeypatch.setattr(main_module, "_graph", agent_module.build_graph())
    request = QueryRequest(question=question)
    route, answer, sources = await _public_result(main_module, request, channel)
    assert route == expected_route
    assert not sources
    assert "[doc" not in answer
    if expected_route == "needs_clarification":
        assert "plan" in answer.casefold()
        assert "precisa" in answer.casefold() or "identifica" in answer.casefold()
        assert "tres meses" not in answer.casefold() and "dos años" not in answer.casefold()


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize(
    "question",
    [
        "Entre el plan de manejo de playas y el plan de restauración del litoral, "
        "¿cuánto tiempo hay para terminar ese plan conforme al Decreto 881 de 2006?",
        "Con relación al POMIUAC Insular, hay un plan de manejo de playas y otro "
        "de restauración del litoral. ¿Quién debe aprobar ese plan?",
    ],
    ids=["two-plans-with-norm-reference", "two-plans-with-pomiuac"],
)
async def test_active_enricher_clarification_survives_in_json_and_sse(
    monkeypatch: pytest.MonkeyPatch, channel: str, question: str
) -> None:
    import rag.api.main as main_module

    expected = EnrichedQuery(
        route="needs_clarification",
        standalone_question=question,
        expanded_query=question,
        doc_types=[],
    )
    calls = []

    def analyze(prompt):
        calls.append(prompt.to_messages())
        return expected

    def structured_output(schema):
        assert schema is EnrichedQuery
        return RunnableLambda(analyze)

    monkeypatch.setattr(enricher_module, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(
        enricher_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True, supports_structured_output=True),
    )
    monkeypatch.setattr(
        enricher_module,
        "get_enrichment_llm",
        lambda: SimpleNamespace(with_structured_output=structured_output),
    )
    monkeypatch.setattr(agent_module, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
    monkeypatch.setattr(
        agent_module,
        "get_ensemble_retriever",
        lambda **kwargs: pytest.fail("La aclaración del analizador debe impedir la búsqueda"),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: pytest.fail("La aclaración del analizador debe impedir la generación"),
    )
    monkeypatch.setattr(main_module, "_graph", agent_module.build_graph())
    route, answer, sources = await _public_result(
        main_module, QueryRequest(question=question), channel
    )
    assert len(calls) == 1 and question in calls[0][-1].content
    assert route == "needs_clarification"
    assert not sources and "[doc" not in answer
    assert "plan" in answer.casefold()
    assert "precisa" in answer.casefold() or "identifica" in answer.casefold()
