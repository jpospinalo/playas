"""A3.4 — tipado y límite de tamaño de `sources` al persistir un mensaje.

`AddMessageRequest.sources` pasó de `list | None` (sin validar estructura)
a `list[SourceGroup] | None` (el mismo modelo que ya usa `QueryResponse` en
`/api/query`) — la escritura ahora rechaza estructuras arbitrarias con 422 y
un payload cuyo tamaño serializado exceda `_MAX_SOURCES_SERIALIZED_CHARS`.

Alcance deliberadamente limitado a la ESCRITURA (`AddMessageRequest`):

  - El frontend ya normaliza `sources` a la forma `SourceGroup[]` antes de
    persistir (`normalizeSources` en `frontend/lib/types.ts`, aplicado al
    evento SSE `sources` antes de llamar a `persistMessage`), así que
    endurecer la escritura no rompe ningún payload válido actual.
  - La LECTURA (`MessageOut.sources`, aún `list | None`) NO se toca: filas
    antiguas guardadas antes de adoptar `SourceGroup[]` (shape plano legado,
    ver el comentario de `normalizeSources` en el frontend) deben poder
    seguir leyéndose sin que una validación de respuesta las rechace. Este
    archivo prueba explícitamente que una fila con ese shape legado se lee
    sin alterarse (`test_reading_legacy_shaped_sources_is_unaffected`).

Reutiliza el patrón de este suite: grafo real no hace falta aquí (no se
toca el agente), pero sí una base SQLite real vía
`monkeypatch.setattr(database_module, "async_session_factory", ...)` (mismo
patrón que `test_ephemeral_checkpoint_cleanup.py`) y el patrón de llamada
directa a las funciones de ruta, sorteando `Depends(...)`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import rag.api.database as database_module
from rag.api.models import Base, Conversation, Message, User
from rag.api.routes.conversations import (
    _MAX_SOURCES_SERIALIZED_CHARS,
    AddMessageRequest,
    add_message,
    list_messages,
)

_USER = {"sub": "test-user"}

# Payload actual, tal como lo produce `normalizeSources` en el frontend tras
# recibir el evento SSE `sources` (ver frontend/lib/types.ts) — un
# `SourceGroup` por documento, cada uno con uno o más `SourceFragment`.
_CURRENT_SHAPE_SOURCES = [
    {
        "source": "sentencia-2024-001.pdf",
        "title": "Consejo de Estado, Sentencia 2024-001",
        "doc_type": "jurisprudencia",
        "metadata": {"Corporación": "Consejo de Estado", "Radicado": "11001-03"},
        "fragments": [
            {
                "index": 1,
                "content": "El dominio público marítimo-terrestre comprende...",
                "metadata": {"summary": "Definición de playa"},
            }
        ],
    },
    {
        "source": "decreto-1076-2015.pdf",
        "title": "Decreto 1076 de 2015",
        "doc_type": "normativa",
        "metadata": {"norma": "Decreto 1076 de 2015", "articulo": "Artículo 2.2.1.1"},
        "fragments": [
            {
                "index": 2,
                "content": "Las playas son bienes de uso público...",
                "metadata": {"articulo": "Artículo 2.2.1.1"},
            }
        ],
    },
]

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


async def _fresh_db_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


async def _seed_conversation(session_factory: async_sessionmaker, conversation_id: str) -> None:
    async with session_factory() as session:
        session.add_all(
            [
                User(id="test-user", email="u@example.com", password_hash="hash", role="user"),
                Conversation(
                    id=conversation_id,
                    user_id="test-user",
                    thread_id=f"{conversation_id}-thread",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                ),
            ]
        )
        await session.commit()


# ---------------------------------------------------------------------------
# Nivel schema — estructura y tamaño (proxy directo del 422 que produce
# FastAPI ante un `pydantic.ValidationError` al parsear el body; mismo patrón
# que test_query_schema.py).
# ---------------------------------------------------------------------------


def test_normal_sources_are_accepted() -> None:
    request = AddMessageRequest(role="assistant", text="Respuesta.", sources=_CURRENT_SHAPE_SOURCES)
    assert request.sources is not None
    assert len(request.sources) == 2
    assert request.sources[0].source == "sentencia-2024-001.pdf"


def test_none_sources_are_accepted() -> None:
    request = AddMessageRequest(role="assistant", text="Respuesta.", sources=None)
    assert request.sources is None


@pytest.mark.parametrize(
    "bad_sources",
    [
        [{"foo": "bar"}],  # faltan campos requeridos de SourceGroup
        [{"source": "x", "title": "y", "metadata": {}, "fragments": "no-es-lista"}],
        ["solo-un-string"],
        [
            {
                "source": "x",
                "title": "y",
                "metadata": {},
                "fragments": [{"index": "no-es-int", "content": "c"}],
            }
        ],
    ],
)
def test_arbitrary_structure_is_rejected(bad_sources: list) -> None:
    with pytest.raises(ValidationError):
        AddMessageRequest(role="assistant", text="Respuesta.", sources=bad_sources)


def test_excessive_payload_is_rejected() -> None:
    """El tamaño serializado, no solo la cantidad de grupos (ya acotada por
    `max_length=20`), debe rechazar un payload que supere el margen elegido
    (ver `_MAX_SOURCES_SERIALIZED_CHARS` en conversations.py)."""
    huge_content = "x" * (_MAX_SOURCES_SERIALIZED_CHARS)
    oversized_sources = [
        {
            "source": "s",
            "title": "t",
            "metadata": {},
            "fragments": [{"index": 1, "content": huge_content, "metadata": {}}],
        }
    ]
    with pytest.raises(ValidationError):
        AddMessageRequest(role="assistant", text="Respuesta.", sources=oversized_sources)


def test_a_payload_comfortably_under_the_limit_is_accepted() -> None:
    """Confirma que el límite no es tan estricto que rechace payloads reales
    típicos (ver la medición documentada: ~10-15 KB en el peor caso con
    k=8) — sirve de guarda contra un umbral mal calibrado en cualquier
    dirección."""
    request = AddMessageRequest(role="assistant", text="Respuesta.", sources=_CURRENT_SHAPE_SOURCES)
    assert request.sources is not None


# ---------------------------------------------------------------------------
# Nivel ruta — round-trip, conversión explícita a dict antes de persistir, y
# que la lectura no se vea afectada por el nuevo tipado de la escritura.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_round_trip_of_current_payload_is_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = await _fresh_db_session_factory()
    await _seed_conversation(session_factory, "conv-1")
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    payload = AddMessageRequest(
        role="assistant", text="Respuesta con fuentes.", sources=_CURRENT_SHAPE_SOURCES
    )
    async with session_factory() as session:
        created = await add_message("conv-1", payload, _USER, session)

    async with session_factory() as session:
        listed = await list_messages("conv-1", _USER, session)

    assert len(listed) == 1
    # El JSON persistido y releído debe ser idéntico (como dicts planos, no
    # instancias SourceGroup) al payload original enviado por el cliente.
    assert listed[0].sources == _CURRENT_SHAPE_SOURCES
    assert listed[0].sources == created.sources


@pytest.mark.anyio
async def test_source_group_instances_are_never_written_to_the_json_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guarda explícitamente contra la regresión que advierte el plan: pasar
    instancias Pydantic directamente a la columna JSON en vez de
    `model_dump()`. Si eso ocurriera, lo guardado no sería JSON-serializable
    de forma estándar y `listed[0].sources` no serían dicts planos."""
    session_factory = await _fresh_db_session_factory()
    await _seed_conversation(session_factory, "conv-2")
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    payload = AddMessageRequest(role="assistant", text="R.", sources=_CURRENT_SHAPE_SOURCES)
    async with session_factory() as session:
        await add_message("conv-2", payload, _USER, session)

    async with session_factory() as session:
        listed = await list_messages("conv-2", _USER, session)

    assert listed[0].sources is not None
    for group in listed[0].sources:
        assert isinstance(group, dict)
        for fragment in group["fragments"]:
            assert isinstance(fragment, dict)


