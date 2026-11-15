#!/usr/bin/env bash
# Estado del demo: instancias, servicios, colección y buzón S3.
source "$(dirname "$0")/comun.sh"
comprobar_cuenta
for par in "Ollama:$ID_OLLAMA" "Worker:$ID_WORKER"; do
  echo "  ${par%%:*}: $(estado_instancia "${par#*:}")"
done
if [[ "$(estado_instancia "$ID_WORKER")" == "running" ]]; then
  en_worker "systemctl is-active atlas-chroma atlas-intake | paste -sd' ' | sed 's/^/  Servicios (chroma, intake): /'
    /opt/atlas/playas/ingesta/.venv/bin/python -c \"
import chromadb
c = chromadb.HttpClient(host='127.0.0.1', port=8000)
for x in c.list_collections():
    if x.name.startswith('atlas_demo_') and not x.name.endswith('__staging'):
        print('  Colección', x.name, '=', x.count(), 'fragmentos')
\" 2>/dev/null || echo '  Chroma no responde'
    sudo journalctl -u atlas-intake -n 3 --no-pager -o cat 2>/dev/null | cut -c1-160 | sed 's/^/  log: /'"
fi
for p in inbox processed review rejected; do
  n=$(aws s3 ls "s3://$BUCKET/$p/" --recursive 2>/dev/null | grep -c -v '/$' || true)
  echo "  S3 $p/: $n objetos"
done
