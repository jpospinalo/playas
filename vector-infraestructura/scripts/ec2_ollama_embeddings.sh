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

# Imagen de Ollama 0.40.13 validada con la entrega Gold A.
OLLAMA_IMAGE='ollama/ollama@sha256:b2f0122c476bc9fe7ce679d8bb4bd555351e25e2554eefb156f61cb0a89cf429'

# Ejecutar contenedor
docker run -d \
  --name ollama \
  --restart always \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  -e OLLAMA_NUM_PARALLEL=1 \
  -e OLLAMA_CONTEXT_LENGTH=2048 \
  "${OLLAMA_IMAGE}"

echo "Esperando a que Ollama levante..."
sleep 15

# Descargar el alias; el restaurador exige después versión/digest/perfil exactos.
# Si el registro cambia, el despliegue se detiene antes de restaurar o activar.
docker exec ollama ollama pull embeddinggemma:latest

echo "==== FIN SETUP OLLAMA ===="
