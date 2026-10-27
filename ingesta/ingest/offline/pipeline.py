"""Lotes locales incrementales: SQLite, caché, reglas y publicación por doc_id."""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

from ..legal_metadata import FIELDS, SCHEMA_VERSION, apply_overrides, extract_legal_metadata
from ..offline_embeddings import DIGEST, DIMENSION, MODEL
from .chunks import CHUNKER_VERSION, HEADING, make_chunks
from .extract import (
    EXTRACTOR_VERSION,
    NORMALIZER_VERSION,
    clean_pages,
    cpu_time,
    read_document,
    sha256_file,
)

PIPELINE_VERSION = "offline-1"


def configuration(chunker="legacy", token_budget=512):
    return {
        "pipeline": PIPELINE_VERSION,
        "normalizer": NORMALIZER_VERSION,
        "extractor": EXTRACTOR_VERSION,
        "schema": SCHEMA_VERSION,
        "chunker": chunker,
        "chunker_version": CHUNKER_VERSION,
        "token_budget": token_budget,
        "legacy_size": 1000,
        "legacy_overlap": 200,
        "model": MODEL,
        "digest": DIGEST,
        "dimension": DIMENSION,
    }


def config_hash(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def simhash(text):
    weights = [0] * 64
    for word, count in Counter(re.findall(r"\w+", text.casefold())).items():
        value = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += count if value & (1 << bit) else -count
    return sum(1 << bit for bit, weight in enumerate(weights) if weight > 0)


def quality(document, cleaned, metadata):
    fields = metadata["campos"]
    return {
        "schema": set(fields) == set(FIELDS),
        "identity": fields["corporacion"]["valor"] is not None,
        "characters": document["original"].count("\ufffd") / max(1, len(document["original"]))
        < 0.002,
        "ocr": not document["ocr_failed_pages"],
        "sections": bool(HEADING.search(cleaned["text"])),
        "size": len(cleaned["text"]) >= 200,
    }


class Pipeline:
    def __init__(
        self,
        root,
        state,
        cache,
        embedder,
        publisher,
        chunker="legacy",
        token_budget=512,
        enforce=False,
        overrides=None,
    ):
        self.root, self.state, self.cache = Path(root).resolve(), Path(state), Path(cache)
        self.config = configuration(chunker, token_budget)
        self.hash = config_hash(self.config)
        self.state.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.state / "manifest.sqlite")
        self.db.executescript(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY,build_hash TEXT,artifact TEXT,status TEXT,text_hash TEXT,fingerprint TEXT); CREATE TABLE IF NOT EXISTS paths (path TEXT PRIMARY KEY,doc_id TEXT); CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY,report TEXT);"
        )
        row = self.db.execute("SELECT value FROM settings WHERE key='config'").fetchone()
        if row and row[0] != self.hash:
            raise ValueError("Cambio de versión/modelo: usa estado y colección nuevos")
        self.db.execute("INSERT OR REPLACE INTO settings VALUES ('config',?)", (self.hash,))
        self.db.commit()
        self.embedder, self.publisher, self.enforce = embedder, publisher, enforce
        self.overrides = []
        if overrides and Path(overrides).exists():
            with Path(overrides).open(encoding="utf-8-sig", newline="") as stream:
                self.overrides = list(csv.DictReader(stream))

    def _files(self):
        if not self.root.is_dir():
            raise FileNotFoundError("La raíz de documentos debe existir")
        result = []

        def fail(error):
            raise error

        for directory, _, names in os.walk(self.root, onerror=fail):
            for name in sorted(names):
                path = Path(directory) / name
                if path.suffix.lower() in {".pdf", ".md", ".txt"}:
                    if not path.resolve().is_relative_to(self.root):
                        raise ValueError("Enlace fuera de la raíz; no sincronizar")
                    result.append(path)
        return sorted(result)

    def run(self, add=None):
        start = time.monotonic()
        previous = dict(self.db.execute("SELECT path,doc_id FROM paths"))
        if add:
            path = Path(add).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError("add requiere archivo existente dentro de input-dir")
            files = [path]
            mapping = dict(previous)
        else:
            files = self._files()
            mapping = {}
        for path in files:
            mapping[path.relative_to(self.root).as_posix()] = sha256_file(path)
        by_id = defaultdict(list)
        for path, doc_id in mapping.items():
            by_id[doc_id].append(path)
        report = {
            "utc": dt.datetime.now(dt.UTC).isoformat(),
            "configuration": self.config,
            "config_hash": self.hash,
            "files": len(mapping),
            "documents": len(by_id),
            "processed": 0,
            "skipped": 0,
            "deleted": 0,
            "renamed": 0,
            "new_ocr_pages": 0,
            "llm_api_calls": 0,
            "errors": [],
            "documents_detail": [],
        }
        before_new = self.embedder.new_embeddings
        for doc_id, aliases in sorted(by_id.items()):
            aliases = sorted(aliases)
            rows = [r for r in self.overrides if r.get("doc_id") == doc_id]
            build_hash = hashlib.sha256(
                (self.hash + json.dumps(rows, sort_keys=True) + str(self.enforce)).encode()
            ).hexdigest()
            old = self.db.execute(
                "SELECT build_hash,artifact,status FROM documents WHERE doc_id=?", (doc_id,)
            ).fetchone()
            old_aliases = sorted(path for path, identity in previous.items() if identity == doc_id)
            if old and old[0] == build_hash and aliases == old_aliases and old[2] != "error":
                report["skipped"] += 1
                continue
            started = time.process_time()
            started_local_cpu = cpu_time()
            try:
                document = read_document(self.root / aliases[0], self.cache)
                # Metadatos y referencias SIEMPRE antes de quitar mobiliario.
                metadata = apply_overrides(
                    extract_legal_metadata(document["original"]), rows, doc_id, document["original"]
                )
                cleaned = clean_pages(document["raw_pages"])
                gates = quality(document, cleaned, metadata)
                doc_type = (
                    "normativa" if "normativa" in Path(aliases[0]).parts else "jurisprudencia"
                )
                chunks = make_chunks(
                    doc_id,
                    cleaned,
                    metadata,
                    aliases[0],
                    doc_type,
                    self.config["chunker"],
                    self.config["token_budget"],
                )
                for chunk in chunks:
                    chunk["metadata"]["source_aliases"] = json.dumps(aliases, ensure_ascii=False)
                    chunk["metadata"]["duplicate_exact"] = len(aliases) > 1
                quarantined = self.enforce and not all(gates.values())
                new_before = self.embedder.new_embeddings
                if not quarantined:
                    vectors = self.embedder.embed([c["document"] for c in chunks])
                    self.publisher.upsert_document(doc_id, chunks, vectors)
                else:
                    self.publisher.delete_document(doc_id)
                artifact = {
                    "doc_id": doc_id,
                    "sha256": document["sha256"],
                    "paths": aliases,
                    "text_sha256": hashlib.sha256(cleaned["text"].encode()).hexdigest(),
                    "metadata": metadata,
                    "gates": gates,
                    "quarantined": quarantined,
                    "ocr_pages": document["ocr_pages"],
                    "ocr_failed_pages": document["ocr_failed_pages"],
                    "pages": cleaned["pages"],
                    "offset_map": cleaned["offset_map"],
                    "removed_furniture_keys": cleaned["removed_furniture_keys"],
                    "original_file": document["original_file"],
                    "original": document["original"],
                    "normalized": cleaned["text"],
                    "chunks": chunks,
                }
                target = self.state / "documents" / (doc_id + ".json.gz")
                target.parent.mkdir(exist_ok=True)
                temporary = target.with_suffix(".tmp")
                with gzip.open(temporary, "wt", encoding="utf-8") as stream:
                    json.dump(artifact, stream, ensure_ascii=False)
                temporary.replace(target)
                status = "quarantined" if quarantined else "published"
                self.db.execute(
                    "INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?)",
                    (
                        doc_id,
                        build_hash,
                        str(target),
                        status,
                        artifact["text_sha256"],
                        str(simhash(cleaned["text"])),
                    ),
                )
                self.db.execute("DELETE FROM paths WHERE doc_id=?", (doc_id,))
                self.db.executemany(
                    "INSERT OR REPLACE INTO paths VALUES (?,?)", [(p, doc_id) for p in aliases]
                )
                self.db.commit()
                report["processed"] += 1
                report["renamed"] += int(bool(old_aliases) and aliases != old_aliases)
                report["new_ocr_pages"] += document["new_ocr_pages"]
                report["documents_detail"].append(
                    {
                        "doc_id": doc_id,
                        "path": aliases[0],
                        "chunks": len(chunks),
                        "new_embeddings": self.embedder.new_embeddings - new_before,
                        "cpu_seconds_local": cpu_time() - started_local_cpu,
                        "cpu_seconds_python": time.process_time() - started,
                        "cpu_seconds_extract": document["cpu_seconds"],
                        "quarantined": quarantined,
                        "gates": gates,
                    }
                )
                print(
                    f"{aliases[0]}: {len(chunks)} chunks; embeddings nuevos {self.embedder.new_embeddings - new_before}",
                    flush=True,
                )
            except Exception as exc:
                report["errors"].append(
                    {
                        "doc_id": doc_id,
                        "path": aliases[0],
                        "error": type(exc).__name__,
                        "reason": str(exc)[:200],
                    }
                )
                print(f"ERROR documento {aliases[0]}: {type(exc).__name__}: {exc}", flush=True)
        # No procesar eliminaciones si falló algún documento: conservar el último
        # estado publicable y permitir reanudar las escrituras parciales.
        if not report["errors"]:
            active = set(by_id)
            removed = {identity for identity in previous.values()} - active
            for doc_id in removed:
                self.publisher.delete_document(doc_id)
                self.db.execute("UPDATE documents SET status='deleted' WHERE doc_id=?", (doc_id,))
                self.db.execute("DELETE FROM paths WHERE doc_id=?", (doc_id,))
                report["deleted"] += 1
            self.db.commit()
        report["new_embeddings"] = self.embedder.new_embeddings - before_new
        report["seconds"] = time.monotonic() - start
        report["embeddings"] = self.embedder.manifest()
        self._reports()
        (self.state / "run_manifest.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.db.execute("INSERT INTO runs(report) VALUES (?)", (json.dumps(report),))
        self.db.commit()
        return report

    def _reports(self):
        docs = []
        for doc_id, artifact, status, text_hash, fingerprint in self.db.execute(
            "SELECT doc_id,artifact,status,text_hash,fingerprint FROM documents WHERE status!='deleted'"
        ):
            with gzip.open(artifact, "rt", encoding="utf-8") as stream:
                item = json.load(stream)
            docs.append(
                {
                    "doc_id": doc_id,
                    "status": status,
                    "text_hash": text_hash,
                    "fingerprint": int(fingerprint),
                    "artifact": item,
                }
            )
        with (self.state / "review_queue.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=["doc_id", "paths", "campo", "razon"])
            writer.writeheader()
            for doc in docs:
                item = doc["artifact"]
                for field, value in item["metadata"]["campos"].items():
                    if value["valor"] is None:
                        writer.writerow(
                            {
                                "doc_id": doc["doc_id"],
                                "paths": "|".join(item["paths"]),
                                "campo": field,
                                "razon": value["razon"],
                            }
                        )
                for conflict in item["metadata"]["conflictos"]:
                    writer.writerow(
                        {
                            "doc_id": doc["doc_id"],
                            "paths": "|".join(item["paths"]),
                            "campo": conflict["campo"],
                            "razon": "conflicto_reglas",
                        }
                    )
        exact = defaultdict(list)
        near, buckets, seen = [], defaultdict(list), set()
        for doc in docs:
            exact[doc["text_hash"]].extend(
                {"doc_id": doc["doc_id"], "path": p} for p in doc["artifact"]["paths"]
            )
            for band in range(4):
                bucket = (band, (doc["fingerprint"] >> (band * 16)) & 65535)
                for other in buckets[bucket]:
                    pair = tuple(sorted([doc["doc_id"], other["doc_id"]]))
                    distance = (doc["fingerprint"] ^ other["fingerprint"]).bit_count()
                    if (
                        pair not in seen
                        and distance <= 3
                        and doc["text_hash"] != other["text_hash"]
                    ):
                        near.append({"documents": pair, "hamming_distance": distance})
                        seen.add(pair)
                buckets[bucket].append(doc)
        duplicate_report = {
            "exact": [items for items in exact.values() if len(items) > 1],
            "near_simhash64": near,
            "deleted_source_files": 0,
        }
        (self.state / "duplicates.json").write_text(
            json.dumps(duplicate_report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        coverage = {
            field: sum(
                d["artifact"]["metadata"]["campos"][field]["valor"] is not None for d in docs
            )
            for field in FIELDS
        }
        (self.state / "metadata_coverage.json").write_text(
            json.dumps(
                {
                    "documents": len(docs),
                    "coverage": coverage,
                    "quarantine_if_enforced": [
                        d["doc_id"] for d in docs if not all(d["artifact"]["gates"].values())
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def export(self, path):
        digest = hashlib.sha256()
        count = 0
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # El export se obtiene del manifiesto, no de colecciones ajenas.
        with gzip.open(path, "wt", encoding="utf-8") as stream:
            stream.write(
                json.dumps({"__manifest__": {**self.config, "config_hash": self.hash}}) + "\n"
            )
            for (artifact,) in self.db.execute(
                "SELECT artifact FROM documents WHERE status='published' ORDER BY doc_id"
            ):
                with gzip.open(artifact, "rt", encoding="utf-8") as source:
                    item = json.load(source)
                records = item["chunks"]
                vectors = self.embedder.embed([r["document"] for r in records])
                for record, vector in zip(records, vectors, strict=True):
                    row = {
                        "id": record["id"],
                        "document": record["document"],
                        "metadata": record["metadata"],
                        "embedding": vector,
                    }
                    body = json.dumps(row, ensure_ascii=False, allow_nan=False)
                    stream.write(body + "\n")
                    digest.update((body + "\n").encode())
                    count += 1
        (path.parent / (path.name + ".manifest.json")).write_text(
            json.dumps(
                {
                    "configuration": self.config,
                    "records": count,
                    "records_sha256": digest.hexdigest(),
                    "compressed_sha256": sha256_file(path),
                },
                indent=2,
            )
        )
        return count

    def close(self):
        self.db.close()
