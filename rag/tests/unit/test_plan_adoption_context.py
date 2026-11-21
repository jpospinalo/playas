"""Named-plan adoption contracts with portable bodies and no services."""

from __future__ import annotations

import json
import socket
from collections import Counter
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage

from rag.api.query_support import _build_graph_input
from rag.api.schemas import QueryRequest
from rag.core import agent
from rag.core.query_enricher import EnrichedQuery

NAME = "Plan de Gestión de la Franja Azul"
QUESTION = f"¿A qué órgano corresponde adoptar el {NAME}?"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Plan contracts must not connect to services")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


def documents():
    base = {
        "doc_type": "normativa",
        "source": "independent_plan.md",
        "norma": "Decreto 987 de 2024",
        "chunk_index": 0,
        "total_chunks_in_section": 1,
    }
    rows = [
        (
            "historic-91",
            "1",
            1,
            "Identidad",
            f"Se establece el {NAME} -PGFA- para la franja costera.",
        ),
        (
            "legacy-2",
            "3",
            3,
            "Formulación y adopción del PGFA",
            "Formulación y adopción del PGFA. La formulación del PGFA estará a cargo de la Oficina Técnica y su adopción estará en cabeza de la Junta Territorial.",
        ),
        (
            "old-779",
            "4",
            4,
            "Implementación y ejecución del PGFA",
            "Corresponde a la Oficina Logística coordinar la ejecución del PGFA.",
        ),
    ]
    return [
        Document(
            id=ident,
            page_content=body,
            metadata=dict(
                base, chunk_id=ident, articulo=number, section_index=section, articulo_titulo=title
            ),
        )
        for ident, number, section, title, body in rows
    ]


