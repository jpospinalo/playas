"""C1/3.3 — el login ejecuta SIEMPRE una verificación bcrypt, exista o no el
usuario, y responde exactamente igual (mismo código HTTP, mismo mensaje
público) en ambos casos de fallo.

Antes de esta corrección, ``login()`` cortocircuitaba con `user is None or
not await verify_password_async(...)`: para un email inexistente, la parte
izquierda del ``or`` ya era verdadera y Python nunca evaluaba
``verify_password_async`` (evaluación perezosa de ``or``) — cero bcrypt para
"no existe" frente a un bcrypt real (~cientos de ms) para "existe, contraseña
incorrecta". Esa asimetría de tiempo es una fuga de temporización clásica que
permite enumerar cuentas por email sin acertar ninguna contraseña.

La corrección (``routes/auth.py``) llama SIEMPRE a ``verify_password_async``,
contra el hash real del usuario si existe o contra ``_DUMMY_PASSWORD_HASH``
(constante sintética con el prefijo del esquema actual) si no — mismo costo
computacional, mismo código 401, mismo mensaje en ambos casos. Ninguna
contraseña ni email de este archivo es real.

v1.2/C4 — ``_DUMMY_PASSWORD_HASH`` es ahora un literal fijo (no se calcula
más con ``hash_password()`` al importar el módulo, para no pagar el costo de
``bcrypt.gensalt()`` en cada arranque/recarga sin ningún beneficio real).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

import rag.api.passwords as passwords_module
import rag.api.routes.auth as auth_module
from rag.api.models import Base, User
from rag.api.passwords import hash_password
from rag.api.routes.auth import LoginRequest, login

# Mismo patrón de limpieza de engines que el resto del suite de A2/A3/A4 —
# sin esto, los hilos de fondo de aiosqlite pueden disparar "Event loop is
# closed" contra el event loop de una prueba posterior.
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
    """``Request`` mínimo — suficiente para ``request.client.host``, lo único
    que ``login()`` lee de él además de lo ya parseado en ``payload``."""
    return Request(scope={"type": "http", "client": (host, 12345), "headers": []})


async def _fresh_session_factory() -> async_sessionmaker:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    _pending_engines.append(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return session_factory


# ---------------------------------------------------------------------------
# Una única verificación bcrypt, siempre — exista o no el usuario.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_nonexistent_user_login_executes_exactly_one_bcrypt_verification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    session_factory = await _fresh_session_factory()

    calls: list[tuple[str, str]] = []
    original_verify_password = passwords_module.verify_password

    def _spy(password: str, hashed: str) -> bool:
        calls.append((password, hashed))
        return original_verify_password(password, hashed)

    monkeypatch.setattr(passwords_module, "verify_password", _spy)

    async with session_factory() as session:
        with pytest.raises(HTTPException) as exc_info:
            await login(
                LoginRequest(email="no-existe@example.com", password="cualquier-contraseña"),
                _fake_request(),
                session=session,
            )

    assert exc_info.value.status_code == 401
    assert len(calls) == 1, "debía ejecutarse exactamente una verificación bcrypt"
    # Verificó contra el hash sintético fijo del módulo, no contra una cadena
    # vacía ni contra ningún hash real de usuario.
    assert calls[0][1] == auth_module._DUMMY_PASSWORD_HASH


@pytest.mark.anyio
async def test_dummy_password_hash_is_a_fixed_module_level_constant() -> None:
    """Literal fijo (v1.2/C4 — ya no se calcula con hash_password() al
    importar el módulo): dos accesos ven exactamente el mismo string, con el
    prefijo del esquema actual (para que no dispare needs_rehash)."""
    first = auth_module._DUMMY_PASSWORD_HASH
    second = auth_module._DUMMY_PASSWORD_HASH
    assert first == second
    assert first.startswith("v2:")


@pytest.mark.anyio
async def test_dummy_password_hash_literal_is_a_valid_v2_bcrypt_hash() -> None:
    """v1.2/C4, 7.3 — el literal fijo debe ser un hash bcrypt bien formado,
    aceptado como tal por verify_password/verify_password_async (no un
    string arbitrario que la rama `except (TypeError, ValueError)` de
    verify_password esté ocultando como 'inválido, así que False').

    Se verifica en dos niveles: `bcrypt.checkpw` directamente (que lanza
    `ValueError` ante un hash malformado, a diferencia de verify_password,
    que la atrapa) para probar que el formato es válido de verdad, y luego
    verify_password/verify_password_async — el punto de entrada real que usa
    login() — para confirmar que ambos lo aceptan sin lanzar.
    """
    import hashlib

    import bcrypt

    from rag.api.passwords import verify_password, verify_password_async

    dummy = auth_module._DUMMY_PASSWORD_HASH
    assert dummy.startswith("v2:")
    encoded_hash = dummy[len("v2:") :].encode("utf-8")

    # No debe lanzar ValueError: un hash bcrypt bien formado nunca lanza al
    # comparar, sin importar si la contraseña coincide o no.
    digest = hashlib.sha256("cualquier-contraseña-arbitraria".encode()).digest()
    assert bcrypt.checkpw(digest, encoded_hash) is False

    assert verify_password("cualquier-contraseña-arbitraria", dummy) is False
    assert await verify_password_async("cualquier-contraseña-arbitraria", dummy) is False


@pytest.mark.anyio
async def test_nonexistent_user_login_never_attempts_an_opportunistic_rehash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``user is None`` corta antes de llegar al bloque de re-hash oportunista
    (que solo aplica a un login ya exitoso) — verificado explícitamente, no
    solo inferido del código."""
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    session_factory = await _fresh_session_factory()

    calls: list[int] = []

    async def _boom(*_args: object, **_kwargs: object) -> None:
        calls.append(1)
        raise AssertionError("no debía invocarse para un usuario inexistente")

    monkeypatch.setattr(auth_module, "_opportunistically_rehash", _boom)

    async with session_factory() as session:
        with pytest.raises(HTTPException):
            await login(
                LoginRequest(email="no-existe-2@example.com", password="lo-que-sea"),
                _fake_request(),
                session=session,
            )

    assert calls == []


