"""Script para consultar la cantidad de documentos en la colección de Chroma.

Estrictamente de lectura: usa ``get_collection()``, que falla con claridad si
la colección no existe, en vez de ``get_or_create_collection()``, que la
crearía en silencio y reportaría cero documentos de una colección que el
script mismo acaba de inventar.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv

# ── Configuración ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION_NAME", "rag_playas_docs")


def count_collection(client: Any, collection_name: str) -> int:
    """Cantidad de documentos en ``collection_name``.

    Nunca crea la colección: si no existe, ``get_collection()`` lanza y esa
    excepción se propaga a quien llama.
    """
    collection = client.get_collection(name=collection_name)
    return int(collection.count())


def main() -> int:
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    try:
        count = count_collection(client, CHROMA_COLLECTION)
    except Exception as exc:
        print(
            f"No fue posible leer la colección '{CHROMA_COLLECTION}' en {CHROMA_HOST}:{CHROMA_PORT}: {exc}"
        )
        return 1
    print(f"Cantidad de documentos en '{CHROMA_COLLECTION}': {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
