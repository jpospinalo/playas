#!/usr/bin/env bash
# Exporta la base de datos PostgreSQL (sidecar del servicio ECS "app") a un
# archivo .dump local (formato custom de pg_dump).
#
# ECS Fargate no permite `docker cp` ni montar el volumen EFS directamente, y
# `aws ecs execute-command` trunca cualquier salida grande (~10-13 KB), así
# que no es viable volcar el dump por ese canal. En su lugar:
#   1. Corre `pg_dump -Fc` dentro del contenedor "postgres" (task RUNNING del
#      servicio "${CLUSTER}-app"), escribiendo a un archivo temporal local
#      del contenedor.
#   2. Sube ese archivo a un bucket S3 vía `curl -T` con una URL prefirmada
#      (PUT, SigV4) generada con boto3 — el contenedor tiene salida a
#      internet (subnet pública).
#   3. Descarga el archivo a esta máquina con `aws s3 cp`.
#   4. Por defecto deja la copia en el bucket S3; usar --delete-remote para
#      borrarla tras la descarga.
#
# Uso:
#   ./scripts/export_postgres.sh --bucket <nombre-bucket> [opciones]
#
# Opciones:
#   --bucket <nombre>       Bucket S3 usado como puente de transferencia (obligatorio)
#   --cluster <nombre>      Cluster ECS (default: rag-playas-prod)
#   --region <region>       Región AWS (default: $AWS_DEFAULT_REGION o us-east-1)
#   --db-user <usuario>     Usuario de PostgreSQL (default: atlas)
#   --db-name <nombre>      Base de datos a exportar (default: atlas)
#   --output-dir <ruta>     Carpeta local destino (default: data/backups en la raíz del repo)
#   --delete-remote         Borra la copia del bucket S3 tras descargarla
#
# Requisitos:
#   - Credenciales AWS exportadas en el entorno
#   - Session Manager Plugin instalado (requerido por ECS Exec)
#   - `uv` con el workspace de rag/ sincronizado (usa su boto3 para prefirmar la URL)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RAG_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PROJECT_ROOT="$(cd "${RAG_DIR}/.." && pwd)"

CLUSTER="rag-playas-prod"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
DB_USER="atlas"
DB_NAME="atlas"
BUCKET=""
OUTPUT_DIR="${PROJECT_ROOT}/data/backups"
DELETE_REMOTE=false

# ── Colores ───────────────────────────────────────────────────────────────────
bold='\033[1m'
green='\033[0;32m'
yellow='\033[1;33m'
reset='\033[0m'

log()  { echo -e "${bold}▶ $*${reset}"; }
ok()   { echo -e "${green}✓ $*${reset}"; }
warn() { echo -e "${yellow}⚠ $*${reset}"; }
err()  { echo -e "✗ $*" >&2; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bucket)        BUCKET="$2"; shift 2 ;;
    --cluster)       CLUSTER="$2"; shift 2 ;;
    --region)        REGION="$2"; shift 2 ;;
    --db-user)       DB_USER="$2"; shift 2 ;;
    --db-name)       DB_NAME="$2"; shift 2 ;;
    --output-dir)    OUTPUT_DIR="$2"; shift 2 ;;
    --delete-remote) DELETE_REMOTE=true; shift ;;
    -h|--help)       grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) err "Opción desconocida: $1"; exit 1 ;;
  esac
done

if [[ -z "${BUCKET}" ]]; then
  err "Falta --bucket <nombre-bucket-s3>"
  exit 1
fi

# ── 1. Localizar la tarea RUNNING del servicio app ────────────────────────────
log "Buscando tarea activa del servicio ${CLUSTER}-app..."
TASK_ARN=$(aws ecs list-tasks \
  --cluster "${CLUSTER}" \
  --service-name "${CLUSTER}-app" \
  --desired-status RUNNING \
  --query 'taskArns[0]' --output text --region "${REGION}")

