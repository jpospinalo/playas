#!/usr/bin/env bash
# Instala Docker Engine + Compose plugin en Ubuntu 22.04 (Jammy) o 24.04 (Noble).
# Uso: sudo bash scripts/install-docker-ubuntu.sh
set -euo pipefail

# ── Verificaciones previas ────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  echo "ERROR: ejecuta este script como root o con sudo." >&2
  exit 1
fi

if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
  echo "ERROR: este script solo soporta Ubuntu." >&2
  exit 1
fi

# shellcheck source=/dev/null
source /etc/os-release
UBUNTU_CODENAME="${VERSION_CODENAME:-}"

if [[ "$UBUNTU_CODENAME" != "jammy" && "$UBUNTU_CODENAME" != "noble" ]]; then
  echo "ADVERTENCIA: distribución '$UBUNTU_CODENAME' no probada (se esperaba jammy o noble)."
  echo "Continuando de todas formas..."
fi

echo "──────────────────────────────────────────────────────────"
echo " Instalando Docker en Ubuntu ${UBUNTU_CODENAME}"
echo "──────────────────────────────────────────────────────────"

# ── 1. Dependencias base ──────────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg

# ── 2. GPG key y repositorio oficial de Docker ────────────────────────────────
install -m 0755 -d /etc/apt/keyrings

curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | gpg --dearmor --batch --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

# ── 3. Instalar Docker Engine ─────────────────────────────────────────────────
apt-get update -qq
apt-get install -y -qq \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

# ── 4. Habilitar y arrancar el servicio ───────────────────────────────────────
systemctl enable --now docker

# ── 5. Añadir el usuario invocante al grupo docker ────────────────────────────
TARGET_USER="${SUDO_USER:-}"
if [[ -n "$TARGET_USER" ]] && id "$TARGET_USER" &>/dev/null; then
  usermod -aG docker "$TARGET_USER"
  echo ""
  echo "AVISO: '$TARGET_USER' añadido al grupo 'docker'."
  echo "       Cierra la sesión y vuelve a iniciarla para aplicar el cambio."
fi

# ── 6. Verificación ───────────────────────────────────────────────────────────
echo ""
echo "✓ Instalación completada:"
docker --version
docker compose version
