#!/usr/bin/env bash
# Despliega la aplicación RAG en ECS Fargate.
# Inicializa Terraform, aplica la infraestructura, construye las imágenes
# y fuerza el redespliegue de los servicios ECS.
#
# Uso:
#   ./scripts/deploy.sh [--auto-approve]
#
# Requisitos:
#   - rag/infrastructure/terraform.tfvars con todas las variables configuradas
#   - Credenciales AWS exportadas en el entorno
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/.."
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# ── Colores ───────────────────────────────────────────────────────────────────
bold='\033[1m'
green='\033[0;32m'
reset='\033[0m'

log() { echo -e "${bold}▶ $*${reset}"; }
ok()  { echo -e "${green}✓ $*${reset}"; }

# ── 1. Terraform init ─────────────────────────────────────────────────────────
log "Inicializando Terraform en rag/infrastructure..."
terraform -chdir="${INFRA_DIR}" init -upgrade

# ── 2. Terraform apply ────────────────────────────────────────────────────────
log "Aplicando infraestructura ECS..."

APPLY_ARGS=()
if [[ "${1:-}" == "--auto-approve" ]]; then
  APPLY_ARGS+=("-auto-approve")
fi

terraform -chdir="${INFRA_DIR}" apply "${APPLY_ARGS[@]}"

# ── 3. Construir y subir imágenes a ECR ───────────────────────────────────────
log "Construyendo y subiendo imágenes a ECR..."
"${SCRIPT_DIR}/push_images.sh"

# ── 4. Forzar redespliegue en ECS ─────────────────────────────────────────────
log "Forzando redespliegue de servicios ECS..."
CLUSTER=$(terraform -chdir="${INFRA_DIR}" output -raw ecs_cluster_name)

aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${CLUSTER}-app" \
  --force-new-deployment \
  --region "${REGION}" \
  --query "service.serviceName" --output text

aws ecs update-service \
  --cluster "${CLUSTER}" \
  --service "${CLUSTER}-frontend" \
  --force-new-deployment \
  --region "${REGION}" \
  --query "service.serviceName" --output text

ok "Servicios ECS actualizados"

# ── 5. Resumen ────────────────────────────────────────────────────────────────
ALB_URL=$(terraform -chdir="${INFRA_DIR}" output -raw alb_url)

echo ""
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
echo -e "${bold}Despliegue completado${reset}"
echo ""
echo -e "  URL: ${ALB_URL}"
echo ""
echo -e "  Logs en tiempo real:"
echo -e "    aws logs tail /ecs/${CLUSTER}-app      --region ${REGION} --follow"
echo -e "    aws logs tail /ecs/${CLUSTER}-frontend --region ${REGION} --follow"
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
