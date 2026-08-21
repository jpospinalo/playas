"""Pruebas del limitador reversible de consultas RAG y sus reutilizaciones."""

from __future__ import annotations

import logging

import pytest
from fastapi import HTTPException

from rag.api.rate_limit import QueryRateLimiter, SlidingWindowRateLimiter


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class MutableClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


@pytest.mark.anyio
async def test_off_mode_never_changes_existing_behavior() -> None:
    limiter = QueryRateLimiter(mode="off", max_requests=1, window_seconds=60)
    for _ in range(20):
        await limiter.check("user-1")


@pytest.mark.anyio
async def test_observe_mode_reports_without_blocking(caplog: pytest.LogCaptureFixture) -> None:
    limiter = QueryRateLimiter(mode="observe", max_requests=1, window_seconds=60)
    with caplog.at_level(logging.WARNING):
        await limiter.check("user-1")
        await limiter.check("user-1")
    assert "modo observación" in caplog.text


@pytest.mark.anyio
async def test_enforce_mode_isolated_by_user_and_recovers_after_window() -> None:
    clock = MutableClock()
    limiter = QueryRateLimiter(
        mode="enforce",
        max_requests=2,
        window_seconds=60,
        clock=clock,
    )
    await limiter.check("user-1")
    await limiter.check("user-1")
    await limiter.check("user-2")

    with pytest.raises(HTTPException) as error:
        await limiter.check("user-1")
    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "60"}

    clock.value = 61
    await limiter.check("user-1")


def test_query_rate_limiter_is_an_alias_of_sliding_window_rate_limiter() -> None:
    """Compatibilidad: código/tests existentes que importan QueryRateLimiter
    deben seguir funcionando exactamente igual tras la generalización."""
    assert QueryRateLimiter is SlidingWindowRateLimiter


@pytest.mark.anyio
async def test_sliding_window_rate_limiter_isolates_independent_instances() -> None:
    """Dos límites independientes (p. ej. consultas RAG y generación de
    título) sobre la misma clave de usuario no deben interferir entre sí."""
    query_limiter = SlidingWindowRateLimiter(mode="enforce", max_requests=1, window_seconds=60)
    title_limiter = SlidingWindowRateLimiter(mode="enforce", max_requests=1, window_seconds=60)

    await query_limiter.check("user-1")
    with pytest.raises(HTTPException):
        await query_limiter.check("user-1")

    # El límite de título es independiente: no fue consumido por el de consultas.
    await title_limiter.check("user-1")
    with pytest.raises(HTTPException):
        await title_limiter.check("user-1")


def test_title_rate_limiter_defaults_to_off_mode() -> None:
    """El límite de generación de título debe ser off por defecto, igual que
    el de consultas RAG, para no cambiar el comportamiento actual."""
    from rag.api.rate_limit import title_rate_limiter

    assert title_rate_limiter.mode == "off"


def test_login_rate_limiter_defaults_to_off_mode() -> None:
    """El límite de login debe ser off por defecto: no cambia el
    comportamiento actual hasta que se active explícitamente por env var."""
    from rag.api.rate_limit import login_rate_limiter

    assert login_rate_limiter.mode == "off"


def test_login_rate_limit_key_combines_email_and_ip_via_hash() -> None:
    """La clave del límite de login debe depender tanto del correo como de la
    IP de origen (para no bloquear a todos los usuarios detrás de la misma IP
    por los intentos fallidos de uno solo), y no debe exponer ninguno de los
    dos en claro."""
    from types import SimpleNamespace

    from rag.api.routes.auth import _login_rate_limit_key

    request_a = SimpleNamespace(client=SimpleNamespace(host="10.0.0.1"))
    request_b = SimpleNamespace(client=SimpleNamespace(host="10.0.0.2"))

    key_same_email_diff_ip = _login_rate_limit_key("user@example.com", request_a)  # type: ignore[arg-type]
    key_same_email_diff_ip_2 = _login_rate_limit_key("user@example.com", request_b)  # type: ignore[arg-type]
    key_diff_email_same_ip = _login_rate_limit_key("other@example.com", request_a)  # type: ignore[arg-type]

    assert key_same_email_diff_ip != key_same_email_diff_ip_2
    assert key_same_email_diff_ip != key_diff_email_same_ip
    assert "user@example.com" not in key_same_email_diff_ip
    assert "10.0.0.1" not in key_same_email_diff_ip


@pytest.mark.anyio
async def test_login_rate_limiter_enforces_independently_per_key() -> None:
    """Verificación funcional del límite de login en modo enforce (aunque el
    modo por defecto en producción sigue siendo off): dos claves distintas no
    se bloquean entre sí, y superar el límite responde 429."""
    limiter = SlidingWindowRateLimiter(mode="enforce", max_requests=3, window_seconds=300)
    for _ in range(3):
        await limiter.check("email-a:ip-a")
    with pytest.raises(HTTPException) as error:
        await limiter.check("email-a:ip-a")
    assert error.value.status_code == 429

    # Clave distinta (otro correo o otra IP): no afectada por el límite anterior.
    await limiter.check("email-b:ip-a")


