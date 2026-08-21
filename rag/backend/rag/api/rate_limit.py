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

    #: Mensaje por defecto, preservado exactamente igual al que tenía el
    #: limitador de consultas RAG antes de esta generalización.
    _DEFAULT_DETAIL = "Se alcanzó temporalmente el límite de consultas. Intenta nuevamente más tarde."

    def __init__(
        self,
        *,
        mode: RateLimitMode = "off",
        max_requests: int = 10,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        detail: str = _DEFAULT_DETAIL,
        scope: str = "query",
    ) -> None:
        if max_requests < 1:
            raise ValueError("max_requests debe ser mayor que cero")
        if window_seconds <= 0:
            raise ValueError("window_seconds debe ser mayor que cero")
        self.mode = mode
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        # `detail` es el texto del 429 devuelto al cliente: cada instancia
        # (consultas RAG, títulos, login) tiene el suyo, para no mostrar un
        # mensaje sobre "consultas" cuando en realidad se limitó un login o
        # una generación de título.
        self.detail = detail
        # `scope` es solo una etiqueta estática para los logs en modo
        # observe (p. ej. "query", "title", "login"). Nunca debe llevar
        # datos del usuario (email, IP, contraseña, token): esos ya se
        # excluyen aguas arriba, en la clave que le pasa cada llamador.
        self.scope = scope
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
            # Solo una etiqueta estática (self.scope), nunca la clave en sí:
            # para login, la clave ya es un hash SHA-256, pero igual no se
            # registra aquí para no acoplar este log a su formato.
            logger.warning(
                "Límite de solicitudes superado en modo observación",
                extra={"scope": self.scope},
            )
            return
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=self.detail,
            headers={"Retry-After": str(retry_after)},
        )


# Alias de compatibilidad: el nombre público original se conserva para no
# romper importaciones existentes (tests, código externo).
QueryRateLimiter = SlidingWindowRateLimiter


query_rate_limiter = SlidingWindowRateLimiter(
    mode=RATE_LIMIT_MODE,
    max_requests=RATE_LIMIT_REQUESTS,
    window_seconds=RATE_LIMIT_WINDOW_SECONDS,
    scope="query",
    # detail: sin especificar, conserva _DEFAULT_DETAIL (el mensaje original
    # del limitador de consultas RAG), sin cambio alguno.
)

title_rate_limiter = SlidingWindowRateLimiter(
    mode=TITLE_RATE_LIMIT_MODE,
    max_requests=TITLE_RATE_LIMIT_REQUESTS,
    window_seconds=TITLE_RATE_LIMIT_WINDOW_SECONDS,
    detail="Se alcanzó temporalmente el límite de generación de títulos. Intenta nuevamente más tarde.",
    scope="title",
)

# Sin dependencia de get_current_user: /api/auth/login ocurre antes de la
# autenticación, así que routes/auth.py llama a login_rate_limiter.check(key)
# directamente con una clave derivada de email + IP de origen.
login_rate_limiter = SlidingWindowRateLimiter(
    mode=AUTH_RATE_LIMIT_MODE,
    max_requests=AUTH_RATE_LIMIT_REQUESTS,
    window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS,
    detail="Se alcanzó temporalmente el límite de intentos de inicio de sesión. Intenta nuevamente más tarde.",
    scope="login",
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
