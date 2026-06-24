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


def parse_args():
    parser = argparse.ArgumentParser(description="Import JSONL.GZ into ChromaDB")
    parser.add_argument("file", help="Path to the .jsonl.gz export file")
    parser.add_argument("--host", default=None, help="ChromaDB host (overrides manifest)")
    parser.add_argument("--port", type=int, default=None, help="ChromaDB port (overrides manifest)")
    parser.add_argument("--collection", default=None, help="Collection name (overrides manifest)")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help=f"Upsert batch size (default {BATCH_SIZE})")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate the collection before importing")
    return parser.parse_args()


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


def main():
    args = parse_args()
    path = Path(args.file)

    if not path.exists():
        print(f"ERROR: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading {path} …")
    manifest, records = load_records(path)

    if manifest:
        print(f"  Manifest: {manifest}")

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
        print(f"  Deleting collection '{collection_name}' …")
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    existing = collection.count()
    print(f"  Collection '{collection_name}' — existing docs: {existing}")

    total = len(records)
    print(f"\nImporting {total} documents in batches of {args.batch_size} …\n")

    imported = 0
    errors = 0
    start = time.time()

    for i in range(0, total, args.batch_size):
        batch = records[i : i + args.batch_size]
        try:
            upsert_batch(collection, batch)
            imported += len(batch)
        except Exception as e:
            errors += len(batch)
            print(f"  ERROR on batch {i}–{i+len(batch)}: {e}", file=sys.stderr)

        pct = imported / total * 100
        elapsed = time.time() - start
        rate = imported / elapsed if elapsed > 0 else 0
        print(f"\r  {imported}/{total} ({pct:.1f}%)  {rate:.0f} docs/s  errors={errors}", end="", flush=True)

    print(f"\n\nDone. {imported} imported, {errors} errors in {time.time()-start:.1f}s")
    print(f"Collection '{collection_name}' now has {collection.count()} documents.")


if __name__ == "__main__":
    main()
