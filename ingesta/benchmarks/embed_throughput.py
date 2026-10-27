"""Throughput de /api/embed local con textos gold y prefijos únicos por solicitud."""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
import uuid
from pathlib import Path

from .common import emit, output_dir, positive, rate


def request(path, body=None):
    if path not in {"/api/tags", "/api/embed"}:
        raise ValueError("Endpoint no permitido")
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "http://127.0.0.1:11434" + path,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    # No usar proxies del entorno para un servicio local.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=180
    ) as response:
        return json.load(response)


def gold_texts(root, limit):
    texts = []
    for path in sorted(Path(root).rglob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                if not line.strip():
                    continue
                text = json.loads(line)["page_content"]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(f"Texto gold vacío o inválido: {path}")
                texts.append(text)
                if len(texts) == limit:
                    return texts
    if not texts:
        raise ValueError("--gold debe contener JSONL v2 con page_content")
    return texts


def main(argv=None):
    from ingest.offline_embeddings import DIGEST, DIMENSION, MODEL, validate_vector

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--n", type=positive, default=300)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--num-thread", type=positive)
    parser.add_argument("--batch", type=positive, default=16)
    args = parser.parse_args(argv)
    out = output_dir(args.out, [args.gold])
    originals = gold_texts(args.gold, args.n)
    if not any(
        m["name"] == MODEL and m["digest"] == DIGEST for m in request("/api/tags")["models"]
    ):
        raise ValueError("El digest local de embeddinggemma no coincide con el pin del pipeline")
    salt = uuid.uuid4().hex
    texts = [
        f"SAL-{salt}-{index:08d}\n{text}"
        for index, text in ((i, originals[i % len(originals)]) for i in range(args.n))
    ]
    batches = []
    started = time.perf_counter()
    for offset in range(0, len(texts), args.batch):
        batch = texts[offset : offset + args.batch]
        body = {"model": MODEL, "input": batch, "truncate": False, "keep_alive": "10m"}
        if args.num_thread is not None:
            body["options"] = {"num_thread": args.num_thread}
        tick = time.perf_counter()
        vectors = request("/api/embed", body).get("embeddings", [])
        if len(vectors) != len(batch):
            raise ValueError("Ollama devolvió un lote incompleto")
        for vector in vectors:
            validate_vector(vector, DIMENSION)
        batches.append({"count": len(batch), "seconds": time.perf_counter() - tick})
    elapsed = time.perf_counter() - started
    chars = sum(map(len, texts))
    emit(
        {
            "benchmark": "embed_throughput",
            "model": MODEL,
            "digest": DIGEST,
            "dimension": DIMENSION,
            "embeddings": len(texts),
            "characters": chars,
            "source_chunks": len(originals),
            "salt": salt,
            "num_thread": args.num_thread,
            "batch": args.batch,
            "wall_seconds": elapsed,
            "embeddings_per_second": rate(len(texts), elapsed),
            "chars_per_second": rate(chars, elapsed),
            "batches": batches,
            "cache": "sin caché cliente; prefijo UUID único en cada texto",
            "warmup": "sin calentamiento separado; incluye carga inicial si el modelo estaba descargado de memoria",
        },
        out,
        "embed_throughput.json",
    )


if __name__ == "__main__":
    main()
