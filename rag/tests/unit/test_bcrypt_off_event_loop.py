"""A2, punto de control 1 — bcrypt fuera del event loop.

``bcrypt.hashpw``/``bcrypt.checkpw`` son síncronos y deliberadamente costosos
en CPU (ese costo es la propiedad de seguridad que los hace útiles). Llamarlos
directamente desde un endpoint ``async`` bloquea el event loop del proceso
ASGI durante ese cómputo, congelando *todas* las demás peticiones concurrentes
(incluidas las que no tocan contraseñas) mientras dura el hashing.

``rag.api.passwords`` ahora expone ``hash_password_async``/
``verify_password_async``, que delegan en las variantes síncronas existentes
vía ``asyncio.to_thread`` — el resultado y el formato del hash no cambian en
absoluto, solo el hilo en el que se ejecuta el cómputo. Los cuatro sitios de
llamada en ``routes/auth.py`` y ``routes/admin.py`` (login, registro, alta de
usuario por admin, cambio de contraseña por admin) se actualizaron para usar
las variantes async.

Este archivo cubre dos capas:

  1. Unidad: ``hash_password_async``/``verify_password_async`` producen
     resultados idénticos y cruzadamente verificables con las variantes
     síncronas, y el hashing efectivamente corre en un hilo distinto al que
     hace la llamada (prueba directa de "fuera del event loop", no solo una
     inferencia por ausencia de bloqueo observado).
  2. Regresión de contrato: login, registro, alta de usuario admin y cambio
     de contraseña admin — invocados directamente como funciones async, con
     una base de datos SQLite real — se comportan exactamente igual que
     antes de este cambio (mismos códigos HTTP efectivos vía
     ``HTTPException``, mismo payload de ``TokenResponse``/``AdminUserItem``,
     mismo contrato JWT). Ninguna contraseña ni hash de este archivo es real;
     son cadenas sintéticas usadas solo dentro de la prueba.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import rag.api.passwords as passwords_module
import rag.api.routes.auth as auth_module
from rag.api.models import Base, User
from rag.api.passwords import (
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)
from rag.api.routes.admin import create_user, update_user_password
from rag.api.routes.auth import LoginRequest, RegisterRequest, login, register
from rag.api.schemas import CreateUserRequest, UpdatePasswordRequest

_ADMIN = {"sub": "admin-1", "role": "admin"}

# Engines creados por _fresh_session() en esta ejecución de pytest, pendientes
# de dispose() — mismo patrón que test_readiness_endpoint.py (A1.4): sin esto,
# los hilos de fondo de aiosqlite pueden disparar "Event loop is closed"
# contra el event loop de una prueba posterior.
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


async def _fresh_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory()


def _fake_request(host: str = "127.0.0.1") -> Request:
    """``Request`` mínimo — suficiente para ``request.client.host``, que es
    lo único que ``login()`` lee de él (además de lo ya parseado en ``payload``)."""
    return Request(scope={"type": "http", "client": (host, 12345), "headers": []})


# ---------------------------------------------------------------------------
# 1a. hash_password_async / verify_password_async — equivalencia funcional
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_hash_password_async_produces_a_hash_verify_password_accepts() -> None:
    password = "contraseña-sintética-de-prueba-1"
    hashed = await hash_password_async(password)
    assert await verify_password_async(password, hashed)
    assert not await verify_password_async("otra-contraseña", hashed)


@pytest.mark.anyio
async def test_hash_password_async_output_is_verifiable_by_sync_verify_password() -> None:
    """El formato del hash no cambia — solo dónde se ejecuta el cómputo."""
    password = "contraseña-sintética-de-prueba-2"
    hashed = await hash_password_async(password)
    assert verify_password(password, hashed)


@pytest.mark.anyio
async def test_sync_hash_password_output_is_verifiable_by_verify_password_async() -> None:
    password = "contraseña-sintética-de-prueba-3"
    hashed = hash_password(password)
    assert await verify_password_async(password, hashed)


@pytest.mark.anyio
async def test_verify_password_async_returns_false_for_malformed_hash() -> None:
    assert not await verify_password_async("contraseña", "hash-inválido")


# ---------------------------------------------------------------------------
# 1b. Prueba directa de que el cómputo corre fuera del hilo que llama —
#     no una inferencia por ausencia de bloqueo observado.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_hash_password_async_executes_on_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calling_thread = threading.current_thread()
    seen_threads: list[threading.Thread] = []
    original_hash_password = passwords_module.hash_password

    def _spy(password: str) -> str:
        seen_threads.append(threading.current_thread())
        return original_hash_password(password)

    monkeypatch.setattr(passwords_module, "hash_password", _spy)

    await hash_password_async("contraseña-sintética-de-prueba-4")

    assert len(seen_threads) == 1
    assert seen_threads[0] is not calling_thread


@pytest.mark.anyio
async def test_verify_password_async_executes_on_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calling_thread = threading.current_thread()
    seen_threads: list[threading.Thread] = []
    original_verify_password = passwords_module.verify_password
    hashed = hash_password("contraseña-sintética-de-prueba-5")

    def _spy(password: str, hashed_arg: str) -> bool:
        seen_threads.append(threading.current_thread())
        return original_verify_password(password, hashed_arg)

    monkeypatch.setattr(passwords_module, "verify_password", _spy)

    result = await verify_password_async("contraseña-sintética-de-prueba-5", hashed)

    assert result is True
    assert len(seen_threads) == 1
    assert seen_threads[0] is not calling_thread


@pytest.mark.anyio
async def test_event_loop_stays_responsive_during_hashing() -> None:
    """Mientras ``hash_password_async`` corre (bcrypt real, no simulado), el
    event loop debe seguir atendiendo otras tareas — un ``asyncio.sleep(0)``
    en un loop paralelo debe poder avanzar varias veces antes de que termine
    el hashing. Con la llamada síncrona anterior (bloqueante), el conteo
    habría quedado en 0."""
    progress = 0
    stop = False

    async def _ticker() -> None:
        nonlocal progress
        while not stop:
            await asyncio.sleep(0)
            progress += 1

    ticker_task = asyncio.ensure_future(_ticker())
    await hash_password_async("contraseña-sintética-de-prueba-6")
    stop = True
    await ticker_task

    assert progress > 0, "el event loop no avanzó ninguna otra tarea durante el hashing"


# ---------------------------------------------------------------------------
# 2. Regresión de contrato — login/registro/admin, sin cambios visibles
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_succeeds_and_issues_a_token_for_the_right_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    session = await _fresh_session()
    async with session:
        session.add(
            User(
                id="user-1",
                email="usuaria@example.com",
                password_hash=hash_password("contraseña-sintética-login-ok"),
                display_name="Usuaria de prueba",
                role="user",
            )
        )
        await session.commit()

        response = await login(
            LoginRequest(email="usuaria@example.com", password="contraseña-sintética-login-ok"),
            _fake_request(),
            session=session,
        )

    assert response.user_id == "user-1"
    assert response.email == "usuaria@example.com"
    assert response.role == "user"
    assert response.token_type == "bearer"
    assert response.access_token


@pytest.mark.anyio
async def test_login_rejects_wrong_password_with_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    session = await _fresh_session()
    async with session:
        session.add(
            User(
                id="user-2",
                email="otra@example.com",
                password_hash=hash_password("contraseña-sintética-correcta"),
                display_name=None,
                role="user",
            )
        )
        await session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(email="otra@example.com", password="contraseña-incorrecta"),
                _fake_request(),
                session=session,
            )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Correo o contraseña incorrectos."


@pytest.mark.anyio
async def test_register_creates_user_and_issues_a_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    monkeypatch.setattr(auth_module, "_REGISTER_ENABLED", True)
    session = await _fresh_session()
    async with session:
        response = await register(
            RegisterRequest(
                email="nueva@example.com",
                password="contraseña-sintética-registro",
                display_name="Nueva",
            ),
            session=session,
        )

        assert response.email == "nueva@example.com"
        assert response.role == "user"
        assert response.access_token

        stored = (
            await session.execute(select(User).where(User.email == "nueva@example.com"))
        ).scalar_one()
        assert verify_password("contraseña-sintética-registro", stored.password_hash)


@pytest.mark.anyio
async def test_register_returns_403_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_module, "_REGISTER_ENABLED", False)
    session = await _fresh_session()
    async with session:
        with pytest.raises(HTTPException) as exc_info:
            await register(
                RegisterRequest(email="x@example.com", password="contraseña-sintética-x"),
                session=session,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.anyio
async def test_admin_create_user_stores_a_hash_the_user_can_log_in_with() -> None:
    session = await _fresh_session()
    async with session:
        item = await create_user(
            CreateUserRequest(
                email="creado-por-admin@example.com",
                password="contraseña-sintética-admin-alta",
                displayName="Creada por admin",
            ),
            _admin=_ADMIN,
            session=session,
        )

        assert item.email == "creado-por-admin@example.com"
        assert item.role == "user"

        stored = (
            await session.execute(select(User).where(User.email == "creado-por-admin@example.com"))
        ).scalar_one()
        assert verify_password("contraseña-sintética-admin-alta", stored.password_hash)


@pytest.mark.anyio
async def test_admin_update_password_replaces_the_hash() -> None:
    session = await _fresh_session()
    async with session:
        session.add(
            User(
                id="user-3",
                email="cambia@example.com",
                password_hash=hash_password("contraseña-sintética-vieja"),
                display_name=None,
                role="user",
            )
        )
        await session.commit()

        await update_user_password(
            "user-3",
            UpdatePasswordRequest(password="contraseña-sintética-nueva"),
            _admin=_ADMIN,
            session=session,
        )

        stored = await session.get(User, "user-3")
        assert stored is not None
        assert verify_password("contraseña-sintética-nueva", stored.password_hash)
        assert not verify_password("contraseña-sintética-vieja", stored.password_hash)


@pytest.mark.anyio
async def test_admin_update_password_404s_for_unknown_user() -> None:
    session = await _fresh_session()
    async with session:
        with pytest.raises(HTTPException) as exc_info:
            await update_user_password(
                "no-existe",
                UpdatePasswordRequest(password="contraseña-sintética-cualquiera"),
                _admin=_ADMIN,
                session=session,
            )

    assert exc_info.value.status_code == 404
