"""A2, punto de control 4 — re-hash oportunista de hashes heredados en login.

Tras un login exitoso con un hash heredado (ver ``rag.api.passwords`` para
los tres formatos reconocidos), ``login()`` intenta actualizar
``password_hash`` al formato actual (``_opportunistically_rehash`` en
``routes/auth.py``). La contraseña ya fue validada contra el hash heredado
*antes* de intentar esa actualización — por lo tanto un fallo exclusivamente
en ese paso (calcular el nuevo hash, o confirmarlo en la base de datos) NUNCA
debe impedir el login ya validado: se revierte solo esa actualización
(``session.rollback()``) y se conserva el hash anterior intacto, sin afectar
el código HTTP, el payload ni el JWT emitido.

Un hash ya en formato actual no se toca en absoluto (``needs_rehash`` es
``False``): se comprueba por conteo de llamadas, no solo por el resultado —
mismo motivo que en ``test_enrichment_llm_skip.py`` (A1.5). Ninguna
contraseña ni hash de este archivo es real; son cadenas sintéticas usadas
solo dentro de la prueba.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator

import bcrypt
import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import rag.api.routes.auth as auth_module
from rag.api.models import Base, User
from rag.api.passwords import hash_password, verify_password
from rag.api.routes.auth import LoginRequest, login

# Engines creados por _fresh_session_factory() en esta ejecución de pytest,
# pendientes de dispose() — mismo patrón que test_readiness_endpoint.py
# (A1.4) y test_bcrypt_off_event_loop.py (A2): sin esto, los hilos de fondo
# de aiosqlite pueden disparar "Event loop is closed" contra el event loop
# de una prueba posterior.
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


def _fake_request(host: str = "127.0.0.1") -> Request:
    return Request(scope={"type": "http", "client": (host, 12345), "headers": []})


async def _fresh_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


def _legacy_prehash_hash(password: str) -> str:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")


def _legacy_direct_hash(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def _seed_user(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: str,
    email: str,
    password_hash: str,
) -> None:
    async with session_factory() as session:
        session.add(
            User(
                id=user_id,
                email=email,
                password_hash=password_hash,
                display_name="Usuaria de prueba",
                role="user",
            )
        )
        await session.commit()


# ---------------------------------------------------------------------------
# El login sube un hash heredado (cualquiera de los dos formatos) al actual
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("legacy_hash_factory", [_legacy_prehash_hash, _legacy_direct_hash])
async def test_login_upgrades_a_legacy_hash_to_current_format(
    legacy_hash_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    password = "contraseña-sintética-heredada"
    old_hash = legacy_hash_factory(password)
    session_factory = await _fresh_session_factory()
    await _seed_user(
        session_factory, user_id="user-legacy", email="legado@example.com", password_hash=old_hash
    )

    async with session_factory() as login_session:
        response = await login(
            LoginRequest(email="legado@example.com", password=password),
            _fake_request(),
            session=login_session,
        )

    assert response.user_id == "user-legacy"
    assert response.access_token

    async with session_factory() as check_session:
        stored = await check_session.get(User, "user-legacy")
        assert stored is not None
        assert stored.password_hash != old_hash
        assert stored.password_hash.startswith("v2:")
        assert verify_password(password, stored.password_hash)


@pytest.mark.anyio
async def test_login_does_not_touch_an_already_current_format_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    password = "contraseña-sintética-actual"
    current_hash = hash_password(password)  # ya en formato actual (prefijo v2:)
    session_factory = await _fresh_session_factory()
    await _seed_user(
        session_factory,
        user_id="user-current",
        email="actual@example.com",
        password_hash=current_hash,
    )

    calls: list[int] = []

    async def _boom(_password: str) -> str:
        calls.append(1)
        raise AssertionError("hash_password_async no debía llamarse para un hash ya actual")

    monkeypatch.setattr(auth_module, "hash_password_async", _boom)

    async with session_factory() as login_session:
        response = await login(
            LoginRequest(email="actual@example.com", password=password),
            _fake_request(),
            session=login_session,
        )

    assert calls == []
    assert response.user_id == "user-current"

    async with session_factory() as check_session:
        stored = await check_session.get(User, "user-current")
        assert stored is not None
        assert stored.password_hash == current_hash


# ---------------------------------------------------------------------------
# Un fallo EXCLUSIVO del re-hash oportunista no impide el login ya validado
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_succeeds_and_keeps_old_hash_when_rehash_computation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    password = "contraseña-sintética-heredada-2"
    old_hash = _legacy_prehash_hash(password)
    session_factory = await _fresh_session_factory()
    await _seed_user(
        session_factory, user_id="user-fail-1", email="falla1@example.com", password_hash=old_hash
    )

    async def _boom(_password: str) -> str:
        raise RuntimeError("fallo simulado calculando el nuevo hash")

    monkeypatch.setattr(auth_module, "hash_password_async", _boom)

    async with session_factory() as login_session:
        response = await login(
            LoginRequest(email="falla1@example.com", password=password),
            _fake_request(),
            session=login_session,
        )

    # El login ya validado no debe verse afectado: mismo contrato de
    # respuesta que un login exitoso normal.
    assert response.user_id == "user-fail-1"
    assert response.email == "falla1@example.com"
    assert response.token_type == "bearer"
    assert response.access_token

    async with session_factory() as check_session:
        stored = await check_session.get(User, "user-fail-1")
        assert stored is not None
        assert stored.password_hash == old_hash, "el hash heredado debía conservarse intacto"
        assert verify_password(password, stored.password_hash)


@pytest.mark.anyio
async def test_login_succeeds_and_keeps_old_hash_when_rehash_commit_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    password = "contraseña-sintética-heredada-3"
    old_hash = _legacy_direct_hash(password)
    session_factory = await _fresh_session_factory()
    await _seed_user(
        session_factory, user_id="user-fail-2", email="falla2@example.com", password_hash=old_hash
    )

    async with session_factory() as login_session:

        async def _boom_commit() -> None:
            raise RuntimeError("fallo simulado confirmando el nuevo hash en la base de datos")

        monkeypatch.setattr(login_session, "commit", _boom_commit)

        response = await login(
            LoginRequest(email="falla2@example.com", password=password),
            _fake_request(),
            session=login_session,
        )

    assert response.user_id == "user-fail-2"
    assert response.access_token

    async with session_factory() as check_session:
        stored = await check_session.get(User, "user-fail-2")
        assert stored is not None
        assert stored.password_hash == old_hash, "el hash heredado debía conservarse intacto"
        assert verify_password(password, stored.password_hash)


@pytest.mark.anyio
async def test_wrong_password_never_attempts_a_rehash(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un intento fallido de login (contraseña incorrecta) no debe tocar el
    hash almacenado bajo ninguna circunstancia — la ruta de re-hash está
    estrictamente después de la verificación exitosa."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    old_hash = _legacy_prehash_hash("contraseña-correcta-4")
    session_factory = await _fresh_session_factory()
    await _seed_user(
        session_factory,
        user_id="user-wrong",
        email="incorrecta@example.com",
        password_hash=old_hash,
    )

    calls: list[int] = []

    async def _boom(_password: str) -> str:
        calls.append(1)
        raise AssertionError("hash_password_async no debía llamarse")

    monkeypatch.setattr(auth_module, "hash_password_async", _boom)

    async with session_factory() as login_session:
        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(email="incorrecta@example.com", password="contraseña-equivocada"),
                _fake_request(),
                session=login_session,
            )

    assert exc_info.value.status_code == 401
    assert calls == []

    async with session_factory() as check_session:
        stored = await check_session.get(User, "user-wrong")
        assert stored is not None
        assert stored.password_hash == old_hash
