"""T3.6 — backpressure de concurrencia (rag.api.rate_limit.ConcurrencyBackpressure).

Distinto del rate limiting existente (SlidingWindowRateLimiter): eso acota
solicitudes POR CLAVE en una ventana de tiempo; esto acota cuántas consultas
pueden estar EN VUELO simultáneamente en todo el proceso, sin importar la
clave. Mismo modelo off/observe/enforce, mecanismo distinto (semáforo de
concurrencia, no ventana deslizante) — nunca deben confundirse ni compartir
estado.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import HTTPException

from rag.api.rate_limit import ConcurrencyBackpressure


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_off_mode_never_blocks_or_tracks() -> None:
    backpressure = ConcurrencyBackpressure(mode="off", max_concurrent=1)
    async with backpressure.slot():
        async with backpressure.slot():
            async with backpressure.slot():
                pass
    # off no debe ni siquiera contabilizar: cero overhead, igual que hoy.
    assert backpressure.in_flight == 0


@pytest.mark.anyio
async def test_enforce_mode_allows_up_to_the_limit() -> None:
    backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=2)
    async with backpressure.slot():
        async with backpressure.slot():
            assert backpressure.in_flight == 2


@pytest.mark.anyio
async def test_enforce_mode_rejects_with_503_when_at_capacity() -> None:
    backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    async with backpressure.slot():
        with pytest.raises(HTTPException) as error:
            async with backpressure.slot():
                pass
    assert error.value.status_code == 503
    assert "Retry-After" in (error.value.headers or {})


@pytest.mark.anyio
async def test_enforce_mode_releases_slot_after_success() -> None:
    backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    async with backpressure.slot():
        pass
    assert backpressure.in_flight == 0
    # El slot liberado debe poder reutilizarse sin lanzar.
    async with backpressure.slot():
        assert backpressure.in_flight == 1


@pytest.mark.anyio
async def test_enforce_mode_releases_slot_even_on_exception() -> None:
    backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    with pytest.raises(RuntimeError):
        async with backpressure.slot():
            raise RuntimeError("boom")
    assert backpressure.in_flight == 0
    async with backpressure.slot():
        assert backpressure.in_flight == 1


@pytest.mark.anyio
async def test_observe_mode_never_blocks_even_over_capacity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backpressure = ConcurrencyBackpressure(mode="observe", max_concurrent=1, scope="query")
    with caplog.at_level(logging.WARNING):
        async with backpressure.slot():
            # Segundo slot concurrente por encima del límite: en observe NO
            # debe bloquear ni lanzar, solo registrar.
            async with backpressure.slot():
                assert backpressure.in_flight == 2
    assert "modo observación" in caplog.text


@pytest.mark.anyio
async def test_observe_mode_does_not_log_below_capacity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    backpressure = ConcurrencyBackpressure(mode="observe", max_concurrent=5)
    with caplog.at_level(logging.WARNING):
        async with backpressure.slot():
            pass
    assert caplog.text == ""


@pytest.mark.anyio
async def test_concurrent_requests_actually_serialize_at_the_limit() -> None:
    """Prueba de concurrencia real (no solo secuencial): con max_concurrent=2
    y 3 tareas que retienen su slot 50ms, la tercera debe recibir 503 en
    algún punto porque coincide con las otras dos en vuelo."""
    backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=2)
    results: list[str] = []

    async def worker(tag: str) -> None:
        try:
            async with backpressure.slot():
                results.append(f"{tag}:ok")
                await asyncio.sleep(0.05)
        except HTTPException:
            results.append(f"{tag}:rejected")

    await asyncio.gather(worker("a"), worker("b"), worker("c"))

    assert results.count("a:ok") + results.count("b:ok") + results.count("c:ok") == 2
    assert (
        results.count("a:rejected") + results.count("b:rejected") + results.count("c:rejected") == 1
    )


def test_backpressure_mode_and_max_concurrent_default_to_off_and_twenty() -> None:
    """off por defecto: sin cambio funcional hasta que se active por env var."""
    from rag.config import BACKPRESSURE_MAX_CONCURRENT, BACKPRESSURE_MODE

    assert BACKPRESSURE_MODE == "off"
    assert BACKPRESSURE_MAX_CONCURRENT == 20


def test_backpressure_detail_message_is_distinct_from_rate_limit_messages() -> None:
    from rag.api.rate_limit import login_rate_limiter, query_rate_limiter, title_rate_limiter

    backpressure = ConcurrencyBackpressure(mode="enforce", max_concurrent=1)
    assert backpressure.detail != query_rate_limiter.detail
    assert backpressure.detail != title_rate_limiter.detail
    assert backpressure.detail != login_rate_limiter.detail
