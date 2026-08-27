"""C5 — cobertura real del endpoint SSE (/api/query/stream).

`test_main_backpressure.py` afirmaba en su propio docstring cubrir el
wiring de `ConcurrencyBackpressure` en AMBOS endpoints, pero ninguna de sus
pruebas llamaba jamás a `query_stream` — solo a `query`. Ese archivo ya fue
corregido (C5, puntos 1 y 2: 503 antes de construir el stream en modo
enforce, comportamiento inalterado en modo off).

Este archivo cubre el resto de las propiedades que el plan de C5 exige para
el handler SSE, sin servicios externos:
  3. Dos turnos concurrentes del MISMO hilo no se intercalan (mismo defecto
     que T3.5 demostró para /api/query, pero nunca se probó contra el
     endpoint de streaming).
  4. Hilos DISTINTOS avanzan en paralelo (el lock es por conversación, no
     global — tampoco probado antes contra streaming).
  5. Una excepción dentro de `graph.astream` emite el evento SSE de error
     ya existente y libera lock, slot de backpressure y contador de
     consultas activas.
  6. Cancelar/cerrar el consumo después de iniciado el iterador libera esos
     mismos recursos (p. ej. el cliente cierra la conexión a mitad de
     stream).
  7. y 8. Una finalización normal conserva exactamente el formato de
     eventos actual: nombres de tipo, claves y el marcador `[DONE]`.

Deliberadamente NO se introduce ninguna abstracción general de streaming:
`_consume` es el único helper compartido, y se limita a decodificar las
líneas `data: {...}` en dicts — el mínimo necesario para no duplicar el
protocolo de adquisición/liberación en cada prueba.
"""

from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from starlette.requests import ClientDisconnect

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module
from rag.api.conversation_lock import ConversationLockRegistry
from rag.api.rate_limit import ConcurrencyBackpressure


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_QUESTION_A = "Un pescador artesanal pregunta por la concesión de playa en zona A. " * 2
_QUESTION_B = "Un pescador artesanal pregunta por la concesión de playa en zona B. " * 2


def _make_request(question: str, thread_id: str):
    from rag.api.schemas import QueryRequest

    return QueryRequest(question=question, thread_id=thread_id)


async def _consume(response) -> list[dict]:
    """Decodifica el body de un StreamingResponse SSE en una lista de dicts
    (uno por evento `data: {...}`), ignorando el marcador `[DONE]`."""
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


def _setup_basic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )


class _SlowRetriever:
    """Espejo del doble usado en test_conversation_lock.py: una pausa real
    (`asyncio.sleep`) para forzar una ventana de interleaving determinística
    entre dos invocaciones concurrentes del grafo sobre el mismo thread_id."""

    def __init__(self, tag: str, delay: float = 0.08) -> None:
        self.tag = tag
        self.delay = delay

    async def ainvoke(self, query: str) -> list[Document]:
        await asyncio.sleep(self.delay)
        return [Document(page_content=f"fragmento-{self.tag}", metadata={"chunk_id": self.tag})]


