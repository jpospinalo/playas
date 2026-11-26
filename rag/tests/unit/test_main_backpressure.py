"""T3.6 — wiring de ConcurrencyBackpressure en /api/query y /api/query/stream.

Complementa `test_backpressure.py` (que prueba la clase en aislamiento):
aquí se verifica que los endpoints reales la usan — rechazan con 503 cuando
el proceso está en su límite de concurrencia configurado, y NO cuentan una
consulta rechazada en ACTIVE_QUERIES (nunca llegó a procesarse).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
from rag.api.rate_limit import ConcurrencyBackpressure


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _SlowRetriever:
    async def ainvoke(self, query: str) -> list[Document]:
        await asyncio.sleep(0.08)
        return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

    def invoke(self, query: str) -> list[Document]:
        return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]


def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: _SlowRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta [doc1]."] * 5),
    )


_QUESTION = "Un pescador artesanal pregunta por la concesión de una playa. " * 2


@pytest.mark.anyio
async def test_query_endpoint_rejects_with_503_when_at_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    )

    user = {"sub": "test-user"}
    request_a = QueryRequest(question=_QUESTION, thread_id="thread-a")
    request_b = QueryRequest(question=_QUESTION, thread_id="thread-b")

    results = await asyncio.gather(
        main_module.query(request_a, user),
        main_module.query(request_b, user),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    errors = [r for r in results if isinstance(r, HTTPException)]
    assert len(successes) == 1
    assert len(errors) == 1
    assert errors[0].status_code == 503
    assert main_module.ACTIVE_QUERIES.count == 0


@pytest.mark.anyio
async def test_query_endpoint_never_rejects_in_off_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    import rag.api.main as main_module
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="off", max_concurrent=1)
    )

    user = {"sub": "test-user"}
    request_a = QueryRequest(question=_QUESTION, thread_id="thread-c")
    request_b = QueryRequest(question=_QUESTION, thread_id="thread-d")

    results = await asyncio.gather(
        main_module.query(request_a, user),
        main_module.query(request_b, user),
        return_exceptions=True,
    )
    assert all(not isinstance(r, Exception) for r in results)


# ---------------------------------------------------------------------------
# C5 — este archivo afirmaba en su propio docstring cubrir "wiring de
# ConcurrencyBackpressure en /api/query y /api/query/stream", pero ningún
# test de arriba llamaba jamás a `query_stream`. Las dos pruebas siguientes
# cierran exactamente ese hueco (puntos 1 y 2 del plan de C5); el resto de
# la cobertura de SSE — serialización por hilo, paralelismo entre hilos,
# liberación de recursos ante excepción/cancelación, y estabilidad del
# formato de eventos — vive en test_query_stream_endpoint.py, para no
# convertir este archivo en una prueba general del endpoint de streaming.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stream_endpoint_rejects_with_503_before_constructing_the_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """En modo enforce, con la capacidad ya saturada por otra conversación,
    /api/query/stream debe rechazar con 503 ANTES de devolver el
    StreamingResponse — como una HTTPException normal de la corrutina, no
    como un evento SSE de error dentro de un stream ya iniciado."""
    import rag.api.main as main_module
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    backpressure_double = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    monkeypatch.setattr(main_module, "backpressure", backpressure_double)

    user = {"sub": "test-user"}
    request = QueryRequest(question=_QUESTION, thread_id="stream-thread-saturado")

    # Ocupa el único slot desde fuera, simulando que otra conversación ya
    # satura la capacidad global.
    async with backpressure_double.slot():
        with pytest.raises(HTTPException) as exc:
            await main_module.query_stream(request, user)
    assert exc.value.status_code == 503
    # Rechazada antes de procesar: no debe quedar contabilizada.
    assert main_module.ACTIVE_QUERIES.count == 0


@pytest.mark.anyio
async def test_stream_endpoint_never_rejects_in_off_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Modo off: /api/query/stream conserva el comportamiento previo a T3.6
    — nunca rechaza, ni siquiera con `max_concurrent` deliberadamente bajo."""
    import rag.api.main as main_module
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="off", max_concurrent=1)
    )

    user = {"sub": "test-user"}

    async def _consume(thread_id: str) -> list[dict]:
        import json

        request = QueryRequest(question=_QUESTION, thread_id=thread_id)
        response = await main_module.query_stream(request, user)
        events = []
        async for chunk in response.body_iterator:
            text = chunk if isinstance(chunk, str) else chunk.decode()
            if text.startswith("data: ") and text.strip() != "data: [DONE]":
                events.append(json.loads(text[len("data: ") :].strip()))
        return events

    results = await asyncio.gather(
        _consume("stream-thread-off-1"),
        _consume("stream-thread-off-2"),
        return_exceptions=True,
    )
    assert all(not isinstance(r, Exception) for r in results)
    assert all(any(e.get("type") == "sources" for e in events) for events in results)
