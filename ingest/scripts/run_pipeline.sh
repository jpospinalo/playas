#!/usr/bin/env bash
set -euo pipefail

echo "=== 1/3 Conversión PDF → Markdown ==="
uv run python -m ingest.pdf_to_md

echo "=== 2/3 Ingesta y normalización ==="
uv run python -m ingest.loaders

echo "=== 3/3 Chunking + Enriquecimiento con Gemini ==="
uv run python -m ingest.splitter_and_enrich
