#!/usr/bin/env bash
# Despliega la infraestructura de Ollama y ChromaDB en EC2 y actualiza las
# variables de entorno del proyecto RAG con las IPs estáticas resultantes.
# Una vez que ChromaDB esté disponible, importa el archivo .jsonl.gz de data/.
#
# Uso:
#   ./scripts/deploy.sh [--auto-approve]
#
# Archivos que actualiza:
#   rag/.env                             — CHROMA_HOST y OLLAMA_BASE_URL
#   rag/infrastructure/terraform.tfvars  — chroma_host y ollama_base_url
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VECTOR_INFRA_DIR="${SCRIPT_DIR}/.."
RAG_DIR="${SCRIPT_DIR}/../../rag"
DATA_DIR="${SCRIPT_DIR}/../../data"
RAG_ENV="${RAG_DIR}/.env"
ECS_TFVARS="${RAG_DIR}/infrastructure/terraform.tfvars"

# Tiempo máximo de espera para que ChromaDB levante tras el boot de la EC2
CHROMA_WAIT_SECONDS=420   # 7 min — el user-data instala Docker y descarga la imagen

# ── Colores ───────────────────────────────────────────────────────────────────
bold='\033[1m'
green='\033[0;32m'
yellow='\033[1;33m'
reset='\033[0m'

log()  { echo -e "${bold}▶ $*${reset}"; }
ok()   { echo -e "${green}✓ $*${reset}"; }
warn() { echo -e "${yellow}⚠ $*${reset}"; }

# ── 1. Terraform init + apply ─────────────────────────────────────────────────
log "Inicializando Terraform en vector-infraestructura..."
terraform -chdir="${VECTOR_INFRA_DIR}" init -upgrade

log "Ejecutando terraform apply en vector-infraestructura..."

APPLY_ARGS=()
if [[ "${1:-}" == "--auto-approve" ]]; then
  APPLY_ARGS+=("-auto-approve")
fi

terraform -chdir="${VECTOR_INFRA_DIR}" apply "${APPLY_ARGS[@]}"

# ── 2. Leer IPs estáticas del output ─────────────────────────────────────────
log "Leyendo IPs estáticas desde Terraform outputs..."

CHROMA_IP=$(terraform -chdir="${VECTOR_INFRA_DIR}" output -raw chromadb_public_ip)
OLLAMA_IP=$(terraform -chdir="${VECTOR_INFRA_DIR}" output -raw ollama_public_ip)

ok "ChromaDB IP: ${CHROMA_IP}"
ok "Ollama IP:   ${OLLAMA_IP}"

CHROMA_HOST_VAL="${CHROMA_IP}"
OLLAMA_URL_VAL="http://${OLLAMA_IP}:11434"

# ── 3. Helper: actualiza o agrega una variable ────────────────────────────────
# update_env <archivo> <clave> <valor>
update_env() {
  local file="$1" key="$2" value="$3"
  if grep -qE "^${key}=" "${file}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${value}|" "${file}"
  else
    echo "${key}=${value}" >> "${file}"
  fi
}

# update_tfvars <archivo> <clave> <valor>  (formato HCL: key = "value")
update_tfvars() {
  local file="$1" key="$2" value="$3"
  if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "${file}" 2>/dev/null; then
    sed -i "s|^[[:space:]]*${key}[[:space:]]*=.*|${key} = \"${value}\"|" "${file}"
  else
    echo "${key} = \"${value}\"" >> "${file}"
  fi
}

# get_tfvars_value <archivo> <clave>  → valor sin comillas, vacío si no existe
get_tfvars_value() {
  local file="$1" key="$2"
  grep -E "^[[:space:]]*${key}[[:space:]]*=" "${file}" 2>/dev/null \
    | sed -E 's/^[^=]+=[[:space:]]*"?([^"#]*)"?.*/\1/' \
    | tr -d ' ' \
    | head -1
}

# auto_generate_secret <archivo> <clave> <valor_generado>
# Escribe el secreto solo si el valor actual está vacío o es un placeholder
# (empieza con "cambia-"). Devuelve el valor efectivo.
auto_generate_secret() {
  local file="$1" key="$2" generated="$3"
  local current
  current=$(get_tfvars_value "${file}" "${key}")
  if [[ -z "${current}" || "${current}" == cambia-* ]]; then
    update_tfvars "${file}" "${key}" "${generated}"
    echo "${generated}"
  else
    echo "${current}"
  fi
}

# ── 4. Actualizar rag/.env ────────────────────────────────────────────────────
if [[ -f "${RAG_ENV}" ]]; then
  log "Actualizando ${RAG_ENV}..."
  update_env "${RAG_ENV}" "CHROMA_HOST"     "${CHROMA_HOST_VAL}"
  update_env "${RAG_ENV}" "OLLAMA_BASE_URL" "${OLLAMA_URL_VAL}"
  ok ".env actualizado"
else
  warn "${RAG_ENV} no existe — omitiendo"
fi

# ── 5. Actualizar rag/infrastructure/terraform.tfvars ────────────────────────
ECS_TFVARS_EXAMPLE="${RAG_DIR}/infrastructure/terraform.tfvars.example"