if [[ -z "${TASK_ARN}" || "${TASK_ARN}" == "None" ]]; then
  err "No se encontró una tarea RUNNING del servicio ${CLUSTER}-app"
  exit 1
fi
ok "Tarea: ${TASK_ARN##*/}"

# ── 2. Generar URL prefirmada (PUT) para subir el dump ────────────────────────
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
KEY="${DB_NAME}-backup-${TIMESTAMP}.dump"

log "Generando URL prefirmada para s3://${BUCKET}/${KEY}..."
PRESIGN_URL=$(cd "${RAG_DIR}" && uv run python3 -c "
import boto3
from botocore.config import Config
s3 = boto3.client('s3', region_name='${REGION}', config=Config(signature_version='s3v4'))
print(s3.generate_presigned_url('put_object', Params={'Bucket': '${BUCKET}', 'Key': '${KEY}'}, ExpiresIn=1800))
")

# ── 3. pg_dump dentro del contenedor + subida vía curl (con fallback a wget) ──
log "Ejecutando pg_dump en el contenedor postgres y subiendo a S3..."
REMOTE_CMD="pg_dump -U ${DB_USER} -Fc ${DB_NAME} > /tmp/${KEY} && \
ls -la /tmp/${KEY} && \
( command -v curl >/dev/null 2>&1 || apk add --no-cache curl >/tmp/apk_out.txt 2>&1 || true ) && \
if command -v curl >/dev/null 2>&1; then \
  curl -sS -X PUT -T /tmp/${KEY} \"${PRESIGN_URL}\" -o /tmp/upload_out.txt -w \"HTTP_STATUS:%{http_code}\n\"; \
else \
  echo \"curl no disponible, probando wget...\"; \
  wget -q --method=PUT --body-file=/tmp/${KEY} \"${PRESIGN_URL}\" -O /tmp/upload_out.txt 2>/tmp/wget_err.txt && echo \"HTTP_STATUS:200\" || (cat /tmp/wget_err.txt; echo \"HTTP_STATUS:000\"); \
fi && \
cat /tmp/upload_out.txt 2>/dev/null; \
rm -f /tmp/${KEY} /tmp/upload_out.txt /tmp/apk_out.txt /tmp/wget_err.txt"

EXEC_OUTPUT=$(aws ecs execute-command \
  --cluster "${CLUSTER}" \
  --task "${TASK_ARN}" \
  --container postgres \
  --interactive \
  --region "${REGION}" \
  --command "sh -c '${REMOTE_CMD}'" 2>&1)

echo "${EXEC_OUTPUT}"

if ! grep -q "HTTP_STATUS:200" <<< "${EXEC_OUTPUT}"; then
  err "La subida a S3 no devolvió HTTP 200; revisar salida de ECS Exec arriba."
  exit 1
fi
ok "Dump subido a s3://${BUCKET}/${KEY}"

# ── 4. Descargar localmente ────────────────────────────────────────────────────
mkdir -p "${OUTPUT_DIR}"
LOCAL_FILE="${OUTPUT_DIR}/${KEY}"

log "Descargando a ${LOCAL_FILE}..."
aws s3 cp "s3://${BUCKET}/${KEY}" "${LOCAL_FILE}" --region "${REGION}"
ok "Descargado ($(du -h "${LOCAL_FILE}" | cut -f1))"

# ── 5. Limpieza opcional del objeto remoto ────────────────────────────────────
if [[ "${DELETE_REMOTE}" == "true" ]]; then
  log "Borrando copia remota s3://${BUCKET}/${KEY}..."
  aws s3 rm "s3://${BUCKET}/${KEY}" --region "${REGION}"
  ok "Copia remota borrada"
else
  warn "La copia en s3://${BUCKET}/${KEY} se conserva (usar --delete-remote para borrarla)"
fi

echo ""
ok "Export completo: ${LOCAL_FILE}"
echo -e "  Restaurar con: pg_restore -U ${DB_USER} -d ${DB_NAME} ${LOCAL_FILE}"
