"""QA-F05: "Intentar otra vez" no duplica la pregunta guardada.

Tras un error del back, el front vuelve a guardar la misma pregunta con otro
id. Si lo último de la conversación ya es esa pregunta (sin respuesta en
medio), `add_message` devuelve la existente. Una pregunta distinta, o la
misma después de una respuesta, sí se guarda.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rag.api.models import Base, Conversation, Message, User
from rag.api.routes.conversations import AddMessageRequest, add_message

_USER = {"sub": "u1"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _fabrica() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with fabrica() as s:
        ahora = datetime.now(UTC)
        s.add_all(
            [
                User(id="u1", email="u1@x.co", password_hash="x", role="user"),
                Conversation(
                    id="c1", user_id="u1", thread_id="t1", created_at=ahora, updated_at=ahora
                ),
            ]
        )
        await s.commit()
    return fabrica


async def _contar(fabrica: async_sessionmaker) -> int:
    async with fabrica() as s:
        return (await s.execute(select(func.count()).select_from(Message))).scalar_one()


@pytest.mark.anyio
async def test_reintento_de_la_misma_pregunta_no_duplica() -> None:
    fabrica = await _fabrica()
    async with fabrica() as s:
        a = await add_message(
            "c1", AddMessageRequest(role="user", text="¿Y los domingos?"), _USER, s
        )
    async with fabrica() as s:
        b = await add_message(
            "c1", AddMessageRequest(role="user", text="¿Y los domingos?"), _USER, s
        )
    assert a.id == b.id
    assert await _contar(fabrica) == 1


@pytest.mark.anyio
async def test_otra_pregunta_o_la_misma_tras_una_respuesta_si_se_guardan() -> None:
    fabrica = await _fabrica()
    for role, texto in [
        ("user", "¿Puedo vender?"),
        ("user", "¿Y los domingos?"),
        ("assistant", "Sí [doc1]."),
        ("user", "¿Y los domingos?"),
    ]:
        async with fabrica() as s:
            await add_message("c1", AddMessageRequest(role=role, text=texto), _USER, s)
    assert await _contar(fabrica) == 4
