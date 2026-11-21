"""Portable body-backed taxonomy fixtures; no corpus files, clients or models."""

from __future__ import annotations

import copy
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.documents import Document

from rag.core.normative_context import select_verified_article_context as select

QUESTION = (
    "Según el artículo 9 de la Ley 222 de 2025, ¿cómo se clasifican los parques y los puertos?"
)


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("These contracts must not connect to any service")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def article():
    bodies = [
        "I. Componentes naturales\n1. Áreas naturales\na) Zonas verdes:\nLos parques forman parte de estas áreas naturales.",
        "La conservación del paisaje se mantiene según sus condiciones ambientales.",
        "Las condiciones de ordenamiento territorial se verifican periódicamente.",
        "La administración informa sus determinaciones a las autoridades competentes.",
        "II. Componentes construidos\n1. Infraestructura\na) Instalaciones:",
        "1. Infraestructura\na) Instalaciones:\nLos puertos forman parte de estas instalaciones construidas.",
        "Los puertos forman parte de estas instalaciones construidas.\nb) Obras complementarias:",
        "La autoridad dispone reglas generales de conservación y mantenimiento.",
    ]
    ids = ["hist-77", "old-2", "legacy-901", "doc-11", "old-53", "hist-1", "legacy-804", "old-20"]
    return [
        Document(
            id=key,
            page_content=body,
            metadata={
                "doc_type": "normativa",
                "norma": "Ley 222 de 2025",
                "articulo": "9",
                "source": "ley_fixture.md",
                "chunk_index": i,
                "total_chunks_in_section": 8,
                "section_index": 3,
            },
        )
        for i, (key, body) in enumerate(zip(ids, bodies, strict=True))
    ]


def single(norma="Decreto 4440 de 2008", articulo="1"):
    return [
        Document(
            id="historical-single-81",
            page_content="El uso de las playas queda sujeto a la reglamentación correspondiente.",
            metadata={
                "doc_type": "normativa",
                "norma": norma,
                "articulo": articulo,
                "source": "single.md",
                "chunk_index": 0,
                "total_chunks_in_section": 1,
                "section_index": 1,
            },
        )
    ]


@pytest.mark.parametrize(
    "variant", ["base", "reversed", "k3", "normativa", "uppercase", "mixed_types"]
)
def test_preserves_original_objects_and_authentic_parent(variant):
    docs = article()
    before = [doc.model_dump() for doc in docs]
    query = QUESTION.upper() if variant == "uppercase" else QUESTION
    original_filter = ["normativa"] if variant == "normativa" else None
    if variant == "mixed_types":
        original_filter = ["normativa", "jurisprudencia"]
    incoming = list(reversed(docs)) if variant == "reversed" else docs
    result = select(query, original_filter, incoming, 3 if variant == "k3" else 4)
    assert result is not None
    assert len(result) == 3
    assert all(
        actual is expected
        for actual, expected in zip(result, [docs[0], docs[4], docs[5]], strict=True)
    )
    assert [doc.model_dump() for doc in docs] == before
    assert "II. Componentes construidos" in result[1].page_content
    assert "Los puertos" in result[2].page_content


@pytest.mark.parametrize(
    ("norma", "number"), [("Decreto 4440 de 2008", "1"), ("Decreto 415 de 2017", "2.2.4.2.3.5")]
)
def test_independent_single_fragment_articles(norma, number):
    docs = single(norma, number)
    result = select(
        f"Según el artículo {number} del {norma}, ¿cómo se clasifican las playas?", None, docs
    )
    assert result == docs
    assert result[0] is docs[0]


@pytest.mark.parametrize("reverse", [False, True])
def test_independent_three_fragment_taxonomy_without_id_order_assumptions(reverse):
    docs = article()
    docs = [docs[0], docs[4], docs[5]]
    for i, doc in enumerate(docs):
        doc.metadata.update(
            norma="Resolución 876 de 2024",
            articulo="12",
            source="resolucion.md",
            chunk_index=i,
            total_chunks_in_section=3,
        )
    incoming = list(reversed(docs)) if reverse else docs
    result = select(
        "Según el artículo 12 de la Resolución 876 de 2024, ¿cómo se clasifican los parques y los puertos?",
        None,
        incoming,
    )
    assert result is not None
    assert all(actual is expected for actual, expected in zip(result, docs, strict=True))


