#!/usr/bin/env bash
# Enciende de forma segura y verificable el cómputo del RAG: EC2 de
# ChromaDB/Ollama primero (verificadas por HTTP), luego ECS app/frontend.
# No declara éxito hasta que /api/ready y / responden a través del ALB.
#
# Solo requiere AWS CLI 2.x y curl — sin Terraform: todo se descubre por
# tag/nombre contra AWS. Idempotente y sin operaciones destructivas (nunca
# termina instancias, nunca libera EIP/borra EBS/EFS, nunca reindexa).
#
# Variables opcionales: AWS_REGION/AWS_DEFAULT_REGION (región; AWS_REGION
# tiene precedencia; por defecto us-east-1), RAG_ECS_CLUSTER (por defecto
# rag-playas-prod), RAG_EXPECTED_AWS_ACCOUNT_ID (guarda de cuenta, 12
# dígitos). Ver README.md para el contrato completo y las precondiciones
# operativas (no concurrencia con stop.sh, recursos compartidos, etc.).
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

# Plazos finitos y globales por fase (compartidos entre los dos endpoints de
# cada fase, medidos con SECONDS en vez de invocar `date` en cada vuelta).
HTTP_PHASE_TIMEOUT=900
HTTP_PER_TRY_TIMEOUT=5
HTTP_SLEEP_BETWEEN=10

CHROMADB_INSTANCE_ID=""
OLLAMA_INSTANCE_ID=""
CHROMADB_IP=""
OLLAMA_IP=""
ALB_URL=""
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
  echo "    aws elbv2 describe-target-groups --names ${CLUSTER}-backend --region ${REGION}"
  echo "    aws logs tail /ecs/${CLUSTER}-app --region ${REGION} --since 15m"
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

get_instance_public_ip() {
  aws ec2 describe-instances --instance-ids "$1" --region "${REGION}" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text 2>/dev/null
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

# Descubre el DNS del ALB y exige que esté 'active'. stdout: solo la URL
# http://...; cualquier mensaje va a stderr. Solo se usa en start.sh.
discover_alb_url() {
  local out dns state
  out="$(aws elbv2 describe-load-balancers --names "${CLUSTER}-alb" --region "${REGION}" \
    --query 'LoadBalancers[0].[DNSName,State.Code]' --output text 2>/dev/null)" || {
    echo "aws elbv2 describe-load-balancers falló para '${CLUSTER}-alb'" >&2
    return 1
  }
  dns="$(printf '%s' "${out}" | cut -f1)"
  state="$(printf '%s' "${out}" | cut -f2)"
  if [[ -z "${dns}" || "${dns}" == "None" ]]; then
    echo "el ALB '${CLUSTER}-alb' no tiene DNSName" >&2
    return 1
  fi
  if [[ "${state}" != "active" ]]; then
    echo "el ALB '${CLUSTER}-alb' no está 'active' (estado: ${state})" >&2
    return 1
  fi
  printf 'http://%s' "${dns}"
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

ensure_instance_running() {
  local logical="$1" id="$2" state
  state="$(get_instance_state "${id}")" || { echo "no se pudo obtener el estado de ${logical} (${id})" >&2; return 1; }
  case "${state}" in
    stopped)
      log "Encendiendo ${logical} (${id})..."
      mark_mutation_attempted
      aws ec2 start-instances --instance-ids "${id}" --region "${REGION}" >/dev/null \
        || { echo "aws ec2 start-instances falló para ${logical} (${id}) (intento ya registrado; estado potencialmente parcial)" >&2; return 1; }
      ;;
    stopping)
      log "${logical} (${id}) se está deteniendo; se espera a que termine antes de encenderla..."
      aws ec2 wait instance-stopped --instance-ids "${id}" --region "${REGION}" \
        || { echo "espera de instance-stopped falló para ${logical} (${id})" >&2; return 1; }
      log "Encendiendo ${logical} (${id})..."
      mark_mutation_attempted
      aws ec2 start-instances --instance-ids "${id}" --region "${REGION}" >/dev/null \
        || { echo "aws ec2 start-instances falló para ${logical} (${id}) (intento ya registrado; estado potencialmente parcial)" >&2; return 1; }
      ;;
    pending)
      log "${logical} (${id}) ya está iniciando; no se repite start-instances."
      ;;
    running)
      log "${logical} (${id}) ya está en ejecución; no se modifica."
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

