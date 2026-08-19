#!/usr/bin/env bash
# Construye las imágenes del backend y frontend y las sube a ECR.
# Uso: ./scripts/push_images.sh [TAG]
# Ejemplo: ./scripts/push_images.sh v1.2.0
set -euo pipefail

TAG="${1:-latest}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Obtener URLs de ECR y la URL pública del ALB desde los outputs de Terraform
BACKEND_REPO=$(terraform -chdir="$(dirname "$0")/.." output -raw ecr_backend_url)
FRONTEND_REPO=$(terraform -chdir="$(dirname "$0")/.." output -raw ecr_frontend_url)
ALB_URL=$(terraform -chdir="$(dirname "$0")/.." output -raw alb_url)

echo "▶ Login en ECR..."
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "${ECR_BASE}"

# Directorio raíz del proyecto rag/
RAG_DIR="$(dirname "$0")/../.."

echo "▶ Construyendo backend → ${BACKEND_REPO}:${TAG}"
docker build \
  -f "${RAG_DIR}/docker/Dockerfile.backend" \
  -t "${BACKEND_REPO}:${TAG}" \
  "${RAG_DIR}"

echo "▶ Construyendo frontend → ${FRONTEND_REPO}:${TAG}"
# NEXT_PUBLIC_API_URL se inyecta en build-time (Next.js la inlinea en el bundle
# del cliente) — sin esto el frontend queda apuntando al valor por defecto
# (http://localhost:8080) y el navegador del usuario no puede alcanzarlo.
docker build \
  --build-arg NEXT_PUBLIC_API_URL="${ALB_URL}" \
  -f "${RAG_DIR}/docker/Dockerfile.frontend" \
  -t "${FRONTEND_REPO}:${TAG}" \
  "${RAG_DIR}"

echo "▶ Subiendo imágenes a ECR..."
docker push "${BACKEND_REPO}:${TAG}"
docker push "${FRONTEND_REPO}:${TAG}"

echo "✓ Imágenes publicadas con tag '${TAG}'"
echo "  Backend:  ${BACKEND_REPO}:${TAG}"
echo "  Frontend: ${FRONTEND_REPO}:${TAG}"
