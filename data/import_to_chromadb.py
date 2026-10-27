#!/usr/bin/env python3
"""
Import a JSONL.GZ export file into a remote ChromaDB server.

Usage:
    python3 import_to_chromadb.py <file.jsonl.gz> [--host HOST] [--port PORT]
                                  [--collection NAME] [--batch-size N]
"""

import argparse
import gzip
import json
import sys
import time
from pathlib import Path

import chromadb

BATCH_SIZE = 100


def positive_int(value):
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return parsed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Import JSONL.GZ into ChromaDB")
    parser.add_argument("file", help="Path to the .jsonl.gz export file")
    parser.add_argument("--host", default=None, help="ChromaDB host (overrides manifest)")
    parser.add_argument("--port", type=int, default=None, help="ChromaDB port (overrides manifest)")
    parser.add_argument("--collection", default=None, help="Collection name (overrides manifest)")
    parser.add_argument(
        "--batch-size",
        type=positive_int,
        default=BATCH_SIZE,
        help=f"Upsert batch size (default {BATCH_SIZE})",
    )
    parser.add_argument("--attempts", type=positive_int, choices=(1, 2), default=2)
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate the collection before importing",
    )
    return parser.parse_args(argv)


def load_records(path: Path):
    manifest = None
    records = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if "__manifest__" in obj:
                manifest = obj["__manifest__"]
            else:
                records.append(obj)
    return manifest, records


def upsert_batch(collection, batch):
    ids = [r["id"] for r in batch]
    documents = [r["document"] for r in batch]
    metadatas = [r.get("metadata", {}) for r in batch]
    embeddings = [r["embedding"] for r in batch]
    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )


def import_records(collection, records, batch_size=BATCH_SIZE, attempts=2):
    """Upsert idempotente, reintentos acotados y conciliación de IDs/conteo."""
    if batch_size <= 0 or attempts not in (1, 2):
        raise ValueError("batch-size positivo y attempts 1 o 2 requeridos")
    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        raise ValueError("IDs duplicados en el snapshot")
    before = collection.count()
    present = set()
    for offset in range(0, len(ids), batch_size):
        present.update(collection.get(ids=ids[offset : offset + batch_size], include=[])["ids"])
    for offset in range(0, len(records), batch_size):
        for attempt in range(attempts):
            try:
                upsert_batch(collection, records[offset : offset + batch_size])
                break
            except Exception:
                if attempt + 1 == attempts:
                    raise RuntimeError(
                        f"Falló lote en posición {offset}; {attempts} intentos"
                    ) from None
                time.sleep(0.5)
    observed = set()
    for offset in range(0, len(ids), batch_size):
        observed.update(collection.get(ids=ids[offset : offset + batch_size], include=[])["ids"])
    expected = before + len(set(ids) - present)
    if observed != set(ids) or collection.count() != expected:
        raise RuntimeError("No concuerdan IDs o conteo final del snapshot")
    return expected


def main(argv=None):
    args = parse_args(argv)
    path = Path(args.file)

    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {path} …")
    manifest, records = load_records(path)

    if manifest:
        print("  Manifest leído (valores no impresos)")

    host = args.host or (manifest or {}).get("chroma_host", "localhost")
    port = args.port or (manifest or {}).get("chroma_port", 8000)
    collection_name = args.collection or (manifest or {}).get("collection", "default")

    print(f"\nConnecting to ChromaDB at {host}:{port} …")
    client = chromadb.HttpClient(host=host, port=port)

    try:
        client.heartbeat()
        print("  Connection OK")
    except Exception as e:
        print(f"ERROR: Could not connect to ChromaDB: {e}", file=sys.stderr)
        sys.exit(1)

    if args.recreate:
        print("ERROR: --recreate deshabilitado; usa un nombre de colección nuevo", file=sys.stderr)
        return 1

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    existing = collection.count()
    print(f"  Collection '{collection_name}' — existing docs: {existing}")

    total = len(records)
    print(f"\nImporting {total} documents in batches of {args.batch_size} …\n")

    start = time.time()
    try:
        final = import_records(collection, records, args.batch_size, args.attempts)
    except Exception as exc:
        print(
            f"ERROR: importación incompleta ({type(exc).__name__}); no reconciliada",
            file=sys.stderr,
        )
        return 1
    print(f"Done. {total} reconciliados; conteo final {final}; {time.time() - start:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
