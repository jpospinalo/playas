"""Paridad JSON/SSE de la validación de conversación y `current_message_id`
en `/api/query` y `/api/query/stream`.

Antes de escribir este archivo se revisó el inventario existente para no
duplicar: `test_query_stream_endpoint.py` cubre la forma de los eventos SSE
y la liberación de recursos ante una excepción DENTRO de `graph.astream`
(retriever/LLM); `test_query_timeouts.py` cubre timeouts; `test_conversation_lock.py`
y `test_lock_before_backpressure.py` cubren el registro de locks y el orden
lock-antes-que-backpressure; `test_checkpoint_cleanup_failure_isolation.py`
cubre que un fallo de limpieza de checkpoint nunca reemplaza el resultado
principal, para AMBOS endpoints, y que su warning no registra `thread_id`
ni contenido de negocio. Ninguno de esos archivos ejercita las ramas de validación de
`_get_initial_messages` (`query_support.py`) — la lógica de validación de
conversación/`current_message_id` que corre en tiempo de ejecución, después
de que el payload ya pasó el schema de Pydantic. (La tercera rama posible,
`current_message_id` sin `conversation_id`, YA la rechaza el propio
`QueryRequest` en `test_query_schema.py::test_query_contract_rejects_invalid_payloads`
— al ser el mismo tipo Pydantic compartido por los dos endpoints, ese caso
ni siquiera llega a construirse para ninguno de los dos, así que no se
duplica aquí.) Este archivo llena las DOS ramas restantes, una sola vez
cada una, para AMBOS endpoints a la vez (mismo código, mismo detalle, y
liberación de lock/backpressure en los dos).

`/api/query` y `/api/query/stream` llaman literalmente a la misma función
compartida (`_get_initial_messages`) con los mismos argumentos y en el
mismo punto (antes de cualquier trabajo del agente) — por diseño no pueden
divergir en este contrato. Esta prueba lo demuestra empíricamente y sirve
de guarda de regresión si algún día uno de los dos deja de llamarla igual.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import rag.api.database as database_module
import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.models import Base, Conversation, Message, User
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.schemas import QueryRequest

_OFF_TOPIC_QUESTION = "Dame una receta de cocina, por favor."
_USER = {"sub": "test-user"}

_pending_engines: list[AsyncEngine] = []


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _dispose_test_db_engines() -> Iterator[None]:
    yield
    if not _pending_engines:
        return
    engines, _pending_engines[:] = list(_pending_engines), []

    async def _dispose_all() -> None:
        for engine in engines:
            await engine.dispose()

    asyncio.run(_dispose_all())


def _real_graph(monkeypatch: pytest.MonkeyPatch):
    # Enrutamiento determinista (`_OFF_TOPIC_QUESTION`): estas pruebas
    # nunca deberían llegar a invocar el LLM ni el retriever, porque la
    # validación de `_get_initial_messages` falla antes de que el grafo
    # se ejecute — pero se deshabilita el enriquecimiento por consistencia
    # con el resto del suite.
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    return agent_module.build_graph()


async def _fresh_db_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


async def _seed(session_factory: async_sessionmaker) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                User(id="test-user", email="u@example.com", password_hash="hash", role="user"),
                User(id="otro-usuario", email="o@example.com", password_hash="hash", role="user"),
                Conversation(
                    id="conv-mine",
                    user_id="test-user",
                    thread_id="conv-mine-thread",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
                Conversation(
                    id="conv-ajena",
                    user_id="otro-usuario",
                    thread_id="conv-ajena-thread",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
                Message(
                    id="msg-mine",
                    conversation_id="conv-mine",
                    role="user",
                    text="Una pregunta distinta a la que se envía ahora.",
                    created_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()


async def _setup(monkeypatch: pytest.MonkeyPatch):
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)

    session_factory = await _fresh_db_session_factory()
    await _seed(session_factory)
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    fresh_locks = ConversationLockRegistry()
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", fresh_locks)
    fresh_backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=3)
    monkeypatch.setattr(main_module, "backpressure", fresh_backpressure)

    return main_module, fresh_locks, fresh_backpressure


async def _call_json(main_module, request: QueryRequest, user: dict):
    return await main_module.query(request, user)


async def _call_sse(main_module, request: QueryRequest, user: dict):
    return await main_module.query_stream(request, user)


_ENDPOINTS = [
    pytest.param(_call_json, id="json"),
    pytest.param(_call_sse, id="sse"),
]


@pytest.mark.anyio
@pytest.mark.parametrize("call_endpoint", _ENDPOINTS)
async def test_conversation_not_found_or_not_owned_rejects_404_in_both_endpoints(
    monkeypatch: pytest.MonkeyPatch, call_endpoint
) -> None:
    main_module, locks, backpressure_double = await _setup(monkeypatch)
    # `conv-ajena` existe, pero pertenece a otro usuario — el mismo 404 que
    # un id inexistente, sin distinguir el caso para no filtrar qué ids
    # existen.
    request = QueryRequest(question=_OFF_TOPIC_QUESTION, conversation_id="conv-ajena")

    with pytest.raises(HTTPException) as exc_info:
        await call_endpoint(main_module, request, _USER)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Conversación no encontrada."
    assert locks._entries == {}
    assert backpressure_double.in_flight == 0


@pytest.mark.anyio
@pytest.mark.parametrize("call_endpoint", _ENDPOINTS)
async def test_current_message_id_mismatch_rejects_422_in_both_endpoints(
    monkeypatch: pytest.MonkeyPatch, call_endpoint
) -> None:
    main_module, locks, backpressure_double = await _setup(monkeypatch)
    # `msg-mine` existe, pertenece a `conv-mine` y es del usuario correcto,
    # pero su texto no coincide con la pregunta actual.
    request = QueryRequest(
        question=_OFF_TOPIC_QUESTION,
        conversation_id="conv-mine",
        current_message_id="msg-mine",
    )

    with pytest.raises(HTTPException) as exc_info:
        await call_endpoint(main_module, request, _USER)

    assert exc_info.value.status_code == 422
    assert (
        exc_info.value.detail == "El mensaje actual no coincide con la conversación y la pregunta."
    )
    assert locks._entries == {}
    assert backpressure_double.in_flight == 0
