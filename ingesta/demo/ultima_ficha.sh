#!/usr/bin/env bash
# Muestra, en lenguaje claro, la decisión y las fases del último documento procesado.
source "$(dirname "$0")/comun.sh"
en_worker "sudo python3 /opt/atlas/playas/ingesta/demo/worker/ultima_ficha.py"
