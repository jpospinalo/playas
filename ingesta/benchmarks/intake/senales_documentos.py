"""FASE 4: señales de la política del intake para los 53 PDF medidos frente a U.

Calcula, desde unas capas ya generadas (por defecto runA) y los PDF originales,
las mismas señales que el intake usa para decidir, y les añade la etiqueta del
veredicto por documento frente a U y su conjunto (ajuste o validación). No usa U
para calcular ninguna señal: U solo aporta la etiqueta.

    python -I -X utf8 senales_documentos.py --capas ../ocr_referencia/trabajo/corridas/runA/pdf/capas \
        --raw C:/Users/Migue/r --salida trabajo/senales_53.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1]))

from ingest.offline.policy import senales_documento  # noqa: E402

FIABILIDAD = (
    BASE.parent / "ocr_referencia" / "resultados" / "fiabilidad" / "fiabilidad_por_documento.csv"
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--capas", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    pdfs = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in args.raw.rglob("*.pdf")}
    filas = []
    with FIABILIDAD.open(encoding="utf-8") as stream:
        for fila in csv.DictReader(stream):
            doc_id = fila["doc_id"] if len(fila["doc_id"]) == 64 else None
            doc_id = doc_id or next(d for d in pdfs if d.startswith(fila["doc_id"]))
            senales = senales_documento(args.capas, doc_id, pdfs[doc_id], fila["categoria"])
            filas.append(
                {
                    "slug": fila["slug"],
                    "doc_id": doc_id,
                    "categoria": fila["categoria"],
                    "conjunto": fila["conjunto"],
                    "veredicto_u": fila["veredicto_final"],
                    "senales": senales,
                }
            )
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    args.salida.write_text(json.dumps(filas, ensure_ascii=False, indent=1), encoding="utf-8")
    print(len(filas), "documentos")


if __name__ == "__main__":
    main()
