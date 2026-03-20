# 1. Actualizar sistema
sudo apt-get update && sudo apt-get upgrade -y

# 2. Paquete de compilación (opcional, pero útil)
sudo apt-get install -y build-essential

# 3. Instalar Docker
sudo apt-get install -y docker.io
sudo systemctl enable --now docker

# 4. Dar permisos al usuario ubuntu para usar Docker sin sudo
sudo usermod -aG docker ubuntu
# (Luego de esto: CERRAR SESIÓN y volver a entrar, o usar `newgrp docker`)

# 5. Directorio para datos persistentes de Chroma
sudo mkdir -p /opt/chroma-data

# 6. Lanzar ChromaDB en Docker
sudo docker run -d --name chromadb \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /opt/chroma-data:/chroma/chroma \
  -e IS_PERSISTENT=TRUE \
  chromadb/chroma:1.3.5
