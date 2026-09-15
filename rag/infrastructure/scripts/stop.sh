#!/usr/bin/env bash
# Apaga de forma segura y verificable el cómputo encendido por start.sh:
# primero ECS app/frontend (confirmando explícitamente desired=running=
# pending=0), y solo entonces las EC2 de ChromaDB/Ollama.
#
# Solo requiere AWS CLI 2.x (sin curl, sin ALB en ningún punto: apagar debe
# funcionar aunque el ALB esté degradado) y sin Terraform — todo se
# descubre por tag/nombre contra AWS. Idempotente y sin operaciones
# destructivas (nunca termina instancias, nunca libera EIP/borra EBS/EFS).
# Apagar NO deja el costo en cero (ALB/EFS/EBS/CloudWatch/EIP persisten).
#
# Variables opcionales: AWS_REGION/AWS_DEFAULT_REGION (región; AWS_REGION
# tiene precedencia; por defecto us-east-1), RAG_ECS_CLUSTER (por defecto
# rag-playas-prod), RAG_EXPECTED_AWS_ACCOUNT_ID (guarda de cuenta, 12
# dígitos). Ver README.md para el contrato completo y las precondiciones
# operativas (no concurrencia con start.sh, recursos compartidos, etc.).
#
# Salida: 0 solo si toda la operación fue verificada de punta a punta;
# distinto de cero ante fallo o interrupción, sin rollback automático —
# vuelve a ejecutar este mismo script para reconciliar el estado.
set -Eeuo pipefail
export AWS_PAGER=""

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-1}}"
CLUSTER="${RAG_ECS_CLUSTER:-rag-playas-prod}"
CHROMADB_TAG_NAME="rag-playas-chromadb"
OLLAMA_TAG_NAME="rag-playas-ollama"

CHROMADB_INSTANCE_ID=""
OLLAMA_INSTANCE_ID=""
# Indica que ya se INTENTÓ al menos una operación mutante contra AWS — no
# que se confirmó su éxito. Si AWS llega a aplicar una operación y la
# respuesta se pierde (red, timeout), esta bandera igual queda en 1, para
# que cualquier fallo posterior se trate como estado potencialmente parcial
# y dispare el diagnóstico de mejor esfuerzo, en vez de asumir que no pasó
# nada. Se activa inmediatamente antes de cada llamada mutante, nunca
# después ni antes de llamadas de solo lectura o waiters.
MUTATION_ATTEMPTED=0

bold='\033[1m'
green='\033[0;32m'
yellow='\033[1;33m'
red='\033[0;31m'
reset='\033[0m'

log()  { echo -e "${bold}▶ $*${reset}"; }
ok()   { echo -e "${green}✓ $*${reset}"; }
warn() { echo -e "${yellow}⚠ $*${reset}"; }
err()  { echo -e "${red}✗ $*${reset}" >&2; }

mark_mutation_attempted() { MUTATION_ATTEMPTED=1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "Falta el comando requerido: $1"; exit 1; }
}

# Estado observable de mejor esfuerzo, solo para diagnóstico tras un fallo
# posterior a haber intentado una mutación (ver fail()). Nunca se llama
# antes de intentar ninguna operación mutante.
show_diagnostics() {
  warn "Operación incompleta. Estado observable (mejor esfuerzo):"
  local svc
  for svc in app frontend; do
    echo "  ECS ${CLUSTER}-${svc}:"
    aws ecs describe-services --cluster "${CLUSTER}" --services "${CLUSTER}-${svc}" --region "${REGION}" \
      --query 'services[0].{status:status,desired:desiredCount,running:runningCount,pending:pendingCount}' \
      --output table 2>/dev/null || echo "    (no se pudo consultar)"
  done
  echo "  EC2 ChromaDB (${CHROMADB_INSTANCE_ID:-<sin identificar>}): $(get_instance_state "${CHROMADB_INSTANCE_ID:-}" 2>/dev/null || echo '?')"
  echo "  EC2 Ollama   (${OLLAMA_INSTANCE_ID:-<sin identificar>}): $(get_instance_state "${OLLAMA_INSTANCE_ID:-}" 2>/dev/null || echo '?')"
  echo ""
  echo "  Comandos de diagnóstico sugeridos:"
  echo "    aws ecs describe-services --cluster ${CLUSTER} --services ${CLUSTER}-app ${CLUSTER}-frontend --region ${REGION}"
  echo "    aws ec2 describe-instances --instance-ids ${CHROMADB_INSTANCE_ID:-<id>} ${OLLAMA_INSTANCE_ID:-<id>} --region ${REGION}"
}

