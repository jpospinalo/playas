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
from langchain_core.runnables import RunnableLambda
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
PARTIAL_CARRERO_QUESTION = (
    "Solo tengo el número 08425 del proceso de erosión costera de Gabriel Carrero en Santa Marta "
    "y desconozco la instancia. ¿Cuál fue el plazo que fijó el fallo para cumplir la orden principal?"
)


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
@pytest.mark.parametrize(
    ("variant", "route"),
    [
        ("complete", "out_of_scope"),
        ("complete", "in_scope"),
        ("wrong_instance", "in_scope"),
        ("independent_report_only", "in_scope"),
        ("post_meeting_report", "in_scope"),
        ("missing_frequency", "in_scope"),
        ("notification_trigger", "in_scope"),
        ("ambiguous_orders", "in_scope"),
    ],
)
async def test_meeting_and_prior_report_require_one_joint_order_in_json_and_sse(
    monkeypatch, tmp_path, variant, route
):
    docs = _source("providencia")
    docs[0].page_content = f"Sentencia de primera instancia\nRadicado: {DOCKET}"
    meeting = (
        "La Magistrada Ponente convocará a reuniones bimestrales a partir de la ejecutoria "
        "del presente fallo, para su verificación y cumplimiento."
    )
    report = (
        "Previo a la realización de las reuniones, las autoridades deberán presentar "
        "informe escrito de sus gestiones y actuaciones."
    )
    combined = f"{meeting} {report}"
    passage = combined
    if variant == "independent_report_only":
        passage = meeting
    if variant == "post_meeting_report":
        passage = combined.replace("Previo a la realización de", "Después de")
    if variant == "missing_frequency":
        passage = combined.replace(" bimestrales", "")
    if variant == "notification_trigger":
        passage = combined.replace("ejecutoria", "notificación")
    if variant == "ambiguous_orders":
        passage += "\n\n" + combined.replace("bimestrales", "mensuales")
    docs[1].page_content = (
        f"SEXTO: Ordenar la integración de un comité.\n\n{passage}\n\n"
        "6.1.º Deberán presentar informes cada dos meses independientemente de las reuniones."
    )
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, route)
    _no_calls(monkeypatch)
    instance = "segunda" if variant == "wrong_instance" else "primera"
    response = await _public_query(
        monkeypatch,
        QueryRequest(
            question=(
                f"¿Qué ordenó en {instance} instancia sobre la frecuencia de reuniones de verificación "
                f"y los informes previos en el radicado {DOCKET}?"
            )
        ),
    )
    if variant == "complete":
        assert response.query_route == "in_scope"
        assert response.answer == f"- «[…] {combined} […]» [doc1]"
        (group,) = response.sources
        (fragment,) = group.fragments
        assert fragment.content == f"[…] {combined} […]"
        assert fragment.metadata["chunk_id"] == docs[1].id
    else:
        assert response.sources == [] and "evidencia insuficiente" in response.answer


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("variant", "route"),
    [
        ("complete", "out_of_scope"),
        ("complete", "in_scope"),
        ("copy_only", "in_scope"),
        ("return_only", "in_scope"),
        ("wrong_trigger_in_order", "in_scope"),
        ("wrong_trigger_in_question", "in_scope"),
        ("wrong_instance", "in_scope"),
        ("wrong_docket", "in_scope"),
        ("different_recipients", "in_scope"),
    ],
)
async def test_copy_and_return_require_both_orders_in_json_and_sse(
    monkeypatch, tmp_path, variant, route
):
    docs = _source("providencia")
    copy = (
        "SEGUNDO: En cumplimiento de lo dispuesto en la ley, REMÍTASE copia auténtica de "
        "ésta decisión a la Defensoría del Pueblo."
    )
    returned = (
        "TERCERO: Ejecutoriado este proveído, DEVUÉLVASE el expediente al Tribunal de origen."
    )
    orders = [copy, returned]
    if variant == "copy_only":
        orders = [copy]
    if variant == "return_only":
        orders = [returned]
    if variant == "wrong_trigger_in_order":
        orders[1] = returned.replace("Ejecutoriado", "Notificado")
    if variant == "different_recipients":
        orders.append(copy.replace("SEGUNDO", "CUARTO").replace("Defensoría", "Procuraduría"))
    docs[1].page_content = "\n\n".join([DECISION, *orders, "CÓPIESE, NOTIFÍQUESE."])
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, route)
    _no_calls(monkeypatch)

    instance = "primera" if variant == "wrong_instance" else "segunda"
    docket = "88001233100020100000001" if variant == "wrong_docket" else DOCKET
    trigger = "notificada" if variant == "wrong_trigger_in_question" else "ejecutoriada"
    request = QueryRequest(
        question=(
            f"En la {instance} instancia del radicado {docket}, ¿a quién se ordenó remitir "
            f"copia auténtica del fallo y qué debía hacerse con el expediente una vez {trigger} "
            "la providencia?"
        )
    )
    response = await _public_query(monkeypatch, request)
    if variant != "complete":
        assert response.sources == [] and "evidencia insuficiente" in response.answer
        return

    excerpt = f"[…] {copy}\n\n{returned} […]"
    assert response.query_route == "in_scope"
    assert response.answer == f"- «{excerpt}» [doc1]"
    (source,) = response.sources
    (fragment,) = source.fragments
    assert source.metadata["Radicado"] == DOCKET
    assert fragment.metadata["chunk_id"] == docs[1].id
    assert fragment.content == f"[…] {copy}  {returned} […]"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "question",
    [
        PARTIAL_CARRERO_QUESTION,
        "Tengo el radicado parcial 07652 y no sé en qué instancia se dictó la sentencia. "
        "¿Cuál fue el plazo que ordenó el tribunal?",
    ],
)
async def test_incomplete_judicial_reference_asks_for_clarification_in_json_and_sse(
    monkeypatch, tmp_path, question
):
    _configured(monkeypatch, tmp_path, _source("providencia"))
    _enrichment(monkeypatch, "in_scope")
    _no_calls(monkeypatch)

    response = await _public_query(monkeypatch, QueryRequest(question=question))

    assert response.query_route == "needs_clarification"
    assert "radicado completo, la instancia o la providencia" in response.answer
    assert response.sources == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("question", "requested", "enabled"),
    [
        (PARTIAL_CARRERO_QUESTION, ["normativa"], True),
        (PARTIAL_CARRERO_QUESTION, None, False),
        (PARTIAL_CARRERO_QUESTION.replace("08425", "8425"), None, True),
        (f"{PARTIAL_CARRERO_QUESTION} Encontré el radicado completo {DOCKET}.", None, True),
        (
            "Solo tengo el número 08425 del trámite de concesión marítima y desconozco la instancia. "
            "¿Cuál es el plazo para resolver ese trámite?",
            None,
            True,
        ),
    ],
)
async def test_incomplete_judicial_clarification_preserves_other_paths(
    monkeypatch, tmp_path, question, requested, enabled
):
    _configured(monkeypatch, tmp_path, _source("providencia"))
    if not enabled:
        monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_PATH", None)
    _enrichment(monkeypatch, "needs_clarification")
    _no_calls(monkeypatch)

    state = await _invoke(agent.build_graph(), question=question, doc_types=requested)

    assert state["query_route"] == "needs_clarification"
    assert state["messages"][-1].content == agent._CLARIFICATION_RESPONSE
    assert state["sources"] == []


