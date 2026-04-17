#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1

echo "=== Inicio setup ChromaDB: $(date) ==="

# CRITICO en Ubuntu 24.04: needrestart envía SIGTERM a cloud-final.service cuando
# apt-get upgrade detecta que el servicio necesita reiniciarse, matando cloud-init.
# NEEDRESTART_SUSPEND=1 desactiva ese comportamiento durante este script.
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_SUSPEND=1

# DPkg::Lock::Timeout=300: en lugar de fallar inmediatamente si apt-daily.service
# tiene el lock, apt espera hasta 5 minutos antes de rendirse.
APT_OPTS="-o DPkg::Lock::Timeout=300 -o Acquire::Retries=3 -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"

# 1. Actualizar sistema
echo "Actualizando paquetes..."
apt-get ${APT_OPTS} update
apt-get ${APT_OPTS} upgrade -y

# 2. Instalar dependencias
apt-get ${APT_OPTS} install -y build-essential docker.io

# 3. Habilitar Docker
# --no-block evita un deadlock conocido donde systemctl start cuelga
# cuando se invoca desde dentro de cloud-final.service
systemctl enable docker
systemctl start --no-block docker

# 4. Dar permisos al usuario ubuntu
usermod -aG docker ubuntu

# 5. Esperar que el Docker daemon esté listo antes de correr contenedores
echo "Esperando Docker daemon..."
for i in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "Docker listo."
    break
  fi
  echo "  intento ${i}/30..."
  sleep 3
done

# 6. Directorio para datos persistentes de Chroma
mkdir -p /opt/chroma-data

# 7. Lanzar ChromaDB en Docker
docker run -d --name chromadb \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /opt/chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  chromadb/chroma:1.3.5

echo "=== Setup ChromaDB completado: $(date) ==="