NEGATIVE_CASES = [
    "missing_act",
    "missing_year",
    "wrong_year",
    "wrong_act_type",
    "wrong_article",
    "article_suffix_A",
    "article_bis",
    "article_hyphen_bis",
    "singular_article_list",
    "plural_articles",
    "multiple_acts",
    "literal",
    "numeral",
    "paragrafo",
    "inciso",
    "jurisprudencia_filter",
    "complex_filter",
    "unknown_filter",
    "string_filter",
    "missing_chunk",
    "single_incomplete",
    "missing_order",
    "duplicate_order",
    "forged_unique_order",
    "missing_section",
    "incoherent_section",
    "missing_source",
    "ambiguous_source",
    "budget_two",
    "unsupported_heading",
    "unknown_object",
    "no_taxonomy_intent",
    "noninteger_order",
    "dotted_article_suffix_A",
    "multiple_years",
    "missing_metadata_identity",
]


@pytest.mark.parametrize("variant", NEGATIVE_CASES)
def test_unsupported_or_unverified_input_keeps_the_fallback(variant):
    docs, query, filt, k = article(), QUESTION, None, 4
    query_changes = {
        "missing_act": ("Ley 222 de 2025", "la norma"),
        "missing_year": (" de 2025", ""),
        "wrong_year": ("2025", "2023"),
        "wrong_act_type": ("Ley", "Decreto"),
        "wrong_article": ("artículo 9", "artículo 99"),
        "article_suffix_A": ("artículo 9", "artículo 9A"),
        "article_bis": ("artículo 9", "artículo 9 bis"),
        "article_hyphen_bis": ("artículo 9", "artículo 9-bis"),
        "singular_article_list": ("artículo 9", "artículo 9 y 10"),
        "plural_articles": ("artículo 9", "artículos 9 y 10"),
        "unknown_object": ("puertos", "dragones"),
        "no_taxonomy_intent": ("cómo se clasifican", "quién autoriza"),
        "dotted_article_suffix_A": ("artículo 9", "artículo 9.1A"),
        "multiple_years": ("2025", "2025 y 2024"),
    }
    if variant in query_changes:
        query = query.replace(*query_changes[variant])
    elif variant == "multiple_acts":
        query += " Compare el Decreto 4440 de 2008."
    elif variant in {"literal", "numeral", "paragrafo", "inciso"}:
        query += {
            "literal": " Del literal b.",
            "numeral": " Del numeral 1.",
            "paragrafo": " Del parágrafo 1.",
            "inciso": " Del inciso 1.",
        }[variant]
    elif variant == "jurisprudencia_filter":
        filt = ["jurisprudencia"]
    elif variant == "complex_filter":
        filt = {"normativa": True}
    elif variant == "unknown_filter":
        filt = ["normativa", "desconocido"]
    elif variant == "string_filter":
        filt = "normativa"
    elif variant == "missing_chunk":
        docs.pop()
    elif variant == "single_incomplete":
        docs = docs[:1]
    elif variant == "missing_order":
        docs[0].metadata.pop("chunk_index")
    elif variant == "duplicate_order":
        docs[1].metadata["chunk_index"] = 0
    elif variant == "forged_unique_order":
        docs[4].metadata["chunk_index"], docs[5].metadata["chunk_index"] = 5, 4
    elif variant == "missing_section":
        docs[0].metadata.pop("section_index")
    elif variant == "incoherent_section":
        docs[0].metadata["section_index"] = 80
    elif variant == "missing_source":
        docs[0].metadata.pop("source")
    elif variant == "ambiguous_source":
        extra = copy.deepcopy(docs[0])
        extra.id, extra.metadata["source"] = "ambiguous-id", "other.md"
        docs.append(extra)
    elif variant == "budget_two":
        k = 2
    elif variant == "unsupported_heading":
        docs[0].page_content = docs[0].page_content.replace(
            "I. Componentes naturales", "Categoría natural"
        )
    elif variant == "noninteger_order":
        docs[0].metadata["chunk_index"] = 0.0
    elif variant == "missing_metadata_identity":
        for doc in docs:
            doc.metadata.pop("norma")
    assert select(query, filt, docs, k) is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", []),
        ("total_chunks_in_section", True),
        ("section_index", -1),
        ("id", {"invalid": "id"}),
    ],
)
def test_malformed_metadata_falls_back_without_exceptions(field, value):
    docs = article()
    docs[0].metadata[field] = value
    assert select(QUESTION, None, docs) is None


