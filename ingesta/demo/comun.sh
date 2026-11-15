#!/usr/bin/env bash
# Funciones compartidas por los scripts del demo. Se carga con `source`.
set -euo pipefail
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$AQUI/demo.env" ]]; then source "$AQUI/demo.env"; else source "$AQUI/demo.env.example"; fi
export AWS_DEFAULT_REGION="$REGION"

ok()    { printf '  \033[32m✔\033[0m %s\n' "$*"; }
aviso() { printf '  \033[33m!\033[0m %s\n' "$*"; }
error() { printf '  \033[31m✘\033[0m %s\n' "$*" >&2; }

comprobar_cuenta() {
  local cuenta
  if ! cuenta=$(aws sts get-caller-identity --query Account --output text 2>/dev/null); then
    error "Credenciales AWS caducadas o ausentes. Reinicia el laboratorio y actualiza ~/.aws/credentials."
    exit 10
  fi
  if [[ "$cuenta" != "$CUENTA_ESPERADA" ]]; then
    error "Cuenta $cuenta inesperada (se esperaba $CUENTA_ESPERADA). No se hace nada."
    exit 11
  fi
  ok "Cuenta AWS $cuenta"
}

estado_instancia() { aws ec2 describe-instances --instance-ids "$1" --query 'Reservations[0].Instances[0].State.Name' --output text; }
ip_publica()       { aws ec2 describe-instances --instance-ids "$1" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text; }

en_worker() {
  ssh -i "$CLAVE_SSH" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -o LogLevel=ERROR "ubuntu@$(ip_publica "$ID_WORKER")" "$@"
}