def configure(monkeypatch, tmp_path: Path, docs):
    rows = []
    positions = Counter()
    for doc in docs:
        source = doc.metadata["source"]
        positions[source] += 1
        meta = json.dumps(doc.metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        rows.append(
            {
                "id": doc.id,
                "document_source": {"path": source + ".jsonl", "line": positions[source]},
                "page_content_sha256": sha256(doc.page_content.encode()).hexdigest(),
                "metadata_payload_sha256": sha256(meta.encode()).hexdigest(),
            }
        )
    data = json.dumps({"vector_records": rows}).encode()
    path = tmp_path / "plan_provenance.json"
    path.write_bytes(data)
    monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_PATH", str(path))
    monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_SHA256", sha256(data).hexdigest())
    monkeypatch.setattr(agent, "bm25_documents", lambda: docs)


def setup_graph(monkeypatch, tmp_path, route):
    docs = documents()
    configure(monkeypatch, tmp_path, docs)

    async def analyze(question, history):
        return EnrichedQuery(
            route=route,
            standalone_question=question,
            expanded_query=question,
            doc_types=["normativa"] if route == "in_scope" else [],
        )

    monkeypatch.setattr(agent, "enrich_query_async", analyze)
    fallback = SimpleNamespace(ainvoke=AsyncMock(return_value=[docs[0], docs[2]]))
    monkeypatch.setattr(agent, "get_ensemble_retriever", lambda **kwargs: fallback)
    monkeypatch.setattr(
        agent, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    monkeypatch.setattr(
        agent,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["La Junta Territorial adopta el plan [doc2]."]),
    )
    return agent.build_graph(), docs, fallback


@pytest.mark.anyio
async def test_verified_plan_admits_only_with_its_authority_packet(monkeypatch, tmp_path):
    graph, docs, fallback = setup_graph(monkeypatch, tmp_path, "needs_clarification")
    request = QueryRequest(question=QUESTION)
    result = await graph.ainvoke(
        _build_graph_input(request, [HumanMessage(content=QUESTION)]),
        config={"configurable": {"thread_id": "plan-first-turn"}},
    )
    assert result["query_route"] == "in_scope"
    assert [doc.id for doc in result["sources"]] == [docs[0].id, docs[1].id]
    fallback.ainvoke.assert_not_awaited()


@pytest.mark.anyio
async def test_public_json_and_sse_cite_adoption_not_execution(monkeypatch, tmp_path):
    from rag.api import main

    graph, docs, fallback = setup_graph(monkeypatch, tmp_path, "in_scope")
    monkeypatch.setattr(main, "_graph", graph)
    request = QueryRequest(question=QUESTION)
    response = await main.query(request, {"sub": "independent-plan-test"})
    streaming = await main.query_stream(request, {"sub": "independent-plan-test"})
    events = []
    async for raw in streaming.body_iterator:
        value = raw.strip().removeprefix("data: ")
        if value != "[DONE]":
            events.append(json.loads(value))
    fragments = [f for group in response.sources for f in group.fragments]
    assert [f.metadata["chunk_id"] for f in fragments] == [docs[0].id, docs[1].id]
    assert fragments[1].index == 2 and "Junta Territorial" in fragments[1].content
    sources = next(e for e in events if e["type"] == "sources")
    assert sources["sources"] == [g.model_dump() for g in response.sources]
    assert response.answer == "".join(e["content"] for e in events if e["type"] == "token")
    assert "[doc2]" in response.answer
    fallback.ainvoke.assert_not_awaited()


@pytest.mark.parametrize("form", ["linked", "direct"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("types", [None, ["normativa"], ["jurisprudencia", "normativa"]])
def test_pure_packet_preserves_original_documents_and_fields(form, reverse, types):
    from rag.core.normative_context import select_verified_plan_adoption_context

    docs = documents()
    if form == "direct":
        docs[
            1
        ].page_content = "Formulación y adopción del PGFA. La adopción del PGFA estará en cabeza de la Junta Territorial."
    before = [d.model_dump() for d in docs]
    result = select_verified_plan_adoption_context(
        QUESTION, types, list(reversed(docs)) if reverse else docs, 2
    )
    assert result is not None and len(result) == 2
    assert result[0] is docs[0] and result[1] is docs[1]
    assert [d.model_dump() for d in docs] == before


NEGATIVES = [
    "unknown_name",
    "unnamed",
    "two_plans",
    "formulate",
    "execute",
    "juris",
    "empty_filter",
    "unknown_filter",
    "string_filter",
    "dict_in_filter",
    "k1",
    "k5",
    "bool_k",
    "no_identity",
    "no_authority",
    "wrong_source",
    "wrong_norma",
    "no_source",
    "no_norma",
    "no_alias",
    "two_aliases",
    "two_identity_sources",
    "two_authority_articles",
    "partial_count",
    "bool_count",
    "no_order",
    "bool_order",
    "negative_section",
    "no_article",
    "article_suffix",
    "wrong_title",
    "body_title_differs",
    "execution_clause",
    "other_plan",
    "unbound_pronoun",
    "two_linked",
    "direct_other_direct",
    "direct_other_pronoun",
    "direct_long_other_plan",
    "duplicate_object",
    "malformed_metadata",
]


@pytest.mark.parametrize("variant", NEGATIVES)
def test_pure_packet_declines_missing_or_ambiguous_proof(variant):
    import copy

    from rag.core.normative_context import select_verified_plan_adoption_context

    docs = documents()
    question, types, k = QUESTION, None, 4
    if variant == "unknown_name":
        question = QUESTION.replace("Franja Azul", "Lunazul Remota")
    elif variant == "unnamed":
        question = "¿Qué autoridad debe adoptar ese plan?"
    elif variant == "two_plans":
        question = QUESTION[:-1] + " y el Plan Interior?"
    elif variant == "formulate":
        question = QUESTION.replace("adoptar", "formular")
    elif variant == "execute":
        question = QUESTION.replace("adoptar", "ejecutar")
    elif variant == "juris":
        types = ["jurisprudencia"]
    elif variant == "empty_filter":
        types = []
    elif variant == "unknown_filter":
        types = ["otro"]
    elif variant == "string_filter":
        types = "normativa"
    elif variant == "dict_in_filter":
        types = [{}]
    elif variant == "k1":
        k = 1
    elif variant == "k5":
        k = 5
    elif variant == "bool_k":
        k = True
    elif variant == "no_identity":
        docs.pop(0)
    elif variant == "no_authority":
        docs.pop(1)
    elif variant == "wrong_source":
        docs[1].metadata["source"] = "different.md"
    elif variant == "wrong_norma":
        docs[1].metadata["norma"] = "Ley 998 de 2025"
    elif variant == "no_source":
        docs[0].metadata.pop("source")
    elif variant == "no_norma":
        docs[0].metadata.pop("norma")
    elif variant == "no_alias":
        docs[0].page_content = f"Se establece el {NAME} para la franja."
    elif variant == "two_aliases":
        docs[0].page_content += f" También el {NAME} -OTRO-."
    elif variant == "two_identity_sources":
        other = copy.deepcopy(docs[0])
        other.metadata["source"] = "another.md"
        other.id = "independent-old"
        docs.append(other)
    elif variant == "two_authority_articles":
        other = copy.deepcopy(docs[1])
        other.metadata["articulo"] = "19"
        other.id = "independent-authority"
        docs.append(other)
    elif variant == "partial_count":
        docs[1].metadata["total_chunks_in_section"] = 2
    elif variant == "bool_count":
        docs[1].metadata["total_chunks_in_section"] = True
    elif variant == "no_order":
        docs[1].metadata.pop("chunk_index")
    elif variant == "bool_order":
        docs[1].metadata["chunk_index"] = False
    elif variant == "negative_section":
        docs[1].metadata["section_index"] = -1
    elif variant == "no_article":
        docs[1].metadata.pop("articulo")
    elif variant == "article_suffix":
        docs[1].metadata["articulo"] = "3A"
    elif variant == "wrong_title":
        docs[1].metadata["articulo_titulo"] = "Adopción de otro plan"
    elif variant == "body_title_differs":
        docs[1].page_content = docs[1].page_content.replace(
            "Formulación y adopción del PGFA.", "Reglas del territorio."
        )
    elif variant == "execution_clause":
        docs[1].page_content = docs[1].page_content.replace("su adopción", "la ejecución")
    elif variant == "other_plan":
        docs[
            1
        ].page_content = "Formulación y adopción del PGFA. Respecto del Plan Interior, su adopción estará en cabeza de la Junta Territorial."
    elif variant == "unbound_pronoun":
        docs[
            1
        ].page_content = (
            "Formulación y adopción del PGFA. Su adopción estará en cabeza de la Junta Territorial."
        )
    elif variant == "two_linked":
        docs[1].page_content += " La adopción corresponderá al Comité Local."
    elif variant in {"direct_other_direct", "direct_other_pronoun", "direct_long_other_plan"}:
        docs[
            1
        ].page_content = "Formulación y adopción del PGFA. La adopción del PGFA estará en cabeza de la Junta Territorial."
        if variant == "direct_other_direct":
            docs[1].page_content += " La adopción del Plan Interior estará en cabeza del Comité."
        elif variant == "direct_other_pronoun":
            docs[
                1
            ].page_content += (
                " Respecto del Plan Interior, su adopción estará en cabeza del Comité."
            )
        else:
            docs[1].page_content += (
                " La adopción del Plan de "
                + "Gestión del Interior " * 15
                + " estará en cabeza del Comité."
            )
    elif variant == "duplicate_object":
        docs[1].page_content = docs[0].page_content + " " + docs[1].page_content
        docs = [docs[1]]
    elif variant == "malformed_metadata":
        docs[0].metadata = None
    else:
        raise AssertionError(variant)
    assert select_verified_plan_adoption_context(question, types, docs, k) is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "variant",
    ["disabled", "bad_provenance", "juris_filter", "k1", "history", "out_of_scope", "conversation"],
)
async def test_graph_preserves_terminal_routes_and_unproven_context(monkeypatch, tmp_path, variant):
    route = variant if variant in {"out_of_scope", "conversation"} else "needs_clarification"
    graph, docs, fallback = setup_graph(monkeypatch, tmp_path, route)
    if variant == "disabled":
        monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
        graph = agent.build_graph()
    if variant == "bad_provenance":
        monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_SHA256", "0" * 64)
        graph = agent.build_graph()
    request = QueryRequest(
        question=QUESTION,
        doc_types=["jurisprudencia"] if variant == "juris_filter" else None,
        k=1 if variant == "k1" else 4,
    )
    messages = [HumanMessage(content=QUESTION)]
    if variant == "history":
        messages.insert(0, HumanMessage(content="Pregunta anterior sobre otra playa"))
    result = await graph.ainvoke(
        _build_graph_input(request, messages),
        config={"configurable": {"thread_id": "gate-" + variant}},
    )
    assert result["query_route"] == route and result["sources"] == []
    fallback.ainvoke.assert_not_awaited()


@pytest.mark.anyio
async def test_proven_plan_discards_a_rewrite_about_a_different_plan(monkeypatch, tmp_path):
    from langchain_core.runnables import RunnableLambda

    graph, docs, fallback = setup_graph(monkeypatch, tmp_path, "needs_clarification")

    async def analyze(question, history):
        return EnrichedQuery(
            route="needs_clarification",
            standalone_question="¿Quién adopta el Plan Interior?",
            expanded_query="Plan Interior adopción órgano",
            doc_types=[],
        )

    monkeypatch.setattr(agent, "enrich_query_async", analyze)
    captured = []

    def generation(prompt):
        captured.append(prompt.to_string())
        return "La Junta Territorial adopta el plan [doc2]."

    monkeypatch.setattr(agent, "get_generation_llm", lambda: RunnableLambda(generation))
    request = QueryRequest(question=QUESTION)
    result = await graph.ainvoke(
        _build_graph_input(request, [HumanMessage(content=QUESTION)]),
        config={"configurable": {"thread_id": "bad-rewrite"}},
    )
    assert result["standalone_question"] == QUESTION and result["enriched_query"] == QUESTION
    assert captured and "Plan Interior" not in captured[0]
    assert [d.id for d in result["sources"]] == [docs[0].id, docs[1].id]


@pytest.mark.anyio
async def test_second_turn_does_not_reuse_or_readmit_the_previous_packet(monkeypatch, tmp_path):
    graph, docs, fallback = setup_graph(monkeypatch, tmp_path, "needs_clarification")
    config = {"configurable": {"thread_id": "two-plan-turns"}}
    request = QueryRequest(question=QUESTION)
    first = await graph.ainvoke(
        _build_graph_input(request, [HumanMessage(content=QUESTION)]), config=config
    )
    assert first["query_route"] == "in_scope" and len(first["sources"]) == 2
    second = await graph.ainvoke(
        _build_graph_input(request, [HumanMessage(content=QUESTION)]), config=config
    )
    assert second["query_route"] == "needs_clarification" and second["sources"] == []
    assert second.get("documentary_answer") is None and second.get("verified_docket") is None
    fallback.ainvoke.assert_not_awaited()


JUDICIAL_RESERVES = [
    "¿Qué ordenó en primera instancia sobre el apoyo técnico, documental y logístico en el radicado 47001233300020180036800?",
    *[
        f"¿Qué resolvió en {instance} instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado {docket}?"
        for docket in [
            "05837-33-33-001-2015-00281-01",
            "05837333300120150028101",
            "05001-33-33-001-2015-00281-01",
            "05001333300120150028101",
        ]
        for instance in ["segunda", "primera", "única"]
    ],
]


@pytest.mark.anyio
@pytest.mark.parametrize("question", JUDICIAL_RESERVES)
async def test_plan_route_cannot_rescue_unverified_judicial_identity_in_json_or_sse(
    monkeypatch, tmp_path, question
):
    from rag.api import main

    graph, _, _ = setup_graph(monkeypatch, tmp_path, "in_scope")
    monkeypatch.setattr(main, "_graph", graph)
    monkeypatch.setattr(
        agent,
        "get_ensemble_retriever",
        lambda **_: pytest.fail("Judicial proof must precede plan selection"),
    )
    monkeypatch.setattr(
        agent, "get_generation_llm", lambda: pytest.fail("No generation without judicial proof")
    )
    response = await main.query(QueryRequest(question=question), {"sub": "plan-negative-reserves"})
    stream = await main.query_stream(
        QueryRequest(question=question), {"sub": "plan-negative-reserves"}
    )
    events = []
    async for raw in stream.body_iterator:
        text = raw.strip().removeprefix("data: ")
        if text != "[DONE]":
            events.append(json.loads(text))
    assert response.sources == [] and "evidencia insuficiente" in response.answer
    assert next(e for e in events if e["type"] == "sources")["sources"] == []
    assert response.answer == "".join(e["content"] for e in events if e["type"] == "token")


@pytest.mark.anyio
async def test_long_literal_plan_keeps_original_question_and_expansion_word_limit(
    monkeypatch, tmp_path
):
    _, docs, fallback = setup_graph(monkeypatch, tmp_path, "needs_clarification")
    long_name = "Plan de " + "la " * 40 + "Costa Azul"
    question = f"¿A qué órgano corresponde adoptar el {long_name}?"
    assert len(question.split()) > 45
    docs[0].page_content = docs[0].page_content.replace(NAME, long_name)
    configure(monkeypatch, tmp_path, docs)
    graph = agent.build_graph()
    request = QueryRequest(question=question)
    result = await graph.ainvoke(
        _build_graph_input(request, [HumanMessage(content=question)]),
        config={"configurable": {"thread_id": "bounded-original-expansion"}},
    )
    assert result["query_route"] == "in_scope"
    assert result["standalone_question"] == question
    assert len(result["enriched_query"].split()) <= 45
    assert len(result["enriched_query"]) <= 1000
    assert [d.id for d in result["sources"]] == [docs[0].id, docs[1].id]
    fallback.ainvoke.assert_not_awaited()


@pytest.mark.parametrize("variant", ["same_body", "separate_body", "different_norma"])
def test_alias_scope_rejects_a_second_plan_only_in_the_same_source_and_norma(variant):
    from rag.core.normative_context import select_verified_plan_adoption_context

    docs = documents()
    declaration = " Se establece el Plan de Gestión del Interior -PGFA- para otra zona."
    if variant == "same_body":
        docs[0].page_content += declaration
    else:
        other = Document(
            id="other-plan-509",
            page_content=declaration,
            metadata=dict(
                docs[0].metadata,
                chunk_id="other-plan-509",
                articulo="5",
                section_index=5,
                articulo_titulo="Identidad de otro plan",
            ),
        )
        if variant == "different_norma":
            other.metadata["norma"] = "Ley 998 de 2025"
        docs.append(other)
    result = select_verified_plan_adoption_context(QUESTION, None, docs, 4)
    if variant == "different_norma":
        assert result is not None and result[0] is docs[0] and result[1] is docs[1]
    else:
        assert result is None
