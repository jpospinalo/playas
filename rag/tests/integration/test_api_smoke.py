"""Pruebas de humo opcionales contra una API desplegada.

No crean conversaciones ni modifican Chroma. Se omiten automáticamente si no
se proporcionan ``RAG_SMOKE_API_URL`` y ``RAG_SMOKE_TOKEN``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

import httpx
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def api_client() -> Iterator[httpx.Client]:
    api_url = os.getenv("RAG_SMOKE_API_URL", "").rstrip("/")
    token = os.getenv("RAG_SMOKE_TOKEN", "")
    if not api_url or not token:
        pytest.skip("Configura RAG_SMOKE_API_URL y RAG_SMOKE_TOKEN para ejecutar estas pruebas.")
    with httpx.Client(
        base_url=api_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    ) as client:
        yield client


def _query(client: httpx.Client, question: str) -> dict:
    response = client.post("/api/query", json={"question": question})
    response.raise_for_status()
    return response.json()


def test_health_and_off_topic_guard(api_client: httpx.Client) -> None:
    health = api_client.get("/api/health")
    health.raise_for_status()
    assert health.json() == {"status": "ok"}

    result = _query(api_client, "¿Cuál es la capital de Francia?")
    assert result["query_route"] == "out_of_scope"
    assert result["sources"] == []
    assert "París" not in result["answer"]


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué permisos se requieren para realizar pesca artesanal desde una playa?",
        "¿Puede un operador turístico restringir el acceso público a una playa?",
    ],
)
def test_domain_queries_are_retrieved_and_cited(
    api_client: httpx.Client,
    question: str,
) -> None:
    result = _query(api_client, question)
    assert result["query_route"] == "in_scope"
    assert result["sources"]
    assert re.search(r"\[doc\d+\]", result["answer"], re.IGNORECASE)
