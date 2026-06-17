# ingest/metadata_csv.py
"""Carga opcional de metadatos legales desde CSV.

Cada tipo de documento (``jurisprudencia``, ``normativa``) puede tener un archivo
``raw/<doc_type>/metadata.csv`` con metadatos enriquecidos (separador ``;``).
El CSV es opcional: si no existe, el pipeline funciona sin enriquecimiento.

El CSV de jurisprudencia típicamente incluye: Corporación, Radicado, Magistrado
ponente, Partes procesales, Tema principal, etc. Se indexa por la columna
``Archivo`` (nombre del PDF/MD original).

Uso::

    from ingest.metadata_csv import get_metadata_for_file
    meta = get_metadata_for_file("SM-01_sentencia.pdf", "jurisprudencia")
    # → {"Corporación": "Tribunal Administrativo del Magdalena", ...}
"""

from __future__ import annotations

import csv
import io

from .config import layer_prefix
from .s3_client import key_exists, read_text

# Caché de CSV por doc_type (cada tipo tiene su propio metadata.csv opcional).
_csv_cache: dict[str, dict[str, dict]] = {}


def parse_metadata_csv_content(content: str) -> dict[str, dict]:
    """Parsea metadata.csv (delimiter `;`). Quita BOM UTF-8 para que exista la columna `Archivo`."""
    content = content.lstrip("﻿")
    result: dict[str, dict] = {}
    reader = csv.DictReader(io.StringIO(content), delimiter=";")
    for row in reader:
        archivo = row.get("Archivo", "").strip()
        if archivo:
            result[archivo] = {k: v.strip() for k, v in row.items() if v.strip()}
    return result


def load_metadata_csv(doc_type: str = "jurisprudencia") -> dict[str, dict]:
    """Carga el metadata.csv de un tipo de documento desde raw/<doc_type>/metadata.csv.

    El CSV es OPCIONAL: si no existe (caso típico de normativa al arrancar), se
    devuelve un diccionario vacío sin error. El resultado se cachea por doc_type.
    """
    if doc_type in _csv_cache:
        return _csv_cache[doc_type]

    key = f"{layer_prefix('raw', doc_type)}metadata.csv"
    if not key_exists(key):
        _csv_cache[doc_type] = {}
        return _csv_cache[doc_type]

    _csv_cache[doc_type] = parse_metadata_csv_content(read_text(key))
    return _csv_cache[doc_type]


def get_metadata_for_file(filename: str, doc_type: str = "jurisprudencia") -> dict | None:
    """Devuelve la fila de metadatos del CSV que matchea *filename*, o None.

    Prueba varias variantes de extensión porque la columna `Archivo` del CSV de
    jurisprudencia usa `.pdf`, mientras que la normativa puede entrar como `.md`.
    """
    table = load_metadata_csv(doc_type)
    if not table:
        return None

    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    for candidate in (filename, f"{stem}.pdf", f"{stem}.md", stem):
        if candidate in table:
            return table[candidate]
    return None
