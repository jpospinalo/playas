#!/usr/bin/env bash
# Crea el bucket privado del buzón del intake (compatible con LabRole: sin IAM nuevo).
#
#   ./crear_bucket.sh [nombre-del-bucket]
#
# Por defecto: atlas-demo-intake-<cuenta>. Región us-east-1. El bucket queda:
#   - con bloqueo total de acceso público,
#   - con cifrado por defecto SSE-S3 (AES256),
#   - con propiedad de objetos «BucketOwnerEnforced» (sin ACL),
#   - sin política de bucket (el acceso es el del rol LabRole / LabInstanceProfile),
#   - con los prefijos inbox/, processed/, review/ y rejected/.
# Es idempotente: si el bucket ya existe y es de la cuenta, solo reaplica la configuración.
# Para destruirlo: ver destruir_bucket.sh (no se ejecuta solo; borra datos).
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CUENTA="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${1:-atlas-demo-intake-${CUENTA}}"

if [[ "$CUENTA" != "679786170402" ]]; then
  echo "Cuenta inesperada ($CUENTA): este script es solo para el sandbox 679786170402." >&2
  exit 3
fi

if aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  echo "El bucket $BUCKET ya existe; se reaplica la configuración."
else
  echo "Creando $BUCKET en $REGION..."
  if [[ "$REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET" --region "$REGION" \
      --create-bucket-configuration "LocationConstraint=$REGION" >/dev/null
  fi
fi

aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"},"BucketKeyEnabled":true}]}'
aws s3api put-bucket-ownership-controls --bucket "$BUCKET" \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'
aws s3api put-bucket-tagging --bucket "$BUCKET" \
  --tagging 'TagSet=[{Key=Proyecto,Value=atlas-playas},{Key=Uso,Value=intake-demo}]'
for prefijo in inbox processed review rejected; do
  aws s3api put-object --bucket "$BUCKET" --key "$prefijo/" >/dev/null
done

echo "Comprobación:"
aws s3api get-public-access-block --bucket "$BUCKET" --query 'PublicAccessBlockConfiguration' --output text
aws s3api get-bucket-encryption --bucket "$BUCKET" \
  --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm' --output text
if aws s3api get-bucket-policy --bucket "$BUCKET" >/dev/null 2>&1; then
  echo "ATENCIÓN: el bucket tiene una política; revisarla." >&2
  exit 2
fi
echo "Sin política de bucket. Listo: s3://$BUCKET/inbox/"
