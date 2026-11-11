"""Llamadas digitales fieles, sin cambios de blancos ni contaminación numérica."""

import re

import pytest

from ingest.legal_metadata import extract_legal_metadata, identidad_normativa
from ingest.offline.chunks import make_chunks
from ingest.offline.extract import clean_pages, digital_text, read_document, source_span
from ingest.offline.layers import ARTICLE_RE

fitz = pytest.importorskip("fitz")


def crear_pdf(path, *, nota=True, llamada="44", elevada=True):
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 100), "2002", fontsize=12)
        if nota:
            x = 72 + fitz.get_text_length("2002", fontsize=12)
            page.insert_text((x, 96 if elevada else 100), llamada, fontsize=7)
        page.insert_text((72, 130), "Texto juridico de control sin cambios. " * 3, fontsize=8)
        page.insert_text((250, 160), "Otra columna, articulo 15 y 2024.", fontsize=11)
        baseline = page.get_text("text", sort=True)
        pdf.save(path)
    return baseline


def test_bronce_separa_llamada_del_anio_sin_insertar_espacios(tmp_path):
    path = tmp_path / "nota.pdf"
    baseline = crear_pdf(path)
    assert "200244" in baseline  # Reproduce el defecto de PyMuPDF.
    doc = read_document(path, tmp_path / "cache")
    assert not doc["ocr_pages"] and not doc["ocr_failed_pages"]
    assert doc["raw_pages"][0] == baseline.replace("200244", "2002⁴⁴")
    assert re.findall(r"\d+", doc["raw_pages"][0])[0] == "2002"


@pytest.mark.parametrize(
    "kwargs", [{"nota": False}, {"elevada": False}, {"llamada": "a"}, {"llamada": "4a"}]
)
def test_sin_superindices_numericos_es_identico_byte_a_byte(tmp_path, kwargs):
    path = tmp_path / "sin_notas.pdf"
    baseline = crear_pdf(path, **kwargs)
    doc = read_document(path, tmp_path / "cache")
    assert doc["original"].encode("utf-8") == baseline.encode("utf-8")


def test_no_sustituye_otra_aparicion_de_los_mismos_digitos():
    with fitz.open() as pdf:
        page = pdf.new_page()
        for y in (100, 140):
            page.insert_text((72, y), "2002", fontsize=12)
            x = 72 + fitz.get_text_length("2002", fontsize=12)
            page.insert_text((x, y - 4 if y == 140 else y), "44", fontsize=7)
        baseline = page.get_text("text", sort=True)
        assert digital_text(page, baseline).split() == ["200244", "2002⁴⁴"]


def test_ocr_no_pasa_por_sustitucion_digital(tmp_path, monkeypatch):
    from ingest.offline import extract

    path = tmp_path / "escaneado.pdf"
    with fitz.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    monkeypatch.setattr(extract, "_ocr", lambda *args: ("OCR 200244 sin cambios", False, 99))

    def prohibida(*args):
        pytest.fail("Una página OCR no debe pasar por digital_text")

    monkeypatch.setattr(extract, "digital_text", prohibida)
    doc = read_document(path, tmp_path / "cache")
    assert doc["raw_pages"] == ["OCR 200244 sin cambios"]
    assert doc["ocr_pages"] == [1]


def test_silver_gold_conservan_notas_busqueda_y_offsets():
    original = "CONSIDERACIONES\nEn 2002⁴⁴ se aplicó la Ley 99 de 1993.\nArtículo 15¹. Playas."
    cleaned = clean_pages([original])
    assert "2002" in cleaned["text"] and "2002⁴⁴" in cleaned["text"]
    for index, char in enumerate(cleaned["text"]):
        start, end = source_span(cleaned["offset_map"], index, index + 1)
        assert original[start:end] == char
    assert ARTICLE_RE.search("Artículo 15¹. Playas").group(1) == "15"
    metadata = extract_legal_metadata(original)
    chunks = make_chunks("doc", cleaned, metadata, "fallo.pdf", "jurisprudencia")
    assert any("2002⁴⁴" in c["raw_text"] for c in chunks)
    for chunk in chunks:
        meta = chunk["metadata"]
        assert original[meta["source_start"] : meta["source_end"]] == chunk["raw_text"]


@pytest.mark.parametrize("nota", ["", "⁴⁴"])
def test_metadatos_numero_anio_fecha_y_articulo_no_absorben_notas(nota):
    text = f"Ley 99{nota} de 1993{nota}\n12 de marzo de 2002{nota}.\nArtículo 15{nota}."
    fields = extract_legal_metadata(text)["campos"]
    assert fields["numero"]["valor"] == "99"
    assert fields["anio"]["valor"] == 1993
    assert fields["fecha_iso"]["valor"] == "2002-03-12"
    assert any(cita.startswith("Artículo 15") for cita in fields["normas_citadas"]["valor"])
    assert all("15" + nota not in cita for cita in fields["normas_citadas"]["valor"] if nota)
    for field in fields.values():
        quotes = field["evidencia"]
        quotes = quotes if isinstance(quotes, list) else [quotes]
        assert all(quote in text for quote in quotes if quote)
    normativa = f"LEY 99{nota} DE 1993{nota}\n12 de marzo de 1993{nota}"
    identity = identidad_normativa(normativa)
    assert identity["numero"] == "99" and identity["anio"] == 1993
    fields = extract_legal_metadata(normativa, "normativa")["campos"]
    assert fields["fecha_iso"]["valor"] == "1993-03-12"


def test_anio_con_letras_no_se_vuelve_fecha_valida():
    fields = extract_legal_metadata("12 de marzo de 2002abc")["campos"]
    assert fields["fecha_iso"]["valor"] is None
