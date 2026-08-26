# rag/api/conversation_lock.py
"""T3.5 — lock por conversación.

Añadido ÚNICAMENTE porque un test demuestra interleaving real (ver
``tests/unit/test_conversation_lock.py``): dos turnos concurrentes sobre el
mismo ``thread_id`` de LangGraph (p. ej. doble clic en enviar, o dos
pestañas del navegador abiertas sobre la misma conversación) pueden
interleavearse durante ``graph.ainvoke()``/``graph.astream()`` porque ambos
leen/escriben el mismo checkpoint de ``MemorySaver`` sin ninguna exclusión
mutua — el resultado observado fue que uno de los dos ``AIMessage`` de
respuesta se perdía silenciosamente del checkpoint final.

No serializa nada más: conversaciones con ``thread_id`` distintos siguen
avanzando en paralelo sin esperarse entre sí (ver el mismo archivo de
pruebas, ``test_concurrent_turns_on_different_threads_are_not_serialized``).
"""

from __future__ import annotations

import asyncio
from collections import defaultdict


class ConversationLockRegistry:
    """Un ``asyncio.Lock`` por clave (``thread_id``), creado bajo demanda.

    Sin límite de memoria explícito: el número de conversaciones con un
    turno realmente en vuelo en un instante dado está acotado por el
    tráfico concurrente real (no por el total de conversaciones históricas),
    varios órdenes de magnitud más chico. Si eso deja de ser cierto, conviene
    revisarlo junto con T3.4 (autoridad de ``MemorySaver``), que tiene el
    mismo patrón de crecimiento por ``thread_id``.
    """

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def lock_for(self, key: str) -> asyncio.Lock:
        return self._locks[key]
