#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/user-data.log | logger -t user-data -s 2>/dev/console) 2>&1

# Esperar a que cloud-init libere el lock de apt antes de continuar
echo "Esperando a que cloud-init libere el lock de apt..."
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
      fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
    sleep 2
done
echo "Lock liberado, continuando instalacion..."

# 1. Actualizar sistema
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# 2. Paquete de compilación
apt-get install -y build-essential

# 3. Instalar Docker
apt-get install -y docker.io
systemctl enable --now docker

# 4. Dar permisos al usuario ubuntu para usar Docker sin sudo
usermod -aG docker ubuntu

# 5. Directorio para datos persistentes de Chroma
mkdir -p /opt/chroma-data

# 6. Lanzar ChromaDB en Docker
docker run -d --name chromadb \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /opt/chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  chromadb/chroma:1.3.5

echo "Setup de ChromaDB completado."
