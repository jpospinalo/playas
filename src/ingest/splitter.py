# src/ingest/splitter.py

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .utils import load_all_docs_from_dir, save_docs_jsonl_per_file

# ---------------------------------------------------------------------
# Configuración global
# ---------------------------------------------------------------------

warnings.filterwarnings("ignore", category=FutureWarning)

# Silenciar logs ruidosos de LangChain
logging.getLogger("langchain").setLevel(logging.WARNING)

# Rutas base
DATA_DIR = Path("data")
SILVER_DIR = DATA_DIR / "silver"              # documentos completos, limpios
SILVER_CHUNKED_DIR = SILVER_DIR / "chunked"   # documentos chunked

SILVER_DIR.mkdir(parents=True, exist_ok=True)
SILVER_CHUNKED_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------

def chunk_documents(
    docs: List[Document] | None = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> List[Document]:
    """
    Genera la capa de documentos fragmentados (chunked).

    Si se pasan *docs* directamente, se usan esos documentos.
    Si no, se cargan desde data/silver (.jsonl) y se guardan
    los chunks resultantes en data/silver/chunked.

    Devuelve la lista de chunks generados.
    """
    save_to_disk = docs is None

    if docs is None:
        existing_silver = list(SILVER_DIR.glob("*.jsonl"))
        if not existing_silver:
            print(f"No se encontraron .jsonl en {SILVER_DIR}. Genera primero la capa silver.")
            return []

        print(f"Cargando documentos desde {SILVER_DIR}...")
        docs = load_all_docs_from_dir(SILVER_DIR)
        print("Total documentos silver (completos):", len(docs))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )

    all_chunks: List[Document] = []

    for doc_idx, doc in enumerate(docs):
        base_meta = dict(doc.metadata) if doc.metadata else {}
        source = base_meta.get("source") or base_meta.get("file_path") or f"doc_{doc_idx}"

        base_doc = Document(page_content=doc.page_content, metadata=base_meta)
        chunks = splitter.split_documents([base_doc])

        for idx, chunk in enumerate(chunks):
            meta = dict(chunk.metadata) if chunk.metadata else {}

            meta["source"] = source
            meta.setdefault("title", base_meta.get("title", ""))
            meta.setdefault("author", base_meta.get("author", ""))

            meta["chunk_index"] = idx
            meta["chunk_id"] = f"{source}_chunk_{idx}"

            chunk.metadata = meta
            all_chunks.append(chunk)

        print(f"Documento {doc_idx + 1}/{len(docs)} -> {len(chunks)} chunks")

    print("Total de chunks generados:", len(all_chunks))

    if save_to_disk:
        save_docs_jsonl_per_file(all_chunks, SILVER_CHUNKED_DIR)
        print(f"Chunks guardados en: {SILVER_CHUNKED_DIR}")

    return all_chunks


def main() -> None:
    chunk_documents()


if __name__ == "__main__":
    main()
