#!/usr/bin/env bash
# Vuelve a la línea base: retira de Chroma todo documento que no sea de la base,
# borra sus fichas (para poder volver a subirlos) y archiva sus objetos S3.
#   ./reset_demo.sh          conserva las cachés (OCR y embeddings): re-subir es rápido
#   ./reset_demo.sh --frio   borra también las cachés: el siguiente procesamiento es en frío
source "$(dirname "$0")/comun.sh"
comprobar_cuenta
MODO="${1:-}"
if [[ -n "$MODO" && "$MODO" != "--frio" ]]; then
  error "Única opción admitida: --frio"
  exit 2
fi
en_worker "sudo bash -s -- '$MODO'" <<'EOF'
set -euo pipefail
mkdir -p /var/lib/atlas/locks
exec 9>/var/lib/atlas/locks/operacion.lock
flock -x 9
trap 'systemctl start atlas-intake' EXIT
systemctl stop atlas-intake
cd /opt/atlas/playas/ingesta
set -a; source /etc/atlas-intake.env; set +a
sudo -u atlas --preserve-env=ATLAS_BUCKET,ATLAS_COLECCION,ATLAS_OLLAMA,ATLAS_CHROMA_LOCK_DIR,AWS_DEFAULT_REGION .venv/bin/python -X utf8 demo/worker/reset_demo.py "$1"
EOF
"$(dirname "$0")/status.sh"
