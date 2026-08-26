"""T3.5 — lock por conversación, agregado SOLO porque un test demuestra
interleaving real (no "por si acaso").

Bug demostrado empíricamente antes de este cambio: dos turnos concurrentes
sobre el MISMO `thread_id` (p. ej. doble clic en enviar, o dos pestañas del
navegador sobre la misma conversación) pueden interleavearse durante
`graph.ainvoke()` porque ambos leen/escriben el mismo checkpoint de
`MemorySaver` sin ninguna exclusión mutua. Resultado observado: uno de los
dos `AIMessage` de respuesta se pierde silenciosamente del checkpoint final
— la conversación persistida en memoria queda incompleta, aunque cada
request individualmente reciba su propia respuesta correcta por HTTP.

Estas pruebas usan un `SlowRetriever` (con una pausa real de E/S vía
`asyncio.sleep`) para forzar una ventana de interleaving determinística en
lugar de depender de timing real de red/LLM.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.language_models.fake_chat_models import FakeListChatModel

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _SlowRetriever:
    """Retriever falso con una pausa real (asyncio.sleep) para forzar
    interleaving determinístico entre dos invocaciones concurrentes del
    grafo sobre el mismo thread_id."""

    def __init__(self, tag: str, delay: float = 0.08) -> None:
        self.tag = tag
        self.delay = delay

    async def ainvoke(self, query: str) -> list[Document]:
        await asyncio.sleep(self.delay)
        return [Document(page_content=f"fragmento-{self.tag}", metadata={"chunk_id": self.tag})]

    def invoke(self, query: str) -> list[Document]:
        return [Document(page_content=f"fragmento-{self.tag}", metadata={"chunk_id": self.tag})]


def _make_request(question: str, thread_id: str):
    from rag.api.schemas import QueryRequest

    return QueryRequest(question=question, thread_id=thread_id)


def _setup_concurrent_turns(monkeypatch: pytest.MonkeyPatch):
    """Deja todo listo para disparar dos turnos concurrentes sobre el mismo
    thread_id: clasificador real (sin LLM), retrievers lentos distintos por
    llamada, y un LLM de generación que responde de forma determinística y
    distinguible por turno."""
    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)

    calls = {"n": 0}

    def make_retriever(**kwargs):
        calls["n"] += 1
        return _SlowRetriever(tag=f"turno-{calls['n']}")

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )

    responses = iter(["Respuesta al turno A [doc1].", "Respuesta al turno B [doc1]."])
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=[next(responses)]),
    )


_QUESTION_A = "Un pescador artesanal pregunta por la concesión de playa en zona A. " * 2
_QUESTION_B = "Un pescador artesanal pregunta por la concesión de playa en zona B. " * 2


@pytest.mark.anyio
async def test_concurrent_turns_on_the_same_thread_do_not_lose_a_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module
    from rag.api.rate_limit import get_query_user

    _setup_concurrent_turns(monkeypatch)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    main_module.app.dependency_overrides[get_query_user] = lambda: {"sub": "test-user"}

    try:
        thread_id = "shared-conversation-thread"
        user = {"sub": "test-user"}
        responses = await asyncio.gather(
            main_module.query(_make_request(_QUESTION_A, thread_id), user),
            main_module.query(_make_request(_QUESTION_B, thread_id), user),
        )

        # Cada request individual debe seguir recibiendo su propia respuesta
        # correcta por HTTP (esto ya funcionaba antes del lock).
        answers = {r.answer for r in responses}
        assert answers == {"Respuesta al turno A [doc1].", "Respuesta al turno B [doc1]."}

        # La garantía que el lock añade: el checkpoint final en memoria debe
        # contener AMBOS turnos completos (2 preguntas + 2 respuestas) — sin
        # el lock, uno de los dos AIMessage se pierde por interleaving.
        config = {
            "configurable": {"thread_id": f"user:test-user:conversation:{thread_id}"},
        }
        final_state = await graph.aget_state(config)
        messages = final_state.values.get("messages", [])
        ai_contents = {m.content for m in messages if type(m).__name__ == "AIMessage"}

        assert len(messages) == 4, f"se esperaban 4 mensajes, hay {len(messages)}: {messages}"
        assert ai_contents == {"Respuesta al turno A [doc1].", "Respuesta al turno B [doc1]."}
    finally:
        main_module.app.dependency_overrides.clear()


def test_lock_registry_gives_independent_locks_per_key() -> None:
    """Garantía estructural, sin timing: el registro es por clave — dos
    conversaciones distintas nunca comparten lock, y la misma conversación
    siempre obtiene el mismo lock (para que sí se serialice consigo misma)."""
    from rag.api.conversation_lock import ConversationLockRegistry

    registry = ConversationLockRegistry()
    lock_a1 = registry.lock_for("thread-a")
    lock_a2 = registry.lock_for("thread-a")
    lock_b = registry.lock_for("thread-b")

    assert lock_a1 is lock_a2
    assert lock_a1 is not lock_b


@pytest.mark.anyio
async def test_concurrent_turns_on_different_threads_start_without_waiting_on_each_other(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El lock es por conversación, no global: dos turnos en threads
    DISTINTOS deben poder empezar a recuperar casi al mismo tiempo, sin que
    uno espere a que el otro termine su turno completo.

    Se compara el instante relativo en que cada retriever ARRANCA (no la
    duración total), para no depender de umbrales de tiempo absolutos
    sensibles a la carga de la máquina donde corre la suite completa.
    """
    import time

    import rag.api.main as main_module
    from rag.api.rate_limit import get_query_user

    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)

    start_times: dict[str, float] = {}

    class _RecordingSlowRetriever:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def ainvoke(self, query: str) -> list[Document]:
            start_times[self.tag] = time.perf_counter()
            await asyncio.sleep(0.1)
            return [Document(page_content=self.tag, metadata={"chunk_id": self.tag})]

    calls = {"n": 0}

    def make_retriever(**kwargs):
        calls["n"] += 1
        return _RecordingSlowRetriever(tag=f"turno-{calls['n']}")

    monkeypatch.setattr(agent_module, "get_ensemble_retriever", make_retriever)
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    responses = iter(["Respuesta A [doc1].", "Respuesta B [doc1]."])
    monkeypatch.setattr(
        agent_module,
        "get_generation_llm",
        lambda: FakeListChatModel(responses=[next(responses)]),
    )

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    main_module.app.dependency_overrides[get_query_user] = lambda: {"sub": "test-user"}

    try:
        user = {"sub": "test-user"}
        await asyncio.gather(
            main_module.query(_make_request(_QUESTION_A, "thread-independiente-1"), user),
            main_module.query(_make_request(_QUESTION_B, "thread-independiente-2"), user),
        )

        assert set(start_times) == {"turno-1", "turno-2"}
        gap = abs(start_times["turno-1"] - start_times["turno-2"])
        # Si estuvieran serializados por el lock, "turno-2" arrancaría su
        # recuperación DESPUÉS de que "turno-1" termine por completo
        # (>= 0.1s de diferencia). Concurrentes, arrancan casi juntos.
        assert gap < 0.08, f"arrancaron con {gap:.3f}s de diferencia — parece serializado"
    finally:
        main_module.app.dependency_overrides.clear()
