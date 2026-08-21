"""Manejo de la carrera de email duplicado en registro y creación admin.

Ambos endpoints comprueban primero si el email ya existe y luego confirman
la inserción; esa comprobación no es atómica con el commit, así que dos
solicitudes concurrentes con el mismo email pueden pasar ambas la
comprobación y competir por la restricción unique de la base de datos. El
código de producción maneja esto con `try: await session.commit() / except
IntegrityError: rollback + reconsulta + 409 si es la carrera, o `raise` si
no lo es.

Las pruebas `..._masks_concurrent_duplicate_email_as_conflict` y
`..._unrelated_to_email_race_mocked` usan una sesión simulada
(`unittest.mock`) que fuerza el `IntegrityError` exactamente en
`session.commit()`, y verifican no solo cuántas veces se llamó cada método
sino la secuencia exacta `execute -> commit -> rollback -> execute` que
produce el bloque real `try/except IntegrityError`. Esto reemplaza una
versión anterior que insertaba el usuario competidor *antes* de la primera
consulta `SELECT` del endpoint: como esa consulta inicial ya encontraba el
email y devolvía 409 de inmediato, el `commit`, el `except IntegrityError` y
el `rollback` nunca llegaban a ejecutarse — la prueba pasaba, pero no
ejercitaba el código que decía validar.

Las pruebas `..._unrelated_to_email_race` (sin sufijo `_mocked`) se
conservan como cobertura adicional con una base de datos SQLite real: fuerzan
un `IntegrityError` genuino en el commit mediante una colisión de clave
primaria (id duplicado, no email), lo que sí ejercita `commit()` de verdad.

Todos los correos y contraseñas usados en este archivo son valores sintéticos
de prueba (dominio `example.com`, reservado para documentación por RFC 2606),
no datos de usuarios reales.
"""

from __future__ import annotations

import uuid as uuid_module
from unittest.mock import AsyncMock, MagicMock

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


def _mocked_session(
    execute_results: list, commit_error: Exception
) -> tuple[MagicMock, list[str]]:
    """Sesión simulada: `execute` devuelve `execute_results` en orden (uno por
    llamada), `commit` lanza `commit_error`, `rollback` y `add` son no-ops.

    Además de servir esos valores/errores, cada llamada a `execute`/`commit`/
    `rollback` se anota (en ese orden) en la lista `call_order` devuelta junto
    a la sesión: como son tres `AsyncMock` distintos (no generados por el
    `MagicMock` padre vía autoatributo, sino asignados explícitamente),
    `session.mock_calls` no captura su orden relativo por sí solo, así que se
    registra a mano. Esto permite comprobar no solo cuántas veces se llamó
    cada método, sino la secuencia exacta `execute -> commit -> rollback ->
    execute` que produce el bloque `try/except IntegrityError` real.
    """
    call_order: list[str] = []
    results_iter = iter(execute_results)

    async def _execute(*_args: object, **_kwargs: object) -> object:
        call_order.append("execute")
        return next(results_iter)

    async def _commit(*_args: object, **_kwargs: object) -> None:
        call_order.append("commit")
        raise commit_error

    async def _rollback(*_args: object, **_kwargs: object) -> None:
        call_order.append("rollback")

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)
    session.commit = AsyncMock(side_effect=_commit)
    session.rollback = AsyncMock(side_effect=_rollback)
    session.add = MagicMock()
    return session, call_order


