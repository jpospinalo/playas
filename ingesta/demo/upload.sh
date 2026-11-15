#!/usr/bin/env bash
# Sube un PDF al buzón S3; el worker lo procesa en segundos (ver ./status.sh).
source "$(dirname "$0")/comun.sh"
ARCHIVO="${1:?Uso: ./upload.sh <archivo.pdf>}"
[[ -f "$ARCHIVO" ]] || { error "No existe $ARCHIVO"; exit 2; }
comprobar_cuenta
aws s3 cp "$ARCHIVO" "s3://$BUCKET/inbox/$(basename "$ARCHIVO")" --only-show-errors
ok "Subido a s3://$BUCKET/inbox/$(basename "$ARCHIVO")"
echo "  Seguir el procesamiento en vivo:  ./seguir.sh"
