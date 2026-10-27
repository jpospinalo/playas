#!/usr/bin/env bash
# Entrada local: no carga .env, S3 ni módulos de enriquecimiento.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PYTHON="${OFFLINE_PYTHON:-${REPO_DIR}/.offline-venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  printf 'Falta Python offline: %s. Consulte docs/INGESTA.md.\n' "$PYTHON" >&2
  exit 1
fi
export GOOGLE_API_KEY='' GEMINI_API_KEY='' OPENAI_API_KEY='' OPENROUTER_API_KEY=''
export PYTHONPATH="${REPO_DIR}/ingesta"
cd "$REPO_DIR"
exec "$PYTHON" -m ingest.offline "$@"
