#!/bin/bash
set -e

# Logs
exec > /var/log/user-data-chromadb.log 2>&1

# Evita que apt/needrestart se detengan esperando confirmacion interactiva
# (Ubuntu 24.04 trae needrestart activo por defecto, que en modo interactivo
# pregunta que servicios reiniciar tras instalar paquetes).
export DEBIAN_FRONTEND=noninteractive
export NEEDRESTART_MODE=a

echo "==== INICIO SETUP CHROMADB ===="

# 1. Refrescar el indice de paquetes (sin upgrade completo del sistema: esta
# instancia es de un solo proposito y vida corta — se recrea en cada
# despliegue — y el AMI ya se selecciona como la mas reciente disponible en
# chromadb.tf, asi que un `apt-get upgrade -y` completo solo agrega minutos
# sin aportar nada a lo que esta maquina hace).
apt-get update -y

# 2. Paquetes necesarios: solo Docker. `build-essential` (gcc/g++/make, ~80
# paquetes, ~550MB) no es necesario — esta maquina solo ejecuta una imagen
# Docker ya construida (chromadb/chroma:1.3.5), no compila nada.
apt-get install -y docker.io

# 3. Habilitar y arrancar Docker
systemctl enable docker
systemctl start docker

echo "Esperando a que Docker esté listo..."
sleep 10

# 4. Directorio persistente
mkdir -p /opt/chroma-data

# 5. Ejecutar ChromaDB
docker run -d --name chromadb \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /opt/chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  chromadb/chroma:1.3.5

echo "==== FIN SETUP CHROMADB ===="
