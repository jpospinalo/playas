#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1

echo "=== Inicio setup Ollama: $(date) ==="

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

# 2. Instalar Docker
apt-get ${APT_OPTS} install -y docker.io

# 3. Habilitar Docker
# --no-block evita un deadlock conocido donde systemctl start cuelga
# cuando se invoca desde dentro de cloud-final.service
systemctl enable docker
systemctl start --no-block docker

# 4. Esperar que el Docker daemon esté listo antes de correr contenedores
echo "Esperando Docker daemon..."
for i in $(seq 1 30); do
  if docker info >/dev/null 2>&1; then
    echo "Docker listo."
    break
  fi
  echo "  intento ${i}/30..."
  sleep 3
done

# 5. Crear volumen y lanzar Ollama
docker volume create ollama

docker run -d \
  --name ollama \
  --restart always \
  -p 11434:11434 \
  -v ollama:/root/.ollama \
  ollama/ollama

# 6. Esperar que el servicio Ollama esté listo dentro del contenedor
echo "Esperando que Ollama este listo..."
for i in $(seq 1 30); do
  if docker exec ollama ollama list >/dev/null 2>&1; then
    echo "Ollama listo."
    break
  fi
  echo "  intento ${i}/30..."
  sleep 5
done

# 7. Descargar el modelo
echo "Descargando modelo embeddinggemma..."
docker exec ollama ollama pull embeddinggemma:latest

echo "=== Setup Ollama completado: $(date) ==="
