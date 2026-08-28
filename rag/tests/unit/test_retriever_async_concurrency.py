"""T3.2 — eliminar el ThreadPoolExecutor anidado en HybridEnsembleRetriever.

Antes: `retrieve_forced_node` (agent.py) ejecutaba `retriever.invoke()` (sync)
dentro de `asyncio.to_thread(...)`, y ese `invoke()` sync internamente creaba
su PROPIO `ThreadPoolExecutor` para correr BM25 y el retriever vectorial en
paralelo — dos capas de concurrencia anidadas para un solo fan-out de dos
tareas.

Después: una sola capa. `HybridEnsembleRetriever` implementa
`_aget_relevant_documents` con `asyncio.gather` + `asyncio.to_thread` (un
`to_thread` por sub-retriever, sin crear ningún pool propio), y
`retrieve_forced_node` orquesta la concurrencia desde el límite async
llamando a `retriever.ainvoke(query)` directamente — ver
`test_agent_graph.py`/`test_agent_observability.py` para la prueba de que el
nodo real usa esta ruta.

El camino síncrono (`.invoke()`) se conserva sin cambios de comportamiento
(mismo resultado, mismo orden) para quien lo siga usando de forma síncrona
(scripts, demo()) — ver `test_retriever_limit.py` y
`test_retriever_structural_filter.py`, que siguen pasando sin modificarse.
"""

from __future__ import annotations

import inspect
import time

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

import rag.core.retriever as retriever_module
from rag.core.retriever import HybridEnsembleRetriever


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _doc(identifier: str) -> Document:
    return Document(page_content=identifier, metadata={"chunk_id": identifier})


class _StaticRetriever(BaseRetriever):
    docs: list[Document]

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        del query, run_manager
        return self.docs


class _SlowRetriever(BaseRetriever):
    """Simula E/S o CPU bloqueante (~150ms) para poder medir concurrencia real."""

    docs: list[Document]
    delay_seconds: float = 0.15

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        del query, run_manager
        time.sleep(self.delay_seconds)
        return self.docs


# ---------------------------------------------------------------------------
# No debe existir ningún ThreadPoolExecutor propio en el módulo
# ---------------------------------------------------------------------------


def test_no_threadpoolexecutor_in_retriever_module() -> None:
    """No debe existir ningún import ni instanciación de ThreadPoolExecutor.

    (El nombre puede seguir apareciendo en prosa de docstrings explicando el
    cambio — lo que no debe existir es el import ni la construcción real.)
    """
    source = inspect.getsource(retriever_module)
    assert "import concurrent.futures" not in source
    assert "from concurrent.futures" not in source
    assert "ThreadPoolExecutor(" not in source


# ---------------------------------------------------------------------------
# ainvoke() orquesta BM25 + vector concurrentemente desde una sola capa
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_ainvoke_runs_subretrievers_concurrently_not_sequentially() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _SlowRetriever(docs=[_doc("a")], delay_seconds=0.15),
            _SlowRetriever(docs=[_doc("b")], delay_seconds=0.15),
        ],
        weights=[0.5, 0.5],
        max_results=2,
    )

    start = time.perf_counter()
    await retriever.ainvoke("consulta")
    elapsed = time.perf_counter() - start

    # Secuencial habría tomado ~0.30s; concurrente, ~0.15s. Margen generoso
    # para no ser un test frágil en CI, pero suficiente para distinguir ambos.
    assert elapsed < 0.27, f"tardó {elapsed:.3f}s — no parece concurrente"


@pytest.mark.anyio
async def test_ainvoke_produces_the_same_fused_result_as_sync_invoke() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(docs=[_doc("a"), _doc("b"), _doc("c")]),
            _StaticRetriever(docs=[_doc("d"), _doc("e")]),
        ],
        weights=[0.6, 0.4],
        max_results=4,
    )

    sync_result = retriever.invoke("consulta")
    async_result = await retriever.ainvoke("consulta")

    sync_ids = [d.metadata["chunk_id"] for d in sync_result]
    async_ids = [d.metadata["chunk_id"] for d in async_result]
    assert async_ids == sync_ids


@pytest.mark.anyio
async def test_ainvoke_still_filters_structural_noise_and_respects_max_results() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(
                docs=[_doc("a"), Document(page_content="---", metadata={"chunk_id": "junk"})]
            ),
            _StaticRetriever(docs=[_doc("b"), _doc("c")]),
        ],
        weights=[0.5, 0.5],
        max_results=2,
    )

    result = await retriever.ainvoke("consulta")

    assert len(result) == 2
    assert "junk" not in [d.metadata["chunk_id"] for d in result]


@pytest.mark.anyio
async def test_ainvoke_propagates_a_subretriever_exception() -> None:
    class _BoomRetriever(BaseRetriever):
        def _get_relevant_documents(
            self, query: str, *, run_manager: CallbackManagerForRetrieverRun
        ) -> list[Document]:
            del query, run_manager
            raise RuntimeError("subretriever caído")

    retriever = HybridEnsembleRetriever(
        retrievers=[_BoomRetriever(), _StaticRetriever(docs=[_doc("a")])],
        weights=[0.5, 0.5],
        max_results=2,
    )

    with pytest.raises(RuntimeError, match="subretriever caído"):
        await retriever.ainvoke("consulta")