# ── Corrección 4: mensajes y configuración por instancia ────────────────────


@pytest.mark.anyio
async def test_query_rate_limiter_keeps_its_original_detail_message() -> None:
    """El limitador de consultas RAG no cambia su texto de 429 con esta
    generalización: mismo mensaje que antes, palabra por palabra."""
    limiter = SlidingWindowRateLimiter(mode="enforce", max_requests=1, window_seconds=60)
    await limiter.check("user-1")
    with pytest.raises(HTTPException) as error:
        await limiter.check("user-1")
    assert (
        error.value.detail
        == "Se alcanzó temporalmente el límite de consultas. Intenta nuevamente más tarde."
    )

    from rag.api.rate_limit import query_rate_limiter

    assert query_rate_limiter.detail == (
        "Se alcanzó temporalmente el límite de consultas. Intenta nuevamente más tarde."
    )


@pytest.mark.anyio
async def test_title_and_login_rate_limiters_have_their_own_detail_message() -> None:
    """Título y login no deben mostrar el mensaje de "consultas": cada uno
    tiene su propio texto de 429, y Retry-After sigue presente en ambos."""
    from rag.api.rate_limit import login_rate_limiter, query_rate_limiter, title_rate_limiter

    title_limiter = SlidingWindowRateLimiter(
        mode="enforce",
        max_requests=1,
        window_seconds=60,
        detail=title_rate_limiter.detail,
        scope="title",
    )
    login_limiter = SlidingWindowRateLimiter(
        mode="enforce",
        max_requests=1,
        window_seconds=60,
        detail=login_rate_limiter.detail,
        scope="login",
    )

    await title_limiter.check("user-1")
    with pytest.raises(HTTPException) as title_error:
        await title_limiter.check("user-1")
    await login_limiter.check("key-1")
    with pytest.raises(HTTPException) as login_error:
        await login_limiter.check("key-1")

    assert "título" in title_error.value.detail
    assert "inicio de sesión" in login_error.value.detail
    assert title_error.value.detail != login_error.value.detail
    assert title_error.value.detail != query_rate_limiter.detail
    assert login_error.value.detail != query_rate_limiter.detail
    assert title_error.value.headers is not None and "Retry-After" in title_error.value.headers
    assert login_error.value.headers is not None and "Retry-After" in login_error.value.headers


def test_rate_limiter_instances_default_to_distinct_scopes() -> None:
    """Cada instancia global se etiqueta con su propio scope, para que un log
    en modo observe sea identificable sin exponer datos del usuario."""
    from rag.api.rate_limit import login_rate_limiter, query_rate_limiter, title_rate_limiter

    assert query_rate_limiter.scope == "query"
    assert title_rate_limiter.scope == "title"
    assert login_rate_limiter.scope == "login"


def test_title_rate_limit_default_requests_is_five() -> None:
    """El plan aprobado especificó TITLE_RATE_LIMIT_REQUESTS=5; el código y
    .env.example deben coincidir (el modo sigue en off, así que esto no activa
    ningún bloqueo nuevo)."""
    from rag.config import TITLE_RATE_LIMIT_REQUESTS

    assert TITLE_RATE_LIMIT_REQUESTS == 5


@pytest.mark.anyio
async def test_off_mode_never_logs(caplog: pytest.LogCaptureFixture) -> None:
    """off debe retornar antes de adquirir el lock, guardar eventos o escribir
    logs — igual que hoy — incluso llamado muchas veces."""
    limiter = SlidingWindowRateLimiter(mode="off", max_requests=1, window_seconds=60)
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            await limiter.check("user-1")
    assert caplog.text == ""
    assert limiter._events == {}


@pytest.mark.anyio
async def test_login_observe_logs_never_contain_email_ip_or_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """El log de modo observe para login debe llevar únicamente la etiqueta
    estática de scope, nunca el email, la IP ni la contraseña del intento.

    Todos los valores usados abajo son sintéticos, no datos reales: el email
    usa el dominio `example.com` (RFC 2606, reservado para documentación) y
    la IP usa el rango `203.0.113.0/24` (RFC 5737, TEST-NET-3, reservado para
    ejemplos); la "contraseña" es un literal de prueba que nunca se envía a
    ningún servicio, solo se compara contra el texto del log en memoria.
    """
    import hashlib

    email = "someone@example.com"
    ip = "203.0.113.7"
    password = "hunter2-super-secret"
    key = hashlib.sha256(f"{email}:{ip}".encode()).hexdigest()

    limiter = SlidingWindowRateLimiter(
        mode="observe",
        max_requests=1,
        window_seconds=60,
        scope="login",
    )
    with caplog.at_level(logging.WARNING):
        await limiter.check(key)
        await limiter.check(key)

    assert email not in caplog.text
    assert ip not in caplog.text
    assert password not in caplog.text
    assert "modo observación" in caplog.text
