"""T3.1 — instrumentación de observabilidad conectada al grafo real.

Complementa `test_observability.py` (que prueba las piezas en aislamiento):
aquí se verifica que `enrich_query_node`, `retrieve_forced_node` y
`generate_node` efectivamente invocan esa instrumentación durante una
ejecución real del grafo, y que ninguna ejecución filtra el texto de la
pregunta ni del contenido de los documentos en los logs — solo nombres de
etapa/ruta y conteos.
"""

from __future__ import annotations

import logging
import re
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage

import rag.core.agent as agent_module
from rag.core.query_enricher import EnrichedQuery

_SENTINEL_QUESTION = "¿Puede DIMAR sancionar un chiringuito clandestino en Playa Zafiro Oculta?"
_SENTINEL_DOC_TEXT = "TEXTO_LITERAL_DEL_FRAGMENTO_QUE_NUNCA_DEBE_APARECER_EN_UN_LOG"


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
async def test_in_scope_run_logs_all_three_stage_timers_without_leaking_question(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
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
            return [
                Document(page_content=_SENTINEL_DOC_TEXT, metadata={"chunk_id": "1"}),
                Document(page_content=_SENTINEL_DOC_TEXT, metadata={"chunk_id": "2"}),
            ]

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
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta con cita [doc1]."]),
    )

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        result = await agent_module.build_graph().ainvoke(
            _state(_SENTINEL_QUESTION),
            config={"configurable": {"thread_id": "obs-in-scope"}},
        )

    assert result["query_route"] == "in_scope"

    stage_messages = [r.message for r in caplog.records if r.message.startswith("stage=")]
    stages_logged = {m.split()[0].split("=")[1] for m in stage_messages}
    assert stages_logged == {"enrich_query", "retrieve_forced", "generate"}

    retrieve_msg = next(m for m in stage_messages if "stage=retrieve_forced" in m)
    assert "doc_count=2" in retrieve_msg
    generate_msg = next(m for m in stage_messages if "stage=generate" in m)
    assert "doc_count=2" in generate_msg
    enrich_msg = next(m for m in stage_messages if "stage=enrich_query" in m)
    assert "route=in_scope" in enrich_msg

    full_output = "\n".join(r.message for r in caplog.records)
    assert _SENTINEL_QUESTION not in full_output
    assert _SENTINEL_DOC_TEXT not in full_output


@pytest.mark.anyio
async def test_out_of_scope_run_only_logs_the_enrich_stage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
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
    monkeypatch.setattr(
        agent_module,
        "get_ensemble_retriever",
        lambda **kwargs: pytest.fail("No debía recuperar"),
    )

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        result = await agent_module.build_graph().ainvoke(
            _state(_SENTINEL_QUESTION),
            config={"configurable": {"thread_id": "obs-out-of-scope"}},
        )

    assert result["query_route"] == "out_of_scope"
    stage_messages = [r.message for r in caplog.records if r.message.startswith("stage=")]
    stages_logged = {m.split()[0].split("=")[1] for m in stage_messages}
    assert stages_logged == {"enrich_query"}


@pytest.mark.anyio
async def test_invalid_citations_logs_a_citation_format_error(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def analyze(question: str, history: str) -> EnrichedQuery:
        del question, history
        return EnrichedQuery(
            route="in_scope",
            standalone_question="reformulación",
            expanded_query="consulta",
            doc_types=["normativa"],
        )

    class FakeRetriever:
        def invoke(self, query: str) -> list[Document]:
            del query
            return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

        async def ainvoke(self, query: str) -> list[Document]:
            return self.invoke(query)

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: FakeRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    # Sin marcador [docN]: la respuesta no pasa la validación de citas.
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta sin ninguna cita válida."]),
    )

    with caplog.at_level(logging.WARNING, logger="rag.observability"):
        result = await agent_module.build_graph().ainvoke(
            _state("¿Puede cerrarse el acceso?"),
            config={"configurable": {"thread_id": "obs-invalid-citation"}},
        )

    assert (
        "no fue posible producir una respuesta verificable"
        in result["messages"][-1].content.lower()
    )
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("citation_format_error" in m and "doc_count=1" in m for m in warning_messages)


