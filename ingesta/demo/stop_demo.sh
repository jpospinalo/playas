#!/usr/bin/env bash
# Detiene (stop, NO terminate) las instancias del demo. Los datos se conservan en EBS.
source "$(dirname "$0")/comun.sh"
echo "Deteniendo el demo de ATLAS..."
comprobar_cuenta
aws ec2 stop-instances --instance-ids "$ID_WORKER" "$ID_OLLAMA" >/dev/null
aws ec2 wait instance-stopped --instance-ids "$ID_WORKER" "$ID_OLLAMA"
ok "Worker y Ollama detenidos (siguen facturando solo sus discos EBS)."
