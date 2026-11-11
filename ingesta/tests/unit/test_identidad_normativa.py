"""Identidad de normativa: campos propios, solo con evidencia del encabezado."""

from __future__ import annotations

from ingest.legal_metadata import extract_legal_metadata, identity_gate
from ingest.offline.pipeline import quality


def campos(texto, doc_type="normativa"):
    metadata = extract_legal_metadata(texto, doc_type)
    return metadata, {k: v["valor"] for k, v in metadata["campos"].items()}


def test_encabezado_fecha_y_emisor_de_un_decreto():
    texto = (
        "MINISTERIO DE COMERCIO, INDUSTRIA Y TURISMO\n"
        "DECRETO NÚMERO 1766 DE 2013\n"
        "(16 de agosto de 2013)\n"
        "Por el cual se reglamenta el funcionamiento de los comités locales\n"
        "EL PRESIDENTE DE LA REPÚBLICA DE COLOMBIA\n"
        "en ejercicio de sus facultades y de lo previsto en la Ley 1558 de 2012\n"
    )
    metadata, valores = campos(texto)
    assert (valores["tipo_documento"], valores["numero"], valores["anio"]) == (
        "Decreto",
        "1766",
        2013,
    )
    assert valores["fecha_iso"] == "2013-08-16"
    assert valores["entidad_emisora"] == "Presidente de la república"
    gate = identity_gate(metadata, "normativa")
    assert gate == {"pasa": True, "faltan": [], "recomendados_ausentes": []}
    for campo in ("tipo_documento", "numero", "anio", "fecha_iso", "entidad_emisora"):
        assert metadata["campos"][campo]["evidencia"] in texto


def test_una_norma_citada_no_es_la_identidad_del_documento():
    # Fragmento de compilación sin encabezado propio: antes se tomaba la cita.
    texto = (
        "Que de acuerdo al Artículo 30 del Decreto No. 1512 del 2000, la Dirección General\n"
        "Marítima es una dependencia; y la Ley 810 de 2003 dispone que\n"
    )
    metadata, valores = campos(texto)
    assert valores["numero"] is None and valores["anio"] is None
    assert metadata["campos"]["numero"]["razon"] == "sin_identidad_en_texto"
    gate = identity_gate(metadata, "normativa")
    assert not gate["pasa"]
    assert gate["faltan"] == ["tipo_documento", "numero", "anio"]


def test_fecha_con_mes_primero_da_el_anio_si_el_encabezado_no_lo_trae():
    _, valores = campos("DECRETO 1431\n(octubre 15 de 2024)\nPOR MEDIO DEL CUAL SE IMPLEMENTA\n")
    assert (valores["numero"], valores["anio"], valores["fecha_iso"]) == (
        "1431",
        2024,
        "2024-10-15",
    )


def test_fecha_corta_de_expedicion_gana_a_la_de_publicacion():
    # Revisión manual: el Decreto 1875 de 1979 se expidió el 2 de agosto; el 31 es
    # la fecha del Diario Oficial.
    texto = "DECRETO 1875 DE 1979\n(agosto 2)\nDiario Oficial No. 35339 de 31 de agosto de 1979\n"
    metadata, valores = campos(texto)
    assert valores["fecha_iso"] == "1979-08-02"
    assert metadata["campos"]["fecha_iso"]["evidencia"] == "(agosto 2)"


def test_fecha_de_otro_anio_es_de_una_norma_citada_y_se_ignora():
    texto = "DECRETO 4440 DE 2008\nQue el Decreto 3888 del 10 de octubre de 2007 dispuso\n"
    _, valores = campos(texto)
    assert valores["anio"] == 2008
    assert valores["fecha_iso"] is None


def test_cabecera_suin_y_pie_del_gestor_normativo():
    _, suin = campos("DECRETO 1436 DE 1984 - Colombia | SUIN Juriscol 18/04/26, 6:11 p.m.\n")
    assert (suin["tipo_documento"], suin["numero"], suin["anio"]) == ("Decreto", "1436", 1984)
    pie = "ARTÍCULO 2.2.3.2.5 Déficit.\nDecreto 1077 de 2015 Sector Vivienda 12 EVA - Gestor Normativo\n"
    _, gestor = campos(pie)
    assert (gestor["tipo_documento"], gestor["numero"], gestor["anio"]) == ("Decreto", "1077", 2015)


def test_numero_ilegible_por_ocr_no_inventa_identidad():
    _, valores = campos("DECRETO No. (2) J\n( MO MAR 2013 )\nEL ALCALDE DEL DISTRITO TURISTICO\n")
    assert valores["numero"] is None
    assert valores["entidad_emisora"] == "Alcalde del distrito turistico"


def test_jurisprudencia_conserva_su_puerta_de_corporacion():
    texto = "CONSEJO DE ESTADO\nSALA DE LO CONTENCIOSO ADMINISTRATIVO\nConsejero ponente: Fulano de Tal\n"
    metadata = extract_legal_metadata(texto, "jurisprudencia")
    assert metadata == extract_legal_metadata(texto)
    assert identity_gate(metadata, "jurisprudencia")["pasa"]
    assert not identity_gate(extract_legal_metadata("texto sin corporación"), None)["pasa"]


def test_puerta_de_calidad_usa_el_tipo_de_documento():
    texto = "DECRETO NÚMERO 1766 DE 2013\n(16 de agosto de 2013)\n" + "Artículo 1. Texto. " * 20
    documento = {"original": texto, "ocr_failed_pages": []}
    limpio = {"text": texto}
    metadata = extract_legal_metadata(texto, "normativa")
    assert not quality(documento, limpio, metadata)["identity"]  # sin doc_type: corporación
    metadata["doc_type"] = "normativa"
    assert quality(documento, limpio, metadata)["identity"]