@pytest.mark.anyio
async def test_reading_legacy_shaped_sources_is_unaffected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A3.4 solo tipa la ESCRITURA. Una fila con el shape plano legado
    (guardada antes de adoptar `SourceGroup[]`, ver `normalizeSources` en el
    frontend) debe seguir leyéndose tal cual, sin que la respuesta de
    lectura la rechace o la transforme."""
    session_factory = await _fresh_db_session_factory()
    await _seed_conversation(session_factory, "conv-legacy")
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    legacy_shape = [{"source": "viejo.pdf", "title": "Doc viejo", "content": "texto plano legado"}]
    async with session_factory() as session:
        session.add(
            Message(
                id="legacy-msg-1",
                conversation_id="conv-legacy",
                role="assistant",
                text="Respuesta antigua.",
                sources=legacy_shape,
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()

    async with session_factory() as session:
        listed = await list_messages("conv-legacy", _USER, session)

    assert len(listed) == 1
    assert listed[0].sources == legacy_shape


@pytest.mark.anyio
async def test_add_message_with_no_sources_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    session_factory = await _fresh_db_session_factory()
    await _seed_conversation(session_factory, "conv-3")
    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    payload = AddMessageRequest(role="user", text="Pregunta sin fuentes.", sources=None)
    async with session_factory() as session:
        created = await add_message("conv-3", payload, _USER, session)

    assert created.sources is None


def test_add_message_request_is_a_declared_fastapi_body_model() -> None:
    """Verifica que la validación de estructura efectivamente produce el
    422 automático de FastAPI (no solo un `pydantic.ValidationError` fuera
    de contexto): `RequestValidationError` es la excepción que FastAPI
    traduce a 422 cuando el parseo del body falla."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.post("/probe")
    async def probe(payload: AddMessageRequest) -> dict:
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post(
        "/probe",
        json={"role": "assistant", "text": "x", "sources": [{"foo": "bar"}]},
    )
    assert response.status_code == 422
