"""Manejo de la carrera de email duplicado en registro y creación admin.

Ambos endpoints comprueban primero si el email ya existe y luego confirman
la inserción; esa comprobación no es atómica con el commit, así que dos
solicitudes concurrentes con el mismo email pueden pasar ambas la
comprobación y competir por la restricción unique de la base de datos. Estas
pruebas verifican que la carrera real se enmascara como un 409 normal (en
lugar de propagar un IntegrityError sin manejar / 500), y que un
IntegrityError que no corresponda a esa carrera específica sí se relanza.
"""

from __future__ import annotations

import uuid as uuid_module

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rag.api.models import Base, User
from rag.api.routes.admin import CreateUserRequest, create_user
from rag.api.routes.auth import RegisterRequest, register


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _fresh_engine_and_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


@pytest.mark.anyio
async def test_register_masks_concurrent_duplicate_email_as_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos registros concurrentes con el mismo email: el que pierde la carrera
    en el commit debe recibir 409, no un IntegrityError sin manejar."""
    monkeypatch.setattr("rag.api.routes.auth._REGISTER_ENABLED", True)
    engine, session_factory = await _fresh_engine_and_factory()

    async with session_factory() as session:
        real_execute = session.execute
        call_count = 0

        async def racing_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simula la solicitud concurrente que gana la carrera: se
                # registra y confirma el mismo email justo después de que
                # esta solicitud comprobó (sin verlo aún) que no existía.
                async with session_factory() as racing_session:
                    racing_session.add(
                        User(
                            id="racer-id",
                            email="race@example.com",
                            password_hash="hash",
                            role="user",
                        )
                    )
                    await racing_session.commit()
            return await real_execute(*args, **kwargs)

        session.execute = racing_execute  # type: ignore[method-assign]

        payload = RegisterRequest(
            email="race@example.com", password="supersecret1", display_name=None
        )
        with pytest.raises(HTTPException) as error:
            await register(payload, session)

    assert error.value.status_code == 409
    await engine.dispose()


@pytest.mark.anyio
async def test_register_reraises_integrity_error_unrelated_to_email_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un IntegrityError que no es la carrera de email (aquí: colisión del id
    generado) no debe enmascararse como 409: debe propagarse tal cual."""
    monkeypatch.setattr("rag.api.routes.auth._REGISTER_ENABLED", True)
    fixed_id = "fixed-uuid-collision"
    monkeypatch.setattr(uuid_module, "uuid4", lambda: fixed_id)
    engine, session_factory = await _fresh_engine_and_factory()

    async with session_factory() as racing_session:
        racing_session.add(
            User(
                id=fixed_id,
                email="someone-else@example.com",
                password_hash="hash",
                role="user",
            )
        )
        await racing_session.commit()

    async with session_factory() as session:
        payload = RegisterRequest(
            email="new-unique-email@example.com",
            password="supersecret1",
            display_name=None,
        )
        with pytest.raises(IntegrityError):
            await register(payload, session)

    await engine.dispose()


@pytest.mark.anyio
async def test_admin_create_user_masks_concurrent_duplicate_email_as_conflict() -> None:
    """Misma carrera que en el registro público, pero en la creación de
    usuarios desde el panel de administración."""
    engine, session_factory = await _fresh_engine_and_factory()

    async with session_factory() as session:
        real_execute = session.execute
        call_count = 0

        async def racing_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                async with session_factory() as racing_session:
                    racing_session.add(
                        User(
                            id="racer-id",
                            email="admin-race@example.com",
                            password_hash="hash",
                            role="user",
                        )
                    )
                    await racing_session.commit()
            return await real_execute(*args, **kwargs)

        session.execute = racing_execute  # type: ignore[method-assign]

        payload = CreateUserRequest(
            email="admin-race@example.com", password="supersecret1", displayName=None
        )
        with pytest.raises(HTTPException) as error:
            await create_user(payload, {"sub": "admin-1", "role": "admin"}, session)

    assert error.value.status_code == 409
    await engine.dispose()


@pytest.mark.anyio
async def test_admin_create_user_reraises_integrity_error_unrelated_to_email_race(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_id = "fixed-uuid-collision-admin"
    monkeypatch.setattr(uuid_module, "uuid4", lambda: fixed_id)
    engine, session_factory = await _fresh_engine_and_factory()

    async with session_factory() as racing_session:
        racing_session.add(
            User(
                id=fixed_id,
                email="admin-someone-else@example.com",
                password_hash="hash",
                role="user",
            )
        )
        await racing_session.commit()

    async with session_factory() as session:
        payload = CreateUserRequest(
            email="admin-new-unique-email@example.com",
            password="supersecret1",
            displayName=None,
        )
        with pytest.raises(IntegrityError):
            await create_user(payload, {"sub": "admin-1", "role": "admin"}, session)

    await engine.dispose()
