"""T2.5 — endpoint de disponibilidad (`GET /api/ready`).

Distinto de `/api/health` (liveness: siempre `{"status": "ok"}` si el
proceso responde), `/api/ready` verifica que las dependencias necesarias
para atender una consulta estén realmente disponibles:

  - el grafo LangGraph ya terminó de compilarse en el lifespan
    (``main._graph is not None``);
  - el índice BM25 se inicializó con un corpus no vacío
    (``retriever.bm25_index_is_empty()``, expuesta desde T2.1 justo para
    este propósito);
  - la base de datos responde dentro de un timeout corto.

No debe invocar ningún LLM ni el grafo (``graph.ainvoke``/``graph.astream``)
bajo ninguna combinación de estado, y no debe filtrar detalles de
infraestructura (mensajes de excepción, tipos, hosts) en la respuesta: solo
booleanos por chequeo.

Se usa ``TestClient`` SIN bloque ``with`` para no disparar el lifespan real
de la app (que tocaría la base de datos y Chroma de verdad) — mismo patrón
que ``test_expanded_query_length.py``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from langchain_core.documents import Document
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import rag.api.main as main_module
import rag.core.retriever as retriever_module
from rag.api.models import Base


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _reset_bm25_singleton():
    """Aísla el singleton de módulo entre pruebas (igual que test_bm25_*)."""
    original = retriever_module._bm25_base
    retriever_module._bm25_base = None
    yield
    retriever_module._bm25_base = original


@pytest.fixture(autouse=True)
def _reset_graph_singleton():
    original = main_module._graph
    yield
    main_module._graph = original


class _RefusingGraph:
    """Grafo falso que falla si algo intenta invocarlo — /api/ready nunca debe hacerlo."""

    async def ainvoke(self, *args, **kwargs):
        raise AssertionError("/api/ready no debe invocar el grafo (LLM)")

    async def astream(self, *args, **kwargs):
        raise AssertionError("/api/ready no debe invocar el grafo (LLM)")
        yield  # pragma: no cover - hace de esta función un generador


def _set_bm25(docs: list) -> None:
    """Coloca el singleton BM25 en un estado ya-inicializado con `docs`."""
    vectorizer = SimpleNamespace(corpus_size=len(docs)) if docs else None
    retriever_module._bm25_base = retriever_module.BM25Retriever(
        vectorizer=vectorizer, docs=docs, k=50
    )


async def _working_db_setup(tmp_path) -> async_sessionmaker:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/ready_test.db")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


def _client() -> TestClient:
    return TestClient(main_module.app)


# ---------------------------------------------------------------------------
# Todo disponible → 200 "ready"
# ---------------------------------------------------------------------------


def test_ready_returns_200_when_everything_is_available(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    main_module._graph = _RefusingGraph()
    _set_bm25([Document(page_content="algo", metadata={})])

    session_factory = asyncio.run(_working_db_setup(tmp_path))
    monkeypatch.setattr(main_module, "async_session_factory", session_factory, raising=False)
    import rag.api.database as database_module

    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    response = _client().get("/api/ready")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "graph_compiled": True,
        "index_not_empty": True,
        "database": True,
    }


# ---------------------------------------------------------------------------
# Lifespan aún no terminó → 503, y NO se confunde con "índice vacío real"
# ---------------------------------------------------------------------------


def test_ready_returns_503_when_graph_not_compiled_yet(monkeypatch: pytest.MonkeyPatch) -> None:
    main_module._graph = None
    # bm25_index_is_empty() es False aquí (aún no inicializado) — el chequeo
    # de índice no debe reportarse como "no vacío" solo por eso.
    assert retriever_module.bm25_index_is_empty() is False

    response = _client().get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["graph_compiled"] is False
    assert body["checks"]["index_not_empty"] is False


# ---------------------------------------------------------------------------
# Índice inicializado pero vacío → 503
# ---------------------------------------------------------------------------


def test_ready_returns_503_when_index_initialized_but_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    main_module._graph = _RefusingGraph()
    _set_bm25([])
    assert retriever_module.bm25_index_is_empty() is True

    session_factory = asyncio.run(_working_db_setup(tmp_path))
    import rag.api.database as database_module

    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    response = _client().get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["graph_compiled"] is True
    assert body["checks"]["index_not_empty"] is False


# ---------------------------------------------------------------------------
# Base de datos no responde → 503, sin filtrar detalles de infraestructura
# ---------------------------------------------------------------------------


def test_ready_returns_503_when_database_unreachable_without_leaking_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_module._graph = _RefusingGraph()
    _set_bm25([Document(page_content="algo", metadata={})])

    class _BoomSessionFactory:
        def __call__(self):
            raise RuntimeError(
                "no fue posible conectar a postgres://usuario:secreto@10.0.5.12:5432/atlas"
            )

    import rag.api.database as database_module

    monkeypatch.setattr(database_module, "async_session_factory", _BoomSessionFactory())

    response = _client().get("/api/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] is False
    # Ningún detalle de infraestructura (host, usuario, credenciales) debe
    # aparecer en la respuesta expuesta al cliente.
    raw = response.text
    assert "postgres://" not in raw
    assert "secreto" not in raw
    assert "10.0.5.12" not in raw


# ---------------------------------------------------------------------------
# Timeout corto: una base de datos colgada no debe bloquear el chequeo
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_database_ready_respects_short_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.database as database_module

    class _HangingSession:
        async def __aenter__(self):
            await asyncio.sleep(5)
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *args, **kwargs):
            return None

    monkeypatch.setattr(database_module, "async_session_factory", lambda: _HangingSession())

    result = await main_module._check_database_ready(timeout=0.05)

    assert result is False


@pytest.mark.anyio
async def test_check_database_ready_true_when_query_succeeds(tmp_path) -> None:
    session_factory = await _working_db_setup(tmp_path)

    import rag.api.database as database_module

    original = database_module.async_session_factory
    database_module.async_session_factory = session_factory
    try:
        result = await main_module._check_database_ready(timeout=2.0)
    finally:
        database_module.async_session_factory = original

    assert result is True


# ---------------------------------------------------------------------------
# Nunca invoca al grafo (LLM), en ninguna combinación de estado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("graph_state", [None, "compiled"])
def test_ready_never_invokes_the_graph(
    monkeypatch: pytest.MonkeyPatch, tmp_path, graph_state: str | None
) -> None:
    main_module._graph = _RefusingGraph() if graph_state == "compiled" else None
    _set_bm25([Document(page_content="algo", metadata={})])

    session_factory = asyncio.run(_working_db_setup(tmp_path))
    import rag.api.database as database_module

    monkeypatch.setattr(database_module, "async_session_factory", session_factory)

    response = _client().get("/api/ready")

    # Si el grafo falso hubiera sido invocado, habría lanzado AssertionError
    # dentro de la app y este request habría fallado con 500, no 200/503.
    assert response.status_code in (200, 503)
