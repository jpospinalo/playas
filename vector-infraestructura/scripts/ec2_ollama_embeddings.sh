#!/bin/bash
set -e

# Logs
exec > /var/log/user-data-ollama.log 2>&1

echo "==== INICIO SETUP OLLAMA ===="

# Actualizar sistema
apt-get update -y
apt-get upgrade -y

# Instalar Docker
apt-get install -y docker.io

# Habilitar y arrancar Docker
systemctl enable docker
systemctl start docker

echo "Esperando a que Docker esté listo..."
sleep 10

# Crear volumen persistente
docker volume create ollama

# Ejecutar contenedor
docker run -d \
  --name ollama \
  --restart always \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  -e OLLAMA_NUM_PARALLEL=1 \
  -e OLLAMA_CONTEXT_LENGTH=2048 \
  ollama/ollama

echo "Esperando a que Ollama levante..."
sleep 15

# Descargar el alias; el restaurador exige después versión/digest/perfil exactos.
# Si el registro cambia, el despliegue se detiene antes de restaurar o activar.
docker exec ollama ollama pull embeddinggemma:latest

echo "==== FIN SETUP OLLAMA ===="
