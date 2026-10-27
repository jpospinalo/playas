"""Corpus PDF sintético; se esperan avisos de duplicados y casi duplicados."""

from __future__ import annotations

import argparse
import hashlib
import random
import shutil
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
            for page in pdf:
                # Una línea corta conserva el umbral <80 en páginas escaneadas.
                page.insert_text((4, 9), salt, fontsize=5, color=(0, 0, 0), overlay=True)
                if salt not in page.get_text():
                    raise ValueError(f"No se pudo insertar la sal en {source}")
            pdf.save(target, garbage=4, deflate=True, no_new_id=True)
        copies.append(
            {
                "index": index,
                "source": source.relative_to(src).as_posix(),
                "file": target.relative_to(out).as_posix(),
                "salt": salt,
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
                "La sal no garantiza chunks únicos: limpieza/OCR pueden omitirla y otros chunks no la contienen.",
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
