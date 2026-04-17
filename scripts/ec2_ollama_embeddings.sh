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

# 2. Instalar Docker
apt-get install -y docker.io
systemctl enable --now docker

# 3. Crear volumen y lanzar Ollama
docker volume create ollama

docker run -d \
  --name ollama \
  --restart always \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

# 4. Esperar a que el servicio Ollama esté listo antes de descargar el modelo
echo "Esperando a que Ollama este listo..."
until docker exec ollama ollama list >/dev/null 2>&1; do
    sleep 3
done
echo "Ollama listo. Descargando modelo embeddinggemma..."

docker exec ollama ollama pull embeddinggemma:latest

echo "Setup de Ollama completado."
