"""Pruebas de las métricas deterministas (sin LLM) de ``evaluation.metricas_sin_llm``."""

from __future__ import annotations

import pytest

from evaluation.metricas_sin_llm import (
    metricas_recuperacion,
    metricas_respuesta,
    norma_local,
    referencias_legales,
    resumir,
)

CARTAGENA = (
    "Por medio del cual se expiden las normas bases para la reglamentación de las "
    "actividades en las playas urbanas y rurales en el Distrito de Cartagena de Indias"
)
REMAC = "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)"


def _frag(title: str, texto: str = "", doc_type: str = "normativa") -> dict:
    return {"title": title, "doc_type": doc_type, "texto": texto}


def _caso(**kw) -> dict:
    base = {
        "id": "registro-001",
        "tipo": "5. Aplicación normativa o jurisprudencial",
        "pregunta": "¿Puedo vender en la playa?",
        "respuesta": "",
        "ubicacion_evidencia": "",
        "documentos_esperados": [REMAC],
    }
    return {**base, **kw}


# ── referencias_legales ──────────────────────────────────────────────────────


def test_extrae_normas_con_numero_y_anio_sin_importar_tildes_ni_mayusculas():
    texto = "Según la LEY 768 de 2002 y el Decreto-Ley 2324 de 1984, y la Resolución No. 12 de 2020"
    assert referencias_legales(texto) == {"ley 768/2002", "decreto 2324/1984", "resolucion 12/2020"}


def test_extrae_articulos_con_numeracion_jerarquica():
    texto = "ARTÍCULO 5.3.6.2. Alcance. Ver también los artículos 5.3.6.4 y 5.3.6.15."
    assert referencias_legales(texto) == {"art 5.3.6.2", "art 5.3.6.4", "art 5.3.6.15"}


def test_ignora_articulos_cortos_porque_son_ambiguos_entre_normas():
    assert referencias_legales("el artículo 15 dispone") == set()


# ── norma_local ──────────────────────────────────────────────────────────────


def test_detecta_el_lugar_de_una_norma_local():
    assert norma_local(_frag(CARTAGENA)) == "cartagena"
    assert norma_local(_frag("Reglamento del Balneario Turístico El Rodadero")) == "santa marta"


def test_la_norma_nacional_y_la_jurisprudencia_no_son_normas_locales():
    assert norma_local(_frag(REMAC)) is None
    assert norma_local(_frag("AP X VS Distrito de Cartagena", doc_type="jurisprudencia")) is None


# ── metricas_recuperacion ────────────────────────────────────────────────────


def test_acierto_y_posicion_del_documento_esperado():
    top4 = [_frag("Otro"), _frag(REMAC, "ARTÍCULO 5.3.6.2. Alcance")]
    fila = metricas_recuperacion(_caso(), top4, ["Otro", REMAC])
    assert fila["acierto_doc_4"] is True
    assert fila["posicion_doc_20"] == 2


def test_cobertura_de_articulos_esperados_en_los_fragmentos():
    caso = _caso(ubicacion_evidencia="Artículos 5.3.6.2 y 5.3.6.4")
    top4 = [_frag(REMAC, "ARTÍCULO 5.3.6.2. Alcance")]
    assert metricas_recuperacion(caso, top4, [REMAC])["articulos_4"] == pytest.approx(0.5)


def test_sin_referencias_esperadas_la_cobertura_no_aplica():
    assert metricas_recuperacion(_caso(), [_frag(REMAC)], [REMAC])["articulos_4"] is None


def test_fuga_territorial_si_llega_norma_local_de_un_lugar_no_mencionado():
    top4 = [_frag(CARTAGENA), _frag(REMAC)]
    assert metricas_recuperacion(_caso(), top4, [])["fuga_territorial_4"] is True


def test_no_hay_fuga_si_la_pregunta_menciona_el_lugar():
    caso = _caso(pregunta="Tengo un evento en Bocagrande, ¿qué permiso necesito?")
    assert metricas_recuperacion(caso, [_frag(CARTAGENA)], [])["fuga_territorial_4"] is False


def test_documentos_distintos_en_el_top_4():
    top4 = [_frag(REMAC), _frag(REMAC), _frag(CARTAGENA)]
    assert metricas_recuperacion(_caso(), top4, [])["docs_distintos_4"] == 2


def test_caso_sin_documento_esperado_no_aplica_acierto():
    fila = metricas_recuperacion(_caso(documentos_esperados=[]), [_frag(REMAC)], [REMAC])
    assert fila["acierto_doc_4"] is None
    assert fila["posicion_doc_20"] is None


# ── metricas_respuesta ───────────────────────────────────────────────────────


def test_referencia_sin_respaldo_en_los_fragmentos():
    fila = metricas_respuesta(
        _caso(),
        answer="Aplica la Ley 768 de 2002 [doc1] y la Ley 99 de 1993 [doc1].",
        contexts=["... la Ley 768 de 2002 dispone ..."],
    )
    assert fila["refs_sin_respaldo"] == ["ley 99/1993"]
    assert fila["citas_validas"] is True


def test_una_referencia_mencionada_en_la_pregunta_no_cuenta_como_sin_respaldo():
    fila = metricas_respuesta(
        _caso(pregunta="¿Qué dice la Ley 99 de 1993?"),
        answer="La Ley 99 de 1993 [doc1] ...",
        contexts=["texto"],
    )
    assert fila["refs_sin_respaldo"] == []


def test_cita_fuera_de_rango_es_invalida():
    fila = metricas_respuesta(_caso(), answer="Según [doc3].", contexts=["a", "b"])
    assert fila["citas_validas"] is False


def test_referencias_esperadas_presentes_en_la_respuesta():
    caso = _caso(respuesta="Lo regula el artículo 5.3.6.2 y la Ley 768 de 2002.")
    fila = metricas_respuesta(caso, answer="Ver artículo 5.3.6.2 [doc1].", contexts=["x"])
    assert fila["refs_esperadas_en_respuesta"] == pytest.approx(0.5)


# ── resumir ──────────────────────────────────────────────────────────────────


def test_resumir_ignora_los_casos_donde_la_metrica_no_aplica():
    filas = [
        {"acierto_doc_4": True, "articulos_4": None, "posicion_doc_20": 1},
        {"acierto_doc_4": False, "articulos_4": 0.5, "posicion_doc_20": None},
        {"acierto_doc_4": None, "articulos_4": None, "posicion_doc_20": None},
    ]
    resumen = resumir(filas)
    assert resumen["acierto_doc_4"] == {"n": 2, "valor": 0.5}
    assert resumen["articulos_4"] == {"n": 1, "valor": 0.5}
    assert resumen["mrr_doc_20"] == {"n": 2, "valor": 0.5}
