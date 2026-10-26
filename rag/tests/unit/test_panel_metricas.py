"""Clasificaciones del panel (``rag/api/panel_metricas.py``): reglas sin IA.

Incluye dos pruebas de sincronía con el resto del repo: las preguntas fijas
del flujo guiado deben ser idénticas a ``rag/frontend/lib/guia/temas.ts`` y
los inicios de las respuestas fijas deben seguir coincidiendo con
``rag/core/agent.py``. Si alguien cambia esos textos, el panel dejaría de
reconocerlos sin avisar: estas pruebas lo avisan.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from rag.api import panel_metricas as pm
from rag.core import agent

_TEMAS_TS = Path(__file__).resolve().parents[2] / "frontend" / "lib" / "guia" / "temas.ts"


def _preguntas_del_front() -> dict[str, list[str]]:
    texto = _TEMAS_TS.read_text(encoding="utf-8")
    salida: dict[str, list[str]] = {}
    for bloque in re.split(r"\n\t\{\n\t\tid: ", texto)[1:]:
        tema_id = re.match(r'"([^"]+)"', bloque).group(1)
        salida[tema_id] = re.findall(r'pregunta:\s*"([^"]+)"', bloque)
    return salida


def test_preguntas_guiadas_iguales_al_front() -> None:
    front = _preguntas_del_front()
    assert set(front) == set(pm.TEMAS_POR_ID)
    for tema_id, preguntas in front.items():
        assert list(pm.TEMAS_POR_ID[tema_id].preguntas) == preguntas, tema_id


def test_playas_iguales_al_front() -> None:
    texto = _TEMAS_TS.read_text(encoding="utf-8")
    bloque = re.search(r"PLAYAS = \[(.*?)\]", texto, re.S).group(1)
    assert tuple(re.findall(r'"([^"]+)"', bloque)) == pm.PLAYAS


@pytest.mark.parametrize(
    ("constante", "esperado"),
    [
        (agent._NO_EVIDENCE_RESPONSE, pm.SIN_EVIDENCIA),
        (agent._INVALID_CITATIONS_RESPONSE, pm.SIN_CITA_VALIDA),
        (agent._OUT_OF_SCOPE_RESPONSE, pm.FUERA_DE_TEMA),
        (agent._CLARIFICATION_RESPONSE, pm.PIDE_ACLARAR),
        (agent._CONVERSATION_RESPONSE, pm.SALUDO),
    ],
)
def test_respuestas_fijas_del_agente(constante: str, esperado: str) -> None:
    # Aunque traiga fuentes, una respuesta fija nunca cuenta como "con fuente".
    assert pm.clasificar_respuesta(constante, [{"title": "x"}]) == esperado


def test_resultado_con_y_sin_fuente() -> None:
    assert (
        pm.clasificar_respuesta("Sí, según el Decreto 2324 [doc1].", [{"title": "D"}])
        == pm.CON_FUENTE
    )
    assert pm.clasificar_respuesta("Sí, según el Decreto 2324.", []) == pm.SIN_FUENTE_OTRO
    assert pm.clasificar_respuesta("Sí.", None) == pm.SIN_FUENTE_OTRO
    assert pm.clasificar_respuesta(None, None) == pm.SIN_RESPUESTA
    assert pm.BRECHAS == {pm.SIN_EVIDENCIA, pm.SIN_CITA_VALIDA, pm.SIN_FUENTE_OTRO}


def test_tema_exacto_de_cada_boton_aunque_lleve_playa() -> None:
    for tema in pm.TEMAS:
        for pregunta in tema.preguntas:
            assert pm.clasificar_tema(pregunta) == tema.id
            assert pm.clasificar_tema(f"{pregunta} Es en Taganga, en Santa Marta.") == tema.id


@pytest.mark.parametrize(
    ("texto", "tema"),
    [
        ("¿Me pueden cobrar la entrada a la playa del hotel?", "entrar"),
        ("Necesito saber si con chinchorro se puede PESCAR de noche", "pescar"),
        ("¿Qué carné necesita un vendedor ambulante?", "vender"),
        ("El restaurante puso parasoles en toda la arena", "hoteles"),
        ("Las motos de agua pasan muy cerca de los bañistas", "lanchas"),
        ("¿Puedo arreglar el techo de mi kiosco sin licencia?", "obras"),
        ("¿Qué horario tiene el museo del oro?", pm.TEMA_OTROS),
        ("", pm.TEMA_OTROS),
    ],
)
def test_tema_por_palabras_clave(texto: str, tema: str) -> None:
    assert pm.clasificar_tema(texto) == tema


def test_playa_por_sufijo_y_por_texto() -> None:
    assert pm.detectar_playa("¿Puedo vender? Es en El Rodadero, en Santa Marta.") == "El Rodadero"
    assert pm.detectar_playa("Es en la bahia de santa marta donde pasa") == "Bahía de Santa Marta"
    assert pm.detectar_playa("En taganga no dejan pescar") == "Taganga"
    # "Santa Marta" sola no es una playa.
    assert pm.detectar_playa("¿Qué pasa en Santa Marta?") == pm.SIN_PLAYA
    assert pm.detectar_playa("Es en Otra, en Santa Marta.") == pm.SIN_PLAYA


def test_normas_citadas_sin_repetidos() -> None:
    sources = [
        {
            "source": "normativa/decreto-2324.md",
            "title": "Decreto 2324 de 1984",
            "doc_type": "normativa",
        },
        {
            "source": "normativa/decreto-2324.md",
            "title": "Decreto 2324 de 1984",
            "doc_type": "normativa",
        },
        {"source": "jurisprudencia/AP Gieseken.md", "title": "", "doc_type": "jurisprudencia"},
        "basura",
        {"source": "", "title": ""},
    ]
    assert pm.normas_citadas(sources) == [
        ("Decreto 2324 de 1984", "normativa"),
        ("AP Gieseken", "jurisprudencia"),
    ]
    assert pm.normas_citadas(None) == []


@pytest.mark.parametrize(
    ("ratings", "esperado"),
    [
        ({"pertinence": 5, "accuracy": 5}, pm.UTIL),
        ({"pertinence": 4, "accuracy": 4}, pm.UTIL),
        ({"pertinence": 3, "accuracy": 3}, pm.NEUTRA),
        ({"pertinence": 1, "accuracy": 1}, pm.NO_UTIL),
        ({"pertinence": 2, "accuracy": 2}, pm.NO_UTIL),
        ({}, None),
        (None, None),
    ],
)
def test_calificacion(ratings: dict | None, esperado: str | None) -> None:
    assert pm.calificacion(ratings) == esperado


def test_periodo_en_hora_de_colombia_incluye_hoy() -> None:
    # 26-oct 03:00 UTC = 25-oct 22:00 en Colombia: "hoy" es el 25.
    ahora = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)
    p = pm.calcular_periodo(7, ahora)
    assert p.inicio == datetime(2026, 10, 19, 5, 0, tzinfo=UTC)  # 19-oct 00:00 COT
    assert p.anterior_inicio == datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
    assert p.fin == ahora
    todo = pm.calcular_periodo(0, ahora)
    assert todo.inicio is None and todo.anterior_inicio is None


def test_claves_de_dia_y_semana() -> None:
    # Domingo 25-oct 23:30 en Colombia = lunes 26-oct 04:30 UTC.
    dt = datetime(2026, 10, 26, 4, 30, tzinfo=UTC)
    assert pm.clave_dia(dt) == "2026-10-25"
    assert pm.clave_semana(dt) == "2026-10-19"
    assert pm.clave_semana(datetime(2026, 10, 26, 5, 0)) == "2026-10-26"  # sin zona = UTC
