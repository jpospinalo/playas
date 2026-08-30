"""Controles del contrato JWT y, desde A4.2, reutilización de sesión SQL.

A4.2 — `get_current_user` dejó de abrir su propia sesión (`async with
database.async_session_factory() as session`) y ahora declara `session:
AsyncSession = Depends(get_session)` como cualquier otra dependencia.
FastAPI cachea cada dependencia una sola vez por solicitud
(`use_cache=True` es el default de `Depends`), así que un endpoint que
también declare `Depends(get_session)` — todos los de `routes/admin.py`,
`routes/conversations.py`, `routes/feedback.py` — recibe la MISMA instancia
de sesión que ya usó `get_current_user`, no una segunda.

Las pruebas de más abajo (`test_current_user_refreshes_profile_from_database`
en adelante) usan el patrón de llamada directa ya establecido en este suite
para lo que no necesita el árbol de dependencias real. La prueba de "una
sola instancia de sesión" SÍ necesita el árbol de dependencias real de
FastAPI (es precisamente lo que prueba), así que usa un `TestClient` sobre
una app mínima con `dependency_overrides` — el único caso de este archivo
que no puede usar llamada directa.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from rag.api.auth import (
    _decode,
    create_access_token,
    get_current_user,
    get_optional_user,
    require_admin,
)
from rag.api.database import get_session
from rag.api.models import Base, User

# Engines creados por _fresh_session_factory() en esta ejecución de pytest,
# pendientes de dispose() — mismo patrón que test_ephemeral_checkpoint_
# cleanup.py y los demás archivos de A2/A3: sin esto, los hilos de fondo de
# aiosqlite pueden disparar "Event loop is closed" contra el event loop de
# una prueba posterior.
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


def test_token_requires_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_access_token("user-1", "u1@example.com", "user")


def test_token_contains_required_identity_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    token = create_access_token("user-1", "u1@example.com", "admin")
    payload = _decode(token)
    assert payload["sub"] == "user-1"
    assert payload["email"] == "u1@example.com"
    assert payload["role"] == "admin"
    assert "iat" in payload
    assert "exp" in payload


async def _fresh_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


# ---------------------------------------------------------------------------
# get_current_user — identidad/rol vigentes, usuario eliminado.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_current_user_refreshes_profile_from_database() -> None:
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        session.add(
            User(
                id="user-1",
                email="actual@example.com",
                display_name="Usuario actual",
                password_hash="hash",
                role="admin",
            )
        )
        await session.commit()

    async with session_factory() as session:
        result = await get_current_user(
            {"sub": "user-1", "email": "old@example.com", "role": "user"}, session
        )

    assert result["email"] == "actual@example.com"
    assert result["display_name"] == "Usuario actual"
    assert result["role"] == "admin"


@pytest.mark.anyio
async def test_current_user_raises_401_when_no_token() -> None:
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        with pytest.raises(HTTPException) as error:
            await get_current_user(None, session)
    assert error.value.status_code == 401


@pytest.mark.anyio
async def test_current_user_raises_401_when_the_user_was_deleted() -> None:
    """El JWT sigue siendo válido (no expiró), pero la cuenta ya no existe
    en la base de datos — debe rechazarse, no confiar ciegamente en el
    payload del token."""
    session_factory = await _fresh_session_factory()  # sin usuarios sembrados

    async with session_factory() as session:
        with pytest.raises(HTTPException) as error:
            await get_current_user(
                {"sub": "user-deleted", "email": "e@example.com", "role": "user"}, session
            )

    assert error.value.status_code == 401
    assert error.value.detail == "Usuario no encontrado."


# ---------------------------------------------------------------------------
# require_admin — admin/no admin.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_require_admin_allows_admin_role() -> None:
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        session.add(User(id="u1", email="a@example.com", password_hash="x", role="admin"))
        await session.commit()

    async with session_factory() as session:
        user = await get_current_user(
            {"sub": "u1", "email": "a@example.com", "role": "admin"}, session
        )
        result = await require_admin(user)

    assert result["role"] == "admin"


@pytest.mark.anyio
async def test_require_admin_allows_super_admin_role() -> None:
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        session.add(User(id="u1", email="a@example.com", password_hash="x", role="super-admin"))
        await session.commit()

    async with session_factory() as session:
        user = await get_current_user(
            {"sub": "u1", "email": "a@example.com", "role": "super-admin"}, session
        )
        result = await require_admin(user)

    assert result["role"] == "super-admin"


@pytest.mark.anyio
async def test_require_admin_rejects_regular_user_role_with_403() -> None:
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        session.add(User(id="u1", email="a@example.com", password_hash="x", role="user"))
        await session.commit()

    async with session_factory() as session:
        user = await get_current_user(
            {"sub": "u1", "email": "a@example.com", "role": "user"}, session
        )
        with pytest.raises(HTTPException) as error:
            await require_admin(user)

    assert error.value.status_code == 403


# ---------------------------------------------------------------------------
# A4.2 — una sola instancia de sesión dentro del mismo árbol de
# dependencias, cuando el endpoint también pide su propia
# Depends(get_session). Necesita el árbol de dependencias REAL de FastAPI
# (es justo lo que se prueba), así que no usa el patrón de llamada directa.
# ---------------------------------------------------------------------------


def test_endpoint_with_its_own_session_dependency_reuses_get_current_users_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un endpoint que declara `Depends(get_current_user)` Y su propia
    `Depends(get_session)` — como todos los de admin/conversations/feedback
    — debe recibir la MISMA instancia de sesión que `get_current_user` ya
    usó internamente, no abrir una segunda. Se cuenta cuántas veces se
    EJECUTA el generador que produce la sesión (no cuántas veces `Depends`
    se menciona en la firma): antes de A4.2 esto habría sido 2 (una abierta
    a mano dentro de `get_current_user`, otra vía `Depends(get_session)` del
    propio endpoint); ahora debe ser 1."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(User(id="u1", email="a@example.com", password_hash="x", role="user"))
            await session.commit()

    asyncio.run(_setup())

    session_open_count = {"n": 0}

    async def _instrumented_get_session():
        session_open_count["n"] += 1
        async with session_factory() as session:
            yield session

    app = FastAPI()

    @app.get("/probe")
    async def probe(
        user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> dict:
        # La sesión que el endpoint recibe debe ser la misma que
        # get_current_user ya usó — lo confirma indirectamente el contador
        # de aperturas de abajo, pero también se verifica aquí que sigue
        # siendo una AsyncSession utilizable (no fue cerrada prematuramente
        # por compartirse).
        assert isinstance(session, AsyncSession)
        return {"user_id": user["sub"], "role": user["role"]}

    app.dependency_overrides[get_optional_user] = lambda: {
        "sub": "u1",
        "email": "a@example.com",
        "role": "user",
    }
    app.dependency_overrides[get_session] = _instrumented_get_session

    client = TestClient(app)
    try:
        response = client.get("/probe")
    finally:
        asyncio.run(engine.dispose())

    assert response.status_code == 200
    assert response.json() == {"user_id": "u1", "role": "user"}
    assert session_open_count["n"] == 1, (
        f"la sesión se abrió {session_open_count['n']} veces en una sola solicitud; "
        "se esperaba 1 (compartida entre get_current_user y el endpoint)"
    )


def test_two_separate_requests_each_get_their_own_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """El contrario de la prueba anterior: compartir la sesión DENTRO de
    una solicitud no debe convertirse en compartirla ENTRE solicitudes
    distintas — cada request sigue abriendo (y cerrando) la suya."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _setup() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(User(id="u1", email="a@example.com", password_hash="x", role="user"))
            await session.commit()

    asyncio.run(_setup())

    session_open_count = {"n": 0}

    async def _instrumented_get_session():
        session_open_count["n"] += 1
        async with session_factory() as session:
            yield session

    app = FastAPI()

    @app.get("/probe")
    async def probe(
        user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_session),
    ) -> dict:
        return {"user_id": user["sub"]}

    app.dependency_overrides[get_optional_user] = lambda: {
        "sub": "u1",
        "email": "a@example.com",
        "role": "user",
    }
    app.dependency_overrides[get_session] = _instrumented_get_session

    client = TestClient(app)
    try:
        client.get("/probe")
        client.get("/probe")
    finally:
        asyncio.run(engine.dispose())

    assert session_open_count["n"] == 2
