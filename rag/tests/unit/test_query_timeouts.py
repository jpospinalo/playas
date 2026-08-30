"""A3.3 — timeouts controlados, ajustados a cómo funciona realmente el
timeout de inactividad de 300s del ALB/Nginx delante de este servicio (no
es un límite total de duración, ver ``rag.config`` para el razonamiento
completo):

  - ``/api/query`` (JSON, sin datos intermedios): timeout TOTAL de
    ``graph.ainvoke(...)`` (``QUERY_TOTAL_TIMEOUT_SECONDS``, default 280s).
    Al vencer, responde 504 de forma controlada — nunca deja que el proxy
    corte la conexión sin explicación.
  - ``/api/query/stream`` (SSE): SIN timeout total — los eventos `status`
    intermedios pueden mantener viva una consulta legítimamente más larga
    que 280s. En su lugar, timeout POR ETAPA
    (``QUERY_STREAM_STAGE_TIMEOUT_SECONDS``, default 285s): se mide el
    tiempo ENTRE eventos consecutivos del grafo, no la duración total del
    stream.

En ambos casos, el timeout debe liberar el lock de conversación, el slot de
backpressure y el checkpoint efímero (A3.1) exactamente igual que cualquier
otra excepción — estas pruebas lo verifican explícitamente para la ruta de
timeout, no solo para errores genéricos (ya cubiertos en otros archivos).

Usa valores de timeout pequeños (milisegundos) SOLO en estas pruebas, vía
``monkeypatch.setattr(main_module, "QUERY_..._TIMEOUT_SECONDS", ...)` —
nunca como default de despliegue (ver ``rag.config``).
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
from rag.api.rate_limit import ConcurrencyBackpressure
from rag.api.schemas import QueryRequest

_USER = {"sub": "test-user"}
_OFF_TOPIC_QUESTION = "Dame una receta de cocina, por favor."


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def _consume_sse(response) -> list[dict]:
    events: list[dict] = []
    async for chunk in response.body_iterator:
        text = chunk if isinstance(chunk, str) else chunk.decode()
        if not text.startswith("data: "):
            continue
        payload = text[len("data: ") :].strip()
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


def _make_request(**overrides: object) -> QueryRequest:
    fields = {"question": _OFF_TOPIC_QUESTION, **overrides}
    return QueryRequest(**fields)  # type: ignore[arg-type]


class _HangingGraph:
    """`ainvoke` nunca vuelve por sí solo — solo termina si algo la cancela
    (el timeout bajo prueba)."""

    checkpointer = agent_module.build_graph().checkpointer

    async def ainvoke(self, *args: object, **kwargs: object) -> dict:
        await asyncio.Event().wait()
        raise AssertionError("no debería alcanzarse — ainvoke debía cancelarse por timeout")


class _StagedStreamGraph:
    """`astream` emite eventos `status` con retrasos controlados entre cada
    uno, y termina con un `values` final — para poder distinguir el
    timeout POR ETAPA (gap entre eventos) de una duración TOTAL larga
    compuesta por varias etapas cortas."""

    checkpointer = agent_module.build_graph().checkpointer

    def __init__(self, stage_delays: list[float], hang_forever: bool = False) -> None:
        self._stage_delays = stage_delays
        self._hang_forever = hang_forever

    async def astream(self, *args: object, **kwargs: object):
        for i, delay in enumerate(self._stage_delays):
            await asyncio.sleep(delay)
            yield "custom", {"type": "status", "stage": f"etapa-{i}"}
        if self._hang_forever:
            await asyncio.Event().wait()
        yield (
            "values",
            {
                "messages": [AIMessage(content="Respuesta final de prueba [doc1].")],
                "sources": [],
                "enriched_query": None,
                "query_route": "conversation",
            },
        )


def _observing_backpressure() -> ConcurrencyBackpressure:
    """Instancia fresca en modo `observe`: cuenta `_in_flight` sin bloquear
    ni rechazar nada — el modo `off` (default de producción) no cuenta en
    absoluto, así que no serviría para verificar que el slot se liberó."""
    return ConcurrencyBackpressure(mode="observe", max_concurrent=20, scope="query")


# ---------------------------------------------------------------------------
# /api/query — timeout TOTAL
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_query_total_timeout_returns_504_and_releases_all_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _HangingGraph()
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(main_module, "QUERY_TOTAL_TIMEOUT_SECONDS", 0.05)
    fresh_backpressure = _observing_backpressure()
    monkeypatch.setattr(main_module, "backpressure", fresh_backpressure)

    request = _make_request()  # sin conversation_id ni thread_id: efímera
    with pytest.raises(HTTPException) as exc_info:
        await main_module.query(request, _USER)

    assert exc_info.value.status_code == 504

    # Los tres recursos deben quedar liberados exactamente igual que ante
    # cualquier otra excepción.
    assert main_module.CONVERSATION_LOCKS._entries == {}
    assert fresh_backpressure.in_flight == 0
    assert dict(graph.checkpointer.storage) == {}


@pytest.mark.anyio
async def test_query_completes_normally_within_the_default_total_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El wrapping con `asyncio.wait_for` no debe alterar el camino feliz:
    una consulta determinista (sin LLM) termina muy por debajo del default
    de producción (280s, aquí sin monkeypatchear)."""
    import rag.api.main as main_module

    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    response = await main_module.query(_make_request(), _USER)

    assert response.answer
    assert main_module.CONVERSATION_LOCKS._entries == {}


# ---------------------------------------------------------------------------
# /api/query/stream — timeout POR ETAPA, no total
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_stream_stage_timeout_emits_a_controlled_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    graph = _StagedStreamGraph(stage_delays=[], hang_forever=True)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(main_module, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", 0.05)
    fresh_backpressure = _observing_backpressure()
    monkeypatch.setattr(main_module, "backpressure", fresh_backpressure)

    request = _make_request()
    response = await main_module.query_stream(request, _USER)
    events = await _consume_sse(response)

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "etapa" in events[0]["detail"]

    assert main_module.CONVERSATION_LOCKS._entries == {}
    assert fresh_backpressure.in_flight == 0
    assert dict(graph.checkpointer.storage) == {}


@pytest.mark.anyio
async def test_stream_survives_several_stages_that_together_exceed_a_total_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La prueba central de A3.3: NINGÚN gap individual entre eventos supera
    el timeout por etapa, pero la SUMA de las tres etapas sí supera
    ampliamente ese mismo valor — el stream debe completarse con éxito de
    todas formas, porque no existe ningún timeout TOTAL para streaming."""
    import rag.api.main as main_module

    stage_timeout = 0.05
    # 3 etapas de 0.6×stage_timeout cada una => acumulado 1.8×stage_timeout,
    # muy por encima de un timeout total hipotético, pero cada gap
    # individual queda cómodamente por debajo de stage_timeout.
    graph = _StagedStreamGraph(stage_delays=[stage_timeout * 0.6] * 3)
    monkeypatch.setattr(main_module, "_graph", graph)
    monkeypatch.setattr(main_module, "QUERY_STREAM_STAGE_TIMEOUT_SECONDS", stage_timeout)

    request = _make_request()
    response = await main_module.query_stream(request, _USER)
    events = await _consume_sse(response)

    status_events = [e for e in events if e.get("type") == "status"]
    assert len(status_events) == 3

    token_text = "".join(e["content"] for e in events if e.get("type") == "token")
    assert token_text == "Respuesta final de prueba [doc1]."
    assert any(e.get("type") == "sources" for e in events)

    assert main_module.CONVERSATION_LOCKS._entries == {}
