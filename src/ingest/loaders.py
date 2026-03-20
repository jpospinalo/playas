# src/loaders.py

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

from .normalize import normalize_documents
from .utils import load_all_docs_from_dir, save_docs_jsonl_per_file

# ---------------------------------------------------------------------
# Configuración global
# ---------------------------------------------------------------------

warnings.filterwarnings("ignore", category=FutureWarning)

# Silenciar logs ruidosos de dependencias
logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("rapidocr").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)

load_dotenv()

# Rutas base
DATA_DIR = Path("data")
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"


# ---------------------------------------------------------------------
# Funciones principales
# ---------------------------------------------------------------------

def load_documents() -> List[Document]:
    """
    Carga y normaliza documentos para la capa SILVER.

    Flujo:
      1) Si ya existen archivos .jsonl en SILVER_DIR:
         - Carga todos los documentos desde allí (cache).
      2) Si no existen:
         - Carga los PDFs de BRONZE_DIR con Docling.
         - Normaliza texto y metadatos.
         - Guarda un .jsonl por archivo en SILVER_DIR.

    Devuelve:
        Lista de Document de LangChain.
    """
    # 1) Usar cache si ya hay .jsonl en SILVER_DIR
    # existing_jsonl = list(SILVER_DIR.glob("*.jsonl"))
    # if existing_jsonl:
    #     print(f"Cargando documentos desde .jsonl en {SILVER_DIR}")
    #     docs = load_all_docs_from_dir(SILVER_DIR)
    #     print("Total documentos (desde .jsonl):", len(docs))
    #     return docs

    # 2) No hay cache: procesar PDFs con Docling
    file_paths = sorted(str(p) for p in BRONZE_DIR.glob("*.pdf"))
    if not file_paths:
        print(f"No se encontraron PDFs en {BRONZE_DIR}")
        return []

    loader = DoclingLoader(
        file_path=file_paths,
        export_type=ExportType.MARKDOWN,  # 1 Document por archivo
    )
    raw_docs = loader.load()
    print("Documentos cargados con Docling (raw):", len(raw_docs))

    # Normalizar texto + metadata
    docs = normalize_documents(raw_docs)
    print("Documentos normalizados:", len(docs))

    # Guardar un .jsonl por archivo (en silver)
    save_docs_jsonl_per_file(docs, SILVER_DIR)
    print(f"Documentos normalizados guardados en: {SILVER_DIR}")

    return docs


def main() -> None:
    documents = load_documents()
    if not documents:
        print("No hay documentos.")
        return

    print("Documentos cargados y listos...")
    print("Total documentos:", len(documents))

    # Ejemplo de inspección básica
    ejemplo_idx = 1 if len(documents) > 1 else 0
    print("Ejemplo metadata:", documents[ejemplo_idx].metadata)
    print("Ejemplo texto:\n", documents[ejemplo_idx].page_content)


if __name__ == "__main__":
    main()
