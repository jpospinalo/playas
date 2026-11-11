"""Siembra la caché de OCR con las páginas OCR de una corrida Linux de referencia.

Permite regenerar el bronce en una máquina sin Tesseract cuando el cambio que se
mide NO toca el OCR (p. ej. extracción de páginas digitales): las páginas que el
extractor enviaría a Tesseract se sirven desde la caché con el texto y la
confianza que produjo Tesseract en la corrida de referencia. La clave usa la
``EXTRACTOR_VERSION`` actual, igual que ``extract._ocr``. No sirve para medir
cambios del OCR; para eso hace falta Tesseract.

    python -I sembrar_cache_ocr.py --referencia trabajo/corridas/runA/pdf/capas \
        --cache <tmp>/cache
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest.offline.extract import EXTRACTOR_VERSION, atomic_text  # noqa: E402


def sembrar(referencia: Path, cache: Path) -> int:
    sembradas = 0
    for extraccion in sorted((referencia / "bronze").glob("*.extraction.json")):
        doc_id = extraccion.name.removesuffix(".extraction.json")
        datos = json.loads(extraccion.read_text(encoding="utf-8"))
        paginas = (referencia / "bronze" / (doc_id + ".txt")).read_text(encoding="utf-8")
        paginas = paginas.split("\n\f\n")
        confianzas = datos.get("ocr_confidence", {})
        for numero in datos.get("ocr_pages", []):
            destino = cache / "ocr" / f"{doc_id}-{numero - 1}-{EXTRACTOR_VERSION}.txt"
            destino.parent.mkdir(parents=True, exist_ok=True)
            atomic_text(destino, paginas[numero - 1])
            atomic_text(
                destino.with_suffix(".confidence.json"),
                json.dumps(confianzas.get(str(numero))),
            )
            sembradas += 1
    return sembradas


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--referencia", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    if args.cache.exists() and any(args.cache.iterdir()):
        parser.error(f"{args.cache} debe estar vacío")
    print(sembrar(args.referencia, args.cache), "páginas OCR sembradas para", EXTRACTOR_VERSION)


if __name__ == "__main__":
    main()