@pytest.mark.anyio
async def test_same_thread_concurrent_turns_do_not_lose_a_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C5 (3): dos turnos concurrentes por SSE sobre el MISMO thread_id no
    deben intercalarse — el checkpoint final debe conservar ambas preguntas
    y ambas respuestas completas, igual que ya se exige para /api/query."""
    import rag.api.main as main_module

    _setup_basic(monkeypatch)
    calls = {"n": 0}

    def make_retriever(**kwargs: object) -> _SlowRetriever:
        calls["n"] += 1
        return _SlowRetriever(tag=f"turno-{calls['n']}")

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)
    responses = iter(["Respuesta SSE al turno A [doc1].", "Respuesta SSE al turno B [doc1]."])
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=[next(responses)]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    user = {"sub": "test-user"}
    thread_id = "sse-shared-conversation"

    async def _run(question: str) -> list[dict]:
        response = await main_module.query_stream(_make_request(question, thread_id), user)
        return await _consume(response)

    events_a, events_b = await asyncio.gather(_run(_QUESTION_A), _run(_QUESTION_B))

    answers = set()
    for events in (events_a, events_b):
        tokens = "".join(e["content"] for e in events if e.get("type") == "token")
        answers.add(tokens)
    assert answers == {"Respuesta SSE al turno A [doc1].", "Respuesta SSE al turno B [doc1]."}

    config = {"configurable": {"thread_id": f"user:test-user:conversation:{thread_id}"}}
    final_state = await graph.aget_state(config)
    messages = final_state.values.get("messages", [])
    ai_contents = {m.content for m in messages if type(m).__name__ == "AIMessage"}
    assert len(messages) == 4, f"se esperaban 4 mensajes, hay {len(messages)}: {messages}"
    assert ai_contents == {"Respuesta SSE al turno A [doc1].", "Respuesta SSE al turno B [doc1]."}


@pytest.mark.anyio
async def test_different_threads_proceed_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    """C5 (4): hilos DISTINTOS deben poder empezar a recuperar casi al mismo
    tiempo por SSE — el lock es por conversación, no global."""
    import rag.api.main as main_module

    _setup_basic(monkeypatch)
    start_times: dict[str, float] = {}

    class _RecordingSlowRetriever:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def ainvoke(self, query: str) -> list[Document]:
            start_times[self.tag] = time.perf_counter()
            await asyncio.sleep(0.1)
            return [Document(page_content=self.tag, metadata={"chunk_id": self.tag})]

    calls = {"n": 0}

    def make_retriever(**kwargs: object) -> _RecordingSlowRetriever:
        calls["n"] += 1
        return _RecordingSlowRetriever(tag=f"turno-{calls['n']}")

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)
    responses = iter(["Respuesta A [doc1].", "Respuesta B [doc1]."])
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=[next(responses)]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    user = {"sub": "test-user"}

    async def _run(question: str, thread_id: str) -> list[dict]:
        response = await main_module.query_stream(_make_request(question, thread_id), user)
        return await _consume(response)

    await asyncio.gather(
        _run(_QUESTION_A, "sse-thread-independiente-1"),
        _run(_QUESTION_B, "sse-thread-independiente-2"),
    )

    assert set(start_times) == {"turno-1", "turno-2"}
    gap = abs(start_times["turno-1"] - start_times["turno-2"])
    assert gap < 0.08, f"arrancaron con {gap:.3f}s de diferencia — parece serializado"


@pytest.mark.anyio
async def test_exception_in_astream_emits_error_event_and_releases_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C5 (5): si `graph.astream` falla (aquí, un retriever que lanza una
    excepción real), el generador debe emitir el evento SSE de error ya
    existente — sin cambiar su forma — y dejar lock, slot de backpressure y
    contador de consultas activas en su estado de reposo."""
    import rag.api.main as main_module

    _setup_basic(monkeypatch)

    class _FailingRetriever:
        async def ainvoke(self, query: str) -> list[Document]:
            raise RuntimeError("fallo simulado de recuperación")

    monkeypatch.setattr(
        agent_module, "get_ensemble_retriever", lambda **kwargs: _FailingRetriever()
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["no debería usarse"]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    backpressure_double = ConcurrencyBackpressure(mode="enforce", max_concurrent=3)
    monkeypatch.setattr(main_module, "backpressure", backpressure_double)
    locks = ConversationLockRegistry()
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)

    user = {"sub": "test-user"}
    response = await main_module.query_stream(
        _make_request(_QUESTION_A, "sse-thread-con-error"), user
    )
    events = await _consume(response)

    # Los eventos de estado emitidos antes de que el retriever falle
    # (enriching, retrieving) son comportamiento normal y no forman parte
    # de lo que esta prueba verifica; lo que importa es que el ÚLTIMO
    # evento sea el error existente, sin alterar su forma, y que no haya
    # ningún evento de "sources" ni "[DONE]" tras un fallo real.
    assert events[-1] == {"type": "error", "detail": "No fue posible procesar la consulta."}
    assert all(e["type"] in ("status", "error") for e in events)
    assert sum(1 for e in events if e["type"] == "error") == 1
    assert backpressure_double.in_flight == 0
    assert locks._entries == {}
    assert main_module.ACTIVE_QUERIES.count == 0


