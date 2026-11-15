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
BUZON="$DATOS/buzon_base"
rm -rf "$BUZON" && mkdir -p "$BUZON"
"$RAIZ/ingesta/.venv/bin/python" - "$@" <<'EOF'
import hashlib, json, shutil, sys
from pathlib import Path
raiz = Path("/opt/atlas/playas")
mapa = json.loads((raiz / "ingesta/benchmarks/demo_aws/sufijos_raw.json").read_text())
quiero, vistos = set(sys.argv[1:]), set()
for p in sorted((raiz / "data/documents/raw").rglob("*.pdf")):
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    if mapa.get(h) in quiero and h not in vistos:
        vistos.add(h)
        shutil.copy2(p, Path("/var/lib/atlas/buzon_base") / p.name)
        (Path("/var/lib/atlas/buzon_base") / (p.name + ".meta.json")).write_text(
            json.dumps({"categoria": p.parent.name}))
print(len(vistos), "documentos en el buzón de la base")
EOF
chown -R atlas:atlas "$BUZON"
systemctl stop atlas-intake
cd "$RAIZ/ingesta"
sudo -u atlas --preserve-env=ATLAS_CHROMA_LOCK_DIR,AWS_DEFAULT_REGION .venv/bin/python -X utf8 -m ingest.offline intake \
  --inbox "$BUZON" --once --collection "$ATLAS_COLECCION" --port 8000 \
  --state "$DATOS/estado" --layers-root "$DATOS/capas" --cache "$DATOS/cache" --raw-root "$DATOS/raw" \
  --ollama "$ATLAS_OLLAMA" --allow-remote-ollama | tail -n +1 > "$DATOS/base.log" || true
ls "$DATOS/estado/intake"/*.json | xargs -n1 basename | sed 's/\.json$//' > "$DATOS/base_hashes.txt"
chown atlas:atlas "$DATOS/base_hashes.txt"
echo "Base: $(wc -l < "$DATOS/base_hashes.txt") documentos registrados en base_hashes.txt"
systemctl start atlas-intake
