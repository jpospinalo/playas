#!/usr/bin/env bash
# Crea una EC2 "bastion" y despliega ATLAS completo desde ella siguiendo las
# instrucciones de despliegue automático descritas en el README del proyecto:
#
#   1. Infraestructura vectorial (ChromaDB + Ollama)  → vector-infraestructura/scripts/deploy.sh
#   2. Aplicación RAG en ECS Fargate                  → rag/infrastructure/scripts/deploy.sh
#
# La EC2 se usa solo como máquina de build/despliegue (corre Terraform, AWS
# CLI y Docker); la app final queda en ECS Fargate detrás del ALB, no en esta
# instancia.
#
# Requisitos locales:
#   - AWS CLI configurado (usa las credenciales de sesión del Learner Lab)
#   - Key pair "vockey" ya creado en EC2 y el archivo vockey.pem disponible localmente
#   - rag/.env con OPENAI_API_KEY configurada (se usa para el paso 2 del README)
#
# Uso:
#   ./scripts/deploy_bastion_ec2.sh
#
# Variables opcionales:
#   KEY_FILE   Ruta al .pem (default: ~/vockey.pem)
#   AWS_REGION Región AWS (default: us-east-1)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT="rag-playas"
INSTANCE_NAME="${PROJECT}-bastion"
INSTANCE_TYPE="m4.large"
VOLUME_SIZE_GB=50
KEY_NAME="vockey"
KEY_FILE="${KEY_FILE:-${HOME}/vockey.pem}"
REGION="${AWS_REGION:-us-east-1}"
# LabRole es el rol preexistente en AWS Academy (ver rag/infrastructure/iam.tf);
# LabInstanceProfile es el instance profile estándar que lo expone a las EC2.
IAM_INSTANCE_PROFILE="LabInstanceProfile"
REPO_URL="https://github.com/jpospinalo/playas.git"
SSH_USER="ubuntu"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -i "${KEY_FILE}")

# ── Colores / helpers ──────────────────────────────────────────────────────
bold='\033[1m'; green='\033[0;32m'; yellow='\033[1;33m'; red='\033[0;31m'; reset='\033[0m'

LOCAL_STEP=0
LOCAL_TOTAL=8
step()  { LOCAL_STEP=$((LOCAL_STEP+1)); echo ""; echo -e "${bold}▶ [LOCAL ${LOCAL_STEP}/${LOCAL_TOTAL}] $*${reset}"; }
ok()    { echo -e "${green}✓ $*${reset}"; }
warn()  { echo -e "${yellow}⚠ $*${reset}"; }
fail()  { echo -e "${red}✗ $*${reset}"; exit 1; }

# ── 1. Validar prerrequisitos locales ──────────────────────────────────────
step "Validando prerrequisitos locales"

command -v aws >/dev/null 2>&1 || fail "aws CLI no está instalado."

[[ -f "${KEY_FILE}" ]] || fail "No se encontró el key pair local en ${KEY_FILE} (usa KEY_FILE=/ruta/vockey.pem)."
chmod 400 "${KEY_FILE}"

RAG_ENV="${REPO_DIR}/rag/.env"
[[ -f "${RAG_ENV}" ]] || fail "No se encontró ${RAG_ENV}."

OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' "${RAG_ENV}" | head -1 | cut -d'=' -f2-)"
[[ -n "${OPENAI_API_KEY}" ]] || fail "OPENAI_API_KEY no está configurada en ${RAG_ENV}."

ok "Prerrequisitos OK (key pair, OPENAI_API_KEY presentes)"

# ── 2. Security group SSH ──────────────────────────────────────────────────
step "Buscando/creando security group para SSH"

VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text --region "${REGION}")
[[ "${VPC_ID}" != "None" ]] || fail "No se encontró una VPC por defecto en ${REGION}."

SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=vpc-id,Values=${VPC_ID}" "Name=group-name,Values=${INSTANCE_NAME}-sg" \
  --query 'SecurityGroups[0].GroupId' --output text --region "${REGION}" 2>/dev/null || true)

if [[ -z "${SG_ID}" || "${SG_ID}" == "None" ]]; then
  SG_ID=$(aws ec2 create-security-group \
    --group-name "${INSTANCE_NAME}-sg" \
    --description "SSH para bastion de despliegue de ${PROJECT}" \
    --vpc-id "${VPC_ID}" \
    --query 'GroupId' --output text --region "${REGION}")
  aws ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" --protocol tcp --port 22 --cidr 0.0.0.0/0 \
    --region "${REGION}" >/dev/null
  ok "Security group creado: ${SG_ID}"
