"""C2 — un fallo de ``adelete_thread()`` (backend del checkpointer caído,
error interno de LangGraph, lo que sea) nunca debe alterar el resultado que
el cliente recibe, en ninguno de los dos endpoints.

Antes de esta corrección, ``_cleanup_ephemeral_checkpoint`` no capturaba
ninguna excepción propia y se invocaba dentro de un ``finally`` plano en
ambos endpoints. Por la semántica de Python, una excepción lanzada dentro de
un ``finally`` REEMPLAZA en silencio lo que ese bloque estaba terminando de
propagar — así que un fallo ahí:

  - en ``/api/query``, habría descartado una ``QueryResponse`` ya exitosa
    (reemplazándola por la excepción de limpieza, nunca vista por el
    llamador porque el `return` está DESPUÉS del `finally`), o habría
    sustituido el 500/504 real de un fallo de negocio por un error de
    limpieza sin relación;
  - en ``/api/query/stream``, además habría impedido que
    ``resource_stack.aclose()`` (la línea siguiente en el mismo `finally`
    plano) llegara a ejecutarse — dejando el lock de conversación y el slot
    de backpressure sin liberar.

Estas pruebas reproducen las tres formas del bug con un fallo de limpieza
REAL (``adelete_thread`` monkeypatcheado para lanzar) y confirman que, tras
la corrección, ninguna se manifiesta. Reutiliza los mismos patrones que
``test_ephemeral_checkpoint_cleanup.py`` y ``test_shutdown_cleanup.py``:
grafo real compilado con enriquecimiento deshabilitado, pregunta con
enrutamiento determinista ``out_of_scope`` (sin LLM ni retriever reales).
"""

from __future__ import annotations

import json
import logging

import pytest

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
from rag.api.schemas import QueryRequest

_OFF_TOPIC_QUESTION = "Dame una receta de cocina, por favor."
_USER = {"sub": "test-user"}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _real_graph(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    return agent_module.build_graph()


async def _boom_adelete_thread(_thread_id: str) -> None:
    raise RuntimeError("fallo simulado del backend del checkpointer")


# v1.2/C2 — sentinelas inequívocos: si alguno apareciera en el log, sería
# prueba directa de que el mensaje/traceback de la excepción se filtró.
_SENTINEL_THREAD_ID = "THREAD-ID-PRIVADO-123"
_SENTINEL_BUSINESS_CONTENT = "CONTENIDO-NEGOCIO-PRIVADO-456"


async def _boom_adelete_thread_with_sentinels(_thread_id: str) -> None:
    raise RuntimeError(
        f"fallo del checkpointer para thread_id={_SENTINEL_THREAD_ID} "
        f"al procesar '{_SENTINEL_BUSINESS_CONTENT}'"
    )


async def _consume_sse_events(response) -> list[dict]:
    events = []
    async for chunk in response.body_iterator:
        for line in chunk.split("\n"):
            if not line.startswith("data: "):
                continue
            payload = line[len("data: ") :]
            if payload == "[DONE]":
                events.append({"type": "DONE"})
            else:
                events.append(json.loads(payload))
    return events


# ---------------------------------------------------------------------------
# /api/query (JSON) — éxito preservado
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_json_query_succeeds_even_if_checkpoint_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(graph.checkpointer, "adelete_thread", _boom_adelete_thread)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)  # efímera: sin conversation_id/thread_id
    response = await main_module.query(request, _USER)

    assert response.answer


@pytest.mark.anyio
async def test_json_query_original_500_is_not_replaced_by_a_failed_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El error de negocio original (fallo real dentro del grafo) debe seguir
    siendo un 500 — no una excepción distinta filtrada desde la limpieza del
    checkpoint, que también falla en esta prueba."""
    from fastapi import HTTPException

    import rag.api.main as main_module

    class _BoomGraph:
        checkpointer = agent_module.build_graph().checkpointer

        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("fallo simulado dentro del grafo")

    boom_graph = _BoomGraph()
    monkeypatch.setattr(boom_graph.checkpointer, "adelete_thread", _boom_adelete_thread)
    monkeypatch.setattr(main_module, "_graph", boom_graph)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    with pytest.raises(HTTPException) as exc_info:
        await main_module.query(request, _USER)

    assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# /api/query/stream (SSE) — eventos normales preservados
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sse_stream_still_emits_normal_events_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(graph.checkpointer, "adelete_thread", _boom_adelete_thread)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    response = await main_module.query_stream(request, _USER)
    events = await _consume_sse_events(response)

    event_types = [e["type"] for e in events]
    assert "error" not in event_types, f"no debía haber ningún evento de error: {events}"
    assert "sources" in event_types
    assert event_types[-1] == "DONE"


# ---------------------------------------------------------------------------
# Lock de conversación y slot de backpressure liberados pese al fallo.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_json_query_releases_lock_and_backpressure_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(graph.checkpointer, "adelete_thread", _boom_adelete_thread)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    await main_module.query(request, _USER)

    assert main_module.CONVERSATION_LOCKS._entries == {}
    assert main_module.backpressure._in_flight == 0


@pytest.mark.anyio
async def test_sse_stream_releases_lock_and_backpressure_when_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Este es el caso que el `finally` plano anterior rompía: la limpieza
    fallida impedía que `resource_stack.aclose()` (siguiente línea del mismo
    bloque) llegara a ejecutarse, dejando el lock/slot retenidos para
    siempre."""
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(graph.checkpointer, "adelete_thread", _boom_adelete_thread)

    request = QueryRequest(question=_OFF_TOPIC_QUESTION)
    response = await main_module.query_stream(request, _USER)
    await _consume_sse_events(response)

    assert main_module.CONVERSATION_LOCKS._entries == {}
    assert main_module.backpressure._in_flight == 0


# ---------------------------------------------------------------------------
# El warning de limpieza no incluye thread_id ni contenido de negocio.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_cleanup_failure_warning_carries_no_thread_id_or_business_content(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import rag.api.main as main_module

    graph = _real_graph(monkeypatch)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(graph.checkpointer, "adelete_thread", _boom_adelete_thread_with_sentinels)

    with caplog.at_level(logging.WARNING, logger="rag.api.main"):
        request = QueryRequest(question=_OFF_TOPIC_QUESTION)
        await main_module.query(request, _USER)

    warnings = [r for r in caplog.records if r.name == "rag.api.main"]
    assert len(warnings) == 1
    # v1.2/C2 — el evento fijo (con, como mucho, el nombre de la clase de la
    # excepción) sí debe aparecer...
    assert warnings[0].getMessage() == "ephemeral_checkpoint_cleanup_failed error_type=RuntimeError"
    # ...pero ni los sentinelas ni ningún rastro de la excepción original
    # (mensaje o traceback) deben aparecer en ninguna parte del log
    # FORMATEADO — no solo en `getMessage()`, que no incluiría un traceback
    # adjunto por `exc_info` si lo hubiera.
    assert _SENTINEL_THREAD_ID not in caplog.text
    assert _SENTINEL_BUSINESS_CONTENT not in caplog.text
    assert _OFF_TOPIC_QUESTION not in caplog.text
    # v1.2/C2 — sin `exc_info=True`: no debe adjuntarse ningún traceback.
    assert warnings[0].exc_info is None
