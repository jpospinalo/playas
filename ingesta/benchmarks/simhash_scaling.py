"""Mide SimHash real y reproduce exactamente el bucle de candidatos de Pipeline._reports."""

from __future__ import annotations

import argparse
import hashlib
import math
import random
import time
from collections import defaultdict
from pathlib import Path

from .common import emit, output_dir, sizes


def fit_exponent(counts, seconds):
    """Pendiente OLS log(tiempo) frente a log(tamaño); no implica causalidad."""
    if len(counts) != len(seconds) or len(counts) < 2:
        raise ValueError("Se requieren al menos dos pares tamaño/tiempo")
    if any(not math.isfinite(v) or v <= 0 for v in (*counts, *seconds)):
        raise ValueError("Tamaños y tiempos deben ser finitos positivos")
    x, y = [math.log(v) for v in counts], [math.log(v) for v in seconds]
    mean_x, mean_y = sum(x) / len(x), sum(y) / len(y)
    denominator = sum((v - mean_x) ** 2 for v in x)
    if not denominator:
        raise ValueError("Se necesitan tamaños distintos")
    return sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y, strict=True)) / denominator


def near_duplicates(docs):
    """Copia literal del bucle near de _reports; omite CSV y agrupación exacta."""
    near, buckets, seen = [], defaultdict(list), set()
    for doc in docs:
        for band in range(4):
            bucket = (band, (doc["fingerprint"] >> (band * 16)) & 65535)
            for other in buckets[bucket]:
                pair = tuple(sorted([doc["doc_id"], other["doc_id"]]))
                distance = (doc["fingerprint"] ^ other["fingerprint"]).bit_count()
                if pair not in seen and distance <= 3 and doc["text_hash"] != other["text_hash"]:
                    near.append({"documents": pair, "hamming_distance": distance})
                    seen.add(pair)
            buckets[bucket].append(doc)
    return near


def main(argv=None):
    from ingest.offline.pipeline import simhash

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=sizes, default=sizes("1000,5000,20000,50000"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--workload", choices=["diverse", "clustered"], default="diverse")
    args = parser.parse_args(argv)
    out = output_dir(args.out)
    generator = random.Random(args.seed)
    # Prefijos anidados entre escalas; la generación queda fuera del cronómetro.
    texts = []
    for index in range(max(args.sizes)):
        words = " ".join(f"palabra{generator.getrandbits(64):016x}" for _ in range(40))
        texts.append(
            ("playa acceso público " * 200 if args.workload == "clustered" else "")
            + words
            + f" {index}"
        )
    rows = []
    for size in args.sizes:
        started = time.perf_counter()
        docs = [
            {
                "doc_id": f"{index:016x}",
                "text_hash": hashlib.sha256(text.encode()).hexdigest(),
                "fingerprint": simhash(text),
            }
            for index, text in enumerate(texts[:size])
        ]
        fingerprint_seconds = time.perf_counter() - started
        started = time.perf_counter()
        near = near_duplicates(docs)
        elapsed = time.perf_counter() - started
        rows.append(
            {
                "size": size,
                "detection_seconds": elapsed,
                "fingerprint_seconds": fingerprint_seconds,
                "near_pairs": len(near),
            }
        )
        del near
        # Guarda cada escala: el caso concentrado puede agotar memoria como el original.
        emit(
            {
                "benchmark": "simhash_scaling",
                "workload": args.workload,
                "seed": args.seed,
                "rows": rows,
            },
            out,
            "simhash_scaling.json",
        )
    exponent = (
        fit_exponent([r["size"] for r in rows], [r["detection_seconds"] for r in rows])
        if len(rows) > 1
        else None
    )
    emit(
        {
            "benchmark": "simhash_scaling",
            "rows": rows,
            "workload": args.workload,
            "seed": args.seed,
            "exponent": exponent,
            "quadratic_observed": 1.8 <= exponent <= 2.2 if exponent is not None else None,
            "interpretation": "Criterio descriptivo: pendiente entre 1.8 y 2.2; depende de colisiones y escala, no demuestra complejidad asintótica.",
            "algorithm": "ingest.offline.pipeline.simhash importado; bucle near de Pipeline._reports replicado exactamente, sin lectura de artefactos ni CSV. El pipeline compara documentos; aquí recibe fingerprints de textos sintéticos tipo chunk.",
        },
        out,
        "simhash_scaling.json",
    )


if __name__ == "__main__":
    main()