# Único punto de salida por error: antes de intentar cualquier mutación
# imprime un error corto; después de intentar una (MUTATION_ATTEMPTED=1,
# aunque no se sepa si AWS la aplicó) además muestra el diagnóstico de
# arriba. Desactiva su propio trap ERR primero para no autorrecursionar si
# algo usado por el diagnóstico también falla.
fail() {
  trap - ERR
  err "$1"
  if [[ "${MUTATION_ATTEMPTED}" -eq 1 ]]; then
    show_diagnostics
  fi
  exit 1
}

get_instance_state() {
  aws ec2 describe-instances --instance-ids "$1" --region "${REGION}" \
    --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null
}

# Descubre por tag Name= la única instancia EC2 válida (pending/running/
# stopping/stopped — shutting-down/terminated quedan excluidas por el
# filtro). Falla si hay cero o más de una coincidencia. stdout: solo el ID;
# cualquier mensaje va a stderr.
discover_ec2_id() {
  local tag_name="$1" out count
  out="$(aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=${tag_name}" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --region "${REGION}" \
    --query 'Reservations[].Instances[].InstanceId' --output text 2>/dev/null)" || {
    echo "aws ec2 describe-instances falló para tag Name='${tag_name}'" >&2
    return 1
  }
  if [[ -z "${out}" ]]; then
    echo "ninguna instancia EC2 con tag Name='${tag_name}' en un estado válido" >&2
    return 1
  fi
  count="$(printf '%s' "${out}" | wc -w | tr -d ' ')"
  if [[ "${count}" != "1" ]]; then
    echo "se esperaba exactamente una instancia con tag Name='${tag_name}'; se encontraron ${count}: ${out}" >&2
    return 1
  fi
  printf '%s' "${out}"
}

# Valida en una sola llamada que ambos servicios ECS existan, estén ACTIVE
# y sin failures. No produce datos (solo éxito/fracaso + mensaje a stderr).
validate_ecs_services() {
  local out nfailures nservices nactive
  out="$(aws ecs describe-services --cluster "${CLUSTER}" \
    --services "${CLUSTER}-app" "${CLUSTER}-frontend" --region "${REGION}" \
    --query '[length(failures), length(services), length(services[?status==`ACTIVE`])]' \
    --output text 2>/dev/null)" || { echo "aws ecs describe-services falló" >&2; return 1; }
  nfailures="$(printf '%s' "${out}" | cut -f1)"
  nservices="$(printf '%s' "${out}" | cut -f2)"
  nactive="$(printf '%s' "${out}" | cut -f3)"
  if [[ "${nfailures}" != "0" ]]; then
    echo "describe-services reportó fallos (${nfailures}) para ${CLUSTER}-app/${CLUSTER}-frontend" >&2
    return 1
  fi
  if [[ "${nservices}" != "2" ]]; then
    echo "se esperaban exactamente 2 servicios ECS, se encontraron ${nservices}" >&2
    return 1
  fi
  if [[ "${nactive}" != "2" ]]; then
    echo "no todos los servicios ECS están ACTIVE (${nactive}/2 activos)" >&2
    return 1
  fi
}

