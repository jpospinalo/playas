#!/usr/bin/env bash
# Construye la colección base del demo en el worker (servicio parado) y registra sus
# hashes en /var/lib/atlas/base_hashes.txt (reset_demo.py vuelve a esta línea base).
#
#   sudo ./construir_base.sh d512 19a7 9523 ...    (sufijos de benchmarks/demo_aws/sufijos_raw.json)
#
# Usa el mismo intake que el worker, con un buzón LOCAL y archivo lateral de categoría
# (la carpeta de origen en raw). Con embeddings reales tarda ~0,7 fragmentos/s.
set -euo pipefail
RAIZ=/opt/atlas/playas
DATOS=/var/lib/atlas
set -a; source /etc/atlas-intake.env; set +a
mkdir -p "$DATOS/locks"
exec 9>"$DATOS/locks/operacion.lock"
flock -x 9
trap 'systemctl start atlas-intake' EXIT
systemctl stop atlas-intake
cd "$RAIZ/ingesta"
BUZON="$DATOS/buzon_base"
rm -rf "$BUZON" && mkdir -p "$BUZON"
"$RAIZ/ingesta/.venv/bin/python" - "$@" <<'EOF'
import sys
from pathlib import Path
from demo.worker.base_demo import preparar_base
raiz = Path("/opt/atlas/playas")
hashes = preparar_base(raiz, Path("/var/lib/atlas/buzon_base"), sys.argv[1:])
Path("/var/lib/atlas/base_solicitada.txt").write_text("\n".join(hashes), encoding="utf-8")
print(len(hashes), "documentos en el buzón de la base")
EOF
chown -R atlas:atlas "$BUZON"
sudo -u atlas --preserve-env=ATLAS_CHROMA_LOCK_DIR,AWS_DEFAULT_REGION .venv/bin/python -X utf8 -m ingest.offline intake \
  --inbox "$BUZON" --once --collection "$ATLAS_COLECCION" --port 8000 \
  --state "$DATOS/estado" --layers-root "$DATOS/capas" --cache "$DATOS/cache" --raw-root "$DATOS/raw" \
  --ollama "$ATLAS_OLLAMA" --allow-remote-ollama > "$DATOS/base.log"
"$RAIZ/ingesta/.venv/bin/python" - <<'EOF'
from pathlib import Path
from demo.worker.base_demo import registrar_base
datos = Path("/var/lib/atlas")
registrar_base(datos / "estado", (datos / "base_solicitada.txt").read_text().split(), datos / "base_hashes.txt")
EOF
chown atlas:atlas "$DATOS/base_hashes.txt"
echo "Base: $(wc -l < "$DATOS/base_hashes.txt") documentos registrados en base_hashes.txt"
