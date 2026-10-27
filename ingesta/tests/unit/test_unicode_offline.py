from ingest.metadata_csv import get_metadata_for_file, parse_metadata_csv_content
from ingest.normalize import normalize_text


def test_nfc_and_controls_including_nul():
    assert normalize_text("Cafe\u0301\x00\x01\u200b\tlegal\ntexto") == "Café\tlegal\ntexto"


def test_csv_filename_matching_uses_nfc(monkeypatch):
    table = parse_metadata_csv_content("Archivo;Corporación\nCafe\u0301.pdf;CORTE\x00\n")
    monkeypatch.setattr("ingest.metadata_csv.load_metadata_csv", lambda _: table)
    assert get_metadata_for_file("Café.md")["Corporación"] == "CORTE"
