"""C4 — orden entre el lock de conversación y el slot de backpressure.

Antes de esta entrega, ambos endpoints adquirían primero un slot GLOBAL de
backpressure y solo después esperaban el lock de su conversación. Eso
significa que una segunda solicitud de una conversación que YA tiene un
turno en curso reservaba un slot global — aunque no fuera a hacer ningún
trabajo real hasta que el primer turno terminara y soltara el lock —
restando capacidad a conversaciones completamente independientes.

Esta prueba reproduce exactamente ese escenario de falta de equidad, con
capacidad global = 2:
  1. Una consulta de la conversación A ocupa un slot y queda "trabajando"
     (retenida deliberadamente por un `asyncio.Event` de la prueba).
  2. Una segunda consulta de la conversación A se lanza justo después: debe
     quedar esperando el lock de SU conversación, sin tocar el segundo slot.
  3. Una consulta de la conversación B (independiente) debe poder usar el
     segundo slot y completarse — sin esperar a que termine el turno A.

Con el orden anterior (backpressure → lock), el paso 2 ya reserva el
segundo slot solo por esperar su propio lock, así que el paso 3 recibe 503
aunque solo hay UN turno realmente procesando. Con el orden nuevo
(lock → backpressure), el paso 2 nunca toca backpressure mientras espera, y
el paso 3 se completa sin problema.
"""

from __future__ import annotations

import asyncio
import json
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


_QUESTION = "Un pescador artesanal pregunta por la concesión de una playa. " * 2


def _setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta [doc1]."] * 10),
    )


def _make_gated_and_fast_retrievers() -> tuple[object, asyncio.Event, asyncio.Event]:
    """El primer retriever creado (para la conversación A) se bloquea en un
    Event controlado por la prueba, tras avisar que ya empezó — así la
    prueba sabe con certeza cuándo la primera consulta ya tiene su lock y su
    slot, sin depender de timings frágiles. Los siguientes retrievers son
    instantáneos."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls = {"n": 0}

    class _Retriever:
        def __init__(self, gated: bool) -> None:
            self.gated = gated

        async def ainvoke(self, query: str) -> list[Document]:
            if self.gated:
                started.set()
                await release.wait()
            return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

    def make_retriever(**kwargs: object) -> _Retriever:
        calls["n"] += 1
        return _Retriever(gated=calls["n"] == 1)

    return make_retriever, started, release


@pytest.mark.anyio
async def test_second_turn_of_same_conversation_does_not_starve_an_independent_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    make_retriever, started, release = _make_gated_and_fast_retrievers()
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="enforce", max_concurrent=2)
    )

    user = {"sub": "test-user"}
    thread_a = "conversacion-a"
    thread_b = "conversacion-b"

    task_a1 = asyncio.create_task(
        main_module.query(QueryRequest(question=_QUESTION, thread_id=thread_a), user)
    )
    await started.wait()  # A1 ya tiene su lock y su slot; está "trabajando".

    task_a2 = asyncio.create_task(
        main_module.query(QueryRequest(question=_QUESTION, thread_id=thread_a), user)
    )
    # Le da a A2 una oportunidad real de llegar hasta donde vaya a quedarse
    # esperando (el lock de su propia conversación, con el orden nuevo).
    await asyncio.sleep(0.02)

    # B es una conversación totalmente independiente: con el orden correcto
    # debe poder usar el segundo slot y completarse sin esperar a A.
    result_b = await asyncio.wait_for(
        main_module.query(QueryRequest(question=_QUESTION, thread_id=thread_b), user),
        timeout=2.0,
    )
    assert result_b.answer == "Respuesta [doc1]."

    release.set()
    result_a1 = await task_a1
    result_a2 = await task_a2
    assert result_a1.answer == "Respuesta [doc1]."
    assert result_a2.answer == "Respuesta [doc1]."


@pytest.mark.anyio
async def test_backpressure_rejection_releases_the_conversation_lock_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si backpressure rechaza con 503 (capacidad ya llena por OTRAS
    conversaciones), el lock de la conversación rechazada no debe quedar
    retenido — una consulta posterior de esa misma conversación debe poder
    proceder de inmediato una vez haya capacidad."""
    import rag.api.main as main_module
    from rag.api.conversation_lock import ConversationLockRegistry
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: _FastRetriever())
    backpressure_double = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    monkeypatch.setattr(main_module, "backpressure", backpressure_double)
    locks = ConversationLockRegistry()
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    user = {"sub": "test-user"}
    request = QueryRequest(question=_QUESTION, thread_id="conversacion-rechazada")

    # Ocupa el único slot desde fuera, simulando que otra conversación ya
    # satura la capacidad global — la solicitud de abajo debe rechazarse.
    async with backpressure_double.slot():
        with pytest.raises(HTTPException) as exc:
            await main_module.query(request, user)
    assert exc.value.status_code == 503

    # El registro no debe conservar una entrada huérfana para esta
    # conversación tras el rechazo.
    assert locks._entries == {}


class _FastRetriever:
    async def ainvoke(self, query: str) -> list[Document]:
        return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]


@pytest.mark.anyio
async def test_stream_endpoint_second_turn_of_same_conversation_does_not_starve_independent_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Misma propiedad de equidad que arriba, pero contra /api/query/stream
    — C4 exige el mismo orden en ambos endpoints."""
    import rag.api.main as main_module
    from rag.api.schemas import QueryRequest

    _setup(monkeypatch)
    make_retriever, started, release = _make_gated_and_fast_retrievers()
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(
        main_module, "backpressure", ConcurrencyBackpressure(mode="enforce", max_concurrent=2)
    )

    user = {"sub": "test-user"}

    async def _consume(thread_id: str) -> list[dict]:
        request = QueryRequest(question=_QUESTION, thread_id=thread_id)
        response = await main_module.query_stream(request, user)
        events = []
        async for chunk in response.body_iterator:
            text = chunk if isinstance(chunk, str) else chunk.decode()
            if text.startswith("data: ") and text.strip() != "data: [DONE]":
                payload = text[len("data: ") :].strip()
                if payload != "[DONE]":
                    events.append(json.loads(payload))
        return events

    task_a1 = asyncio.create_task(_consume("stream-conversacion-a"))
    await started.wait()

    task_a2 = asyncio.create_task(_consume("stream-conversacion-a"))
    await asyncio.sleep(0.02)

    events_b = await asyncio.wait_for(_consume("stream-conversacion-b"), timeout=2.0)
    assert any(e.get("type") == "sources" for e in events_b)

    release.set()
    await task_a1
    await task_a2
