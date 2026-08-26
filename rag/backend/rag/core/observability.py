# rag/core/observability.py
"""T3.1 — observabilidad/logging del pipeline RAG.

Instrumentación pura (no cambia ningún comportamiento de negocio): latencia
por etapa del grafo, ruta de clasificación, conteo de documentos
recuperados, errores de formato de citas, consultas activas y conversaciones
retenidas por el checkpointer.

Regla estricta de este módulo: NUNCA loguear contenido potencialmente
sensible — ni la pregunta del usuario, ni el contenido de documentos
recuperados, ni tokens/embeddings, ni credenciales. Solo números, nombres de
etapa/ruta (enums cerrados, no texto libre) y contadores.

No toca clasificación, prompts, recuperación, umbrales de evidencia ni
citación/abstención — únicamente observa lo que ya ocurre alrededor de esos
componentes.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

logger = logging.getLogger("rag.observability")


@contextmanager
def stage_timer(stage: str, **safe_fields: object) -> Iterator[dict[str, object]]:
    """Mide la duración de una etapa del pipeline y la loguea al salir.

    ``safe_fields`` debe contener solo campos seguros (conteos, nombres de
    ruta/enum, booleanos) — nunca texto de la pregunta, documentos o
    tokens/credenciales; quien llama es responsable de esa garantía. El
    diccionario devuelto es el mismo que se loguea al final: puede seguir
    completándose dentro del bloque ``with`` (p. ej. añadir el conteo de
    documentos, que solo se conoce al terminar la etapa).

    Loguea incluso si el bloque lanza una excepción (para no perder la
    medición de una etapa que falló), y luego deja que la excepción se
    propague sin capturarla.
    """
    fields: dict[str, object] = dict(safe_fields)
    start = time.perf_counter()
    try:
        yield fields
    finally:
        duration_ms = (time.perf_counter() - start) * 1000
        extra = " ".join(f"{key}={value}" for key, value in fields.items())
        logger.info("stage=%s duration_ms=%.1f %s", stage, duration_ms, extra)


def log_citation_format_error(*, doc_count: int) -> None:
    """Registra que una respuesta generada no superó la validación de citas.

    Nunca incluye el texto de la respuesta ni de los documentos — solo
    cuántos documentos estaban disponibles para citar en ese turno.
    """
    logger.warning("citation_format_error doc_count=%d", doc_count)


class ActiveQueryTracker:
    """Gauge en proceso de consultas en curso, sin contenido de negocio.

    Pensado para un único proceso (no distribuido): un contador en memoria
    incrementado/decrementado alrededor de cada consulta. Como los handlers
    async de FastAPI corren en un único hilo de event loop, incrementar y
    decrementar antes/después de un ``await`` no tiene condiciones de
    carrera reales dentro de este proceso.
    """

    def __init__(self) -> None:
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @contextmanager
    def track(self) -> Iterator[None]:
        self._count += 1
        logger.info("active_queries=%d", self._count)
        try:
            yield
        finally:
            self._count -= 1
            logger.info("active_queries=%d", self._count)


def log_retained_conversations(checkpointer: object) -> None:
    """Registra cuántas conversaciones (``thread_id``) retiene el checkpointer.

    Introspección de solo lectura sobre ``MemorySaver.storage`` (un
    ``defaultdict`` de solo-lectura para este propósito: nunca se escribe ni
    se inspecciona su contenido, solo se cuenta su cantidad de claves). Si el
    checkpointer no expone ``storage`` con la forma esperada — por ejemplo un
    backend distinto en el futuro — no falla ni loguea nada: esta función es
    puramente informativa y nunca debe poder romper una consulta real.
    """
    storage = getattr(checkpointer, "storage", None)
    if storage is None:
        return
    try:
        count = len(storage)
    except TypeError:
        return
    logger.info("retained_conversations=%d", count)
