#!/usr/bin/env bash
# Hace una pregunta con el buscador real de la aplicación (BM25 + vectores) sobre la
# colección del demo y muestra los 4 fragmentos con su cita. Sin LLM.
source "$(dirname "$0")/comun.sh"
PREGUNTA="${1:?Uso: ./preguntar.sh \"pregunta\"}"
comprobar_cuenta >/dev/null
PREGUNTA_B64=$(printf '%s' "$PREGUNTA" | base64 | tr -d '\n')
en_worker "cd /opt/atlas/playas/rag && set -a && . /etc/atlas-intake.env && set +a && \
  CHROMA_HOST=127.0.0.1 CHROMA_PORT=8000 CHROMA_COLLECTION=\$ATLAS_COLECCION OLLAMA_BASE_URL=\$ATLAS_OLLAMA \
  PYTHONPATH=backend .venv/bin/python /opt/atlas/playas/ingesta/benchmarks/demo_aws/pregunta_rag.py \
  \"\$(echo $PREGUNTA_B64 | base64 -d)\" 2>/dev/null"
