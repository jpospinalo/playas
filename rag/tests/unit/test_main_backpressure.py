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
