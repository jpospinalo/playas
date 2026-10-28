"""Pruebas de las métricas deterministas (sin LLM) de ``evaluation.metricas_sin_llm``."""

from __future__ import annotations

import pytest

from evaluation.metricas_sin_llm import (
    clase_esperada,
    comparar,
    intervalo_95,
    linea_base,
    metricas_recuperacion,
    metricas_respuesta,
    norma_local,
    referencias_legales,
    reporte_markdown,
    resumir,
    resumir_por,
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
        {"acierto_doc_4": True, "articulos_4": None, "mrr_doc_20": 1.0},
        {"acierto_doc_4": False, "articulos_4": 0.5, "mrr_doc_20": 0.0},
        {"acierto_doc_4": None, "articulos_4": None, "mrr_doc_20": None},
    ]
    resumen = resumir(filas, con_intervalo=False)
    assert resumen["acierto_doc_4"] == {"n": 2, "valor": 0.5}
    assert resumen["articulos_4"] == {"n": 1, "valor": 0.5}
    assert resumen["mrr_doc_20"] == {"n": 2, "valor": 0.5}


def test_mrr_es_cero_si_el_documento_no_esta_en_el_top_20():
    fila = metricas_recuperacion(_caso(), [_frag("Otro")], ["Otro"])
    assert fila["acierto_doc_20"] is False
    assert fila["mrr_doc_20"] == 0.0


def test_doc_recall_con_dos_documentos_esperados():
    caso = _caso(documentos_esperados=[REMAC, "AP X VS DIMAR"])
    fila = metricas_recuperacion(caso, [_frag(REMAC), _frag("Otro")], [REMAC])
    assert fila["doc_recall_4"] == pytest.approx(0.5)


def test_clase_del_documento_esperado():
    assert clase_esperada([REMAC]) == "normativa"
    assert clase_esperada(["AP X VS DIMAR"]) == "jurisprudencia"
    assert clase_esperada([REMAC, "AP X VS DIMAR"]) == "mixta"
    assert clase_esperada([]) == "sin documento"


# ── grafo (caché) ────────────────────────────────────────────────────────────


def test_acierto_del_grafo_con_los_titulos_de_la_cache():
    fila = metricas_respuesta(_caso(), "x [doc1]", ["texto"], context_titles=[REMAC])
    assert fila["acierto_doc_4_grafo"] is True
    sin_titulos = metricas_respuesta(_caso(), "x [doc1]", ["texto"])
    assert sin_titulos["acierto_doc_4_grafo"] is None


def test_articulos_en_los_fragmentos_del_grafo():
    caso = _caso(ubicacion_evidencia="Artículos 5.3.6.2 y 5.3.6.4")
    fila = metricas_respuesta(caso, "x [doc1]", ["ARTÍCULO 5.3.6.4. Alcance"])
    assert fila["articulos_4_grafo"] == pytest.approx(0.5)


# ── intervalo y comparación ──────────────────────────────────────────────────


def test_intervalo_es_reproducible_y_contiene_la_media():
    valores = [1.0] * 30 + [0.0] * 30
    ic = intervalo_95(valores)
    assert ic == intervalo_95(valores)
    assert ic is not None and ic[0] < 0.5 < ic[1]


def test_intervalo_no_aplica_con_menos_de_dos_casos():
    assert intervalo_95([1.0]) is None


def test_intervalo_sin_variacion_es_un_punto():
    assert intervalo_95([1.0, 1.0, 1.0]) == [1.0, 1.0]


def _base(valor: float, ic: list[float], casos: dict[str, float]) -> dict:
    return {
        "global": {"acierto_doc_4": {"valor": valor, "n": 2, "ic95": ic}},
        "casos": {"acierto_doc_4": casos},
    }


def test_regresion_si_sale_del_intervalo_hacia_abajo():
    base = _base(0.6, [0.5, 0.7], {"r1": 1.0, "r2": 0.0})
    filas = [{"case_id": "r1", "acierto_doc_4": False}, {"case_id": "r2", "acierto_doc_4": False}]
    c = comparar({"acierto_doc_4": {"valor": 0.4, "n": 2}}, filas, base)["acierto_doc_4"]
    assert c["estado"] == "regresion"
    assert c["delta"] == pytest.approx(-0.2)
    assert c["casos_peor"] == ["r1"]
    assert c["casos_mejor"] == []


def test_dentro_del_intervalo_es_igual_aunque_cambien_casos():
    base = _base(0.5, [0.3, 0.7], {"r1": 1.0, "r2": 0.0})
    filas = [{"case_id": "r1", "acierto_doc_4": False}, {"case_id": "r2", "acierto_doc_4": True}]
    c = comparar({"acierto_doc_4": {"valor": 0.5, "n": 2}}, filas, base)["acierto_doc_4"]
    assert c["estado"] == "igual"
    assert (c["casos_peor"], c["casos_mejor"]) == (["r1"], ["r2"])


def test_en_metricas_donde_menos_es_mejor_subir_es_regresion():
    base = {"global": {"fuga_territorial_4": {"valor": 0.05, "n": 2, "ic95": [0.0, 0.1]}}}
    c = comparar({"fuga_territorial_4": {"valor": 0.3, "n": 2}}, [], base)
    assert c["fuga_territorial_4"]["estado"] == "regresion"


# ── reporte de punta a punta ─────────────────────────────────────────────────


def _reporte() -> dict:
    caso_ok = _caso(id="registro-001")
    caso_fuga = _caso(id="registro-002", documentos_esperados=["AP X VS DIMAR"])
    rec = [
        metricas_recuperacion(caso_ok, [_frag(REMAC)], [REMAC]),
        metricas_recuperacion(caso_fuga, [_frag(CARTAGENA)], []),
    ]
    resp = [metricas_respuesta(caso_ok, "La Ley 99 de 1993 [doc1].", ["texto"], [REMAC])]
    seccion = lambda filas: {  # noqa: E731
        "global": resumir(filas),
        **{f"por_{c}": resumir_por(filas, c) for c in ("tipo", "revisado", "clase_esperada")},
        "casos": filas,
    }
    return {
        "dataset": "legal-ground-truth-v0.2",
        "fecha": "2026-10-28",
        "git": {"commit": "abcdef1234", "dirty": False},
        "recuperacion": seccion(rec),
        "respuesta": {"cache": "cache.jsonl", **seccion(resp)},
    }


def test_linea_base_guarda_global_y_valores_por_caso():
    base = linea_base(_reporte())
    assert base["global"]["acierto_doc_4"]["valor"] == pytest.approx(0.5)
    assert base["casos"]["acierto_doc_4"] == {"registro-001": 1.0, "registro-002": 0.0}
    assert base["casos"]["respuestas_con_refs_sin_respaldo"] == {"registro-001": 1.0}


def test_reporte_markdown_lista_desgloses_y_casos_a_revisar():
    reporte = _reporte()
    md = reporte_markdown(reporte)
    assert "| clase_esperada |" in md
    assert "| jurisprudencia | 1 |" in md
    assert "registro-002 (cartagena)" in md
    assert "registro-001 (ley 99/1993)" in md
    assert "Línea base" not in md


def test_reporte_markdown_compara_contra_la_linea_base():
    reporte = _reporte()
    base = linea_base(reporte)
    filas = reporte["recuperacion"]["casos"]
    reporte["comparacion"] = comparar(reporte["recuperacion"]["global"], filas, base)
    md = reporte_markdown(reporte)
    assert "| Línea base |" in md
    assert "igual" in md