# Muestra cuenta/ARN/región antes de mutar y, si se definió
# RAG_EXPECTED_AWS_ACCOUNT_ID, exige que coincida con la cuenta activa.
show_identity_and_guard() {
  local out account arn
  out="$(aws sts get-caller-identity --query '[Account,Arn]' --output text 2>/dev/null)" || {
    echo "aws sts get-caller-identity falló (credenciales inválidas o ausentes)" >&2
    return 1
  }
  account="$(printf '%s' "${out}" | cut -f1)"
  arn="$(printf '%s' "${out}" | cut -f2)"
  if [[ -z "${account}" || "${account}" == "None" ]]; then
    echo "no se pudo determinar la cuenta AWS activa" >&2
    return 1
  fi
  log "Identidad AWS: cuenta ${account} · ${arn} · región ${REGION}."
  if [[ -n "${RAG_EXPECTED_AWS_ACCOUNT_ID:-}" ]]; then
    if [[ ${#RAG_EXPECTED_AWS_ACCOUNT_ID} -ne 12 || "${RAG_EXPECTED_AWS_ACCOUNT_ID}" == *[!0-9]* ]]; then
      echo "RAG_EXPECTED_AWS_ACCOUNT_ID debe tener exactamente 12 dígitos (valor: '${RAG_EXPECTED_AWS_ACCOUNT_ID}')" >&2
      return 1
    fi
    if [[ "${account}" != "${RAG_EXPECTED_AWS_ACCOUNT_ID}" ]]; then
      echo "la cuenta AWS activa (${account}) no coincide con RAG_EXPECTED_AWS_ACCOUNT_ID (${RAG_EXPECTED_AWS_ACCOUNT_ID})" >&2
      return 1
    fi
  fi
}

ensure_instance_stopped() {
  local logical="$1" id="$2" state
  state="$(get_instance_state "${id}")" || { echo "no se pudo obtener el estado de ${logical} (${id})" >&2; return 1; }
  case "${state}" in
    running)
      log "Apagando ${logical} (${id})..."
      mark_mutation_attempted
      aws ec2 stop-instances --instance-ids "${id}" --region "${REGION}" >/dev/null \
        || { echo "aws ec2 stop-instances falló para ${logical} (${id}) (intento ya registrado; estado potencialmente parcial)" >&2; return 1; }
      ;;
    pending)
      log "${logical} (${id}) todavía está iniciando; se espera a que termine antes de apagarla..."
      aws ec2 wait instance-running --instance-ids "${id}" --region "${REGION}" \
        || { echo "espera de instance-running falló para ${logical} (${id})" >&2; return 1; }
      log "Apagando ${logical} (${id})..."
      mark_mutation_attempted
      aws ec2 stop-instances --instance-ids "${id}" --region "${REGION}" >/dev/null \
        || { echo "aws ec2 stop-instances falló para ${logical} (${id}) (intento ya registrado; estado potencialmente parcial)" >&2; return 1; }
      ;;
    stopping)
      log "${logical} (${id}) ya se está deteniendo; no se repite stop-instances."
      ;;
    stopped)
      log "${logical} (${id}) ya está detenida; no se modifica."
      ;;
    shutting-down|terminated)
      echo "${logical} (${id}) está en estado '${state}'; no corresponde con el contrato persistente esperado" >&2
      return 1
      ;;
    *)
      echo "${logical} (${id}) reportó un estado desconocido o vacío ('${state}')" >&2
      return 1
      ;;
  esac
}

# Confirma en una sola llamada agregada que AMBOS servicios ECS solicitados
# quedaron simultáneamente en desired=running=pending=0. Como la solicitud
# pide exactamente los dos nombres esperados, failures=0 + services=2 +
# en_cero=2 garantiza a la vez que AWS devolvió ambos servicios (no menos,
# nunca de más) y que los dos están en cero al mismo tiempo — un 0/2/1 o un
# 0/1/1 fallan aquí y nunca llegan a apagar las EC2. No basta con esperar
# 'services-stable': ese waiter no distingue "estable en 0" de otros fallos.
verify_ecs_zero_both() {
  local out nfailures nservices nzero
  out="$(aws ecs describe-services --cluster "${CLUSTER}" \
    --services "${CLUSTER}-app" "${CLUSTER}-frontend" --region "${REGION}" \
    --query '[length(failures), length(services), length(services[?desiredCount==`0` && runningCount==`0` && pendingCount==`0`])]' \
    --output text 2>/dev/null)" || { echo "aws ecs describe-services falló al verificar ceros" >&2; return 1; }
  nfailures="$(printf '%s' "${out}" | cut -f1)"
  nservices="$(printf '%s' "${out}" | cut -f2)"
  nzero="$(printf '%s' "${out}" | cut -f3)"
  if [[ "${nfailures}" != "0" ]]; then
    echo "describe-services reportó fallos (${nfailures}) al verificar ceros" >&2
    return 1
  fi
  if [[ "${nservices}" != "2" ]]; then
    echo "se esperaban exactamente 2 servicios ECS al verificar ceros, se encontraron ${nservices}" >&2
    return 1
  fi
  if [[ "${nzero}" != "2" ]]; then
    echo "no todos los servicios ECS están en desired=running=pending=0 (${nzero}/2 en cero)" >&2
    return 1
  fi
}

# ── Traps: instalados solo después de definir todas las funciones de arriba.
on_interrupt() {
  local sig="$1" code="$2"
  echo ""
  warn "Operación interrumpida (señal ${sig}) antes de completarse."
  if [[ "${MUTATION_ATTEMPTED}" -eq 1 ]]; then
    warn "Se había intentado al menos una operación mutante: estado potencialmente parcial. Inspecciona ECS/EC2 y vuelve a ejecutar './scripts/stop.sh' para reconciliar."
  else
    warn "No se había intentado ninguna operación mutante todavía."
  fi
  exit "${code}"
}
trap 'on_interrupt INT 130' INT
trap 'on_interrupt TERM 143' TERM