# Polling silencioso (sin -S: ningún error de curl se imprime por intento,
# solo un punto de progreso) contra un deadline absoluto compartido (medido
# en SECONDS) que el llamador ya calculó. No imprime mensaje al agotar el
# plazo: el llamador decide el mensaje final vía fail().
poll_one_http() {
  local label="$1" url="$2" deadline="$3" remaining try_timeout sleep_for
  log "Esperando respuesta de ${label} (${url})..."
  while true; do
    remaining=$(( deadline - SECONDS ))
    if (( remaining <= 0 )); then
      echo ""
      return 1
    fi
    try_timeout="${HTTP_PER_TRY_TIMEOUT}"
    if (( remaining < try_timeout )); then
      try_timeout="${remaining}"
    fi
    if curl -fs --max-time "${try_timeout}" -o /dev/null "${url}"; then
      echo ""
      ok "${label} responde."
      return 0
    fi
    printf '.'
    remaining=$(( deadline - SECONDS ))
    if (( remaining <= 0 )); then
      echo ""
      return 1
    fi
    sleep_for="${HTTP_SLEEP_BETWEEN}"
    if (( remaining < sleep_for )); then
      sleep_for="${remaining}"
    fi
    sleep "${sleep_for}"
  done
}

# ── Traps: instalados solo después de definir todas las funciones de arriba.
on_interrupt() {
  local sig="$1" code="$2"
  echo ""
  warn "Operación interrumpida (señal ${sig}) antes de completarse."
  if [[ "${MUTATION_ATTEMPTED}" -eq 1 ]]; then
    warn "Se había intentado al menos una operación mutante: estado potencialmente parcial. Inspecciona ECS/EC2 y vuelve a ejecutar './scripts/start.sh' para reconciliar."
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

log "Verificando comandos requeridos (aws, curl)..."
require_cmd aws
require_cmd curl

show_identity_and_guard || fail "No se pudo verificar la identidad/cuenta AWS activa."

log "Descubriendo recursos por tag/nombre..."
CHROMADB_INSTANCE_ID="$(discover_ec2_id "${CHROMADB_TAG_NAME}")" || fail "No se pudo identificar de forma única la instancia ChromaDB (tag Name='${CHROMADB_TAG_NAME}')."
OLLAMA_INSTANCE_ID="$(discover_ec2_id "${OLLAMA_TAG_NAME}")" || fail "No se pudo identificar de forma única la instancia Ollama (tag Name='${OLLAMA_TAG_NAME}')."
validate_ecs_services || fail "Los servicios ECS ${CLUSTER}-app/${CLUSTER}-frontend no están ambos ACTIVE y sin fallos."
ALB_URL="$(discover_alb_url)" || fail "El ALB ${CLUSTER}-alb no existe, no tiene DNS o no está 'active'."
ok "Recursos identificados — ChromaDB: ${CHROMADB_INSTANCE_ID} · Ollama: ${OLLAMA_INSTANCE_ID} · ALB: ${ALB_URL}"

# ── 1. Encender EC2 (idempotente) ───────────────────────────────────────────

ensure_instance_running "ChromaDB" "${CHROMADB_INSTANCE_ID}" || fail "No se pudo encender ChromaDB."
ensure_instance_running "Ollama" "${OLLAMA_INSTANCE_ID}" || fail "No se pudo encender Ollama."

log "Esperando a que ChromaDB y Ollama estén 'running'..."
aws ec2 wait instance-running --instance-ids "${CHROMADB_INSTANCE_ID}" "${OLLAMA_INSTANCE_ID}" --region "${REGION}" \
  || fail "ChromaDB/Ollama no llegaron a 'running' dentro del plazo del waiter de AWS."

log "Esperando el chequeo de estado (instance-status-ok)..."
aws ec2 wait instance-status-ok --instance-ids "${CHROMADB_INSTANCE_ID}" "${OLLAMA_INSTANCE_ID}" --region "${REGION}" \
  || fail "ChromaDB/Ollama no pasaron 'instance-status-ok' dentro del plazo del waiter de AWS."
ok "EC2 ChromaDB y Ollama en ejecución y con status-ok."

CHROMADB_IP="$(get_instance_public_ip "${CHROMADB_INSTANCE_ID}")" || fail "No se pudo obtener la IP pública de ChromaDB."
OLLAMA_IP="$(get_instance_public_ip "${OLLAMA_INSTANCE_ID}")" || fail "No se pudo obtener la IP pública de Ollama."
[[ -n "${CHROMADB_IP}" && "${CHROMADB_IP}" != "None" ]] || fail "ChromaDB no tiene IP pública asignada."
[[ -n "${OLLAMA_IP}" && "${OLLAMA_IP}" != "None" ]] || fail "Ollama no tiene IP pública asignada."

# ── 2. Verificar por HTTP que ChromaDB y Ollama responden (deadline
# compartido: si ChromaDB consume tiempo, a Ollama le queda el remanente) ──

phase_start=${SECONDS}
deadline=$(( SECONDS + HTTP_PHASE_TIMEOUT ))
poll_one_http "ChromaDB" "http://${CHROMADB_IP}:8000/api/v2/heartbeat" "${deadline}" \
  || fail "ChromaDB (http://${CHROMADB_IP}:8000/api/v2/heartbeat) no respondió tras $(( SECONDS - phase_start ))s (plazo compartido de fase: ${HTTP_PHASE_TIMEOUT}s); no se enciende ECS."
poll_one_http "Ollama" "http://${OLLAMA_IP}:11434/api/tags" "${deadline}" \
  || fail "Ollama (http://${OLLAMA_IP}:11434/api/tags) no respondió tras $(( SECONDS - phase_start ))s (plazo compartido de fase: ${HTTP_PHASE_TIMEOUT}s); no se enciende ECS."

# ── 3. Encender ECS (app + frontend) solo si lo anterior ya respondió ──────
# Cada update-service se marca como intento ANTES de invocarlo (por si AWS
# lo aplica y la respuesta se pierde), se protege con || fail explícito (no
# se depende solo de set -e), y se exige que el desiredCount devuelto sea
# exactamente 1 — si AWS responde algo distinto, vacío o 'None', se falla de
# inmediato en vez de seguir esperando un estado que nunca se pidió.

for svc in app frontend; do
  log "Encendiendo servicio ${CLUSTER}-${svc}..."
  mark_mutation_attempted
  desired="$(aws ecs update-service --cluster "${CLUSTER}" --service "${CLUSTER}-${svc}" --desired-count 1 --region "${REGION}" \
    --query "service.desiredCount" --output text)" \
    || fail "aws ecs update-service falló para ${CLUSTER}-${svc} (intento ya registrado; estado potencialmente parcial)."
  [[ "${desired}" == "1" ]] \
    || fail "ecs update-service para ${CLUSTER}-${svc} devolvió desiredCount='${desired}' (se esperaba 1); estado potencialmente parcial."
done

log "Esperando a que ambos servicios ECS estén estables (esto no es prueba suficiente de disponibilidad; se verifica por HTTP a continuación)..."
aws ecs wait services-stable --cluster "${CLUSTER}" --services "${CLUSTER}-app" "${CLUSTER}-frontend" --region "${REGION}" \
  || fail "Los servicios ECS no alcanzaron un estado estable dentro del plazo del waiter de AWS."
ok "Servicios ECS estables (a nivel de ECS)."

# ── 4. Verificación extremo a extremo por HTTP (otro deadline compartido) ──
# No se usa /api/health como comprobación final: solo indica que el proceso
# responde. /api/ready confirma que el grafo LangGraph fue compilado, el
# índice BM25 no está vacío y PostgreSQL responde.

phase_start=${SECONDS}
deadline=$(( SECONDS + HTTP_PHASE_TIMEOUT ))
poll_one_http "Backend (/api/ready)" "${ALB_URL}/api/ready" "${deadline}" \
  || fail "El backend (${ALB_URL}/api/ready) no quedó listo tras $(( SECONDS - phase_start ))s (plazo compartido de fase: ${HTTP_PHASE_TIMEOUT}s)."
poll_one_http "Frontend (/)" "${ALB_URL}/" "${deadline}" \
  || fail "El frontend (${ALB_URL}/) no respondió tras $(( SECONDS - phase_start ))s (plazo compartido de fase: ${HTTP_PHASE_TIMEOUT}s)."

# ── 5. Éxito ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
ok "EC2 ChromaDB y Ollama: encendidas y verificadas por HTTP."
ok "Servicios ECS (app + frontend): encendidos y estables."
ok "Frontend: disponible (${ALB_URL}/)."
ok "Backend: listo (${ALB_URL}/api/ready)."
echo ""
echo -e "  URL: ${ALB_URL}"
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
