# src/normalize.py

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any

from langchain_core.documents import Document


def normalize_text(text: str) -> str:
    """
    Limpieza mínima del texto:

    - Elimina espacios al inicio y al final de cada línea.
    - Descarta líneas vacías.
    - Elimina líneas de créditos/web conocidas
      (por ejemplo: elejandria.com, 'gracias por leer este libro').
    - Une las líneas restantes en una sola cadena separada por espacios.
    """
    lines = text.splitlines()
    cleaned_lines: List[str] = []

    for line in lines:
        l = line.strip()
        if not l:
            continue

        low = l.lower()

        # Líneas de créditos / web (reglas específicas)
        if "elejandria.com" in low:
            continue
        if "gracias por leer este libro" in low:
            continue

        # Aquí se pueden añadir reglas adicionales si se detecta más ruido
        cleaned_lines.append(l)

    return " ".join(cleaned_lines)


def normalize_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza la metadata partiendo del campo 'source'.

    Comportamiento:
    - Conserva solo el nombre de archivo en 'source'.
    - Intenta inferir 'title' y 'author' a partir del patrón
      'Titulo-Autor' en el nombre base del archivo.

    Ejemplo:
        source = 'El_cuervo-Allan_Poe_Edgar.pdf'
        -> title  = 'El cuervo'
        -> author = 'Allan Poe Edgar'
    """
    src = meta.get("source", "")
    file_path = Path(src)
    filename = file_path.name           # p.ej. "El_cuervo-Allan_Poe_Edgar.pdf"
    stem = file_path.stem               # p.ej. "El_cuervo-Allan_Poe_Edgar"

    parts = stem.split("-")
    title_raw = parts[0] if parts else stem
    author_raw = "-".join(parts[1:]) if len(parts) > 1 else ""

    title = title_raw.replace("_", " ").strip()
    author = author_raw.replace("_", " ").strip()

    return {
        "source": filename,
        "title": title or None,
        "author": author or None,
    }


def normalize_documents(docs: List[Document]) -> List[Document]:
    """
    Aplica normalize_text y normalize_metadata a una lista de Documents.

    Devuelve:
        Lista de Document normalizados (nuevo objeto por cada entrada).
    """
    normalized: List[Document] = []

    for d in docs:
        text = normalize_text(d.page_content)
        meta = normalize_metadata(d.metadata)
        normalized.append(Document(page_content=text, metadata=meta))

    return normalized
