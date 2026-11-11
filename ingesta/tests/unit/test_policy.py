"""Política del intake: cada decisión con sus motivos."""

from __future__ import annotations

import copy
import json

import pytest

from ingest.offline.policy import (
    PUBLICABLES,
    cargar_politica,
    decidir,
    senales_documento,
)


@pytest.fixture
def politica():
    return cargar_politica()


def senales(**cambios):
    base = {
        "doc_type": "normativa",
        "paginas": 3,
        "caracteres": 5000,
        "caracteres_reemplazo": 0.0,
        "paginas_ocr": 0,
        "ocr_paginas_fallidas": 0,
        "ocr_paginas_sin_confianza": 0,
        "ocr_confianza_media": None,
        "ocr_confianza_minima": None,
        "ocr_confianzas": [],
        "identidad": {"pasa": True, "faltan": [], "recomendados_ausentes": []},
        "secuencia": {"simbolos_sospechosos": 0, "descensos": 0, "duplicados": 0, "saltos": 0},
        "imagenes_digitales": [],
        "caida_texto": [],
        "chunks": 10,
        "chunks_cortos": 0,
    }
    base.update(cambios)
    return base


def test_politica_del_repositorio_es_valida_y_completa(politica, tmp_path):
    yaml = pytest.importorskip("yaml")
    assert politica["version"] >= 1
    rota = copy.deepcopy(politica)
    del rota["revision"]["identidad_obligatoria"]
    ruta = tmp_path / "rota.yaml"
    ruta.write_text(yaml.safe_dump(rota), encoding="utf-8")
    with pytest.raises(ValueError, match="identidad_obligatoria"):
        cargar_politica(ruta)


def test_documento_limpio_se_acepta(politica):
    assert decidir(senales(), politica) == ("aceptado", [], [])


def test_identidad_recomendada_ausente_publica_con_advertencia(politica):
    identidad = {"pasa": True, "faltan": [], "recomendados_ausentes": ["entidad_emisora"]}
    decision, motivos, avisos = decidir(senales(identidad=identidad), politica)
    assert decision == "aceptado_con_advertencias" and decision in PUBLICABLES
    assert motivos == [] and "entidad_emisora" in avisos[0]


def test_ocr_con_mayoria_de_paginas_bajas_va_a_revision(politica):
    s = senales(
        paginas_ocr=4,
        ocr_confianzas=[90.0, 93.0, 94.5, 97.0],
        ocr_confianza_media=93.6,
        ocr_confianza_minima=90.0,
    )
    decision, motivos, _ = decidir(s, politica)
    assert decision == "revision_humana"
    assert "75% de páginas OCR con confianza ≤ 95" in motivos[0]


def test_identidad_incompleta_va_a_revision(politica):
    identidad = {"pasa": False, "faltan": ["numero", "anio"], "recomendados_ausentes": []}
    decision, motivos, _ = decidir(senales(identidad=identidad), politica)
    assert decision == "revision_humana"
    assert motivos == ["identidad incompleta: faltan numero, anio"]


def test_tablas_imagen_en_dos_paginas_digitales_va_a_revision(politica):
    imagenes = [
        {"pagina": p, "fraccion_imagen": 0.34, "caracteres": 500, "pagina_completa": False}
        for p in (3, 4)
    ]
    decision, motivos, _ = decidir(senales(imagenes_digitales=imagenes), politica)
    assert decision == "revision_humana"
    assert "[3, 4]" in motivos[0]
    # Una sola página, o una página entera escaneada con capa de texto, no bloquea.
    assert decidir(senales(imagenes_digitales=imagenes[:1]), politica)[0] == "aceptado"


def test_cuasi_duplicado_va_a_revision_sin_fusionar(politica):
    decision, motivos, _ = decidir(senales(), politica, cuasi_duplicado_de="abc123")
    assert decision == "revision_humana"
    assert "cuasi-duplicado de abc123" in motivos[0]


def test_documento_sin_texto_se_rechaza(politica):
    decision, motivos, _ = decidir(senales(caracteres=12), politica)
    assert decision == "rechazado"
    assert "sin texto útil" in motivos[0]


def test_ocr_fallido_va_a_revision(politica):
    decision, motivos, _ = decidir(senales(ocr_paginas_fallidas=1), politica)
    assert decision == "revision_humana" and "OCR fallido" in motivos[0]


def test_senales_desde_capas(tmp_path):
    doc_id = "a" * 64
    bronce = tmp_path / "bronze"
    bronce.mkdir()
    texto = (
        "DECRETO 1766 DE 2013\n(16 de agosto de 2013)\nARTÍCULO 1. Objeto.\n\f\nARTÍCULO 2. Fin."
    )
    (bronce / (doc_id + ".txt")).write_text(texto, encoding="utf-8")
    (bronce / (doc_id + ".extraction.json")).write_text(
        json.dumps({"ocr_pages": [2], "ocr_confidence": {"2": 91.5}, "chars_per_page": [60, 15]}),
        encoding="utf-8",
    )
    (tmp_path / "gold").mkdir()
    (tmp_path / "gold" / (doc_id + ".jsonl")).write_text(
        json.dumps({"metadata": {"clean_start": 0, "clean_end": 120}}) + "\n", encoding="utf-8"
    )
    s = senales_documento(tmp_path, doc_id, None, "normativa")
    assert s["paginas"] == 2 and s["paginas_ocr"] == 1
    assert s["ocr_confianza_media"] == 91.5
    assert s["identidad"]["pasa"]
    assert s["chunks"] == 1 and s["chunks_cortos"] == 1
