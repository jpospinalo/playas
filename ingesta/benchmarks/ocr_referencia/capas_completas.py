"""Genera las capas bronze, silver y gold de ingest.offline sin embeddings ni Chroma.

Llama a ``Layers.build`` igual que ``Pipeline._run`` (misma configuración por
defecto ``legacy``/512, mismos overrides por doc_id, alias agrupados por SHA256),
pero sin ``ChromaPublisher`` ni embedder: ``Layers.build`` termina en gold. No
modifica el código del pipeline. Uso (Linux, con Tesseract spa, desde la raíz):

    python ingesta/benchmarks/ocr_referencia/capas_completas.py --entrada data/documents/raw \
        --layers-root <tmp>/capas --cache <tmp>/cache --extension pdf
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ingest.offline.extract import EXTRACTOR_VERSION, sha256_file  # noqa: E402
from ingest.offline.layers import STAGE_VERSIONS, Layers  # noqa: E402
from ingest.offline.pipeline import configuration, quality  # noqa: E402
from ingest.offline_embeddings import DIGEST  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--entrada", type=Path, required=True)
    parser.add_argument("--layers-root", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--extension", choices=["pdf", "md"], required=True)
    parser.add_argument("--overrides", type=Path, default=Path("data/metadata_overrides.csv"))
    parser.add_argument(
        "--cache-ocr-sembrada",
        action="store_true",
        help="Admite una caché que solo contenga ocr/ sembrado por sembrar_cache_ocr.py",
    )
    args = parser.parse_args()
    entrada = args.entrada.resolve()
    for ruta in (args.layers_root, args.cache):
        contenido = {p.name for p in ruta.iterdir()} if ruta.exists() else set()
        if ruta == args.cache and args.cache_ocr_sembrada:
            contenido -= {"ocr"}
        if contenido:
            parser.error(f"{ruta} debe estar vacío: la corrida es desde cero")
    overrides = []
    if args.overrides.exists():
        with args.overrides.open(encoding="utf-8-sig", newline="") as stream:
            overrides = list(csv.DictReader(stream))
    por_id = defaultdict(list)
    for directorio, _, nombres in os.walk(entrada):
        for nombre in sorted(nombres):
            ruta = Path(directorio) / nombre
            if ruta.suffix.lower() == "." + args.extension:
                por_id[sha256_file(ruta)].append(ruta.relative_to(entrada).as_posix())
    config = configuration()
    capas = Layers(args.layers_root.resolve(), sqlite3.connect(":memory:"), entrada)
    resumen = []
    for doc_id, alias in sorted(por_id.items()):
        alias = sorted(alias)
        inicio = time.monotonic()
        filas = [r for r in overrides if r.get("doc_id") == doc_id]
        document, metadata, cleaned, chunks, _ = capas.build(
            doc_id, alias, entrada, args.cache.resolve(), config, filas, DIGEST
        )
        resumen.append(
            {
                "doc_id": doc_id,
                "alias": alias,
                "paginas": len(document["raw_pages"]),
                "paginas_ocr": len(document.get("ocr_pages", [])),
                "chunks": len(chunks),
                "puertas_calidad": quality(document, cleaned, metadata),
                "segundos": round(time.monotonic() - inicio, 2),
            }
        )
        print(json.dumps(resumen[-1], ensure_ascii=False), flush=True)
    capas.persist()
    (args.layers_root / "resumen_corrida.json").write_text(
        json.dumps(
            {
                "extractor": EXTRACTOR_VERSION,
                "stage_versions": STAGE_VERSIONS,
                "configuracion": config,
                "extension": args.extension,
                "documentos": resumen,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