def state():
    return {
        "question": QUESTION,
        "sources": [],
        "doc_types": ["normativa"],
        "requested_doc_types": None,
        "k": 4,
        "k_candidates": 8,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "variant",
    [
        "off",
        "no_index",
        "unverified",
        "missing_original",
        "missing_snapshot",
        "verified_docket",
        "juris_filter",
    ],
)
async def test_node_gates_preserve_existing_retrieval(monkeypatch, variant):
    from rag.core import agent

    docs, incoming = article(), state()
    fallback = Document(
        id="fallback", page_content="Existing hybrid context.", metadata={"doc_type": "normativa"}
    )
    retriever = SimpleNamespace(ainvoke=AsyncMock(return_value=[fallback]))
    calls = []

    def observed_factory(**kwargs):
        calls.append(kwargs)
        return retriever

    monkeypatch.setattr(agent, "get_ensemble_retriever", observed_factory)
    index = (
        None
        if variant == "no_index"
        else SimpleNamespace(snapshot_verified=variant != "unverified")
    )
    if variant == "missing_original":
        incoming.pop("requested_doc_types")
    if variant == "verified_docket":
        incoming["verified_docket"] = "known-existing-docket"
    if variant == "juris_filter":
        incoming.update(requested_doc_types=["jurisprudencia"], doc_types=["jurisprudencia"])
    result = await agent.retrieve_forced_node(
        incoming,
        verify_docket=variant != "off",
        resolution_index=index,
        verified_documents=None if variant == "missing_snapshot" else tuple(docs),
    )
    assert result["sources"] == [fallback]
    assert retriever.ainvoke.await_count == 1
    assert calls[0]["k"] == 4 and calls[0]["k_candidates"] == 8
    assert calls[0]["doc_types"] == incoming["doc_types"]


@pytest.mark.anyio
async def test_node_uses_only_bound_verified_snapshot_and_original_question(monkeypatch):
    from rag.core import agent

    docs = article()
    monkeypatch.setattr(
        agent,
        "get_ensemble_retriever",
        lambda **kwargs: pytest.fail("No retrieval for proven packet"),
    )
    monkeypatch.setattr(
        agent, "bm25_documents", lambda: pytest.fail("Must not read a different global snapshot")
    )
    incoming = state()
    incoming["enriched_query"] = "Compare el Decreto 999 de 2000 y otro artículo."
    result = await agent.retrieve_forced_node(
        incoming,
        verify_docket=True,
        resolution_index=SimpleNamespace(snapshot_verified=True),
        verified_documents=tuple(docs),
    )
    assert all(
        actual is expected
        for actual, expected in zip(result["sources"], [docs[0], docs[4], docs[5]], strict=True)
    )
    assert result["verified_docket"] is None and result["verified_instance"] is None
    assert result["documentary_answer"] is None


@pytest.mark.anyio
async def test_unverified_docket_is_rejected_before_normative_context(monkeypatch):
    from rag.core import agent

    incoming = state()
    incoming["question"] = (
        "¿Qué ordenó en primera instancia sobre el plazo de recuperación, "
        "en el radicado 47001233300020180036800?"
    )
    assert agent.has_docket_intent(incoming["question"])
    monkeypatch.setattr(
        agent,
        "select_verified_article_context",
        lambda *args: pytest.fail("Docket proof must come first"),
    )
    monkeypatch.setattr(
        agent, "get_ensemble_retriever", lambda **kwargs: pytest.fail("No unverified docket search")
    )
    index = SimpleNamespace(snapshot_verified=True, docket_evidence=lambda question: None)
    result = await agent.retrieve_forced_node(
        incoming, verify_docket=True, resolution_index=index, verified_documents=tuple(article())
    )
    assert result == {"sources": []}
