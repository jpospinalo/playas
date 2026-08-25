#!/usr/bin/env bash
# Enciende los servicios ECS (app y frontend) poniendo desired_count en 1.
# Postgres arranca desde el volumen EFS existente, así que los datos previos
# se conservan.
#
# Uso:
#   ./scripts/start.sh
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
# Coincide con local.name_prefix = var.project + "-" + var.environment (defaults)
CLUSTER="rag-playas-prod"

bold='\033[1m'
green='\033[0;32m'
reset='\033[0m'

log() { echo -e "${bold}▶ $*${reset}"; }
ok()  { echo -e "${green}✓ $*${reset}"; }

log "Encendiendo servicio ${CLUSTER}-app..."
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${CLUSTER}-app" \
  --desired-count 1 \
  --region "${REGION}" \
  --query "service.desiredCount" --output text

log "Encendiendo servicio ${CLUSTER}-frontend..."
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${CLUSTER}-frontend" \
  --desired-count 1 \
  --region "${REGION}" \
  --query "service.desiredCount" --output text

log "Esperando a que ${CLUSTER}-app esté estable (Postgres healthcheck + arranque del backend)..."
aws ecs wait services-stable \
  --cluster "${CLUSTER}" \
  --services "${CLUSTER}-app" \
  --region "${REGION}"

ok "Servicios encendidos y estables."
