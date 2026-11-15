#!/usr/bin/env bash
# Instala el worker del intake en una EC2 Ubuntu 24.04 con el perfil LabInstanceProfile.
# Se ejecuta EN la EC2 (como ubuntu con sudo), con el repositorio ya copiado en
# /opt/atlas/playas (git bundle o clon). No copia ni pide claves: S3 se usa con el
# perfil de instancia. Idempotente.
#
#   sudo ./instalar_worker.sh <bucket> <url-ollama> [coleccion]
set -euo pipefail

BUCKET="${1:?bucket S3 del buzón}"
OLLAMA="${2:?URL de Ollama, p. ej. http://172.31.35.105:11434}"
COLECCION="${3:-atlas_demo_base}"
RAIZ=/opt/atlas/playas
DATOS=/var/lib/atlas

if [[ ! -d "$RAIZ/ingesta" ]]; then
  echo "Falta el repositorio en $RAIZ" >&2
  exit 2
fi

apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tesseract-ocr tesseract-ocr-spa curl >/dev/null
id atlas >/dev/null 2>&1 || useradd --system --home "$DATOS" --shell /usr/sbin/nologin atlas
mkdir -p "$DATOS"/{chroma,estado,capas,cache,raw,uv,locks}
if [[ ! -x /usr/local/bin/uv ]]; then
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh >/dev/null
fi
cd "$RAIZ/ingesta"
UV_CACHE_DIR="$DATOS/uv" /usr/local/bin/uv sync -q --extra offline --extra aws
cd "$RAIZ/rag"
UV_CACHE_DIR="$DATOS/uv" /usr/local/bin/uv sync -q --group dev
chown -R atlas:atlas "$DATOS"

cat > /etc/atlas-intake.env <<EOF
# Configuración del worker (sin secretos: S3 usa el perfil de instancia).
AWS_DEFAULT_REGION=us-east-1
ATLAS_BUCKET=$BUCKET
ATLAS_COLECCION=$COLECCION
ATLAS_OLLAMA=$OLLAMA
ATLAS_INTERVALO=15
ATLAS_CHROMA_LOCK_DIR=$DATOS/locks
EOF

install -m 0644 "$RAIZ/ingesta/demo/worker/atlas-chroma.service" /etc/systemd/system/
install -m 0644 "$RAIZ/ingesta/demo/worker/atlas-intake.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now atlas-chroma.service atlas-intake.service
sleep 5
systemctl --no-pager --lines=0 status atlas-chroma.service atlas-intake.service || true
echo "Worker instalado. Logs: journalctl -u atlas-intake -f"