on_error() {
  local exit_code=$?
  trap - ERR
  err "Fallo inesperado (código ${exit_code}) en la línea ${BASH_LINENO[0]}: ${BASH_COMMAND}"
  if [[ "${MUTATION_ATTEMPTED}" -eq 1 ]]; then
    show_diagnostics
  fi
  exit "${exit_code}"
}
trap on_error ERR

# ── Preflight ────────────────────────────────────────────────────────────────
# Nota: no requiere curl (el apagado no depende de ningún endpoint HTTP ni
# del ALB), a diferencia de start.sh.

log "Verificando comandos requeridos (aws)..."
require_cmd aws

show_identity_and_guard || fail "No se pudo verificar la identidad/cuenta AWS activa."

log "Descubriendo recursos por tag/nombre..."
CHROMADB_INSTANCE_ID="$(discover_ec2_id "${CHROMADB_TAG_NAME}")" || fail "No se pudo identificar de forma única la instancia ChromaDB (tag Name='${CHROMADB_TAG_NAME}')."
OLLAMA_INSTANCE_ID="$(discover_ec2_id "${OLLAMA_TAG_NAME}")" || fail "No se pudo identificar de forma única la instancia Ollama (tag Name='${OLLAMA_TAG_NAME}')."
validate_ecs_services || fail "Los servicios ECS ${CLUSTER}-app/${CLUSTER}-frontend no están ambos ACTIVE y sin fallos."
ok "Recursos identificados — ChromaDB: ${CHROMADB_INSTANCE_ID} · Ollama: ${OLLAMA_INSTANCE_ID}"

# ── 1. Apagar ECS (app + frontend) ──────────────────────────────────────────
# Cada update-service se marca como intento ANTES de invocarlo (por si AWS
# lo aplica y la respuesta se pierde), se protege con || fail explícito (no
# se depende solo de set -e), y se exige que el desiredCount devuelto sea
# exactamente 0 — si AWS responde algo distinto, vacío o 'None', se falla de
# inmediato en vez de continuar hacia el apagado de las EC2.

for svc in app frontend; do
  log "Apagando servicio ${CLUSTER}-${svc} (desired-count 0)..."
  mark_mutation_attempted
  desired="$(aws ecs update-service --cluster "${CLUSTER}" --service "${CLUSTER}-${svc}" --desired-count 0 --region "${REGION}" \
    --query "service.desiredCount" --output text)" \
    || fail "aws ecs update-service falló para ${CLUSTER}-${svc} (intento ya registrado; estado potencialmente parcial)."
  [[ "${desired}" == "0" ]] \
    || fail "ecs update-service para ${CLUSTER}-${svc} devolvió desiredCount='${desired}' (se esperaba 0); estado potencialmente parcial."
done

log "Esperando a que ambos servicios ECS estén estables..."
aws ecs wait services-stable --cluster "${CLUSTER}" --services "${CLUSTER}-app" "${CLUSTER}-frontend" --region "${REGION}" \
  || fail "Los servicios ECS no alcanzaron un estado estable dentro del plazo del waiter de AWS."

log "Confirmando explícitamente desired=running=pending=0 en ambos servicios..."
verify_ecs_zero_both || fail "ECS reportó 'estable' pero no confirmó desired=running=pending=0 en ambos servicios; no se apagan las EC2."
ok "Servicios ECS confirmados en cero."

# ── 2. Apagar EC2 (idempotente) — solo después de confirmar ECS en cero ────

ensure_instance_stopped "ChromaDB" "${CHROMADB_INSTANCE_ID}" || fail "No se pudo apagar ChromaDB."
ensure_instance_stopped "Ollama" "${OLLAMA_INSTANCE_ID}" || fail "No se pudo apagar Ollama."

log "Esperando a que ChromaDB y Ollama estén 'stopped'..."
aws ec2 wait instance-stopped --instance-ids "${CHROMADB_INSTANCE_ID}" "${OLLAMA_INSTANCE_ID}" --region "${REGION}" \
  || fail "ChromaDB/Ollama no llegaron a 'stopped' dentro del plazo del waiter de AWS."
ok "EC2 ChromaDB y Ollama detenidas."

# ── 3. Éxito ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
ok "Servicios ECS (app + frontend): apagados y confirmados en cero."
ok "EC2 ChromaDB y Ollama: detenidas."
echo ""
warn "Esto NO deja el costo en cero: el ALB, EFS, EBS, CloudWatch y las"
warn "direcciones Elastic IP de ChromaDB/Ollama siguen existiendo."
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
