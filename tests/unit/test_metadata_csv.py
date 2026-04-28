# tests/unit/test_metadata_csv.py

from __future__ import annotations

from ingest.metadata_csv import parse_metadata_csv_content


def test_parse_metadata_csv_content_strips_bom_for_archivo_column() -> None:
    """CSV exportado con UTF-8 BOM: sin quitar BOM, DictReader no expone 'Archivo'."""
    raw = "\ufeffArchivo;Nº;Corporación\nfoo.pdf;1;X\n"
    parsed = parse_metadata_csv_content(raw)
    assert parsed["foo.pdf"]["Archivo"] == "foo.pdf"
    assert parsed["foo.pdf"]["Nº"] == "1"
