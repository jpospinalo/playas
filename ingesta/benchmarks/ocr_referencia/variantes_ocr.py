"""Experimento FASE 5: OCR de las páginas escaneadas con zoom y --psm variables.

Replica ``ingest.offline.extract._ocr`` (mismo idioma, mismo armado de líneas a
partir del TSV, parseo sin comillas) cambiando solo el zoom del render y --psm.
No escribe capas ni caché del pipeline. Uso (Linux con Tesseract spa):

    python variantes_ocr.py --entrada <raw> --paginas paginas.json --zoom 2 --psm 3 --salida <dir>

``paginas.json``: {"<sha256>": [pagina, ...]} con páginas 1-indexadas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import subprocess
from pathlib import Path

import fitz


def ocr(page, zoom, psm):
    image = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False).tobytes("png")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", "spa", "--psm", str(psm), "tsv"],
        input=image,
        capture_output=True,
        timeout=300,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        check=True,
    )
    rows = csv.DictReader(
        io.StringIO(result.stdout.decode("utf-8", "replace")),
        delimiter="\t",
        quoting=csv.QUOTE_NONE,
    )
    lines, confidences = {}, []
    for row in rows:
        word = (row.get("text") or "").strip()
        if not word:
            continue
        key = tuple(row.get(k) for k in ("page_num", "block_num", "par_num", "line_num"))
        lines.setdefault(key, []).append(word)
        try:
            value = float(row["conf"])
            if math.isfinite(value) and value >= 0:
                confidences.append(value)
        except (ValueError, KeyError):
            pass
    text = "\n".join(" ".join(words) for words in lines.values())
    return text, (sum(confidences) / len(confidences) if confidences else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--paginas", type=Path, required=True)
    parser.add_argument("--zoom", type=float, required=True)
    parser.add_argument("--psm", type=int, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    objetivo = json.loads(args.paginas.read_text(encoding="utf-8"))
    pdfs = {hashlib.sha256(p.read_bytes()).hexdigest(): p for p in args.entrada.rglob("*.pdf")}
    args.salida.mkdir(parents=True, exist_ok=True)
    confianza = {}
    for digest, paginas in sorted(objetivo.items()):
        doc = fitz.open(pdfs[digest])
        for n in paginas:
            texto, conf = ocr(doc[n - 1], args.zoom, args.psm)
            (args.salida / f"{digest}_{n:03d}.txt").write_text(texto, encoding="utf-8")
            confianza[f"{digest}_{n:03d}"] = conf
        print(digest[:12], len(paginas), flush=True)
    (args.salida / "confianza.json").write_text(json.dumps(confianza, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
