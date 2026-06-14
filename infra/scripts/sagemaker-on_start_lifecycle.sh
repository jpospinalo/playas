# ——————
#!/bin/bash
set -euo pipefail

DATA_ROOT="/home/ec2-user/SageMaker/docker_data"
DOCKER_JSON="/etc/docker/daemon.json"

# 1 Crear carpeta persistente (si no existe)
sudo mkdir -p "$DATA_ROOT"
sudo chown -R root:root "$DATA_ROOT"

# 2 Reescribir daemon.json combinando data-root + runtime nvidia
sudo bash -c "cat > $DOCKER_JSON" <<'EOF'
{
  "data-root": "/home/ec2-user/SageMaker/docker_data",
  "runtimes": {
    "nvidia": {
      "path": "nvidia-container-runtime",
      "args": []
    }
  }
}
EOF

# 3 Reiniciar Docker con esta configuración
sudo systemctl daemon-reload || true
sudo systemctl stop docker || sudo service docker stop || true
sudo systemctl start docker || sudo service docker start
sudo systemctl enable docker || true

# ————