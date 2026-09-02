# rag/core/observability.py
"""Observabilidad/logging del pipeline RAG.

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


def log_full_context_size(*, chars: int) -> None:
    """Registra el tamaño del prompt de generación, medido en caracteres de
    los mensajes que ``ChatPromptTemplate`` produjo.

    Métrica puramente interna, solo para logs: nunca se expone por la API ni
    se guarda en ningún estado. Distinta a propósito del campo público
    ``context_tokens`` (calculado en ``api/main.py::_estimate_context_tokens``
    a partir del historial en ``state["messages"]``, sin contar el system
    prompt ni los documentos recuperados en el turno actual): esta función en
    cambio refleja lo que efectivamente compone el prompt de generación —
    system prompt + contexto recuperado + pregunta — para poder diagnosticar
    consumo real de contexto sin alterar el significado ni el valor de
    ``context_tokens``.

    El conteo son caracteres del CONTENIDO de los mensajes que arma
    LangChain al formatear el ``ChatPromptTemplate`` — no bytes de la
    serialización de red hacia el proveedor (que añade su propio formato de
    request) ni una cuenta exacta de tokens según el tokenizador específico
    del modelo. ``full_context_tokens_est`` es una estimación gruesa
    (``chars // 4``), no un valor medido.

    La firma solo acepta un conteo de caracteres ya calculado por quien
    llama, nunca el texto en sí — así ningún contenido de negocio puede
    llegar a este log por construcción.
    """
    logger.info(
        "full_context_chars=%d full_context_tokens_est=%d",
        chars,
        chars // 4,
    )


def log_context_budget_warning(*, chars: int, doc_count: int, stage: str) -> None:
    """A3.6 — advertencia estructurada cuando el prompt de generación supera
    ``config.CONTEXT_BUDGET_WARNING_CHARS`` (ver ese umbral para el
    razonamiento). Modo puramente observacional: no trunca chunks ni
    respuestas ni fija ``max_tokens`` — solo dimensiona el problema. La
    calibración de ese umbral (o de un futuro ``max_tokens``) queda
    deliberadamente pendiente hasta contar con datos reales de este propio
    warning.

    Registra únicamente caracteres totales, cantidad de documentos y la
    etapa — nunca contenido, igual que ``log_full_context_size``, del cual
    esta función es un complemento (no lo sustituye): esta se activa
    condicionalmente y a nivel warning, la otra registra siempre a nivel
    info.
    """
    logger.warning(
        "context_budget_exceeded stage=%s full_context_chars=%d doc_count=%d",
        stage,
        chars,
        doc_count,
    )


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
