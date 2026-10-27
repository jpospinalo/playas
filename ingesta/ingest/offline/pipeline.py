"""Lotes locales incrementales: SQLite, caché, reglas y publicación por doc_id."""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from contextlib import contextmanager, nullcontext
from functools import partial
from pathlib import Path

from ..legal_metadata import FIELDS, SCHEMA_VERSION
from ..offline_embeddings import DIGEST, DIMENSION, MODEL
from .chunks import CHUNKER_VERSION, HEADING
from .extract import (
    EXTRACTOR_VERSION,
    NORMALIZER_VERSION,
    cpu_time,
    sha256_file,
)
from .layers import STAGE_VERSIONS, Layers, canonical, signature
from .storage import atomic_bytes, atomic_stream, guard_output, input_scope, writer_lock

PIPELINE_VERSION = "offline-1"


@contextmanager
def document_savepoint(db):
    # Las capas en disco y Chroma se pueden reintentar; sus marcas solo se
    # confirman junto al manifiesto después de persistir el artefacto completo.
    db.execute("SAVEPOINT document")
    try:
        yield
    except BaseException:
        db.execute("ROLLBACK TO document")
        db.execute("RELEASE document")
        raise
    else:
        db.execute("RELEASE document")


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
    # Las versiones de etapas invalidan capas, no la identidad de la colección.
    stable = {
        k: v
        for k, v in config.items()
        if k not in {"normalizer", "extractor", "schema", "chunker_version"}
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def legacy_config_hashes(config):
    variants = (config, {**config, "extractor": "pymupdf-tesseract-spa-1"})
    return {
        hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest() for value in variants
    }


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
        layers_root=None,
        from_stage=None,
    ):
        self.root = Path(root).resolve()
        self.state = guard_output(state, self.root)
        self.cache = guard_output(cache, self.root)
        self.layers_root = guard_output(layers_root or self.state / "layers", self.root)
        self.from_stage = from_stage
        self.config = configuration(chunker, token_budget)
        if getattr(embedder, "is_fake", False):
            if not getattr(publisher, "collection_name", "").startswith("bench_"):
                raise ValueError("Embeddings ficticios requieren colección bench_")
            self.config.update(model=embedder.model, digest=embedder.digest)
        self.hash = config_hash(self.config)
        with input_scope(self.root), writer_lock(self.state, self.layers_root, self.cache):
            self.state.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(guard_output(self.state / "manifest.sqlite"))
            self.db.executescript(
                "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT); CREATE TABLE IF NOT EXISTS documents (doc_id TEXT PRIMARY KEY,build_hash TEXT,artifact TEXT,status TEXT,text_hash TEXT,fingerprint TEXT); CREATE TABLE IF NOT EXISTS paths (path TEXT PRIMARY KEY,doc_id TEXT); CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY,report TEXT);"
            )
            compatibility = self.hash
            row = self.db.execute("SELECT value FROM settings WHERE key='compatibility'").fetchone()
            legacy = self.db.execute("SELECT value FROM settings WHERE key='config'").fetchone()
            incompatible = row and row[0] != compatibility
            if (
                not row
                and legacy
                and legacy[0] not in legacy_config_hashes(self.config) | {compatibility}
            ):
                incompatible = True
            if incompatible:
                self.db.close()
                raise ValueError("Cambio de versión/modelo: usa estado y colección nuevos")
            self.db.execute(
                "INSERT OR REPLACE INTO settings VALUES ('compatibility',?)", (compatibility,)
            )
            self.db.execute("INSERT OR REPLACE INTO settings VALUES ('config',?)", (self.hash,))
            self.db.commit()
            self.embedder, self.publisher, self.enforce = embedder, publisher, enforce
            self.layers = Layers(self.layers_root, self.db, self.root)
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

    def run(self, add=None, from_stage=None):
        with (
            input_scope(self.root),
            writer_lock(self.state, self.layers_root, self.cache),
            getattr(self.publisher, "publish_phase", nullcontext)(),
        ):
            return self._run(add, from_stage or self.from_stage)

    def _run(self, add=None, from_stage=None):
        start = time.monotonic()
        previous = dict(self.db.execute("SELECT path,doc_id FROM paths"))
        if from_stage in {"silver", "gold", "embeddings"} and not previous:
            catalog = self.layers_root / "catalog.json"
            if catalog.exists():
                previous = {
                    path: doc_id
                    for doc_id, paths in json.loads(catalog.read_text(encoding="utf-8"))
                    .get("documentos", {})
                    .items()
                    for path in paths
                }
        reuse_mapping = from_stage in {"silver", "gold", "embeddings"} and bool(previous)
        if add:
            path = Path(add).resolve()
            if not path.is_relative_to(self.root) or not path.is_file():
                raise ValueError("add requiere archivo existente dentro de input-dir")
            files = [path]
            mapping = dict(previous)
        elif reuse_mapping:
            files, mapping = [], dict(previous)
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
        timings = {
            name: {"seconds": 0.0, "calls": 0}
            for name in (
                "extraction",
                "ocr",
                "cleaning",
                "metadata",
                "chunking",
                "duplicates",
                "embeddings",
                "chroma_publish",
                "quality_report",
            )
        }

        def measure(name, operation):
            started = time.monotonic()
            try:
                return operation()
            finally:
                timings[name]["seconds"] += time.monotonic() - started
                timings[name]["calls"] += 1

        before_new = self.embedder.new_embeddings
        for doc_id, aliases in sorted(by_id.items()):
            aliases = sorted(aliases)
            rows = [r for r in self.overrides if r.get("doc_id") == doc_id]
            build_hash = signature([self.hash, rows, self.enforce, STAGE_VERSIONS])
            old = self.db.execute(
                "SELECT build_hash,artifact,status FROM documents WHERE doc_id=?", (doc_id,)
            ).fetchone()
            old_aliases = sorted(path for path, identity in previous.items() if identity == doc_id)
            started = time.process_time()
            started_local_cpu = cpu_time()
            try:
                with document_savepoint(self.db):
                    self.layers.restore(doc_id, from_stage)
                    document, metadata, cleaned, chunks, changed = self.layers.build(
                        doc_id,
                        aliases,
                        self.root,
                        self.cache,
                        self.config,
                        rows,
                        getattr(self.embedder, "digest", DIGEST),
                        from_stage,
                        measure,
                    )
                    timings["ocr"]["seconds"] += document.get("ocr_seconds", 0)
                    timings["ocr"]["calls"] += document.get("new_ocr_pages", 0)
                    timings["extraction"]["seconds"] = max(
                        0, timings["extraction"]["seconds"] - document.get("ocr_seconds", 0)
                    )
                    gates = quality(document, cleaned, metadata)
                    quarantined = self.enforce and not all(gates.values())
                    embedding_inputs = [
                        self.layers.artifacts(doc_id, "gold"),
                        getattr(self.embedder, "digest", DIGEST),
                    ]
                    vectors_valid = getattr(self.embedder, "has_vectors", lambda texts: True)(
                        [c["document"] for c in chunks]
                    )
                    embeddings_changed = (
                        not self.layers.valid(doc_id, "embeddings", embedding_inputs)
                        or not vectors_valid
                    )
                    if (
                        old
                        and not changed
                        and not embeddings_changed
                        and old[0] == build_hash
                        and aliases == old_aliases
                        and old[2] != "error"
                    ):
                        report["skipped"] += 1
                        continue
                    for chunk in chunks:
                        chunk["metadata"]["source_aliases"] = json.dumps(
                            aliases, ensure_ascii=False
                        )
                        chunk["metadata"]["duplicate_exact"] = len(aliases) > 1
                    new_before = self.embedder.new_embeddings
                    if not quarantined:
                        vectors = measure(
                            "embeddings",
                            partial(self.embedder.embed, [c["document"] for c in chunks]),
                        )
                        measure(
                            "chroma_publish",
                            partial(self.publisher.upsert_document, doc_id, chunks, vectors),
                        )
                        self.layers.save(
                            doc_id,
                            "embeddings",
                            embedding_inputs,
                            {
                                ".json": canonical(
                                    {
                                        "doc_id": doc_id,
                                        "digest": getattr(self.embedder, "digest", DIGEST),
                                        "dimension": DIMENSION,
                                        "cache_keys": [
                                            c["metadata"]["embedding_cache_key"] for c in chunks
                                        ],
                                    }
                                )
                            },
                        )
                    else:
                        measure("chroma_publish", partial(self.publisher.delete_document, doc_id))
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
                    atomic_bytes(target, gzip.compress(canonical(artifact), mtime=0))
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
                measure("chroma_publish", partial(self.publisher.delete_document, doc_id))
                self.db.execute("UPDATE documents SET status='deleted' WHERE doc_id=?", (doc_id,))
                self.db.execute("DELETE FROM paths WHERE doc_id=?", (doc_id,))
                report["deleted"] += 1
            self.db.commit()
        report["new_embeddings"] = self.embedder.new_embeddings - before_new
        report["seconds"] = time.monotonic() - start
        report["embeddings"] = self.embedder.manifest()
        measure("duplicates", self._reports)
        self.layers.persist()
        active_mapping = defaultdict(list)
        for path, doc_id in self.db.execute("SELECT path,doc_id FROM paths ORDER BY path"):
            active_mapping[doc_id].append(path)
        retired = [
            row[0]
            for row in self.db.execute(
                "SELECT doc_id FROM documents WHERE status='deleted' ORDER BY doc_id"
            )
        ]
        # Un reinicio fallido con estado nuevo debe conservar las rutas recuperables.
        if not (reuse_mapping and report["errors"]):
            atomic_bytes(
                self.layers_root / "catalog.json",
                canonical({"documentos": dict(active_mapping), "retirados": retired}),
            )
        from .quality import report_quality

        quality_report = measure(
            "quality_report",
            lambda: report_quality(
                self.layers_root,
                self.state,
                self.cache
                / (
                    "bench_embeddings.sqlite"
                    if getattr(self.embedder, "is_fake", False)
                    else "embeddings.sqlite"
                ),
                enforce=self.enforce,
                measure=measure,
                input_root=self.root,
            ),
        )
        report["quality_enforce_failed"] = quality_report["enforce_failed"]
        report["stage_timings"] = timings
        report["seconds"] = time.monotonic() - start
        atomic_bytes(self.state / "run_manifest.json", canonical(report))
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
                    # Los informes necesitan solo metadatos: no retener todo
                    # el texto y los chunks del corpus simultáneamente.
                    "artifact": {key: item[key] for key in ("paths", "metadata", "gates")},
                }
            )
        stream = io.StringIO(newline="")
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
            for field, coverage in item["metadata"].get("cobertura_csv", {}).items():
                if coverage.get("estado") == "difiere":
                    writer.writerow(
                        {
                            "doc_id": doc["doc_id"],
                            "paths": "|".join(item["paths"]),
                            "campo": "metadata_curada." + field,
                            "razon": "conflicto_csv_regex",
                        }
                    )
            if item["metadata"].get("origen_csv", {}).get("conflicto_csv"):
                writer.writerow(
                    {
                        "doc_id": doc["doc_id"],
                        "paths": "|".join(item["paths"]),
                        "campo": "metadata_curada",
                        "razon": "coincidencia_csv_ambigua",
                    }
                )
        atomic_bytes(self.state / "review_queue.csv", stream.getvalue().encode())
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
        atomic_bytes(self.state / "duplicates.json", canonical(duplicate_report))
        coverage = {
            field: sum(
                d["artifact"]["metadata"]["campos"][field]["valor"] is not None for d in docs
            )
            for field in FIELDS
        }
        atomic_bytes(
            self.state / "metadata_coverage.json",
            canonical(
                {
                    "documents": len(docs),
                    "coverage": coverage,
                    "quarantine_if_enforced": [
                        d["doc_id"] for d in docs if not all(d["artifact"]["gates"].values())
                    ],
                }
            ),
        )

    def export(self, path):
        with input_scope(self.root), writer_lock(self.state, self.layers_root, self.cache):
            return self._export(path)

    def _export(self, path):
        digest = hashlib.sha256()
        count = 0
        path = guard_output(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # El export se obtiene del manifiesto, no de colecciones ajenas.
        with (
            atomic_stream(path) as raw,
            gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as compressed,
            io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as stream,
        ):
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
        atomic_bytes(
            path.parent / (path.name + ".manifest.json"),
            canonical(
                {
                    "configuration": self.config,
                    "records": count,
                    "records_sha256": digest.hexdigest(),
                    "compressed_sha256": sha256_file(path),
                }
            ),
        )
        return count

    def close(self):
        self.db.close()
