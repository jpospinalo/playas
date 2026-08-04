#!/usr/bin/env bash
# Construye las imágenes del backend y frontend y las sube a ECR.
# Uso: ./scripts/push_images.sh [TAG]
# Ejemplo: ./scripts/push_images.sh v1.2.0
set -euo pipefail

TAG="${1:-latest}"
REGION="${AWS_DEFAULT_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_BASE="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"

# Obtener URLs de ECR y del ALB desde los outputs de Terraform
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

# NEXT_PUBLIC_API_URL se hornea en el JS en tiempo de build (no se lee en runtime).
# Sin este build-arg, el frontend cae al fallback "http://localhost:8080" y todo
# fetch desde el navegador falla con "Failed to fetch" fuera de tu máquina.
echo "▶ Construyendo frontend → ${FRONTEND_REPO}:${TAG} (NEXT_PUBLIC_API_URL=${ALB_URL})"
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
