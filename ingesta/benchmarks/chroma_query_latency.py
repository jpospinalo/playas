"""Latencias locales con vectores explícitos: no descarga ni calcula embeddings."""

from __future__ import annotations

import argparse
import math
import random
import time
import uuid
from pathlib import Path

from .common import emit, isolated_env, output_dir, sizes


def normalized_vector(generator):
    values = [generator.gauss(0, 1) for _ in range(768)]
    norm = math.sqrt(sum(v * v for v in values))
    return [v / norm for v in values]


def percentile(values, q):
    """Percentil con interpolación lineal sobre muestras ordenadas."""
    ordered = sorted(values)
    index = (len(ordered) - 1) * q
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)


def main(argv=None):
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=sizes, default=sizes("1000,5000,20000"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)
    if min(args.sizes) < 5:
        parser.error("Cada tamaño debe ser >=5 para consultar k=5")
    out = output_dir(args.out)
    os.environ.update(isolated_env(out))
    import chromadb
    from chromadb.config import Settings

    client = chromadb.HttpClient(
        host="127.0.0.1", port=8000, settings=Settings(anonymized_telemetry=False)
    )
    name = "bench_query_" + uuid.uuid4().hex
    generator = random.Random(args.seed)
    query_generator = random.Random(args.seed + 1)
    queries = [normalized_vector(query_generator) for _ in range(50)]
    result = {
        "benchmark": "chroma_query_latency",
        "collection": name,
        "seed": args.seed,
        "dimension": 768,
        "k": 5,
        "queries": 50,
        "rows": [],
        "collection_deleted": False,
        "latency_scope": "cliente HTTP + servidor; 5 consultas de calentamiento por escala, inserción excluida",
    }
    created = False
    try:
        collection = client.create_collection(
            name, metadata={"hnsw:space": "cosine"}, embedding_function=None
        )
        created = True
        inserted = 0
        for size in args.sizes:
            tick = time.perf_counter()
            while inserted < size:
                end = min(inserted + 256, size)
                collection.add(
                    ids=[f"vec_{i}" for i in range(inserted, end)],
                    embeddings=[normalized_vector(generator) for _ in range(inserted, end)],
                )
                inserted = end
            insertion = time.perf_counter() - tick
            if collection.count() != size:
                raise RuntimeError("El conteo de Chroma no coincide con la escala")
            for vector in queries[:5]:
                collection.query(query_embeddings=[vector], n_results=5, include=["distances"])
            latencies = []
            for vector in queries:
                tick = time.perf_counter()
                response = collection.query(
                    query_embeddings=[vector], n_results=5, include=["distances"]
                )
                latencies.append((time.perf_counter() - tick) * 1000)
                if len(response["ids"][0]) != 5:
                    raise RuntimeError("Chroma devolvió menos de k=5 vecinos")
            result["rows"].append(
                {
                    "size": size,
                    "insert_seconds": insertion,
                    "p50_ms": percentile(latencies, 0.50),
                    "p95_ms": percentile(latencies, 0.95),
                    "latencies_ms": latencies,
                }
            )
            emit(result, out, "chroma_query_latency.json")
    finally:
        if created:
            client.delete_collection(name)
            result["collection_deleted"] = True
        emit(result, out, "chroma_query_latency.json")


if __name__ == "__main__":
    main()
