"""T1.1 — una consulta válida de hasta 4.000 caracteres no debe producir un
HTTP 500 determinístico.

Antes de esta corrección, ``EnrichedQuery.expanded_query`` tenía
``max_length=1000`` y el recorte a 45 palabras corría en un validador
``mode="after"`` — es decir, DESPUÉS de que Pydantic ya había rechazado el
valor. Cualquier construcción de ``EnrichedQuery`` con un texto de más de
1.000 caracteres (y en particular ``_fallback()``, con la pregunta completa)
lanzaba ``ValidationError`` sin capturar, que ``main.query()`` convierte en un
HTTP 500.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import rag.core.query_enricher as query_enricher
from rag.core.query_enricher import (
    EnrichedQuery,
    _apply_domain_guard,
    _fallback,
    _normalize_expanded_query,
    enrich_query,
    enrich_query_async,
)

# ---------------------------------------------------------------------------
# _normalize_expanded_query — la función de normalización en aislamiento
# ---------------------------------------------------------------------------


def test_normalize_respects_both_limits_simultaneously() -> None:
    texto = "palabra " * 200  # 200 palabras, 1600 caracteres, con espacios
    normalizado = _normalize_expanded_query(texto)
    assert len(normalizado.split()) <= 45
    assert len(normalizado) <= 1000


def test_normalize_handles_no_spaces_via_char_limit() -> None:
    """El caso que el recorte por palabras por sí solo no resuelve: una
    entrada de 4.000 caracteres sin espacios es una única "palabra"."""
    texto = "a" * 4000
    normalizado = _normalize_expanded_query(texto)
    assert len(normalizado.split()) == 1
    assert len(normalizado) == 1000


def test_normalize_is_idempotent() -> None:
    for texto in ["palabra " * 200, "a" * 4000, "consulta corta", ""]:
        once = _normalize_expanded_query(texto)
        twice = _normalize_expanded_query(once)
        assert once == twice


# ---------------------------------------------------------------------------
# Construcción directa de EnrichedQuery con textos largos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("length", [1000, 1001, 4000])
def test_enriched_query_accepts_up_to_4000_chars_with_spaces(length: int) -> None:
    texto = ("palabra de prueba jurídica costera " * 200)[:length]
    result = EnrichedQuery(
        route="out_of_scope",
        standalone_question=texto,
        expanded_query=texto,
        doc_types=[],
    )
    assert len(result.expanded_query) <= 1000
    assert len(result.expanded_query.split()) <= 45


def test_enriched_query_accepts_4000_chars_without_spaces() -> None:
    texto = "a" * 4000
    result = EnrichedQuery(
        route="out_of_scope",
        standalone_question=texto,
        expanded_query=texto,
        doc_types=[],
    )
    assert len(result.expanded_query) == 1000


def test_enriched_query_accepts_unicode_and_newlines() -> None:
    texto = ("¿Qué régimen jurídico se aplica a la línea de más alta marea?\n" * 100)[:4000]
    result = EnrichedQuery(
        route="in_scope",
        standalone_question=texto,
        expanded_query=texto,
        doc_types=["normativa"],
    )
    assert len(result.expanded_query) <= 1000


# ---------------------------------------------------------------------------
# _fallback() directo — la ruta que crasheaba
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("length", [1000, 1001, 4000])
def test_fallback_direct_no_500_with_spaces(length: int) -> None:
    texto = ("normatividad sobre playas y concesiones marítimas " * 100)[:length]
    result = _fallback(texto)
    assert isinstance(result, EnrichedQuery)
    assert result.standalone_question == texto.strip()


def test_fallback_direct_no_500_without_spaces() -> None:
    texto = "a" * 4000
    result = _fallback(texto)
    assert isinstance(result, EnrichedQuery)
    assert result.standalone_question == texto


def test_fallback_direct_no_500_unicode_and_newlines() -> None:
    texto = ("¿Cómo se define la línea de más alta marea?\ncon saltos\n" * 100)[:4000]
    result = _fallback(texto)
    assert isinstance(result, EnrichedQuery)


# ---------------------------------------------------------------------------
# Rutas actuales in_scope / out_of_scope no cambian con textos largos
# ---------------------------------------------------------------------------


def test_fallback_long_in_scope_question_keeps_route() -> None:
    base = "¿Qué permisos exige DIMAR para pescar desde una playa? "
    texto = (base * 100)[:4000]
    result = _fallback(texto)
    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]


def test_fallback_long_out_of_scope_question_keeps_route() -> None:
    base = "Dame una receta para cocinar pescado con arroz y limón. "
    texto = (base * 100)[:4000]
    result = _fallback(texto)
    assert result.route == "out_of_scope"


# ---------------------------------------------------------------------------
# _apply_domain_guard() con un resultado LLM estructurado y válido: la
# heurística interna (_fallback) es la que crasheaba incluso cuando el LLM
# respondió bien.
# ---------------------------------------------------------------------------


def test_domain_guard_with_valid_llm_result_and_long_question() -> None:
    texto = "a" * 4000
    llm_result = EnrichedQuery(
        route="in_scope",
        standalone_question=texto,
        expanded_query="consulta jurídica costera de prueba",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(llm_result, texto, "")
    assert isinstance(guarded, EnrichedQuery)


def test_domain_guard_with_valid_llm_result_and_long_spaced_question() -> None:
    texto = ("permiso concesión playa autoridad marítima " * 100)[:4000]
    llm_result = EnrichedQuery(
        route="in_scope",
        standalone_question=texto,
        expanded_query="consulta jurídica costera de prueba",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(llm_result, texto, "")
    assert isinstance(guarded, EnrichedQuery)


# ---------------------------------------------------------------------------
# Error del LLM — enrich_query/enrich_query_async deben caer a _fallback()
# sin propagar la excepción, incluso con una pregunta larga.
# ---------------------------------------------------------------------------


def _boom() -> SimpleNamespace:
    raise RuntimeError("proveedor no disponible")


def test_enrich_query_sync_llm_error_falls_back_without_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _boom)
    texto = "a" * 4000
    result = enrich_query(texto)
    assert isinstance(result, EnrichedQuery)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_enrich_query_async_llm_error_falls_back_without_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _boom)
    texto = ("consulta muy larga sin sentido jurídico particular " * 100)[:4000]
    result = await enrich_query_async(texto)
    assert isinstance(result, EnrichedQuery)


def test_enrich_query_disabled_enrichment_direct_fallback_no_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", False)
    texto = "a" * 4000
    result = enrich_query(texto)
    assert isinstance(result, EnrichedQuery)


# ---------------------------------------------------------------------------
# Endpoint completo — /api/query no debe responder HTTP 500 para una
# pregunta larga. Se compila el grafo real (LangGraph, MemorySaver en
# memoria) pero con el enriquecimiento deshabilitado, de modo que
# ``enrich_query_node`` ejercita ``_fallback()`` sin necesitar un LLM. Se usa
# una pregunta sin señal de dominio para que el grafo enrute a
# ``respond_without_retrieval_node`` y nunca llegue a invocar Chroma/Ollama.
# El ``TestClient`` se usa SIN bloque ``with`` para no disparar el lifespan
# de la app (que sí tocaría la base de datos y Chroma).
# ---------------------------------------------------------------------------


def test_query_endpoint_long_question_does_not_return_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module
    import rag.core.agent as agent_module
    from rag.api.rate_limit import get_query_user

    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", False)

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    main_module.app.dependency_overrides[get_query_user] = lambda: {"sub": "test-user"}
    try:
        client = TestClient(main_module.app)
        texto = ("Dame una receta para cocinar pescado con arroz y limón. " * 100)[:4000]
        response = client.post("/api/query", json={"question": texto})
        assert response.status_code != 500, response.text
        assert response.status_code == 200
        body = response.json()
        assert body["query_route"] == "out_of_scope"
    finally:
        main_module.app.dependency_overrides.clear()


def test_query_endpoint_long_question_without_spaces_does_not_return_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rag.api.main as main_module
    import rag.core.agent as agent_module
    from rag.api.rate_limit import get_query_user

    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", False)

    graph = agent_module.build_graph()
    monkeypatch.setattr(main_module, "_graph", graph)

    main_module.app.dependency_overrides[get_query_user] = lambda: {"sub": "test-user"}
    try:
        client = TestClient(main_module.app)
        texto = "a" * 4000
        response = client.post("/api/query", json={"question": texto})
        assert response.status_code != 500, response.text
        assert response.status_code == 200
    finally:
        main_module.app.dependency_overrides.clear()