# ---------------------------------------------------------------------------
# T3.7 — log_full_context_size conectado a generate_node
# ---------------------------------------------------------------------------
#
# Complementa `test_observability.py` (que prueba `log_full_context_size` en
# aislamiento): aquí se prueba que `generate_node` la invoca con un conteo
# derivado de contenido real (no un valor fijo), y que ese conteo es
# deliberadamente independiente de lo que alimenta el campo público
# `context_tokens` de la API (el historial en `state["messages"]`, calculado
# aparte en `api/main.py::_estimate_context_tokens`) — para no correr el
# riesgo de que ambas métricas se confundan o se acoplen sin querer.

_FULL_CONTEXT_RE = re.compile(r"full_context_chars=(\d+)")


def _extract_full_context_chars(caplog: pytest.LogCaptureFixture) -> int:
    match = next(
        (m for r in caplog.records if (m := _FULL_CONTEXT_RE.search(r.message))),
        None,
    )
    assert match is not None, "no se logueó full_context_chars"
    return int(match.group(1))


def _generate_only_state(question: str, extra_messages: list | None = None) -> dict:
    return {
        "question": question,
        "standalone_question": None,
        "enriched_query": None,
        "query_route": "in_scope",
        "messages": list(extra_messages or []) + [HumanMessage(content=question)],
        "sources": [],
        "doc_types": None,
        "k": 2,
        "k_candidates": 5,
    }


def _mock_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta con cita [doc1]."] * 10),
    )


@pytest.mark.anyio
async def test_generate_node_logs_full_context_size_without_leaking_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_generation(monkeypatch)
    state = _generate_only_state(_SENTINEL_QUESTION)
    state["sources"] = [Document(page_content=_SENTINEL_DOC_TEXT, metadata={"chunk_id": "1"})]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(state)

    full_output = "\n".join(r.message for r in caplog.records)
    assert "full_context_chars=" in full_output
    assert "full_context_tokens_est=" in full_output
    assert _SENTINEL_QUESTION not in full_output
    assert _SENTINEL_DOC_TEXT not in full_output


