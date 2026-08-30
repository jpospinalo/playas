"""A1.5 — saltar la llamada al LLM de enriquecimiento solo para rutas
terminales deterministas.

``_fallback()`` (``core/domain_scope.py``) resuelve dos familias de señal
sobre la pregunta SOLA, antes de considerar el historial: familia #5
(solicitud inequívocamente ajena -> ``out_of_scope``) y familia #6
(saludo/meta-pregunta completa -> ``conversation``). Ningún historial, por
extenso que sea, puede cambiar ese resultado — así lo confirma
``test_query_analysis.py`` para ``_fallback()`` en aislamiento. Por eso, y
solo para esos dos casos, ``enrich_query``/``enrich_query_async`` pueden
saltarse la llamada al LLM e ir directo a ``_fallback()``.

Para cualquier otra ruta — ``in_scope``, ``needs_clarification``, un
``out_of_scope`` que no venga de esa familia inequívoca, o un seguimiento que
depende del historial — el LLM debe seguir invocándose: el historial, o la
ambigüedad genuina, sí pueden cambiar el resultado en esos casos.

Estas pruebas verifican el comportamiento por CONTEO DE LLAMADAS a
``get_active_provider`` (el primer paso dentro del bloque ``try`` de ambas
variantes), no solo por el valor de retorno: ``enrich_query``/
``enrich_query_async`` capturan ``Exception`` de forma amplia y caen a
``_fallback()`` en cualquier fallo del LLM, así que un doble que lanza al ser
llamado produce el mismo resultado que uno nunca invocado — solo el conteo de
llamadas distingue "se saltó" de "se intentó y falló".
"""

from __future__ import annotations

import pytest

import rag.core.query_enricher as query_enricher
from rag.core.query_enricher import (
    EnrichedQuery,
    _fallback,
    _is_deterministic_terminal,
    enrich_query,
    enrich_query_async,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _counting_boom(calls: list[int]):
    def _inner():
        calls.append(1)
        raise AssertionError("get_active_provider() no debía llamarse")

    return _inner


# ---------------------------------------------------------------------------
# _is_deterministic_terminal() — unidad aislada
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question",
    [
        "Dame una receta para cocinar pescado.",
        "¿Cuál es la capital de Francia?",
        "Escríbeme un poema sobre la luna.",
        "Programa una API en Python para mí.",
        "Recomiéndame un hotel para las vacaciones.",
        "Hola",
        "Buenos días",
        "¿Qué puedes hacer?",
        "¿Cómo funcionas?",
    ],
)
def test_is_deterministic_terminal_true_for_off_topic_and_meta_questions(question: str) -> None:
    assert _is_deterministic_terminal(question) is True


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué permisos exige DIMAR para pescar desde una playa?",
        "¿Qué permiso necesito para operar un negocio turístico?",
        "¿Y quién tiene ese derecho?",
        "¿Qué opinas del clima político actual?",
        "acceso a la playa",
    ],
)
def test_is_deterministic_terminal_false_for_everything_else(question: str) -> None:
    assert _is_deterministic_terminal(question) is False


# ---------------------------------------------------------------------------
# enrich_query() / enrich_query_async() — el LLM se salta SOLO en los dos
# casos terminales deterministas
# ---------------------------------------------------------------------------

_TERMINAL_CASES = [
    "Dame una receta para cocinar pescado.",
    "¿Cuál es la capital de Francia?",
    "Hola",
    "¿Qué puedes hacer?",
]

_NON_TERMINAL_CASES = [
    "¿Qué permisos exige DIMAR para pescar desde una playa?",
    "¿Qué permiso necesito para operar un negocio turístico?",
    "¿Qué opinas del clima político actual?",
]


@pytest.mark.parametrize("question", _TERMINAL_CASES)
def test_enrich_query_sync_skips_llm_for_terminal_cases(
    question: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    result = enrich_query(question)

    assert calls == [], "get_active_provider() se llamó pese a ser un caso terminal"
    assert result == _fallback(question)


@pytest.mark.parametrize("question", _TERMINAL_CASES)
@pytest.mark.anyio
async def test_enrich_query_async_skips_llm_for_terminal_cases(
    question: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    result = await enrich_query_async(question)

    assert calls == [], "get_active_provider() se llamó pese a ser un caso terminal"
    assert result == _fallback(question)


@pytest.mark.parametrize("question", _NON_TERMINAL_CASES)
def test_enrich_query_sync_still_attempts_llm_for_non_terminal_cases(
    question: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    result = enrich_query(question)  # cae a _fallback() vía el except Exception

    assert calls == [1], "get_active_provider() no se llamó para un caso no terminal"
    assert isinstance(result, EnrichedQuery)


@pytest.mark.parametrize("question", _NON_TERMINAL_CASES)
@pytest.mark.anyio
async def test_enrich_query_async_still_attempts_llm_for_non_terminal_cases(
    question: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    result = await enrich_query_async(question)

    assert calls == [1], "get_active_provider() no se llamó para un caso no terminal"
    assert isinstance(result, EnrichedQuery)


def test_enrich_query_sync_still_attempts_llm_for_history_dependent_follow_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La pregunta sola ("¿Y quién tiene ese derecho?") no dispara ninguna de
    las dos familias terminales — el LLM debe intentarse aunque, sin
    historial, el resultado final sea el mismo out_of_scope."""
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    enrich_query(
        "¿Y quién tiene ese derecho?",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )

    assert calls == [1]


@pytest.mark.anyio
async def test_enrich_query_async_still_attempts_llm_for_history_dependent_follow_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    await enrich_query_async(
        "¿Y quién tiene ese derecho?",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )

    assert calls == [1]


# ---------------------------------------------------------------------------
# El historial no puede reactivar el LLM para un caso terminal — coherente
# con que _is_deterministic_terminal() solo mira la pregunta.
# ---------------------------------------------------------------------------


def test_terminal_case_skips_llm_even_with_history_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    result = enrich_query(
        "Dame una receta para cocinar pescado.",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )

    assert calls == []
    assert result.route == "out_of_scope"


# ---------------------------------------------------------------------------
# Con enrichment deshabilitado, el comportamiento previo (fallback directo,
# sin intentar el LLM en ningún caso) no cambia.
# ---------------------------------------------------------------------------


def test_disabled_enrichment_still_skips_llm_regardless_of_terminality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", False)
    monkeypatch.setattr(query_enricher, "get_active_provider", _counting_boom(calls))

    enrich_query("¿Qué permisos exige DIMAR para pescar desde una playa?")

    assert calls == []
