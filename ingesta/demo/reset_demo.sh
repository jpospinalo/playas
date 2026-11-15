#!/usr/bin/env bash
# Vuelve a la línea base: retira de Chroma todo documento que no sea de la base,
# borra sus fichas (para poder volver a subirlos) y archiva sus objetos S3.
#   ./reset_demo.sh          conserva las cachés (OCR y embeddings): re-subir es rápido
#   ./reset_demo.sh --frio   borra también las cachés: el siguiente procesamiento es en frío
source "$(dirname "$0")/comun.sh"
comprobar_cuenta
MODO="${1:-}"
en_worker "sudo systemctl stop atlas-intake && cd /opt/atlas/playas/ingesta && sudo -u atlas env \$(cat /etc/atlas-intake.env | grep -v '^#' | xargs) .venv/bin/python -X utf8 demo/worker/reset_demo.py $MODO && sudo systemctl start atlas-intake"
"$(dirname "$0")/status.sh"