@pytest.mark.anyio
async def test_full_context_size_grows_with_actual_document_content(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """El conteo debe reflejar contenido real recuperado, no un valor fijo."""
    _mock_generation(monkeypatch)

    short_state = _generate_only_state("¿Aplica la norma?")
    short_state["sources"] = [Document(page_content="Fragmento breve.", metadata={"chunk_id": "1"})]

    long_state = _generate_only_state("¿Aplica la norma?")
    long_state["sources"] = [
        Document(page_content="Fragmento extenso. " * 200, metadata={"chunk_id": "1"})
    ]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(short_state)
        short_chars = _extract_full_context_chars(caplog)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(long_state)
        long_chars = _extract_full_context_chars(caplog)

    assert long_chars > short_chars


@pytest.mark.anyio
async def test_full_context_size_is_independent_of_conversation_history_length(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A diferencia de `context_tokens` (que crece con el historial en
    `state["messages"]`), esta métrica interna solo depende del prompt de
    generación del turno actual (instrucciones + contexto + pregunta) — debe
    dar el mismo valor sin importar cuántos turnos previos traiga el estado."""
    _mock_generation(monkeypatch)
    question = "¿Aplica la norma sobre concesiones playeras?"
    docs = [Document(page_content="Fragmento del corpus.", metadata={"chunk_id": "1"})]

    no_history_state = _generate_only_state(question)
    no_history_state["sources"] = docs

    long_history = [
        HumanMessage(content=f"Turno previo {i}")
        if i % 2 == 0
        else AIMessage(content=f"Respuesta {i}")
        for i in range(20)
    ]
    with_history_state = _generate_only_state(question, extra_messages=long_history)
    with_history_state["sources"] = docs

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(no_history_state)
        chars_without_history = _extract_full_context_chars(caplog)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(with_history_state)
        chars_with_history = _extract_full_context_chars(caplog)

    assert chars_with_history == chars_without_history


# ---------------------------------------------------------------------------
# C8 — full_context_chars debe reflejar el prompt REALMENTE formateado.
#
# Antes de C8, `generate_node` aproximaba el tamaño sumando por separado
# `len(BASE_INSTRUCTIONS) + len(context) + len(question)` — eso ignora todo
# el texto literal del template (`<context>`/`</context>`,
# `<question>`/`</question>`, el recordatorio de citación, y en el caso sin
# system role el envoltorio "INSTRUCCIONES:\n{instructions}\n\n"), así que
# subestima el tamaño real de lo que efectivamente se le envía al LLM. Estas
# pruebas comparan contra el valor de referencia calculado formateando el
# MISMO `ChatPromptTemplate` que usa `generate_node` (sin hacer ninguna
# llamada a un LLM: `format_messages` es solo templating local), para ambos
# proveedores (con y sin system role) — sin tocar `context_tokens` ni el
# contrato público.
# ---------------------------------------------------------------------------


def _expected_full_context_chars(*, prompt, context: str, question: str) -> int:
    """Referencia independiente: la suma de caracteres de los mensajes que
    ChatPromptTemplate realmente produce para este prompt — el mismo cálculo
    que generate_node debe hacer, reconstruido aquí desde la prueba (no
    llamando a la implementación) para que la comparación sea significativa."""
    formatted = prompt.format_messages(context=context, question=question)
    return sum(len(str(m.content)) for m in formatted)


@pytest.mark.anyio
async def test_full_context_size_matches_the_actually_formatted_prompt_with_system_role(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _mock_generation(monkeypatch)  # supports_system_role=True → PROMPT_WITH_SYSTEM
    question = "¿Aplica la norma sobre concesiones playeras?"
    docs = [
        Document(
            page_content="Fragmento del corpus con contenido real.", metadata={"chunk_id": "1"}
        )
    ]
    state = _generate_only_state(question)
    state["sources"] = docs

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(state)
        logged_chars = _extract_full_context_chars(caplog)

    context = agent_module.build_context_block(docs)
    expected = _expected_full_context_chars(
        prompt=agent_module.PROMPT_WITH_SYSTEM, context=context, question=question
    )
    assert logged_chars == expected

    # La aproximación anterior (suma de longitudes por separado, sin el
    # texto literal del template) habría dado un valor distinto — confirma
    # que la prueba realmente distingue precisión, no solo que exista un log.
    naive_approximation = len(agent_module.BASE_INSTRUCTIONS) + len(context) + len(question)
    assert logged_chars != naive_approximation


@pytest.mark.anyio
async def test_full_context_size_matches_the_actually_formatted_prompt_without_system_role(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=False),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta con cita [doc1]."] * 10),
    )
    question = "¿Qué autoridad decide sobre una concesión de playa?"
    docs = [
        Document(page_content="Otro fragmento distinto del corpus.", metadata={"chunk_id": "1"})
    ]
    state = _generate_only_state(question)
    state["sources"] = docs

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(state)
        logged_chars = _extract_full_context_chars(caplog)

    context = agent_module.build_context_block(docs)
    prompt = agent_module.PROMPT_NO_SYSTEM.partial(instructions=agent_module.BASE_INSTRUCTIONS)
    expected = _expected_full_context_chars(prompt=prompt, context=context, question=question)
    assert logged_chars == expected


@pytest.mark.anyio
async def test_full_context_size_precision_does_not_add_a_second_llm_call(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Formatear el prompt para medirlo (`ChatPromptTemplate.format_messages`)
    es templating local — no debe traducirse en una llamada adicional al LLM
    de generación."""
    calls = {"n": 0}

    class _CountingFakeLLM(FakeListChatModel):
        async def ainvoke(self, *args, **kwargs):  # type: ignore[override]
            calls["n"] += 1
            return await super().ainvoke(*args, **kwargs)

    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: _CountingFakeLLM(responses=["Respuesta con cita [doc1]."]),
    )
    state = _generate_only_state("¿Aplica la norma?")
    state["sources"] = [Document(page_content="Fragmento.", metadata={"chunk_id": "1"})]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(state)

    assert calls["n"] == 1


@pytest.mark.anyio
async def test_full_context_size_precision_still_never_leaks_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Aunque ahora se formatea el prompt completo para medirlo con
    precisión, el log sigue recibiendo solo el conteo (`chars=int`) — nunca
    el contenido de los mensajes formateados."""
    _mock_generation(monkeypatch)
    state = _generate_only_state(_SENTINEL_QUESTION)
    state["sources"] = [Document(page_content=_SENTINEL_DOC_TEXT, metadata={"chunk_id": "1"})]

    with caplog.at_level(logging.INFO, logger="rag.observability"):
        await agent_module.generate_node(state)

    full_output = "\n".join(r.message for r in caplog.records)
    assert _SENTINEL_QUESTION not in full_output
    assert _SENTINEL_DOC_TEXT not in full_output
