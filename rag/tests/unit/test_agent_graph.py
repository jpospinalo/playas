"""Pruebas del enrutamiento completo del grafo sin servicios externos."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
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


# ── Plan de corrección — enrutamiento de consultas jurídicas costeras ───────
#
# Estas dos pruebas usan el clasificador real (fallback, sin LLM) en vez de
# uno simulado, para comprobar el enrutamiento de extremo a extremo sin
# conectar con ChromaDB ni Ollama.


@pytest.mark.anyio
async def test_legitimate_full_case_reaches_retrieval_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un caso completo legítimo (falso negativo confirmado) debe llegar a
    in_scope con el clasificador real y el grafo debe recuperar exactamente
    una vez."""
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)

    call_count = {"n": 0}

    class FakeRetriever:
        def invoke(self, query: str) -> list[Document]:
            call_count["n"] += 1
            return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: FakeRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Puede acudir a la autoridad marítima [doc1]."]),
    )

    question = (
        "Soy pescador artesanal y vivo con mi familia de lo que gano en el mar. "
        "Hace varios meses una embarcación quedó abandonada cerca del lugar "
        "donde trabajo. ¿Qué puedo hacer para que la autoridad actúe y retire "
        "la embarcación antes de que el problema empeore?"
    )
    result = await agent_module.build_graph().ainvoke(
        _state(question),
        config={"configurable": {"thread_id": "legit-full-case"}},
    )

    assert result["query_route"] == "in_scope"
    assert call_count["n"] == 1


@pytest.mark.anyio
async def test_creative_question_with_playa_does_not_reach_retrieval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falso positivo confirmado: una consulta creativa con la palabra
    'playa' debe seguir fuera de alcance y no debe invocar el retriever."""
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(
        agent_module,
        "get_ensemble_retriever",
        lambda **kwargs: pytest.fail(f"No debía recuperar: {kwargs}"),
    )

    result = await agent_module.build_graph().ainvoke(
        _state("Escribe un poema sobre una playa."),
        config={"configurable": {"thread_id": "creative-playa"}},
    )

    assert result["query_route"] == "out_of_scope"
    assert result["sources"] == []


# ── Revisión posterior con el banco completo de preguntas jurídicas ────────
#
# Protección de consultas narrativas extensas (sección 3 de la revisión): el
# recuperador debe invocarse exactamente una vez, la pregunta original
# completa debe llegar a la consulta enviada al recuperador (aunque
# expanded_query esté recortada a 45 palabras) y la pregunta original debe
# seguir disponible para la generación final — sin perder hechos por el
# límite de expanded_query.


@pytest.mark.anyio
async def test_long_narrative_case_reaches_retriever_with_full_question_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un caso narrativo extenso (>45 palabras) del banco de 21 preguntas
    debe llegar a in_scope con el clasificador real; el grafo debe recuperar
    exactamente una vez, la consulta original completa debe estar presente
    en la consulta enviada al recuperador, expanded_query debe respetar el
    tope de 45 palabras, y la pregunta original debe seguir disponible sin
    modificar para la generación final."""
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)

    call_count = {"n": 0}
    captured: dict = {}

    class FakeRetriever:
        def invoke(self, query: str) -> list[Document]:
            call_count["n"] += 1
            captured["query"] = query
            return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: FakeRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Puede acudir a la autoridad marítima [doc1]."]),
    )

    question = (
        "Vivo en un apartamento frente a la playa de El Rodadero desde hace varios "
        "años. Últimamente he notado que en la zona cercana al edificio donde "
        "vivimos están funcionando motos acuáticas y actividades de parasailing "
        "casi todo el día, especialmente en temporadas altas. Algunos vecinos "
        "consideran que estas actividades atraen turismo y ayudan a la economía "
        "del sector, pero otros creen que las motos están pasando demasiado cerca "
        "de las personas que se bañan y que eso puede generar accidentes o "
        "problemas de seguridad.\n"
        "Hace unos días incluso hubo una discusión entre turistas y trabajadores "
        "de una empresa de deportes náuticos porque unos pedían que se alejaran "
        "más de la orilla y la empresa respondía que tenían autorización para "
        "operar ahí. La verdad yo no sé cómo funciona ese tema ni quién define "
        "hasta dónde pueden trabajar estas empresas. ¿DIMAR establece zonas "
        "específicas para estas actividades o las empresas pueden operar "
        "libremente en cualquier parte de la playa mientras tengan permiso?"
    )
    assert len(question.split()) > 45  # confirma que el límite de 45 palabras aplica aquí

    result = await agent_module.build_graph().ainvoke(
        _state(question),
        config={"configurable": {"thread_id": "narrative-long-case"}},
    )

    assert result["query_route"] == "in_scope"
    assert call_count["n"] == 1
    assert question in captured["query"]
    assert len(result["enriched_query"].split()) <= 45
    assert result["question"] == question
