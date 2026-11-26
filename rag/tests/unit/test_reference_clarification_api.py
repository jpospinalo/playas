"""El referente desconocido se aclara antes de recuperar, en ambos canales."""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
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


_START_DATE_QUESTION = (
    "En el trámite de reversión de una autorización temporal sobre una playa me requirieron "
    "reparar daños. Según el artículo 28 del Decreto 474 de 2015 del corpus, ¿qué día exacto "
    "vence mi plazo si no tengo la fecha de ese requerimiento?"
)
_JUDICIAL_REFERENCE_QUESTION = (
    "Sobre aquella acción popular contra DIMAR relacionada con el uso de una playa, "
    "¿qué orden impartió el juez en primera instancia y en qué plazo?"
)
_IDENTIFIED_CONCEPT_QUESTION = (
    "En la respuesta sobre manglares del concepto 1682 de 2 de noviembre de 2005, "
    "¿la investigación corresponde exclusivamente a DIMAR o cómo se reparten y coordinan "
    "las competencias?"
)


def _necessary_clarification_graph(
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_documentary_path: bool = False,
    rewrites: dict[str, str] | None = None,
    doc_type: str = "normativa",
):
    """Keep the real analysis guard/graph, replacing only external collaborators."""
    import rag.api.main as main_module

    calls = {"analysis": [], "retrieval": [], "generation": []}
    rewrites = rewrites or {}
    document = Document(
        id="necessary-clarification-evidence",
        page_content=(
            "La actuación identificada sobre la playa debe contrastarse con el procedimiento "
            "aplicable y sus condiciones. La fecha del requerimiento de reparación debe "
            "identificarse para examinar el vencimiento concreto. En la sentencia de primera "
            "instancia de Ana Pérez contra DIMAR del 10 de junio de 2020 se ordenó señalizar "
            "el acceso a la playa."
        ),
        metadata={
            "source": "necessary-clarification-evidence.md",
            "chunk_id": "necessary-clarification-evidence",
            "title": "Evidencia local simulada de la actuación identificada",
            "doc_type": doc_type,
        },
    )

    def analyze(prompt):
        # The callback follows the current turn even if an earlier turn is terminal.
        body = prompt.to_messages()[-1].content
        assert isinstance(body, str)
        question = body.rsplit("<question>\n", 1)[1].split("\n</question>", 1)[0]
        calls["analysis"].append(question)
        standalone = rewrites.get(question, question)
        return EnrichedQuery(
            route="in_scope",
            standalone_question=standalone,
            expanded_query=standalone,
            doc_types=[doc_type],
        )

    def structured_output(schema):
        assert schema is EnrichedQuery
        return RunnableLambda(analyze)

    def retrieve(query):
        if not allow_documentary_path:
            pytest.fail("El dato o referente necesario debe aclararse antes de recuperar")
        calls["retrieval"].append(query)
        return [document]

    def generation_llm():
        if not allow_documentary_path:
            pytest.fail("Una aclaración necesaria no debe llamar al generador")
        calls["generation"].append(True)
        return FakeListChatModel(
            responses=["La actuación identificada debe contrastarse con sus condiciones [doc1]."]
        )

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
    monkeypatch.setattr(
        agent_module, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    monkeypatch.setattr(agent_module, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
    monkeypatch.setattr(agent_module, "LEGAL_RESOLUTION_PROVENANCE_SHA256", None)
    monkeypatch.setattr(
        agent_module, "get_ensemble_retriever", lambda **kwargs: RunnableLambda(retrieve)
    )
    monkeypatch.setattr(agent_module, "get_generation_llm", generation_llm)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    return main_module, calls


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize(
    ("question", "kind"),
    [
        (_START_DATE_QUESTION, "start_date"),
        (_JUDICIAL_REFERENCE_QUESTION, "judicial_reference"),
        (
            "Me requirieron reparar los daños de una autorización temporal en la playa. "
            "¿En qué fecha vence el plazo si desconozco la fecha del requerimiento?",
            "start_date",
        ),
        (
            "Respecto de aquella acción popular contra DIMAR por una playa, ¿cuál fue "
            "la orden del juez en primera instancia y su plazo?",
            "judicial_reference",
        ),
    ],
    ids=["C02", "C04", "missing-date-paraphrase", "unknown-decision-paraphrase"],
)
async def test_necessary_clarification_stops_before_retrieval_in_public_handlers(
    monkeypatch: pytest.MonkeyPatch, channel: str, question: str, kind: str
) -> None:
    main_module, calls = _necessary_clarification_graph(monkeypatch)
    route, answer, sources = await _public_result(
        main_module, QueryRequest(question=question), channel
    )
    lower = answer.casefold()
    assert route == "needs_clarification"
    assert not sources and "[doc" not in lower
    assert calls["retrieval"] == calls["generation"] == []
    if kind == "start_date":
        assert "fecha" in lower and "requerimiento" in lower
        assert "dos meses" not in lower
        assert not re.search(r"\b\d{1,2} de \w+ de \d{4}\b", lower)
    else:
        assert any(word in lower for word in ("radicado", "partes", "providencia"))
        assert "conmina" not in lower and "vigilancia" not in lower
        assert not any(
            repeated in lower
            for repeated in (
                "qué instancia",
                "que instancia",
                "la instancia o",
                "indicar la instancia",
            )
        )


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize("kind", ["start_date", "judicial_reference"])
async def test_necessary_clarification_resolved_followup_recovers_with_citation(
    monkeypatch: pytest.MonkeyPatch, channel: str, kind: str
) -> None:
    first_question = _START_DATE_QUESTION if kind == "start_date" else _JUDICIAL_REFERENCE_QUESTION
    if kind == "start_date":
        followup = "La fecha de ese requerimiento de reparación fue el 3 de marzo de 2020."
        standalone = (
            "Sobre la autorización temporal en la playa y el artículo 28 del Decreto 474 de 2015, "
            "¿cómo contrastar el vencimiento si el requerimiento fue el 3 de marzo de 2020?"
        )
    else:
        followup = "Me refiero a la sentencia de Ana Pérez contra DIMAR del 10 de junio de 2020."
        standalone = (
            "En la sentencia de primera instancia de Ana Pérez contra DIMAR del 10 de junio "
            "de 2020 sobre una playa, ¿qué orden impartió el juez y en qué plazo?"
        )
    main_module, calls = _necessary_clarification_graph(
        monkeypatch,
        allow_documentary_path=True,
        rewrites={followup: standalone},
        doc_type="normativa" if kind == "start_date" else "jurisprudencia",
    )
    thread_id = f"necessary-clarification-{kind}-{channel}"
    route, _, sources = await _public_result(
        main_module, QueryRequest(question=first_question, thread_id=thread_id), channel
    )
    assert route == "needs_clarification" and not sources
    assert calls["retrieval"] == calls["generation"] == []

    route, answer, sources = await _public_result(
        main_module, QueryRequest(question=followup, thread_id=thread_id), channel
    )
    assert route == "in_scope" and sources
    assert "[doc1]" in answer and "[doc2]" not in answer
    assert len(calls["retrieval"]) == len(calls["generation"]) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize(
    ("question", "expected_route", "doc_type"),
    [
        (
            "Según el artículo 28 del Decreto 474 de 2015, ¿qué plazo se prevé para reparar "
            "daños en una playa?",
            "in_scope",
            "normativa",
        ),
        (
            "En la sentencia de Ana Pérez contra DIMAR del 10 de junio de 2020, ¿qué orden "
            "impartió el juez en primera instancia?",
            "in_scope",
            "jurisprudencia",
        ),
        (_IDENTIFIED_CONCEPT_QUESTION, "in_scope", "jurisprudencia"),
        (
            "Escribe código Python que aplique un filtro azul a una foto de la playa.",
            "out_of_scope",
            "normativa",
        ),
    ],
    ids=["abstract-term", "identified-decision-without-docket", "J01", "C05"],
)
async def test_necessary_clarification_preserves_identified_and_unrelated_paths(
    monkeypatch: pytest.MonkeyPatch, channel: str, question: str, expected_route: str, doc_type: str
) -> None:
    main_module, calls = _necessary_clarification_graph(
        monkeypatch, allow_documentary_path=expected_route == "in_scope", doc_type=doc_type
    )
    route, answer, sources = await _public_result(
        main_module, QueryRequest(question=question), channel
    )
    assert route == expected_route
    if expected_route == "in_scope":
        assert sources and "[doc1]" in answer
        assert len(calls["retrieval"]) == len(calls["generation"]) == 1
    else:
        assert not sources and "[doc" not in answer
        assert calls["retrieval"] == calls["generation"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
async def test_necessary_clarification_keeps_the_partial_docket_instance_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path, channel: str
) -> None:
    import test_legal_resolution_graph as resolution_fixtures

    main_module, calls = _necessary_clarification_graph(monkeypatch)
    resolution_fixtures._configured(monkeypatch, tmp_path, resolution_fixtures._source("overlap"))
    monkeypatch.setattr(main_module, "_graph", agent_module.build_graph())
    question = (
        "Solo tengo el número 08425 del proceso de erosión costera y desconozco la instancia. "
        "Sobre esa sentencia, ¿cuál fue el plazo de la orden?"
    )
    route, answer, sources = await _public_result(
        main_module, QueryRequest(question=question), channel
    )
    assert route == "needs_clarification"
    assert answer == agent_module._PROVIDENCIA_CLARIFICATION_RESPONSE
    assert "instancia" in answer and not sources and "[doc" not in answer
    assert calls["retrieval"] == calls["generation"] == []
