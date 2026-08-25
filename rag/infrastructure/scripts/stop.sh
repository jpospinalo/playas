#!/usr/bin/env bash
# Apaga los servicios ECS (app y frontend) poniendo desired_count en 0.
# Detiene la facturación de cómputo Fargate mientras el sistema no está en uso.
# Los datos de Postgres persisten en EFS y no se pierden.
#
# Uso:
#   ./scripts/stop.sh
set -euo pipefail

REGION="${AWS_DEFAULT_REGION:-us-east-1}"
# Coincide con local.name_prefix = var.project + "-" + var.environment (defaults)
CLUSTER="rag-playas-prod"

bold='\033[1m'
green='\033[0;32m'
reset='\033[0m'

log() { echo -e "${bold}▶ $*${reset}"; }
ok()  { echo -e "${green}✓ $*${reset}"; }

log "Apagando servicio ${CLUSTER}-app..."
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${CLUSTER}-app" \
  --desired-count 0 \
  --region "${REGION}" \
  --query "service.desiredCount" --output text

log "Apagando servicio ${CLUSTER}-frontend..."
aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${CLUSTER}-frontend" \
  --desired-count 0 \
  --region "${REGION}" \
  --query "service.desiredCount" --output text

ok "Servicios apagados. El ALB sigue activo pero no se cobra cómputo Fargate."
