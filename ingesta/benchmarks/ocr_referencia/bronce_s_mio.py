"""Genera SOLO la capa bronze de ingest.offline sobre un directorio de PDFs.

Reproduce el bloque bronze de ``Layers.build`` (misma extracción, mismo
``.extraction.json`` y ``.quality.json``, guardado con ``Layers.save``) sin
calcular silver, gold, embeddings ni publicar en Chroma. No modifica el código
del pipeline. Uso (Linux, con Tesseract spa):

    python bronce_s_mio.py --entrada <raw> --layers-root <tmp>/capas --cache <tmp>/cache
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest.offline.extract import EXTRACTOR_VERSION, read_document  # noqa: E402
from ingest.offline.layers import Layers, canonical  # noqa: E402
from ingest.offline.quality import extraction_metrics  # noqa: E402

EXCLUIDOS = {
    "raw_pages",
    "original",
    "new_ocr_pages",
    "cpu_seconds",
    "ocr_seconds",
    "extraction_cache_hit",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--layers-root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    entrada = args.entrada.resolve()
    capas = Layers(args.layers_root.resolve(), sqlite3.connect(":memory:"), entrada)
    resumen = []
    for pdf in sorted(entrada.rglob("*.pdf")):
        inicio = time.monotonic()
        doc_id = hashlib.sha256(pdf.read_bytes()).hexdigest()
        if any(r["doc_id"] == doc_id for r in resumen):
            continue
        document = read_document(pdf, args.cache.resolve())
        extraction = {k: v for k, v in document.items() if k not in EXCLUIDOS}
        extraction.update(
            {
                "extractor": document.get("extractor", "PyMuPDF/Tesseract spa"),
                "original_file": Path(document["original_file"]).name,
                "chars_per_page": [len(re.sub(r"\s", "", p)) for p in document["raw_pages"]],
                "errors": [
                    {"page": p, "reason": "ocr_failed"} for p in document["ocr_failed_pages"]
                ],
            }
        )
        capas.save(
            doc_id,
            "bronze",
            [doc_id, EXTRACTOR_VERSION],
            {
                ".txt": document["original"].encode(),
                ".extraction.json": canonical(extraction),
                ".quality.json": canonical(extraction_metrics(document)),
            },
        )
        resumen.append(
            {
                "doc_id": doc_id,
                "ruta": pdf.relative_to(entrada).as_posix(),
                "paginas": len(document["raw_pages"]),
                "paginas_ocr": len(document.get("ocr_pages", [])),
                "segundos": round(time.monotonic() - inicio, 2),
            }
        )
        print(json.dumps(resumen[-1], ensure_ascii=False), flush=True)
    capas.persist()
    salida = args.layers_root.resolve() / "resumen_bronce.json"
    salida.write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
