"""PASO 3: prepara la auditoría visual ciega de los documentos con peor veredicto.

Para cada documento elige las 6 páginas evaluables con más ediciones frente a U y
las reparte alternadas: rangos 1, 3, 5 para el auditor A y 2, 4, 6 para el B.
Cada hoja tiene la imagen a 200 dpi y dos textos (pipeline y U) con nombres
X/Y en orden aleatorio (semilla fija); la clave queda en un archivo aparte.

    python -I preparar_auditoria.py --docs 922e d6b7 9c01 5beb 7c8c 98ef \
        --capas trabajo/corridas/runA/pdf/capas --salida trabajo/auditoria
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from pathlib import Path

import fitz

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

from comun import csv_leer  # noqa: E402

DESC = BASE / "entrada" / "descomprimido"
ORIGINALES = BASE.parent / "fidelidad" / "trabajo" / "originales"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", nargs="+", required=True, help="sufijos de slug")
    parser.add_argument("--capas", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    parser.add_argument("--semilla", type=int, default=20261110)
    args = parser.parse_args()
    capas = args.capas if args.capas.is_absolute() else BASE / args.capas
    salida = args.salida if args.salida.is_absolute() else BASE / args.salida
    mapping = {r["slug"]: r for r in csv_leer(DESC / "mapping.csv")}
    paginas = csv_leer(BASE / "trabajo" / "fiabilidad" / "paginas.csv")
    rnd = random.Random(args.semilla)
    clave = []
    for sufijo in args.docs:
        slug = next(s for s in mapping if s.endswith(sufijo))
        filas = [p for p in paginas if p["slug"] == slug and p["estado"] == "evaluada"]
        filas.sort(key=lambda p: (-int(p["ediciones_caracteres"]), int(p["pagina"])))
        r = mapping[slug]
        bronce = (capas / "bronze" / (r["sha256"] + ".txt")).read_text(encoding="utf-8")
        hojas_s = bronce.split("\n\f\n")
        partes = re.split(
            r"<!-- página (\d+) -->",
            (DESC / "texto" / r["categoria"] / (slug + ".md")).read_text(encoding="utf-8"),
        )
        hojas_u = {int(partes[i]): partes[i + 1] for i in range(1, len(partes), 2)}
        pdf = fitz.open(ORIGINALES / (r["sha256"][:12] + ".pdf"))
        for rango, p in enumerate(filas[:6], 1):
            auditor = "A" if rango % 2 else "B"
            n = int(p["pagina"])
            nombre = f"{sufijo}_p{n:03d}"
            carpeta = salida / auditor
            carpeta.mkdir(parents=True, exist_ok=True)
            pdf[n - 1].get_pixmap(dpi=200).save(carpeta / (nombre + ".png"))
            textos = {"pipeline": hojas_s[n - 1], "U": hojas_u[n]}
            orden = ["pipeline", "U"]
            rnd.shuffle(orden)
            for etiqueta, fuente in zip("XY", orden, strict=True):
                (carpeta / f"{nombre}_{etiqueta}.txt").write_text(
                    textos[fuente].strip() + "\n", encoding="utf-8"
                )
            clave.append(
                {
                    "auditor": auditor,
                    "hoja": nombre,
                    "slug": slug,
                    "pagina": n,
                    "tipo_pagina": p["tipo_pagina"],
                    "cer": p["cer"],
                    "X": orden[0],
                    "Y": orden[1],
                }
            )
    with (salida / "clave.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(clave[0]))
        w.writeheader()
        w.writerows(clave)
    for a in "AB":
        hojas = sorted(c["hoja"] for c in clave if c["auditor"] == a)
        (salida / a / "hojas.json").write_text(json.dumps(hojas, indent=1), encoding="utf-8")
    print(len(clave), "hojas")


if __name__ == "__main__":
    main()
