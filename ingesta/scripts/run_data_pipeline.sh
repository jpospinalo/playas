#!/usr/bin/env bash
# Solo procesamiento de datos; no indexa ni arranca la API.
# Las etapas se ejecutan desde el workspace de ingesta, independientemente del cwd.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}/.."

echo "=== 1/3 Conversión PDF → Markdown ==="
uv run python -m ingest.pdf_to_md

echo "=== 2/3 Ingesta y normalización ==="
uv run python -m ingest.loaders

echo "=== 3/3 Chunking + Enriquecimiento con el proveedor configurado ==="
uv run python -m ingest.splitter_and_enrich
