#!/usr/bin/env bash
# Corre una migración SQL dentro del contenedor "postgres" de la tarea ECS del
# servicio app (mismo camino que usa deploy.sh para los usuarios semilla).
#
# Uso:
#   ./aplicar_migracion.sh verificar <carpeta>   # solo lista tablas y conteos (no cambia nada)
#   ./aplicar_migracion.sh up        <carpeta>   # crea las tablas nuevas (idempotente)
#   ./aplicar_migracion.sh down      <carpeta>   # borra SOLO las tablas nuevas (pide confirmar)
#
# Variables: CLUSTER (default rag-playas-prod), AWS_DEFAULT_REGION (default us-east-1).
# Antes de up o down: sacar copia con ../scripts/export_postgres.sh.
set -euo pipefail

ACCION="${1:?Uso: $0 verificar|up|down <carpeta-de-la-migracion>}"
CARPETA="${2:?Falta la carpeta de la migración}"
CLUSTER="${CLUSTER:-rag-playas-prod}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

case "${ACCION}" in
  verificar)
    SQL="SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1;
SELECT 'users', count(*) FROM users UNION ALL SELECT 'conversations', count(*) FROM conversations
UNION ALL SELECT 'messages', count(*) FROM messages UNION ALL SELECT 'feedback', count(*) FROM feedback
UNION ALL SELECT 'message_feedback', count(*) FROM message_feedback;" ;;
  up) SQL="$(cat "${CARPETA}/up.sql")" ;;
  down)
    echo "Esto BORRA las tablas del ejercicio (cuentas, calificaciones, validaciones, premios) y sus datos."
    read -r -p "Escriba BORRAR para seguir: " ok
    [[ "${ok}" == "BORRAR" ]] || { echo "Cancelado."; exit 1; }
    SQL="$(cat "${CARPETA}/down.sql")" ;;
  *) echo "Acción desconocida: ${ACCION}" >&2; exit 2 ;;
esac

TASK_ARN=$(aws ecs list-tasks --cluster "${CLUSTER}" --service-name "${CLUSTER}-app" \
  --desired-status RUNNING --query 'taskArns[0]' --output text --region "${REGION}")
if [[ -z "${TASK_ARN}" || "${TASK_ARN}" == "None" ]]; then
  echo "No hay una tarea RUNNING de ${CLUSTER}-app." >&2
  exit 1
fi

# base64 sin saltos de línea: portable entre macOS y Linux (igual que deploy.sh).
SQL_B64=$(printf '%s\n' "${SQL}" | base64 | tr -d '\n')
aws ecs execute-command \
  --cluster "${CLUSTER}" \
  --task "${TASK_ARN}" \
  --container postgres \
  --interactive \
  --region "${REGION}" \
  --command "sh -c 'echo ${SQL_B64} | base64 -d | psql -U atlas -d atlas -v ON_ERROR_STOP=1'"