@pytest.mark.anyio
async def test_complete_followup_recovers_the_verified_order_after_clarification(
    monkeypatch, tmp_path
):
    docs = _source("providencia")
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "needs_clarification")
    _no_calls(monkeypatch)
    graph = agent.build_graph()

    clarification = await _invoke(graph, question=PARTIAL_CARRERO_QUESTION)
    assert clarification["messages"][-1].content == agent._PROVIDENCIA_CLARIFICATION_RESPONSE

    decision = await _invoke(graph)
    assert decision["query_route"] == "in_scope"
    assert decision["messages"][-1].content == f"- «[…] {DECISION}» [doc1]"
    assert decision["sources"][0].id == docs[1].id


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
async def test_verified_generation_keeps_historical_ids_out_of_the_prompt(monkeypatch, tmp_path):
    historical_docket = "47001-2332-000-2011-08425-02"
    docs = _source(historical_docket)
    docs[1].metadata["summary"] = "Resumen ordinario disponible en el contexto."
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "in_scope")

    class Retriever:
        async def ainvoke(self, query):
            return [docs[1]]

    answer = f"En segunda instancia, en el radicado {DOCKET}, se confirmó la sentencia [doc1]."

    def generate(prompt):
        text = "\n".join(message.content for message in prompt.to_messages())
        assert historical_docket not in text
        assert f"radicado {DOCKET}, segunda instancia" in text
        assert "[doc1]" in text.splitlines() and DECISION in text
        assert docs[1].metadata["summary"] in text
        return answer

    monkeypatch.setattr(agent, "get_ensemble_retriever", lambda **_: Retriever())
    monkeypatch.setattr(
        agent, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    monkeypatch.setattr(agent, "get_generation_llm", lambda: RunnableLambda(generate))

    response = await _public_query(monkeypatch, QueryRequest(question=GENERATION_QUESTION))
    assert response.answer == answer
    fragment = response.sources[0].fragments[0]
    assert fragment.index == 1
    assert fragment.metadata["chunk_id"] == docs[1].metadata["chunk_id"]
    assert response.sources[0].source == docs[1].metadata["source"]


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
@pytest.mark.parametrize(("k", "unsupported_topic"), [(2, False), (3, False), (4, True)])
async def test_verified_order_completes_only_its_anchored_ordinal(
    monkeypatch, tmp_path, k, unsupported_topic
):
    docs = _source("providencia")
    summary = "El Plan Maestro es un instrumento de planificación."
    docs[1].page_content = "El fallo de primera instancia exigía cronogramas estrictos."
    docs[1].metadata["section_name"] = "Desarrollo procesal"
    parts = [
        "PRIMERO: Ordenar conformar una mesa de trabajo para adoptar el Plan Maestro de",
        "Erosión Costera y establecer los compromisos de las entidades según sus competencias.",
        "El plan se adoptará desde la ejecutoria.\ufffd SEGUNDO: Ordenar presentar otro informe.",
    ]
    for number, text in enumerate(parts, 1):
        ident = f"orden-{number}"
        metadata = {
            **docs[1].metadata,
            "chunk_id": ident,
            "section_name": "Decisión",
            "summary": summary,
        }
        docs.append(Document(id=ident, page_content=text, metadata=metadata))
    copies = [
        Document(
            id=f"copia-{doc.id}",
            page_content=doc.page_content,
            metadata={**doc.metadata, "chunk_id": f"copia-{doc.id}", "source": "copia.pdf"},
        )
        for doc in docs
    ]
    _configured(monkeypatch, tmp_path, docs + copies)
    _enrichment(monkeypatch, "in_scope")
    retrievals = []

    class Retriever:
        async def ainvoke(self, query):
            retrievals.append(query)
            if query == GENERATION_QUESTION:
                return [docs[2]]
            return [docs[1], docs[4], docs[2]]

    def generate(prompt):
        body = str(prompt.to_messages()[-1].content)
        assert GENERATION_QUESTION in body, "El ordinal documentado no llama al generador."
        assert summary in body
        return "La sentencia apelada figura en el expediente [doc1]."

    monkeypatch.setattr(agent, "get_ensemble_retriever", lambda **_: Retriever())
    monkeypatch.setattr(
        agent, "get_active_provider", lambda: SimpleNamespace(supports_system_role=True)
    )
    monkeypatch.setattr(agent, "get_generation_llm", lambda: RunnableLambda(generate))
    subject = (
        "la mesa de trabajo, el Plan Maestro de Erosión Costera y los compromisos de las entidades"
    )
    if unsupported_topic:
        subject += " y la nómina bancaria del comité"
    question = f"¿Qué ordenó en segunda instancia sobre {subject} en el radicado {DOCKET}?"
    result = await _public_query(monkeypatch, QueryRequest(question=question, k=k))
    assert retrievals == [question, question]
    if k == 2 or unsupported_topic:
        assert result.sources == [] and "evidencia insuficiente" in result.answer
    else:
        fragments = result.sources[0].fragments
        assert [f.metadata["chunk_id"] for f in fragments] == ["orden-1", "orden-2", "orden-3"]
        assert fragments[1].content == parts[1]
        assert fragments[2].content == "El plan se adoptará desde la ejecutoria. […]"
        assert [f.metadata["summary"] for f in fragments] == [summary] * 3
        assert all(d.metadata["summary"] == summary for d in docs[2:])
        assert result.answer.splitlines() == [
            f"Segunda instancia. Radicado {DOCKET}.",
            "",
            *(f"- «{f.content}» [doc{f.index}]" for f in fragments),
        ]

        graph = agent.build_graph()
        first_turn = await _invoke(graph, question=question, k=k)
        unsupported_deadline = (
            "¿Qué ordenó en segunda instancia sobre ejecutar las obras en dos meses "
            f"en el radicado {DOCKET}?"
        )
        early_stop = await _invoke(graph, question=unsupported_deadline, k=k)
        next_turn = await _invoke(graph, question=GENERATION_QUESTION, k=k)
        assert first_turn["documentary_answer"] == result.answer
        assert early_stop["sources"] == [] and early_stop["documentary_answer"] is None
        assert next_turn["documentary_answer"] is None
        assert (
            next_turn["messages"][-1].content
            == "La sentencia apelada figura en el expediente [doc1]."
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("order", "supported"),
    [
        (
            "ejecutar la evaluación semestral inmediatamente después de la aprobación del plan.",
            True,
        ),
        (
            "al Municipio que ejecute la evaluación semestral inmediatamente después "
            "de la aprobación del plan.",
            True,
        ),
        ("ejecutar la evaluación semestral después de la aprobación del plan.", False),
        ("ejecutar la evaluación semestral inmediatamente después de la ejecutoria.", False),
        (
            "ejecutar la evaluación semestral y remitir el informe inmediatamente "
            "después de la aprobación del plan.",
            False,
        ),
        (
            "ejecutar la evaluación semestral no inmediatamente después de la aprobación del plan.",
            False,
        ),
        (
            "ejecutar la evaluación semestral. SEGUNDO: Ordenar remitir el informe "
            "inmediatamente después de la aprobación del plan.",
            False,
        ),
        (
            "ejecutar la evaluación semestral. El cronograma se publica "
            "inmediatamente después de la aprobación del plan.",
            False,
        ),
        (
            "ejecutar la evaluación semestral y la Secretaría deberá remitir el informe "
            "inmediatamente después de la aprobación del plan.",
            False,
        ),
        (
            "remitir un informe de la evaluación semestral inmediatamente después "
            "de la aprobación del plan.",
            False,
        ),
        (
            "abstenerse de ejecutar la evaluación semestral inmediatamente después "
            "de la aprobación del plan.",
            False,
        ),
        (
            "evaluar si corresponde ejecutar la evaluación semestral inmediatamente "
            "después de la aprobación del plan.",
            False,
        ),
        (
            "al Municipio que evalúe si corresponde que ejecute la evaluación semestral "
            "inmediatamente después de la aprobación del plan.",
            False,
        ),
        (
            "dejar sin efectos la obligación de ejecutar la evaluación semestral "
            "inmediatamente después de la aprobación del plan.",
            False,
        ),
        (
            "al Municipio que publique el informe y la Secretaría deberá ejecutar la evaluación semestral "
            "inmediatamente después de la aprobación del plan.",
            False,
        ),
    ],
)
async def test_immediate_trigger_requires_the_same_act_and_event_in_json_and_sse(
    monkeypatch, tmp_path, order, supported
):
    docs = _source("providencia")
    docs[1].page_content = f"PRIMERO: Ordenar {order}"
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "in_scope")
    _no_calls(monkeypatch)
    question = (
        "¿Qué ordenó en segunda instancia sobre la evaluación semestral que debe comenzar "
        f"inmediatamente después de la aprobación del plan en el radicado {DOCKET}?"
    )
    response = await _public_query(monkeypatch, QueryRequest(question=question))
    if supported:
        assert response.sources[0].fragments[0].content == docs[1].page_content
        assert "[doc1]" in response.answer
    else:
        assert response.sources == [] and "evidencia insuficiente" in response.answer


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
@pytest.mark.parametrize(
    ("subject", "purpose", "supported"),
    [
        ("para recuperar el predio", "para que se recupere", True),
        ("para que se recupere el predio", "para que se recupere", True),
        ("para recuperar el predio en un plazo de seis meses", "para que se recupere", True),
        ("para recuperar el predio en un plazo de dos meses", "para que se recupere", False),
        (
            "para recuperar el predio en seis meses desde la ejecutoria",
            "para que se recupere",
            False,
        ),
        ("para recuperar el predio en un plazo de seis meses", "para que no se recupere", False),
        ("para recuperar el predio en un plazo de seis meses", "no para que se recupere", False),
    ],
)
async def test_recovery_purpose_keeps_the_term_with_its_own_order(
    monkeypatch, tmp_path, subject, purpose, supported
):
    docs = _source("providencia")
    order = (
        "- d) Ordenar al Municipio y a la DIMAR que a más tardar en el término de seis (6) meses, "
        f"realice los trámites {purpose} el predio."
    )
    docs[1].page_content = (
        "SEGUNDO: Modificar la sentencia apelada.\n"
        "- c) Ordenar al Municipio que en dos (2) meses radique el informe.\n"
        f"{order}"
    )
    _configured(monkeypatch, tmp_path, docs)
    _enrichment(monkeypatch, "in_scope")
    _no_calls(monkeypatch)
    question = (
        f"¿Qué ordenó en segunda instancia sobre los trámites {subject} en el radicado {DOCKET}?"
    )

    response = await _public_query(monkeypatch, QueryRequest(question=question))

    assert response.query_route == "in_scope"
    if supported:
        assert response.answer == f"- «[…] {order}» [doc1]"
        fragment = response.sources[0].fragments[0]
        assert fragment.content == f"[…] {order}"
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
