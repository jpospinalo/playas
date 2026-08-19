#!/usr/bin/env bash
# Pipeline completo: ingesta (paquete `ingesta/`) + indexación y API (paquete `rag/`).
#
# `ingesta/` y `rag/` son workspaces uv independientes con su propio venv — el
# paso de indexación y el de la API deben correr con el venv de `rag/`, no con
# el de `ingesta/`. Este script se ubica en `ingesta/scripts/`, así que resuelve
# `rag/` como el directorio hermano `../rag` y ejecuta cada bloque de pasos con
# `uv run` desde el directorio correspondiente, sin importar desde dónde se invoque.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INGESTA_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RAG_DIR="$(cd "${INGESTA_DIR}/../rag" && pwd)"

echo "=== 1/5 Conversión PDF → Markdown ==="
(cd "${INGESTA_DIR}" && uv run python -m ingest.pdf_to_md)

echo "=== 2/5 Ingesta y normalización ==="
(cd "${INGESTA_DIR}" && uv run python -m ingest.loaders)

echo "=== 3/5 Chunking + Enriquecimiento con Gemini ==="
(cd "${INGESTA_DIR}" && uv run python -m ingest.splitter_and_enrich)

echo "=== 4/5 Indexación en ChromaDB ==="
(cd "${RAG_DIR}" && uv run python -m rag.core.vectorstore)

echo "=== 5/5 Lanzando API FastAPI ==="
(cd "${RAG_DIR}" && uv run uvicorn rag.api.main:app --reload --port 8080)