# ---------------------------------------------------------------------------
# Mismo código y mismo mensaje: usuario inexistente vs. contraseña incorrecta.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_nonexistent_user_and_wrong_password_produce_identical_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    session_factory = await _fresh_session_factory()
    async with session_factory() as session:
        session.add(
            User(
                id="user-exists",
                email="existe@example.com",
                password_hash=hash_password("contraseña-correcta-real"),
                display_name=None,
                role="user",
            )
        )
        await session.commit()

    async with session_factory() as session_a:
        with pytest.raises(HTTPException) as nonexistent_error:
            await login(
                LoginRequest(email="no-existe-3@example.com", password="lo-que-sea"),
                _fake_request(),
                session=session_a,
            )

    async with session_factory() as session_b:
        with pytest.raises(HTTPException) as wrong_password_error:
            await login(
                LoginRequest(email="existe@example.com", password="contraseña-equivocada"),
                _fake_request(),
                session=session_b,
            )

    assert nonexistent_error.value.status_code == 401
    assert wrong_password_error.value.status_code == 401
    assert nonexistent_error.value.detail == wrong_password_error.value.detail
    assert nonexistent_error.value.detail == "Correo o contraseña incorrectos."


# ---------------------------------------------------------------------------
# v1.2/C4 — importar routes/auth.py no invoca hash_password().
# ---------------------------------------------------------------------------


def test_auth_module_does_not_import_hash_password() -> None:
    """``_DUMMY_PASSWORD_HASH`` es ahora un literal fijo — el módulo ya no
    necesita `hash_password` en absoluto (solo `hash_password_async`, para
    el flujo real de registro/rehash). Verificado por inspección (AST del
    árbol de imports, no reload ni maquinaria de temporización): ni el
    símbolo termina en el namespace del módulo, ni el archivo fuente lo
    importa."""
    import ast

    assert not hasattr(auth_module, "hash_password")

    with open(auth_module.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "hash_password" not in imported_names
    # `hash_password_async` sigue (y debe seguir) importado — confirma que
    # la comprobación de arriba distingue ambos nombres correctamente, en
    # vez de pasar trivialmente porque ningún import sobrevivió.
    assert "hash_password_async" in imported_names
