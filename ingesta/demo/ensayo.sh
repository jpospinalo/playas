#!/usr/bin/env bash
# Ensayo completo del guion de DEMO.md, sin intervención, con tiempos por paso.
# Deja el registro en ensayo_<N>.log (sirve de plan B: ejecución grabada).
#   ./ensayo.sh 1
source "$(dirname "$0")/comun.sh"
N="${1:-1}"
LOG="$AQUI/ensayo_${N}.log"
PREGUNTA="¿Qué trámite deben seguir las solicitudes de concesión portuaria según el Decreto 474 de 2015?"
NUEVO="$AQUI/archivos/Decreto 474 de 2015 - concesiones portuarias.pdf"
DEFECTUOSO="$AQUI/archivos/Escaneo degradado.pdf"
exec > >(tee "$LOG") 2>&1

paso() { echo; echo "=== Paso $1: $2  [$(date -u +%H:%M:%S)]"; T0=$(date +%s); }
fin()  { echo "--- duración: $(( $(date +%s) - T0 )) s"; }
esperar_s3() {  # espera a que el objeto salga de inbox/ y aparezca en su destino
  local prefijo
  for i in $(seq 1 120); do
    if [[ -z "$(aws s3 ls "s3://$BUCKET/inbox/" | grep -v ' PRE ' | grep -v ' 0 ' || true)" ]]; then
      for prefijo in processed review rejected; do
        :
      done
      return 0
    fi
    sleep 5
  done
  error "El documento no salió del buzón en 10 min"; return 1
}

echo "Ensayo $N del demo — $(date -u '+%Y-%m-%d %H:%M') UTC"
paso 0 "Arranque (start_demo.sh)"; "$AQUI/start_demo.sh"; fin
paso 0b "Línea base en frío (reset_demo.sh --frio)"; "$AQUI/reset_demo.sh" --frio; fin
paso 1 "Estado inicial"; "$AQUI/status.sh"; fin
paso 2 "Pregunta ANTES de subir el documento nuevo"; "$AQUI/preguntar.sh" "$PREGUNTA"; fin
paso 3 "Subir el escaneado nuevo"; "$AQUI/upload.sh" "$NUEVO"; fin
paso 4 "Procesamiento en vivo (fases y decisión)"; esperar_s3; "$AQUI/ultima_ficha.sh"
fin
paso 5 "Pregunta DESPUÉS: aparece el decreto con su cita"; "$AQUI/preguntar.sh" "$PREGUNTA"; fin
paso 6 "Documento defectuoso (escaneo degradado)"; "$AQUI/upload.sh" "$DEFECTUOSO"; esperar_s3; "$AQUI/ultima_ficha.sh"
"$AQUI/status.sh"; fin
paso 7 "Volver al estado inicial (reset_demo.sh)"; "$AQUI/reset_demo.sh"; fin
echo; echo "Ensayo $N terminado [$(date -u +%H:%M:%S)]. Registro: $LOG"
