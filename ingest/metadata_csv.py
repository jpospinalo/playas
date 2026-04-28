# ingest/metadata_csv.py

from __future__ import annotations

import csv
import io

from .config import RAW_PREFIX
from .s3_client import read_text

_csv_cache: dict[str, dict] | None = None


def parse_metadata_csv_content(content: str) -> dict[str, dict]:
    """Parsea metadata.csv (delimiter `;`). Quita BOM UTF-8 para que exista la columna `Archivo`."""
    content = content.lstrip("\ufeff")
    result: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    for row in reader:
        archivo = row.get("Archivo", "").strip()
        if archivo:
            result[archivo] = {k: v.strip() for k, v in row.items() if v.strip()}
    return result


def load_metadata_csv() -> dict[str, dict]:
    global _csv_cache
    if _csv_cache is not None:
        return _csv_cache

    _csv_cache = parse_metadata_csv_content(read_text(f"{RAW_PREFIX}metadata.csv"))
    return _csv_cache


def get_metadata_for_file(filename: str) -> dict | None:
    # Normalizar extensión .md → .pdf para hacer match con la columna Archivo del CSV
    lookup = filename
    if lookup.endswith(".md"):
        lookup = lookup[:-3] + ".pdf"
    return load_metadata_csv().get(lookup)
