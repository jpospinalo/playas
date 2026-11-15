#!/usr/bin/env bash
# Inicia SOLO lo necesario para el demo (Ollama y worker), espera a que respondan
# y muestra las direcciones. No toca ninguna otra instancia del laboratorio.
source "$(dirname "$0")/comun.sh"
echo "Iniciando el demo de ATLAS..."
comprobar_cuenta
aws ec2 start-instances --instance-ids "$ID_OLLAMA" "$ID_WORKER" >/dev/null
echo "  Esperando a que las instancias estén encendidas (1-2 min)..."
aws ec2 wait instance-running --instance-ids "$ID_OLLAMA" "$ID_WORKER"
ok "Instancias encendidas"
IP_OLLAMA=$(ip_publica "$ID_OLLAMA")
for i in $(seq 1 60); do
  curl -sf -m 5 "http://$IP_OLLAMA:11434/api/tags" >/dev/null && break
  sleep 5
done
if curl -sf -m 5 "http://$IP_OLLAMA:11434/api/tags" | grep -q embeddinggemma; then ok "Ollama responde ($IP_OLLAMA)"; else error "Ollama no responde"; exit 20; fi
for i in $(seq 1 60); do
  en_worker 'systemctl is-active --quiet atlas-chroma atlas-intake && curl -sf http://127.0.0.1:8000/api/v2/heartbeat' >/dev/null 2>&1 && break
  sleep 5
done
if en_worker 'systemctl is-active --quiet atlas-intake'; then ok "Worker y Chroma activos ($(ip_publica "$ID_WORKER"))"; else error "El worker no arrancó: ejecuta ./status.sh"; exit 21; fi
"$(dirname "$0")/status.sh"
echo
echo "Listo. Sube un PDF con:  ./upload.sh <archivo.pdf>"
