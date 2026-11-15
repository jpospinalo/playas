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
# Solo reconfigura buckets existentes con prefijo y etiquetas del demo, sin política.
# Para destruirlo: ver destruir_bucket.sh (no se ejecuta solo; borra datos).
set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
CUENTA="$(aws sts get-caller-identity --query Account --output text)"
BUCKET="${1:-atlas-demo-intake-${CUENTA}}"

if [[ "$CUENTA" != "679786170402" ]]; then
  echo "Cuenta inesperada ($CUENTA): este script es solo para el sandbox 679786170402." >&2
  exit 3
fi

ERROR=$(mktemp)
trap 'rm -f "$ERROR"' EXIT
NUEVO=1
if aws s3api head-bucket --bucket "$BUCKET" 2>"$ERROR"; then
  if [[ "$BUCKET" != atlas-demo-intake-* ]]; then
    echo "Bucket ajeno al demo: no se modifica $BUCKET." >&2
    exit 2
  fi
  for par in Proyecto=atlas-playas Uso=intake-demo; do
    valor=$(aws s3api get-bucket-tagging --bucket "$BUCKET"       --query "TagSet[?Key=='${par%%=*}'].Value | [0]" --output text)
    if [[ "$valor" != "${par#*=}" ]]; then
      echo "Etiquetas del demo ausentes o incorrectas; no se modifica el bucket" >&2
      exit 2
    fi
  done
  NUEVO=0
  # Fallar también si no podemos leer la política; solo NoSuchBucketPolicy es admisible.
  if aws s3api get-bucket-policy --bucket "$BUCKET" > /dev/null 2>"$ERROR"; then
    echo "El bucket tiene una política; no se modifica." >&2
    exit 2
  elif ! grep -q 'NoSuchBucketPolicy' "$ERROR"; then
    cat "$ERROR" >&2
    exit 2
  fi
  echo "Bucket del demo verificado: $BUCKET; se reaplica la configuración."
else
  if ! grep -Eq '404|NoSuchBucket|Not Found' "$ERROR"; then
    cat "$ERROR" >&2
    exit 2
  fi
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
if [[ "$NUEVO" == 1 ]]; then  # un bucket existente ya tiene (y conserva) sus etiquetas
  aws s3api put-bucket-tagging --bucket "$BUCKET"     --tagging 'TagSet=[{Key=Proyecto,Value=atlas-playas},{Key=Uso,Value=intake-demo}]'
fi
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-bucket-lifecycle-configuration --bucket "$BUCKET" \
  --lifecycle-configuration '{"Rules":[{"ID":"expirar-versiones-no-actuales","Status":"Enabled","Filter":{"Prefix":""},"NoncurrentVersionExpiration":{"NoncurrentDays":7}}]}'
for prefijo in inbox processed review rejected; do
  aws s3api put-object --bucket "$BUCKET" --key "$prefijo/" >/dev/null
done

echo "Comprobación:"
aws s3api get-public-access-block --bucket "$BUCKET" --query 'PublicAccessBlockConfiguration' --output text
aws s3api get-bucket-encryption --bucket "$BUCKET" \
  --query 'ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm' --output text
echo "Sin política de bucket. Listo: s3://$BUCKET/inbox/"
