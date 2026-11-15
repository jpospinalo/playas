"""Compone una variante OCR «solo páginas de baja confianza» sobre el bronce base.

Para cada página OCR de ``--todas`` escribe ``<doc>_<pag>.txt``: el texto de la
variante si existe (páginas bajas re-OCR), si no el del bronce base. Así
``evaluar_fase5.py --variante nombre=pagina:<dir>`` compara la variante completa
(base + reemplazos) contra el bronce base sobre las mismas páginas.

    python componer_variante.py --base <capas>/bronze --variante <dir> --todas paginas_ocr_todas.json --salida <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--variante", type=Path, required=True)
    parser.add_argument("--todas", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    args.salida.mkdir(parents=True, exist_ok=True)
    reemplazadas = 0
    for doc_id, paginas in json.loads(args.todas.read_text(encoding="utf-8")).items():
        bronce = (args.base / f"{doc_id}.txt").read_text(encoding="utf-8").split("\n\f\n")
        for n in paginas:
            nombre = f"{doc_id}_{n:03d}.txt"
            origen = args.variante / nombre
            if origen.exists():
                texto = origen.read_text(encoding="utf-8")
                reemplazadas += 1
            else:
                texto = bronce[n - 1]
            (args.salida / nombre).write_text(texto, encoding="utf-8")
    print(reemplazadas, "páginas reemplazadas")


if __name__ == "__main__":
    main()