else
  ok "Security group existente reutilizado: ${SG_ID}"
fi

# ── 3. AMI Ubuntu 24.04 ─────────────────────────────────────────────────────
step "Buscando AMI Ubuntu 24.04 LTS"

AMI_ID=$(aws ec2 describe-images \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
            "Name=virtualization-type,Values=hvm" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text --region "${REGION}")
[[ "${AMI_ID}" != "None" ]] || fail "No se encontró una AMI de Ubuntu 24.04."
ok "AMI: ${AMI_ID}"

# ── 4. Lanzar (o reutilizar) la instancia EC2 ──────────────────────────────
step "Lanzando instancia EC2 (${INSTANCE_TYPE}, ${VOLUME_SIZE_GB}GB, key=${KEY_NAME})"

INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=${INSTANCE_NAME}" "Name=instance-state-name,Values=pending,running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text --region "${REGION}" 2>/dev/null || true)

if [[ -n "${INSTANCE_ID}" && "${INSTANCE_ID}" != "None" ]]; then
  ok "Reutilizando instancia existente: ${INSTANCE_ID}"
else
  INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "${AMI_ID}" \
    --instance-type "${INSTANCE_TYPE}" \
    --key-name "${KEY_NAME}" \
    --security-group-ids "${SG_ID}" \
    --iam-instance-profile "Name=${IAM_INSTANCE_PROFILE}" \
    --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":${VOLUME_SIZE_GB},\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${INSTANCE_NAME}}]" \
    --query 'Instances[0].InstanceId' --output text --region "${REGION}")
  ok "Instancia creada: ${INSTANCE_ID}"
fi

log_wait() { echo -e "${bold}… $*${reset}"; }

log_wait "Esperando a que la instancia esté 'running'..."
aws ec2 wait instance-running --instance-ids "${INSTANCE_ID}" --region "${REGION}"

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "${INSTANCE_ID}" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text --region "${REGION}")
ok "Instancia running — IP pública: ${PUBLIC_IP}"

# ── 5. Esperar SSH disponible ──────────────────────────────────────────────
step "Esperando a que SSH esté disponible en ${PUBLIC_IP}"

for i in $(seq 1 30); do
  if ssh "${SSH_OPTS[@]}" -o BatchMode=yes "${SSH_USER}@${PUBLIC_IP}" "true" 2>/dev/null; then
    ok "SSH disponible"
    break
  fi
  [[ "${i}" == "30" ]] && fail "SSH no respondió tras 5 minutos."
  echo -n "."
  sleep 10
done

# ── 6. Copiar API key de OpenAI y datos semilla al bastion ────────────────
step "Copiando OPENAI_API_KEY y archivos de datos semilla al bastion (sin exponerlos en logs)"

printf '%s' "${OPENAI_API_KEY}" | ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" \
  'umask 077; cat > ~/.openai_api_key'
ok "OPENAI_API_KEY transferida"

ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" 'mkdir -p ~/seed_data'

LATEST_EXPORT="$(ls -t "${REPO_DIR}"/data/*.jsonl.gz 2>/dev/null | head -1 || true)"
if [[ -n "${LATEST_EXPORT}" ]]; then
  scp "${SSH_OPTS[@]}" "${LATEST_EXPORT}" "${SSH_USER}@${PUBLIC_IP}:~/seed_data/" >/dev/null
  ok "Export de ChromaDB copiado: $(basename "${LATEST_EXPORT}")"
else
  warn "No se encontró ningún data/*.jsonl.gz local; la importación a ChromaDB se omitirá."
fi

if [[ -f "${REPO_DIR}/data/seed_users.sql" ]]; then
  scp "${SSH_OPTS[@]}" "${REPO_DIR}/data/seed_users.sql" "${SSH_USER}@${PUBLIC_IP}:~/seed_data/" >/dev/null
  ok "seed_users.sql copiado"
fi

# ── 7. Bootstrap remoto: instalar dependencias y desplegar ────────────────
BOOTSTRAP_ONLY="${BOOTSTRAP_ONLY:-0}"
step "Ejecutando bootstrap y despliegue remoto en la EC2 (esto tarda varios minutos)"