@pytest.mark.anyio
async def test_closing_the_iterator_early_releases_all_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C5 (6): si el cliente cierra la conexión a mitad de stream (aquí,
    cancelando la tarea que consume el iterador mientras el retriever está
    deliberadamente bloqueado), el `finally` del generador debe seguir
    ejecutándose y liberar lock, slot y contador — nada debe quedar
    retenido."""
    import rag.api.main as main_module

    _setup_basic(monkeypatch)
    started = asyncio.Event()
    release = asyncio.Event()

    class _GatedRetriever:
        async def ainvoke(self, query: str) -> list[Document]:
            started.set()
            await release.wait()
            return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: _GatedRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["no debería usarse"]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    backpressure_double = ConcurrencyBackpressure(mode="enforce", max_concurrent=3)
    monkeypatch.setattr(main_module, "backpressure", backpressure_double)
    locks = ConversationLockRegistry()
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)

    user = {"sub": "test-user"}

    async def _run() -> None:
        response = await main_module.query_stream(
            _make_request(_QUESTION_A, "sse-thread-cancelado"), user
        )
        await _consume(response)

    task = asyncio.create_task(_run())
    await started.wait()  # el retriever ya bloqueó: lock y slot están tomados.

    assert backpressure_double.in_flight == 1
    assert "user:test-user:conversation:sse-thread-cancelado" in locks._entries

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert backpressure_double.in_flight == 0
    assert locks._entries == {}
    assert main_module.ACTIVE_QUERIES.count == 0

    release.set()  # no queda nadie esperando; solo evita dejar el Event colgado.


@pytest.mark.anyio
async def test_normal_completion_preserves_event_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C5 (7 y 8): una finalización normal conserva exactamente el formato
    de eventos actual — nombres de tipo, claves de cada uno, orden relativo
    (status* → token* → sources → [DONE]) y el marcador final."""
    import rag.api.main as main_module

    _setup_basic(monkeypatch)

    class _FastRetriever:
        async def ainvoke(self, query: str) -> list[Document]:
            return [
                Document(page_content="fragmento", metadata={"chunk_id": "1", "source": "x.pdf"})
            ]

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **kwargs: _FastRetriever())
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["Respuesta completa [doc1]."]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    user = {"sub": "test-user"}
    response = await main_module.query_stream(_make_request(_QUESTION_A, "sse-thread-normal"), user)

    # El marcador [DONE] no pasa por _consume (se filtra deliberadamente ahí);
    # se verifica aparte, leyendo el body crudo.
    raw_lines: list[str] = []
    async for chunk in response.body_iterator:
        text = chunk if isinstance(chunk, str) else chunk.decode()
        raw_lines.append(text)

    assert raw_lines[-1].strip() == "data: [DONE]"

    events = [
        json.loads(line[len("data: ") :].strip())
        for line in raw_lines
        if line.startswith("data: ") and line.strip() != "data: [DONE]"
    ]

    types = [e["type"] for e in events]
    # Debe haber al menos un evento de estado antes de los tokens, y las
    # fuentes deben ser el último evento antes de [DONE].
    assert types[0] == "status"
    assert types[-1] == "sources"
    assert set(types) <= {"status", "token", "sources"}

    for e in events:
        if e["type"] == "status":
            assert set(e.keys()) == {"type", "stage", "message"}
        elif e["type"] == "token":
            assert set(e.keys()) == {"type", "content"}

    sources_event = events[-1]
    assert set(sources_event.keys()) == {
        "type",
        "sources",
        "enriched_query",
        "query_route",
        "context_tokens",
        "context_limit",
    }
    assert sources_event["query_route"] == "in_scope"
    assert isinstance(sources_event["context_tokens"], int)
    assert isinstance(sources_event["sources"], list)
    assert sources_event["sources"][0]["source"] == "x.pdf"

    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert tokens == "Respuesta completa [doc1]."


@pytest.mark.anyio
async def test_asgi_send_failure_before_first_event_releases_all_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """H1: si el envío ASGI de `http.response.start` falla (p. ej. el
    cliente ya se desconectó) ANTES de que el iterador del stream ejecute su
    primer `__anext__`, el cuerpo de `event_generator()` nunca llega a
    correr — su `try/finally` no se alcanza. Lock de conversación y slot de
    backpressure, adquiridos en `query_stream()` antes del `StreamingResponse`,
    deben liberarse igual, sin depender de que el generador se haya iniciado.

    Se ejercita el ciclo ASGI real (`response(scope, receive, send)`), no
    solo `body_iterator`, porque es justo la diferencia entre ambos caminos
    la que produce la fuga."""
    import rag.api.main as main_module

    _setup_basic(monkeypatch)

    graph_started = False

    class _TrackingRetriever:
        async def ainvoke(self, query: str) -> list[Document]:
            nonlocal graph_started
            graph_started = True
            return [Document(page_content="fragmento", metadata={"chunk_id": "1"})]

    monkeypatch.setattr(
        agent_module, "get_ensemble_retriever", lambda **kwargs: _TrackingRetriever()
    )
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=["no debería usarse"]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    backpressure_double = ConcurrencyBackpressure(mode="enforce", max_concurrent=3)
    monkeypatch.setattr(main_module, "backpressure", backpressure_double)
    locks = ConversationLockRegistry()
    monkeypatch.setattr(main_module, "CONVERSATION_LOCKS", locks)

    user = {"sub": "test-user"}
    response = await main_module.query_stream(
        _make_request(_QUESTION_A, "sse-thread-desconexion-temprana"), user
    )

    # Recursos ya adquiridos antes de que exista el StreamingResponse.
    assert backpressure_double.in_flight == 1
    assert "user:test-user:conversation:sse-thread-desconexion-temprana" in locks._entries

    async def _send(message: dict) -> None:
        if message["type"] == "http.response.start":
            raise OSError("cliente desconectado antes de recibir encabezados")

    async def _receive() -> dict:
        return {"type": "http.disconnect"}

    scope = {"type": "http", "asgi": {"spec_version": "2.4"}}

    with pytest.raises(ClientDisconnect):
        await response(scope, _receive, _send)

    assert backpressure_double.in_flight == 0
    assert locks._entries == {}
    assert main_module.ACTIVE_QUERIES.count == 0
    assert graph_started is False
