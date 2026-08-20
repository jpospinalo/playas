"""Limitador local y reversible para las consultas costosas del RAG."""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from rag.api.auth import get_current_user
from rag.config import (
    AUTH_RATE_LIMIT_MODE,
    AUTH_RATE_LIMIT_REQUESTS,
    AUTH_RATE_LIMIT_WINDOW_SECONDS,
    RATE_LIMIT_MODE,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    TITLE_RATE_LIMIT_MODE,
    TITLE_RATE_LIMIT_REQUESTS,
    TITLE_RATE_LIMIT_WINDOW_SECONDS,
    RateLimitMode,
)

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    """Ventana deslizante por clave, sin dependencias ni estado externo.

    ``off`` conserva exactamente el comportamiento actual. ``observe`` registra
    los excesos sin bloquear. ``enforce`` responde 429.

    Generalización de lo que antes era ``QueryRateLimiter`` (usado solo para
    las consultas RAG): la lógica es idéntica, pero la clave ya no se asume
    que sea siempre un user_id de consulta, para poder reutilizarla en otros
    límites independientes (p. ej. generación de título, login).
    """

    def __init__(
        self,
        *,
        mode: RateLimitMode = "off",
        max_requests: int = 10,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests debe ser mayor que cero")
        if window_seconds <= 0:
            raise ValueError("window_seconds debe ser mayor que cero")
        self.mode = mode
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()
        self._checks = 0

    async def check(self, key: str) -> None:
        if self.mode == "off":
            return

        now = self._clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()

            limited = len(events) >= self.max_requests
            retry_after = (
                max(1, math.ceil(self.window_seconds - (now - events[0]))) if limited else 0
            )
            if not limited:
                events.append(now)

            self._checks += 1
            if self._checks % 1024 == 0:
                stale_keys = [
                    stale_key
                    for stale_key, values in self._events.items()
                    if not values or values[-1] <= cutoff
                ]
                for stale_key in stale_keys:
                    self._events.pop(stale_key, None)

        if not limited:
            return
        if self.mode == "observe":
            logger.warning(
                "Límite de solicitudes superado en modo observación", extra={"key": key}
            )
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Se alcanzó temporalmente el límite de consultas. Intenta nuevamente más tarde.",
            headers={"Retry-After": str(retry_after)},
        )


# Alias de compatibilidad: el nombre público original se conserva para no
# romper importaciones existentes (tests, código externo).
QueryRateLimiter = SlidingWindowRateLimiter


query_rate_limiter = SlidingWindowRateLimiter(
    mode=RATE_LIMIT_MODE,
    max_requests=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
)

title_rate_limiter = SlidingWindowRateLimiter(
    mode=TITLE_RATE_LIMIT_MODE,
    max_requests=TITLE_RATE_LIMIT_REQUESTS,
    window_seconds=TITLE_RATE_LIMIT_WINDOW_SECONDS,
)

# Sin dependencia de get_current_user: /api/auth/login ocurre antes de la
# autenticación, así que routes/auth.py llama a login_rate_limiter.check(key)
# directamente con una clave derivada de email + IP de origen.
login_rate_limiter = SlidingWindowRateLimiter(
    mode=AUTH_RATE_LIMIT_MODE,
    max_requests=AUTH_RATE_LIMIT_REQUESTS,
    window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS,
)


async def get_query_user(user: dict = Depends(get_current_user)) -> dict:
    """Autentica y aplica el límite exclusivamente a consultas RAG."""
    await query_rate_limiter.check(user["sub"])
    return user


async def get_title_user(user: dict = Depends(get_current_user)) -> dict:
    """Autentica y aplica el límite, independiente del de consultas RAG,
    exclusivamente al endpoint de generación de título."""
    await title_rate_limiter.check(user["sub"])
    return user
