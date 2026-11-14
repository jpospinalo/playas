#!/usr/bin/env bash
# DESTRUYE el bucket del buzón del intake y TODO su contenido (irreversible).
#
#   ./destruir_bucket.sh <nombre-del-bucket> --confirmo-borrado
#
# No se ejecuta en ninguna automatización. Antes de usarlo, descargar lo que se quiera
# conservar:  aws s3 sync s3://<bucket>/ ./copia-bucket/
set -euo pipefail

BUCKET="${1:?Indica el nombre del bucket}"
if [[ "${2:-}" != "--confirmo-borrado" ]]; then
  echo "Borrado no confirmado. Repite con: $0 $BUCKET --confirmo-borrado" >&2
  exit 2
fi
CUENTA="$(aws sts get-caller-identity --query Account --output text)"
if [[ "$CUENTA" != "679786170402" || "$BUCKET" != atlas-demo-intake-* ]]; then
  echo "Solo se destruyen buckets atlas-demo-intake-* del sandbox 679786170402." >&2
  exit 3
fi
aws s3 rm "s3://$BUCKET" --recursive
aws s3api delete-bucket --bucket "$BUCKET"
echo "Bucket $BUCKET eliminado."
