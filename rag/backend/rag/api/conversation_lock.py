# rag/api/conversation_lock.py
"""Lock por conversación, con ciclo de vida administrado.

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
pruebas, ``test_concurrent_turns_on_different_threads_start_without_waiting_on_each_other``).

Ciclo de vida: ``hold(key)`` es un context manager async que cuenta
referencias (titular + quienes esperan) sobre el ``asyncio.Lock`` de cada
conversación y elimina la entrada del registro en cuanto nadie más
la necesita — el diccionario crece solo con las conversaciones que
realmente tienen un turno en vuelo, no con el total histórico de
conversaciones distintas.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class _LockEntry:
    """Un lock de conversación más cuántas tareas lo tienen reservado ahora
    mismo — sosteniéndolo o esperándolo. ``waiters`` es lo que permite saber
    cuándo es seguro eliminar la entrada del registro."""

    __slots__ = ("lock", "waiters")

    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.waiters = 0


class ConversationLockRegistry:
    """Serializa turnos concurrentes por conversación (``thread_id``), con
    limpieza determinista: una entrada del registro solo existe mientras al
    menos una tarea la está usando o esperando — nunca queda memoria
    acumulada por conversaciones históricas ya terminadas.
    """

    def __init__(self) -> None:
        self._entries: dict[str, _LockEntry] = {}
        # Protege ÚNICAMENTE las operaciones de diccionario/contador de
        # abajo — nunca se mantiene retenido durante un await de negocio
        # (red, DB, Chroma, LLM): las dos secciones que lo usan
        # (`_reserve`/`_release`) no ceden el control del event loop salvo
        # para esperar este mismo lock, así que su sección crítica es
        # siempre breve.
        self._registry_lock = asyncio.Lock()

    async def _reserve(self, key: str) -> _LockEntry:
        async with self._registry_lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _LockEntry()
                self._entries[key] = entry
            # Se cuenta ANTES de esperar el lock de conversación: así, si
            # otra tarea ya está esperando esta misma entrada, el conteo
            # refleja esa espera y la entrada no se puede eliminar bajo ella.
            entry.waiters += 1
            return entry

    async def _release(self, key: str, entry: _LockEntry) -> None:
        async with self._registry_lock:
            entry.waiters -= 1
            # La comparación por identidad (no solo por clave) evita una
            # carrera muy específica: que esta entrada ya haya sido
            # eliminada y reemplazada por una nueva bajo la misma clave
            # entre que se liberó `_registry_lock` la última vez y ahora.
            if entry.waiters <= 0 and self._entries.get(key) is entry:
                del self._entries[key]

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        """Serializa el bloque envuelto frente a otras llamadas con la misma
        ``key``. Libera el lock solo si llegó a adquirirse (una cancelación
        mientras se espera nunca deja el lock tomado) y siempre decrementa
        el contador de referencia, incluso ante excepción o cancelación —
        para que la entrada se limpie determinísticamente."""
        entry = await self._reserve(key)
        try:
            async with entry.lock:
                yield
        finally:
            await self._release(key, entry)
