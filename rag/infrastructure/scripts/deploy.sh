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
# Coincide con local.name_prefix = var.project + "-" + var.environment (defaults)
NAME_PREFIX="rag-playas-prod"

# ── Colores ───────────────────────────────────────────────────────────────────
bold='\033[1m'
green='\033[0;32m'
yellow='\033[1;33m'
reset='\033[0m'

log()  { echo -e "${bold}▶ $*${reset}"; }
ok()   { echo -e "${green}✓ $*${reset}"; }
warn() { echo -e "${yellow}⚠ $*${reset}"; }

# ── Helpers de reconciliación ─────────────────────────────────────────────────
# Si un SG existe en AWS con distinto ID al del state (o sin estado), lo importa.
# Evita el error "already exists for VPC" en apply tras un destroy parcial.
reconcile_sg() {
  local resource="$1" sg_name="$2" vpc_id="$3"
  local aws_id state_id

  aws_id=$(aws ec2 describe-security-groups \
    --filters "Name=vpc-id,Values=${vpc_id}" "Name=group-name,Values=${sg_name}" \
    --query 'SecurityGroups[0].GroupId' --output text --region "${REGION}" 2>/dev/null)

  [[ -z "${aws_id}" || "${aws_id}" == "None" ]] && return 0

  state_id=$(terraform -chdir="${INFRA_DIR}" state show "${resource}" 2>/dev/null \
    | grep -E '^\s+id\s+=' | sed 's/.*"\(.*\)"/\1/')

  [[ "${state_id}" == "${aws_id}" ]] && return 0

  warn "SG '${sg_name}' existe en AWS (${aws_id}) pero el state tiene '${state_id:-<vacío>}' — reimportando..."
  terraform -chdir="${INFRA_DIR}" state rm "${resource}" 2>/dev/null || true
  terraform -chdir="${INFRA_DIR}" import "${resource}" "${aws_id}"
  ok "Importado ${resource} → ${aws_id}"
}

# ── 1. Terraform init ─────────────────────────────────────────────────────────
log "Inicializando Terraform en rag/infrastructure..."
terraform -chdir="${INFRA_DIR}" init -upgrade

# ── 1b. Reconciliar security groups con AWS ───────────────────────────────────
log "Verificando security groups existentes en AWS..."
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text --region "${REGION}")

reconcile_sg "aws_security_group.alb"      "${NAME_PREFIX}-alb"      "${VPC_ID}"
reconcile_sg "aws_security_group.app"      "${NAME_PREFIX}-app"      "${VPC_ID}"
reconcile_sg "aws_security_group.efs"      "${NAME_PREFIX}-efs"      "${VPC_ID}"
reconcile_sg "aws_security_group.frontend" "${NAME_PREFIX}-frontend" "${VPC_ID}"

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

# ── 5. Importar usuarios semilla a postgres ───────────────────────────────────
# El backend crea la tabla `users` al arrancar (init_db), así que hay que esperar
# a que el servicio esté estable antes de importar. El SQL usa ON CONFLICT DO
# NOTHING, por lo que re-ejecutarlo en cada deploy es inocuo.
SEED_SQL="${SCRIPT_DIR}/../../../data/seed_users.sql"

if [[ -f "${SEED_SQL}" ]]; then
  log "Esperando a que el servicio app esté estable para importar usuarios..."
  aws ecs wait services-stable \
    --cluster "${CLUSTER}" \
    --services "${CLUSTER}-app" \
    --region "${REGION}"

  TASK_ARN=$(aws ecs list-tasks \
    --cluster "${CLUSTER}" \
    --service-name "${CLUSTER}-app" \
    --desired-status RUNNING \
    --query 'taskArns[0]' --output text --region "${REGION}")

  if [[ -z "${TASK_ARN}" || "${TASK_ARN}" == "None" ]]; then
    warn "No se encontró una tarea RUNNING del servicio app; se omite la importación de usuarios."
  else
    log "Importando usuarios semilla vía ECS Exec..."
    # base64 evita problemas de escapado al pasar SQL multilínea por --command
    SEED_B64=$(base64 -w0 "${SEED_SQL}")

    # El agente de ECS Exec puede tardar unos segundos en estar listo tras el deploy
    for intento in 1 2 3 4 5; do
      if aws ecs execute-command \
        --cluster "${CLUSTER}" \
        --task "${TASK_ARN}" \
        --container postgres \
        --interactive \
        --region "${REGION}" \
        --command "sh -c 'echo ${SEED_B64} | base64 -d | psql -U atlas -d atlas -v ON_ERROR_STOP=1'"; then
        ok "Usuarios semilla importados"
        break
      fi
      if [[ "${intento}" == "5" ]]; then
        warn "No se pudo importar usuarios tras ${intento} intentos; importar manualmente con ECS Exec."
      else
        warn "ECS Exec aún no disponible (intento ${intento}); reintentando en 15s..."
        sleep 15
      fi
    done
  fi
else
  warn "No existe ${SEED_SQL}; se omite la importación de usuarios."
fi

# ── 6. Resumen ────────────────────────────────────────────────────────────────
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
