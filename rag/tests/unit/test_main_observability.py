"""T3.1 — instrumentación de observabilidad conectada a los endpoints HTTP.

Verifica que `/api/query` (a) registra el gauge de consultas activas
(`ACTIVE_QUERIES`) alrededor de la ejecución del grafo y lo deja en 0 al
terminar, incluso si la consulta falla, y (b) loguea cuántas conversaciones
retiene el checkpointer — sin filtrar el `thread_id` real en el log.

Mismo patrón que `test_expanded_query_length.py`: `TestClient` SIN bloque
`with` para no disparar el lifespan real (que tocaría Chroma/la base real),
y un grafo real pero compilado a mano con enriquecimiento deshabilitado
para no depender de un LLM.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

import rag.core.agent as agent_module
import rag.core.query_enricher as query_enricher_module


def _client_with_real_graph(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import rag.api.main as main_module
    from rag.api.rate_limit import get_query_user

    monkeypatch.setattr(query_enricher_module, "ENRICHMENT_ENABLED", False)
    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)
    main_module.app.dependency_overrides[get_query_user] = lambda: {"sub": "test-user"}
    return TestClient(main_module.app)


def test_query_endpoint_tracks_active_queries_and_returns_to_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    client = _client_with_real_graph(monkeypatch)
    try:
        assert main_module.ACTIVE_QUERIES.count == 0
        response = client.post(
            "/api/query", json={"question": "Dame una receta de cocina, por favor."}
        )
        assert response.status_code == 200, response.text
        # Tras responder, el gauge debe haber vuelto a 0 — no queda "colgado".
        assert main_module.ACTIVE_QUERIES.count == 0
    finally:
        main_module.app.dependency_overrides.clear()


def test_query_endpoint_logs_retained_conversations_count_not_thread_id(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import rag.api.main as main_module

    client = _client_with_real_graph(monkeypatch)
    try:
        with caplog.at_level(logging.INFO, logger="rag.observability"):
            response = client.post(
                "/api/query", json={"question": "Dame una receta de cocina, por favor."}
            )
        assert response.status_code == 200, response.text

        retained_messages = [
            r.message for r in caplog.records if r.message.startswith("retained_conversations=")
        ]
        assert len(retained_messages) == 1
        # Esta consulta no trae `conversation_id` ni `thread_id`: es efímera
        # (basura de un solo uso, ver `_is_ephemeral_query` en api/main.py) y
        # A3.1 la borra del checkpointer antes de este log — por eso el
        # conteo es 0, no 1. Antes de A3.1 este checkpoint quedaba huérfano
        # para siempre; el conteo en 0 es justamente la prueba de que ya no.
        assert retained_messages[0] == "retained_conversations=0"

        full_output = "\n".join(r.message for r in caplog.records)
        assert "test-user" not in full_output
    finally:
        main_module.app.dependency_overrides.clear()


def test_active_queries_returns_to_zero_even_when_the_graph_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module

    class _BoomGraph:
        checkpointer = agent_module.build_graph().checkpointer

        async def aget_state(self, config):
            del config
            from types import SimpleNamespace

            return SimpleNamespace(values={})

        async def ainvoke(self, *args, **kwargs):
            raise RuntimeError("boom")

    from rag.api.rate_limit import get_query_user

    monkeypatch.setattr(main_module, "_graph", _BoomGraph())
    main_module.app.dependency_overrides[get_query_user] = lambda: {"sub": "test-user"}
    try:
        client = TestClient(main_module.app)
        response = client.post("/api/query", json={"question": "cualquier cosa"})
        assert response.status_code == 500
        assert main_module.ACTIVE_QUERIES.count == 0
    finally:
        main_module.app.dependency_overrides.clear()
