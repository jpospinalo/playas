"""Offline contracts for the opt-in documentary path."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langgraph.errors import NodeCancelledError

from rag.api.query_support import _build_graph_input
from rag.api.schemas import QueryRequest
from rag.core import agent
from rag.core.legal_resolution import ResolutionIndex
from rag.core.query_enricher import EnrichedQuery, QueryRoute

DOCKET = "47001233100020110842502"
QUESTION = (
    "¿Qué resolvió en segunda instancia sobre la sentencia del 8 de agosto de 2024 "
    f"en el radicado {DOCKET}?"
)
GENERATION_QUESTION = QUESTION.replace("la sentencia del 8 de agosto de 2024", "el fallo apelado")
DECISION = "PRIMERO: Confirmar la sentencia del 8 de agosto de 2024."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _source(name: str, *, suffix: str = "", docket: str = DOCKET) -> list[Document]:
    return [
        Document(
            id=f"{name}-{i}",
            page_content=text,
            metadata={
                "chunk_id": f"{name}-{i}",
                "source": f"{name}.pdf",
                "doc_type": "jurisprudencia",
                "Corporación": "Consejo de Estado",
                "Radicado": docket,
                "section_name": section,
            },
        )
        for i, (section, text) in enumerate(
            (
                ("Contexto del caso", f"Sentencia de segunda instancia\nRadicado: {docket}"),
                ("Decisión", "Antecedentes ajenos a la orden. " * 25 + "\n" + DECISION + suffix),
            ),
            1,
        )
    ]


def _configured(monkeypatch, tmp_path: Path, snapshot: list[Document]) -> Path:
    positions: Counter[str] = Counter()
    rows = []
    for doc in snapshot:
        source = doc.metadata["source"]
        positions[source] += 1
        canonical = json.dumps(
            doc.metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        rows.append(
            {
                "id": doc.id,
                "document_source": {"path": source + ".jsonl", "line": positions[source]},
                "page_content_sha256": sha256(doc.page_content.encode()).hexdigest(),
                "metadata_payload_sha256": sha256(canonical.encode()).hexdigest(),
            }
        )
    path = tmp_path / "procedencia.json"
    data = json.dumps({"vector_records": rows}).encode()
    path.write_bytes(data)
    monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_PATH", str(path))
    monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_SHA256", sha256(data).hexdigest())
    monkeypatch.setattr(agent, "bm25_documents", lambda: snapshot)
    return path


def _enrichment(monkeypatch, route: QueryRoute) -> None:
    async def analyze(question: str, history: str) -> EnrichedQuery:
        return EnrichedQuery(
            route=route,
            standalone_question=question,
            expanded_query=question,
            doc_types=["jurisprudencia"] if route == "in_scope" else [],
        )

    monkeypatch.setattr(agent, "enrich_query_async", analyze)


async def _invoke(graph, *, doc_types=None, question=QUESTION, k=4):
    request = QueryRequest(question=question, doc_types=doc_types, k=k, k_candidates=8)
    return await graph.ainvoke(
        _build_graph_input(request, [HumanMessage(content=question)]),
        config={"configurable": {"thread_id": "same-thread"}},
    )


def _no_calls(monkeypatch) -> None:
    monkeypatch.setattr(
        agent, "get_ensemble_retriever", lambda **_: pytest.fail("recuperación inesperada")
    )
    monkeypatch.setattr(agent, "get_generation_llm", lambda: pytest.fail("LLM inesperado"))


@pytest.mark.anyio
async def test_opt_in_rescue_captures_the_current_request_filter(monkeypatch, tmp_path) -> None:
    docs = _source("providencia")
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "needs_clarification")
    _no_calls(monkeypatch)
    graph = agent.build_graph()

    for requested, expected in (
        (["normativa"], False),
        (None, True),
        (["jurisprudencia"], True),
        (["jurisprudencia", "normativa"], True),
        (["normativa"], False),
    ):
        state = await _invoke(graph, doc_types=requested)
        assert state["query_route"] == ("in_scope" if expected else "needs_clarification")
        if expected:
            excerpt = state["sources"][0]
            assert excerpt.id == docs[1].id
            assert excerpt.metadata == docs[1].metadata
            assert excerpt is not docs[1] and excerpt.page_content == "[…] " + DECISION
            assert state["messages"][-1].content == f"- «[…] {DECISION}» [doc1]"
        else:
            assert state["sources"] == []
    assert docs[1].page_content.startswith("Antecedentes")


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["disabled", "absent", "wrong_sha", "empty", "mismatch"])
async def test_rescue_falls_back_without_authenticated_provenance(monkeypatch, tmp_path, mode):
    docs = [] if mode == "empty" else _source("providencia")
    path = _configured(monkeypatch, tmp_path, docs)
    if mode == "disabled":
        monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
        monkeypatch.setattr(agent, "bm25_documents", lambda: pytest.fail("lectura inesperada"))
    elif mode == "absent":
        path.unlink()
    elif mode == "wrong_sha":
        monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_SHA256", "0" * 64)
    elif mode == "mismatch":
        docs[1].metadata["Radicado"] = "13001233300020170103801"
    _enrichment(monkeypatch, "out_of_scope")
    _no_calls(monkeypatch)
    state = await _invoke(agent.build_graph())
    assert state["query_route"] == "out_of_scope"
    assert state["sources"] == []


@pytest.mark.anyio
@pytest.mark.parametrize("cancel", [False, True])
async def test_rescue_does_not_publish_partial_results_on_failure(monkeypatch, tmp_path, cancel):
    _configured(monkeypatch, tmp_path, _source("providencia"))
    _enrichment(monkeypatch, "out_of_scope")
    _no_calls(monkeypatch)

    def fail(*args, **kwargs):
        if cancel:
            raise asyncio.CancelledError
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(ResolutionIndex, "resolve", fail)
    graph = agent.build_graph()
    if cancel:
        with pytest.raises(NodeCancelledError) as error:
            await _invoke(graph)
        assert isinstance(error.value.__cause__, asyncio.CancelledError)
    else:
        state = await _invoke(graph)
        assert state["query_route"] == "out_of_scope" and state["sources"] == []


async def _public_query(monkeypatch, request: QueryRequest):
    from rag.api import main

    monkeypatch.setattr(main, "_graph", agent.build_graph())

    user = {"sub": "legal-resolution-test"}
    response = await main.query(request, user)
    streaming = await main.query_stream(request, user)
    events = []
    async for raw in streaming.body_iterator:
        event = raw.strip().removeprefix("data: ")
        if event != "[DONE]":
            events.append(json.loads(event))
    sources = next(x for x in events if x["type"] == "sources")
    assert sources["sources"] == [group.model_dump() for group in response.sources]
    assert response.query_route == sources["query_route"]
    assert response.answer == "".join(x["content"] for x in events if x["type"] == "token")
    return response


@pytest.mark.anyio
@pytest.mark.parametrize("route", ["needs_clarification", "in_scope"])
async def test_literal_citation_beyond_the_first_500_chars_in_json_and_sse(
    monkeypatch, tmp_path, route
):
    docs = _source("providencia")
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, route)
    _no_calls(monkeypatch)
    response = await _public_query(monkeypatch, QueryRequest(question=QUESTION))
    assert response.query_route == "in_scope"
    assert response.answer == f"- «[…] {DECISION}» [doc1]"
    fragment = response.sources[0].fragments[0]
    assert fragment.index == 1 and fragment.content == "[…] " + DECISION
    assert fragment.metadata["chunk_id"] == docs[1].id
    assert docs[1].page_content.index(DECISION) > 500


@pytest.mark.anyio
async def test_rescue_abstains_when_a_complete_passage_does_not_fit(monkeypatch, tmp_path):
    docs = _source("providencia", suffix=" " + "Alcance de la decisión. " * 30)
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "needs_clarification")
    _no_calls(monkeypatch)
    state = await _invoke(agent.build_graph())
    assert state["query_route"] == "needs_clarification"
    assert state["sources"] == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "admitted"),
    [
        (f"En segunda instancia, en el radicado {DOCKET}, se confirmó la sentencia [doc1].", True),
        (
            "En la sentencia de segunda instancia 47001-2332-000-2011-08425-02 se confirmó [doc1].",
            False,
        ),
        ("En primera instancia se confirmó la sentencia [doc1].", False),
        ("Se confirmó la sentencia apelada.", False),
        ("El Consejo de Estado, en primera instancia, confirmó la sentencia [doc1].", False),
        (
            "El Consejo de Estado resolvió en primera instancia y confirmó la sentencia [doc1].",
            False,
        ),
        ("En **primera instancia** se confirmó la sentencia [doc1].", False),
        ("Se estudió el recurso. En primera instancia se confirmó la sentencia [doc1].", False),
        (
            "En **segunda instancia** se modificó la sentencia apelada de primera instancia [doc1].",
            True,
        ),
        (
            "El Consejo de Estado modificó lo resuelto en primera instancia [doc1].",
            True,
        ),
        (
            "La Sala modificó la sentencia apelada. "
            "En primera instancia, el juez a quo había negado la demanda [doc1].",
            True,
        ),
    ],
)
async def test_in_scope_checks_equivalence_and_answer_attribution(
    monkeypatch, tmp_path, answer, admitted
):
    first, copy = _source("original"), _source("copia")
    _configured(monkeypatch, tmp_path, first + copy)
    _enrichment(monkeypatch, "in_scope")
    other = Document(page_content="Providencia sin relación", metadata={"chunk_id": "ajena"})
    calls = []

    class Retriever:
        async def ainvoke(self, query):
            calls.append(query)
            return [other, copy[1], first[1], first[0]]

    def get_retriever(**kwargs):
        assert kwargs == {"k": 8, "k_candidates": 8, "doc_types": ["jurisprudencia"]}
        return Retriever()

    monkeypatch.setattr(agent, "get_ensemble_retriever", get_retriever)
    monkeypatch.setattr(
        agent, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    monkeypatch.setattr(agent, "get_generation_llm", lambda: FakeListChatModel(responses=[answer]))
    response = await _public_query(monkeypatch, QueryRequest(question=GENERATION_QUESTION, k=2))
    assert calls == [GENERATION_QUESTION, GENERATION_QUESTION]
    if admitted:
        assert [f.metadata["chunk_id"] for group in response.sources for f in group.fragments] == [
            copy[1].id,
            first[0].id,
        ]
        assert response.answer == answer
    else:
        assert response.sources == []
        assert "respuesta verificable" in response.answer


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "admitted"),
    [
        ("En segunda instancia, en el radicado 9999, se confirmó la sentencia [doc1].", False),
        (
            "**Expediente n.º:** `9999`. Se confirmó la sentencia en segunda instancia [doc1].",
            False,
        ),
        ("En segunda instancia, en el radicado 1234, se confirmó la sentencia [doc1].", True),
        (
            "**Radicación número:** 1234. Se confirmó la sentencia del 8 de agosto de 2024 [doc1].",
            True,
        ),
        ("En segunda instancia se confirmó la sentencia del 8 de agosto de 2024 [doc1].", True),
        ("En el expediente radicado en 2024 se confirmó la sentencia [doc1].", True),
    ],
)
async def test_short_docket_conflicts_in_json_and_sse(monkeypatch, tmp_path, answer, admitted):
    docs = _source("providencia", docket="1234")
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "in_scope")

    class Retriever:
        async def ainvoke(self, query):
            return [docs[1]]

    monkeypatch.setattr(agent, "get_ensemble_retriever", lambda **_: Retriever())
    monkeypatch.setattr(
        agent, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    monkeypatch.setattr(agent, "get_generation_llm", lambda: FakeListChatModel(responses=[answer]))
    response = await _public_query(
        monkeypatch, QueryRequest(question=GENERATION_QUESTION.replace(DOCKET, "1234"))
    )
    assert response.query_route == "in_scope"
    if admitted:
        assert response.answer == answer
        assert response.sources[0].fragments[0].metadata["chunk_id"] == docs[1].id
    else:
        assert response.sources == []
        assert "respuesta verificable" in response.answer


@pytest.mark.anyio
@pytest.mark.parametrize(
    "predicate",
    [
        "sobre ejecutar las medidas de mitigación en dos meses desde el vencimiento anterior",
        "sobre ejecutar las medidas de mitigación en dos meses y la limpieza del canal",
        "sobre ejecutar las medidas de mitigación en dos (2) meses",
        "sobre ejecutar las medidas de mitigación en un plazo de dos meses",
        "sobre ejecutar las medidas de mitigación desde la ejecutoria",
        "a la Autoridad Portuaria sobre ejecutar las medidas de mitigación",
        "a la Autoridad Portuaria como responsable único de ejecutar las medidas de mitigación",
    ],
)
async def test_in_scope_requires_evidence_for_an_explicit_operative_premise(
    monkeypatch, tmp_path, predicate
):
    docs = _source("providencia")
    docs[1].page_content = (
        "PRIMERO: Ordenar al Municipio que ejecute las medidas de mitigación "
        "en el término de meses después del vencimiento anterior."
    )
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "in_scope")
    _no_calls(monkeypatch)
    response = await _public_query(
        monkeypatch,
        QueryRequest(
            question=f"¿Qué ordenó en segunda instancia {predicate} en el radicado {DOCKET}?"
        ),
    )
    assert response.query_route == "in_scope"
    assert response.sources == []
    assert "evidencia insuficiente" in response.answer


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("requested", "scope", "supported"),
    [
        ("en dos (2) meses", "en dos (2) meses.", True),
        ("en un plazo de dos meses", "en dos (2) meses.", True),
        ("en dos (3) meses", "en dos (2) meses.", False),
        ("en un plazo de 2,5 meses", "en cinco meses.", False),
        ("en dos (2) meses", "y en dos (2) meses rinda el informe.", False),
        ("en el plazo de dos meses", "y en el plazo de dos meses rinda el informe.", False),
    ],
)
async def test_in_scope_checks_number_and_act_of_a_legal_term(
    monkeypatch, tmp_path, requested, scope, supported
):
    docs = _source("providencia")
    docs[
        1
    ].page_content = f"PRIMERO: Ordenar al Municipio ejecutar las medidas de mitigación {scope}"
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "in_scope")
    _no_calls(monkeypatch)
    response = await _public_query(
        monkeypatch,
        QueryRequest(
            question=(
                "¿Qué ordenó en segunda instancia sobre ejecutar las medidas de mitigación "
                f"{requested} en el radicado {DOCKET}?"
            )
        ),
    )
    assert response.query_route == "in_scope"
    if supported:
        assert response.answer == f"- «{docs[1].page_content}» [doc1]"
        fragment = response.sources[0].fragments[0]
        assert fragment.content == docs[1].page_content
        assert fragment.metadata["chunk_id"] == docs[1].id
    else:
        assert response.sources == []
        assert "evidencia insuficiente" in response.answer


@pytest.mark.anyio
@pytest.mark.parametrize("variant", ["wrong_instance", "unidentified", "different", "incomplete"])
async def test_in_scope_without_documentary_identity_stops_before_generation(
    monkeypatch, tmp_path, variant
):
    docs = _source("principal")
    question = QUESTION
    if variant == "wrong_instance":
        question = QUESTION.replace("segunda instancia", "primera instancia")
    elif variant == "unidentified":
        question = QUESTION.replace(DOCKET, "05001-33-33-001-2015-00281-01")
    elif variant == "different":
        docs += _source("otra", suffix=" El fallo se modificó en otro numeral.")
    elif variant == "incomplete":
        docs += _source("copia")
    _configured(monkeypatch, tmp_path, docs)
    if variant == "incomplete":
        monkeypatch.setattr(agent, "bm25_documents", lambda: docs[:-1])
    _enrichment(monkeypatch, "in_scope")
    _no_calls(monkeypatch)
    state = await _invoke(agent.build_graph(), question=question)
    assert state["sources"] == []
    assert "evidencia insuficiente" in agent.extract_answer_from_state(state)
