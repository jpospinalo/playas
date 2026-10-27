"""Corpus PDF sintético; se esperan avisos de duplicados y casi duplicados."""

from __future__ import annotations

import argparse
import hashlib
import random
import shutil
import string
from pathlib import Path

from .common import emit, inside, output_dir, positive


def build_corpus(src, n, out, seed=0):
    import fitz

    src = Path(src).resolve()
    if not src.is_dir():
        raise ValueError("--src debe ser un directorio existente")
    positive(n)
    sources = sorted(
        (p for p in src.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.relative_to(src).as_posix(),
    )
    if not sources:
        raise ValueError("No se encontraron PDFs")
    out = output_dir(out, [src])
    raw = inside(out, "raw")
    if raw.exists() and any(raw.iterdir()):
        raise ValueError("raw debe estar vacío para evitar mezclar escalas")
    raw.mkdir(exist_ok=True)
    generator = random.Random(seed)
    copies = []
    for index in range(n):
        source = sources[index % len(sources)]
        salt = f"SAL-{index:08d}-{generator.getrandbits(32):08x}"
        target = inside(out, raw / f"{index:08d}_{source.stem}.pdf")
        with fitz.open(source) as pdf:
            if pdf.needs_pass or not len(pdf):
                raise ValueError(f"PDF cifrado o vacío: {source}")
            page_salts = []
            for page in pdf:
                # La sal va en el cuerpo, entre dos líneas anteriores y dos
                # posteriores. Palabras aleatorias por página evitan que el
                # limpiador la confunda con mobiliario repetido (normaliza cifras).
                # El bloque sigue bajo 80 caracteres sin espacios para no evitar
                # el OCR de páginas escaneadas que antes lo necesitaban.
                words = ["".join(generator.choices(string.ascii_lowercase, k=8)) for _ in range(5)]
                page_salt = f"{salt} {words[2]}"
                text = "\n".join([*words[:2], page_salt, *words[3:]])
                rect = page.rect
                fontsize = min(5, rect.width / 45, rect.height / 30)
                page.insert_text(
                    (rect.width * 0.15, rect.height * 0.45),
                    text,
                    fontsize=fontsize,
                    color=(0, 0, 0),
                    overlay=True,
                )
                if salt not in page.get_text():
                    raise ValueError(f"No se pudo insertar la sal en {source}")
                page_salts.append(page_salt)
            pdf.save(target, garbage=4, deflate=True, no_new_id=True)
        copies.append(
            {
                "index": index,
                "source": source.relative_to(src).as_posix(),
                "file": target.relative_to(out).as_posix(),
                "salt": salt,
                "page_salts": page_salts,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    metadata = []
    for source in sorted(src.rglob("*")):
        if source.is_file() and source.suffix.lower() == ".csv":
            target = inside(out, raw / source.relative_to(src))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            metadata.append(target.relative_to(out).as_posix())
    return emit(
        {
            "benchmark": "synth_corpus",
            "documents": n,
            "seed": seed,
            "source_root": str(src),
            "copies": copies,
            "metadata_csv": metadata,
            "warnings": [
                "Se esperan duplicados/casi duplicados sintéticos.",
                "La sal del cuerpo usa palabras distintas por página y queda fuera de las primeras/últimas dos líneas; no garantiza chunks únicos porque otros chunks no la contienen y el OCR puede omitirla.",
                "Los CSV se copian sin alterar: los nombres sintéticos pueden no coincidir con sus filas.",
            ],
        },
        out,
        "synth_corpus.json",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True)
    parser.add_argument("--n", type=positive, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    build_corpus(args.src, args.n, args.out, args.seed)


if __name__ == "__main__":
    main()
