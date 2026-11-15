#!/usr/bin/env bash
# Muestra en vivo las fases y la decisión del worker (Ctrl+C para salir).
source "$(dirname "$0")/comun.sh"
en_worker -t "sudo journalctl -u atlas-intake -f -o cat"
