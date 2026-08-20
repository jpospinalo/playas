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