if [[ ! -f "${ECS_TFVARS}" ]]; then
  if [[ -f "${ECS_TFVARS_EXAMPLE}" ]]; then
    log "Creando ${ECS_TFVARS} desde el ejemplo..."
    cp "${ECS_TFVARS_EXAMPLE}" "${ECS_TFVARS}"
    ok "terraform.tfvars creado"
  else
    warn "No se encontró terraform.tfvars.example — creando archivo vacío"
    touch "${ECS_TFVARS}"
  fi
fi

log "Generando secretos automáticamente (solo si son placeholders)..."
PG_PASSWORD=$(auto_generate_secret "${ECS_TFVARS}" "postgres_password" "$(openssl rand -hex 16)")
JWT_SECRET=$(auto_generate_secret  "${ECS_TFVARS}" "jwt_secret_key"    "$(openssl rand -hex 32)")
ok "Secretos configurados"

log "Actualizando ${ECS_TFVARS}..."
update_tfvars "${ECS_TFVARS}" "chroma_host"     "${CHROMA_HOST_VAL}"
update_tfvars "${ECS_TFVARS}" "ollama_base_url" "${OLLAMA_URL_VAL}"
ok "terraform.tfvars actualizado"

# ── 6. Esperar a que ChromaDB esté disponible ─────────────────────────────────
log "Esperando a que ChromaDB esté disponible en ${CHROMA_HOST_VAL}:8000..."
echo "   (la EC2 necesita instalar Docker y arrancar el contenedor — puede tardar varios minutos)"

deadline=$(( $(date +%s) + CHROMA_WAIT_SECONDS ))
chroma_ready=0

while [[ $(date +%s) -lt ${deadline} ]]; do
  if curl -sf --max-time 5 "http://${CHROMA_HOST_VAL}:8000/api/v2/heartbeat" > /dev/null 2>&1; then
    chroma_ready=1
    break
  fi
  echo -n "."
  sleep 10
done
echo ""

if [[ ${chroma_ready} -eq 0 ]]; then
  warn "ChromaDB no respondió en ${CHROMA_WAIT_SECONDS}s. La importación no se ejecutará."
  echo "  Puede ejecutarla manualmente cuando ChromaDB esté listo:"
  echo "    cd rag && uv run python3 ../data/import_to_chromadb.py <archivo.jsonl.gz> --host ${CHROMA_HOST_VAL}"
else
  ok "ChromaDB disponible"

  # ── 7. Localizar el archivo de exportación ──────────────────────────────────
  EXPORT_FILE=""
  if [[ ! -d "${DATA_DIR}" ]]; then
    warn "El directorio ${DATA_DIR} no existe. Asegúrate de clonar el repositorio completo."
  else
    # ls -t ordena por fecha de modificación (compatible con Linux y macOS)
    EXPORT_FILE=$(ls -t "${DATA_DIR}"/*.jsonl.gz 2>/dev/null | head -1)
  fi

  if [[ -z "${EXPORT_FILE}" ]]; then
    warn "No se encontró ningún archivo .jsonl.gz en ${DATA_DIR}. La importación no se ejecutará."
    echo "  Coloca el archivo de exportación en data/ y ejecuta:"
    echo "    cd rag && uv run python3 ../data/import_to_chromadb.py <archivo.jsonl.gz> --host ${CHROMA_HOST_VAL}"
  else
    log "Importando $(basename "${EXPORT_FILE}") → ChromaDB ${CHROMA_HOST_VAL}:8000..."
    (
      cd "${RAG_DIR}"
      uv run python3 "${DATA_DIR}/import_to_chromadb.py" \
        "${EXPORT_FILE}" \
        --host "${CHROMA_HOST_VAL}" \
        --port 8000
    )
    ok "Importación completada"
  fi
fi

# ── 8. Resumen ────────────────────────────────────────────────────────────────
echo ""
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
echo -e "${bold}Despliegue completado${reset}"
echo ""
echo -e "  CHROMA_HOST       = ${CHROMA_HOST_VAL}"
echo -e "  OLLAMA_BASE_URL   = ${OLLAMA_URL_VAL}"
echo -e "  postgres_password = ${PG_PASSWORD}"
echo -e "  jwt_secret_key    = ${JWT_SECRET}"
echo ""
echo -e "  Archivos actualizados:"
[[ -f "${RAG_ENV}"     ]] && echo -e "    • rag/.env"
[[ -f "${ECS_TFVARS}" ]] && echo -e "    • rag/infrastructure/terraform.tfvars"
echo ""
echo -e "  Antes de desplegar ECS, agrega al menos una API key de LLM en:"
echo -e "    rag/infrastructure/terraform.tfvars"
echo -e "      openai_api_key     = \"...\"   # prioridad 1"
echo -e "      openrouter_api_key = \"...\"   # prioridad 2"
echo -e "      google_api_key     = \"...\"   # prioridad 3"
echo ""
echo -e "  Luego ejecuta:"
echo -e "    ./rag/infrastructure/scripts/deploy.sh --auto-approve"
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