def _result_with(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


async def _fresh_engine_and_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, session_factory


# ── register(): flujo exacto con sesión simulada ────────────────────────────


@pytest.mark.anyio
async def test_register_masks_concurrent_duplicate_email_as_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos registros concurrentes con el mismo email: el que pierde la carrera
    en el commit debe recibir 409 con el mensaje de correo ya registrado, tras
    ejecutar realmente commit -> IntegrityError -> rollback -> reconsulta."""
    monkeypatch.setattr("rag.api.routes.auth._REGISTER_ENABLED", True)

    competing_user = User(
        id="racer-id", email="race@example.com", password_hash="hash", role="user"
    )
    integrity_error = IntegrityError("INSERT INTO users ...", {}, Exception("unique violation"))
    session, call_order = _mocked_session(
        execute_results=[_result_with(None), _result_with(competing_user)],
        commit_error=integrity_error,
    )

    payload = RegisterRequest(
        email="race@example.com", password="supersecret1", display_name=None
    )
    with pytest.raises(HTTPException) as error:
        await register(payload, session)

    assert error.value.status_code == 409
    assert error.value.detail == "Este correo ya está registrado."
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()
    assert session.execute.await_count == 2
    # Orden exacto: la comprobación inicial (execute), el commit que pierde
    # la carrera (commit -> IntegrityError), el rollback, y la reconsulta que
    # encuentra al ganador (execute) — no solo el conteo de cada llamada.
    assert call_order == ["execute", "commit", "rollback", "execute"]


@pytest.mark.anyio
async def test_register_reraises_integrity_error_unrelated_to_email_race_mocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el IntegrityError del commit no es una carrera de email (la
    reconsulta posterior tampoco encuentra el email), se relanza la misma
    instancia sin enmascararla como 409."""
    monkeypatch.setattr("rag.api.routes.auth._REGISTER_ENABLED", True)

    integrity_error = IntegrityError(
        "INSERT INTO users ...", {}, Exception("id primary key collision")
    )
    session, call_order = _mocked_session(
        execute_results=[_result_with(None), _result_with(None)],
        commit_error=integrity_error,
    )

    payload = RegisterRequest(
        email="new-unique-email@example.com",
        password="supersecret1",
        display_name=None,
    )
    with pytest.raises(IntegrityError) as error:
        await register(payload, session)

    assert error.value is integrity_error
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()
    assert session.execute.await_count == 2
    assert call_order == ["execute", "commit", "rollback", "execute"]


# ── register(): cobertura adicional con SQLite real ─────────────────────────


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


# ── create_user() (admin): flujo exacto con sesión simulada ─────────────────


@pytest.mark.anyio
async def test_admin_create_user_masks_concurrent_duplicate_email_as_conflict() -> None:
    """Misma carrera que en el registro público, pero en la creación de
    usuarios desde el panel de administración."""
    competing_user = User(
        id="racer-id",
        email="admin-race@example.com",
        password_hash="hash",
        role="user",
    )
    integrity_error = IntegrityError("INSERT INTO users ...", {}, Exception("unique violation"))
    session, call_order = _mocked_session(
        execute_results=[_result_with(None), _result_with(competing_user)],
        commit_error=integrity_error,
    )

    payload = CreateUserRequest(
        email="admin-race@example.com", password="supersecret1", displayName=None
    )
    with pytest.raises(HTTPException) as error:
        await create_user(payload, {"sub": "admin-1", "role": "admin"}, session)

    assert error.value.status_code == 409
    assert error.value.detail == "Ese email ya está registrado."
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()
    assert session.execute.await_count == 2
    assert call_order == ["execute", "commit", "rollback", "execute"]


@pytest.mark.anyio
async def test_admin_create_user_reraises_integrity_error_unrelated_to_email_race_mocked() -> None:
    """Igual que la versión de registro: un IntegrityError no relacionado con
    el email se relanza tal cual, no se enmascara como 409."""
    integrity_error = IntegrityError(
        "INSERT INTO users ...", {}, Exception("id primary key collision")
    )
    session, call_order = _mocked_session(
        execute_results=[_result_with(None), _result_with(None)],
        commit_error=integrity_error,
    )

    payload = CreateUserRequest(
        email="admin-new-unique-email@example.com",
        password="supersecret1",
        displayName=None,
    )
    with pytest.raises(IntegrityError) as error:
        await create_user(payload, {"sub": "admin-1", "role": "admin"}, session)

    assert error.value is integrity_error
    session.commit.assert_awaited_once()
    session.rollback.assert_awaited_once()
    assert session.execute.await_count == 2
    assert call_order == ["execute", "commit", "rollback", "execute"]


# ── create_user() (admin): cobertura adicional con SQLite real ──────────────


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