ssh "${SSH_OPTS[@]}" "${SSH_USER}@${PUBLIC_IP}" "REPO_URL='${REPO_URL}' BOOTSTRAP_ONLY='${BOOTSTRAP_ONLY}' bash -s" <<'REMOTE_SCRIPT'
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

bold='\033[1m'; green='\033[0;32m'; reset='\033[0m'
STEP=0; TOTAL=12
step() {
  STEP=$((STEP+1))
  echo ""
  echo -e "${bold}════════════════════════════════════════════════════${reset}"
  echo -e "${bold}▶ [EC2 ${STEP}/${TOTAL}] $*${reset}"
  echo -e "${bold}════════════════════════════════════════════════════${reset}"
}
ok() { echo -e "${green}✓ $*${reset}"; }

APT_ENV=(sudo DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a)

step "Actualizando paquetes del sistema"
"${APT_ENV[@]}" apt-get update -y
"${APT_ENV[@]}" apt-get upgrade -y

step "Instalando git"
"${APT_ENV[@]}" apt-get install -y git
ok "git $(git --version)"

step "Instalando Docker y agregando ubuntu al grupo docker"
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo systemctl enable --now docker
ok "docker $(docker --version)"

step "Instalando AWS CLI v2"
if ! command -v aws >/dev/null 2>&1; then
  "${APT_ENV[@]}" apt-get install -y unzip
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  (cd /tmp && unzip -q awscliv2.zip && sudo ./aws/install)
fi
ok "$(aws --version)"

step "Instalando Terraform"
wget -qO - https://apt.releases.hashicorp.com/gpg | sudo gpg --batch --yes --no-tty --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
  | sudo tee /etc/apt/sources.list.d/hashicorp.list >/dev/null
"${APT_ENV[@]}" apt-get update -y
"${APT_ENV[@]}" apt-get install -y terraform
ok "$(terraform -version | head -1)"

step "Instalando uv"
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="${HOME}/.local/bin:${PATH}"
ok "$(uv --version)"

step "Instalando Session Manager Plugin"
curl -fsSL "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o /tmp/session-manager-plugin.deb
sudo dpkg -i /tmp/session-manager-plugin.deb
ok "session-manager-plugin instalado"

step "Clonando el repositorio"
rm -rf ~/playas
git clone "${REPO_URL}" ~/playas
cd ~/playas
ok "Repositorio clonado en ~/playas ($(git rev-parse --short HEAD))"

if [[ "${BOOTSTRAP_ONLY:-0}" == "1" ]]; then
  echo ""
  echo -e "${bold}BOOTSTRAP_ONLY=1: deteniendo antes de los despliegues de Terraform (pasos 9-12).${reset}"
  exit 0
fi

step "Desplegando infraestructura vectorial - README paso 1 (ChromaDB + Ollama)"
mkdir -p ~/playas/data
[[ -d ~/seed_data ]] && cp -v ~/seed_data/* ~/playas/data/ 2>/dev/null || true
cd ~/playas
./vector-infraestructura/scripts/deploy.sh --auto-approve

step "Configurando OPENAI_API_KEY - README paso 2"
TFVARS="${HOME}/playas/rag/infrastructure/terraform.tfvars"
KEY_VALUE="$(cat "${HOME}/.openai_api_key")"
if grep -q '^openai_api_key' "${TFVARS}" 2>/dev/null; then
  sed -i "s|^openai_api_key.*|openai_api_key = \"${KEY_VALUE}\"|" "${TFVARS}"
else
  echo "openai_api_key = \"${KEY_VALUE}\"" >> "${TFVARS}"
fi
shred -u "${HOME}/.openai_api_key" 2>/dev/null || rm -f "${HOME}/.openai_api_key"
ok "openai_api_key configurada en terraform.tfvars"

step "Desplegando aplicación RAG en ECS Fargate - README paso 2"
cd ~/playas
sg docker -c "./rag/infrastructure/scripts/deploy.sh --auto-approve"

step "Despliegue completado"
cd ~/playas/rag/infrastructure
ALB_URL=$(terraform output -raw alb_url 2>/dev/null || echo "(ejecuta 'terraform output alb_url' manualmente)")
ok "URL de la aplicación: ${ALB_URL}"
REMOTE_SCRIPT

echo ""
step "Resumen"
ok "Bastion EC2: ${INSTANCE_ID} (${PUBLIC_IP})"
ok "Conéctate con: ssh -i ${KEY_FILE} ${SSH_USER}@${PUBLIC_IP}"
