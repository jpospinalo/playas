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
if [[ -f "${ECS_TFVARS}" ]]; then
  log "Actualizando ${ECS_TFVARS}..."
  update_tfvars "${ECS_TFVARS}" "chroma_host"     "${CHROMA_HOST_VAL}"
  update_tfvars "${ECS_TFVARS}" "ollama_base_url" "${OLLAMA_URL_VAL}"
  ok "terraform.tfvars actualizado"
else
  warn "${ECS_TFVARS} no existe — omitiendo"
fi

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
  if [[ -d "${DATA_DIR}" ]]; then
    # Toma el .jsonl.gz más reciente si hay varios
    EXPORT_FILE=$(find "${DATA_DIR}" -maxdepth 1 -name "*.jsonl.gz" -printf "%T@ %p\n" 2>/dev/null \
                  | sort -rn | head -1 | awk '{print $2}')
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
echo -e "  CHROMA_HOST     = ${CHROMA_HOST_VAL}"
echo -e "  OLLAMA_BASE_URL = ${OLLAMA_URL_VAL}"
echo ""
echo -e "  Archivos actualizados:"
[[ -f "${RAG_ENV}"     ]] && echo -e "    • rag/.env"
[[ -f "${ECS_TFVARS}" ]] && echo -e "    • rag/infrastructure/terraform.tfvars"
echo ""
echo -e "  Para desplegar la aplicación RAG en ECS Fargate:"
echo -e "    ./rag/infrastructure/scripts/deploy.sh --auto-approve"
echo -e "${bold}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${reset}"
