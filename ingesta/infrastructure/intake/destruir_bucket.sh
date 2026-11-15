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
# Una página contiene como máximo 1000 versiones y marcadores en total.
# La CLI construye el JSON para conservar claves con espacios, comillas, etc.
LOTE="$(mktemp)"
trap 'rm -f -- "$LOTE"' EXIT
PAGINA=(--bucket "$BUCKET" --no-paginate --max-keys 1000)
while true; do
  RESUMEN="$(aws s3api list-object-versions "${PAGINA[@]}" \
    --query '[IsTruncated, length(Versions || `[]`), length(DeleteMarkers || `[]`)]' --output text)"
  read -r TRUNCADA VERSIONES MARCADORES <<< "$RESUMEN"
  if (( VERSIONES + MARCADORES == 0 )); then
    break
  fi
  # Guardar los cursores antes de borrar la página. El centinela conserva los
  # saltos de línea finales que pueda contener la clave del cursor.
  if [[ "$TRUNCADA" == True || "$TRUNCADA" == true ]]; then
    CLAVE="$(aws s3api list-object-versions "${PAGINA[@]}" --query NextKeyMarker --output text && printf '.')"
    CLAVE="${CLAVE%.}"
    CLAVE="${CLAVE%$'\n'}"
    VERSION="$(aws s3api list-object-versions "${PAGINA[@]}" --query NextVersionIdMarker --output text)"
    if [[ -z "$CLAVE" || "$CLAVE" == None || -z "$VERSION" || "$VERSION" == None ]]; then
      echo "Paginación de versiones sin cursor; se conserva el bucket." >&2
      exit 4
    fi
  fi
  aws s3api list-object-versions "${PAGINA[@]}" \
    --query '{Objects: [Versions, DeleteMarkers][].{Key: Key, VersionId: VersionId}, Quiet: `true`}' --output json > "$LOTE"
  ERRORES="$(aws s3api delete-objects --bucket "$BUCKET" --delete "file://$LOTE" \
    --query 'length(Errors || `[]`)' --output text)"
  if [[ "$ERRORES" != 0 ]]; then
    echo "No se pudieron borrar todas las versiones; se conserva el bucket." >&2
    exit 4
  fi
  if [[ "$TRUNCADA" != True && "$TRUNCADA" != true ]]; then
    break
  fi
  PAGINA=(--bucket "$BUCKET" --no-paginate --max-keys 1000 --key-marker "$CLAVE" --version-id-marker "$VERSION")
done
# Verificar desde el principio, también por si hubo escrituras durante el borrado.
RESTOS="$(aws s3api list-object-versions --bucket "$BUCKET" --no-paginate --max-keys 1 \
  --query 'length([Versions, DeleteMarkers][])' --output text)"
if [[ "$RESTOS" != 0 ]]; then
  echo "Quedan versiones o marcadores; se conserva el bucket." >&2
  exit 4
fi
aws s3api delete-bucket --bucket "$BUCKET"
echo "Bucket $BUCKET eliminado."
