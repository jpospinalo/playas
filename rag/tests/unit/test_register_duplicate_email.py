"""Camino directo (sin carrera) de email duplicado en /api/auth/register.

`register()` primero consulta si el email ya existe y responde 409 de
inmediato si lo encuentra, sin llegar nunca a `session.commit()`. Ese
camino es el más común en la práctica (un segundo registro secuencial, no
dos solicitudes concurrentes) y no estaba cubierto: `test_email_race_conditions.py`
solo ejercita el camino de la carrera (IntegrityError en el commit).

Los correos usados son valores sintéticos de prueba (dominio `example.com`,
reservado para documentación por RFC 2606), no datos de usuarios reales.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rag.api.models import Base
from rag.api.routes.auth import RegisterRequest, register


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_register_rejects_duplicate_email_with_409(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un segundo registro con el mismo correo (incluso con mayúsculas
    distintas) recibe 409 con el mensaje que el frontend muestra al usuario,
    sin que el commit llegue a ejecutarse para esa segunda solicitud."""
    monkeypatch.setattr("rag.api.routes.auth._REGISTER_ENABLED", True)
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        await register(
            RegisterRequest(
                email="duplicado@example.com",
                password="supersecret1",
                display_name=None,
            ),
            session,
        )

    async with session_factory() as session:
        payload = RegisterRequest(
            email="DUPLICADO@example.com",
            password="otracontrasena1",
            display_name=None,
        )
        with pytest.raises(HTTPException) as error:
            await register(payload, session)

    assert error.value.status_code == 409
    assert error.value.detail == "Este correo ya está registrado."

    await engine.dispose()
