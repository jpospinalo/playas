"""Sync medido en un subproceso aislado, con capas y cachés bajo --out."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .common import disk_bytes, emit, inside, isolated_env, measured_process, output_dir, rate


def latest_run(state, after=0):
    """Consulta solo una ejecución nueva; nunca atribuye un manifiesto viejo a un fallo."""
    path = state / "manifest.sqlite"
    if not path.exists():
        return None
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute(
            "SELECT id,report FROM runs WHERE id>? ORDER BY id DESC LIMIT 1", (after,)
        ).fetchone()
    return {"run_id": row[0], **json.loads(row[1])} if row else None


def cache_keys(cache, fake):
    path = cache / ("bench_embeddings.sqlite" if fake else "embeddings.sqlite")
    if not path.exists():
        return set()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
        return {row[0] for row in db.execute("SELECT key FROM vectors")}


def embedding_counts(report, layers, before):
    """Distingue hits SQLite de textos iguales coalescidos dentro de un documento."""
    known = set(before)
    hits = pending_duplicates = chunks = 0
    for document in report.get("documents_detail", []):
        if document.get("quarantined"):
            continue
        pending = set()
        path = layers / "gold" / (document["doc_id"] + ".jsonl")
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                key = row["metadata"]["embedding_cache_key"]
                chunks += 1
                if key in known:
                    hits += 1
                elif key in pending:
                    pending_duplicates += 1
                else:
                    pending.add(key)
        known.update(pending)
    new = report.get("new_embeddings", 0)
    return {
        "chunks_embedded_or_reused": chunks,
        "embedding_cache_hits": hits,
        "embedding_pending_duplicates": pending_duplicates,
        "new_embeddings": new,
        "embedding_cache_hit_rate": rate(hits, hits + new),
        "embedding_reuse_fraction": rate(hits + pending_duplicates, chunks),
        "cache_count_consistent": chunks == hits + pending_duplicates + new,
    }


def gold_counts(layers):
    texts = set()
    count = 0
    for path in sorted((layers / "gold").glob("*.jsonl")):
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                count += 1
                texts.add(hashlib.sha256(row["page_content"].encode()).digest())
    return {"gold_chunks_on_disk": count, "gold_unique_texts_on_disk": len(texts)}


def run(args):
    from ingest.offline.extract import sha256_file

    source = args.input.resolve()
    if not source.is_dir():
        raise ValueError("--input debe ser un directorio existente")
    if not args.collection.startswith("bench_"):
        raise ValueError("Solo se permiten colecciones bench_")
    if args.add_new < 0 or (args.add_new and not args.extra_dir):
        raise ValueError("--add-new K requiere K >= 0 y --extra-dir con K documentos nuevos")
    inputs = [source] + ([args.extra_dir] if args.extra_dir else [])
    out = output_dir(args.out, inputs)
    state, cache, layers = (
        inside(out, value) for value in (args.state, args.cache, args.layers_root)
    )
    roots = [state, cache, layers]
    if any(
        a.is_relative_to(b) or b.is_relative_to(a)
        for i, a in enumerate(roots)
        for b in roots[i + 1 :]
    ):
        raise ValueError("state, cache y layers-root deben ser directorios separados")
    extra = []
    if args.add_new:
        extra = sorted(
            p
            for p in args.extra_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in {".pdf", ".md", ".txt"}
        )[: args.add_new]
        if len(extra) != args.add_new:
            raise ValueError("--extra-dir no contiene suficientes documentos")
        identities = {
            sha256_file(path)
            for path in source.rglob("*")
            if path.is_file() and path.suffix.lower() in {".pdf", ".md", ".txt"}
        }
        for path in extra:
            identity = sha256_file(path)
            if identity in identities:
                raise ValueError(f"--extra-dir debe aportar bytes nuevos: {path}")
            identities.add(identity)
        # add exige archivos dentro de input-dir: solo se modifica una copia bajo out.
        staged = inside(out, "input")
        if staged.exists():
            raise ValueError("La entrada temporal ya existe; usar un --out nuevo para --add-new")
        shutil.copytree(source, staged)
        source = staged
        added_dir = source / "bench_added"
        if added_dir.exists():
            raise ValueError("El corpus ya contiene bench_added")
    env = isolated_env(out)
    base = [
        sys.executable,
        "-B",
        "-m",
        "ingest.offline",
        "--input-dir",
        str(source),
        "--collection",
        args.collection,
        "--state",
        str(state),
        "--cache",
        str(cache),
        "--layers-root",
        str(layers),
        "--ollama",
        "http://127.0.0.1:11434",
        "--chunker",
        args.chunker,
        # Evita resolver el CSV por defecto relativo al repositorio.
        "--overrides",
        str(inside(out, "sin_overrides.csv")),
    ]
    if args.fake_embeddings:
        base.append("--fake-embeddings")
    result = {
        "benchmark": "run_pipeline",
        "collection": args.collection,
        "input": str(source),
        "fake_embeddings": args.fake_embeddings,
        "embeddings_measured": not args.fake_embeddings,
        "chunker": args.chunker,
        "from_stage": args.from_stage,
        "preexisting_state": (state / "manifest.sqlite").exists(),
        "preexisting_cache": cache.exists() and any(cache.iterdir()),
        "preexisting_layers": layers.exists() and any(layers.iterdir()),
        "runs": [],
        "resource_scope": "proceso Python e hijos; excluye servidores Ollama y Chroma ya iniciados",
    }

    def timed(label, command):
        previous = latest_run(state)
        before_id = previous["run_id"] if previous else 0
        before_keys = cache_keys(cache, args.fake_embeddings)
        resources = measured_process(command, out, label, env)
        report = latest_run(state, before_id)
        row = {"label": label, "resources": resources, "pipeline": report}
        if report:
            counts = embedding_counts(report, layers, before_keys)
            row.update(counts)
            elapsed = resources["wall_seconds"]
            embedding_seconds = report.get("embeddings", {}).get("embedding_seconds", 0)
            row.update(
                docs_per_hour=rate(report["processed"] * 3600, elapsed),
                scanned_docs_per_hour=rate(report["documents"] * 3600, elapsed),
                chunks_per_second=rate(counts["chunks_embedded_or_reused"], elapsed),
                embeddings_per_second=rate(counts["new_embeddings"], embedding_seconds)
                if not args.fake_embeddings
                else None,
                stage_timings=report.get("stage_timings", {}),
                **gold_counts(layers),
            )
        row["disk_bytes"] = {
            **{
                stage: disk_bytes(layers / stage)
                for stage in ("bronze", "silver", "gold", "quality")
            },
            "manifest_sqlite": disk_bytes(state / "manifest.sqlite"),
            "cache": disk_bytes(cache),
            "state": disk_bytes(state),
        }
        row["success"] = bool(report) and resources["returncode"] == 0
        result["runs"].append(row)
        emit(result, out, "run_pipeline.json")
        return row["success"]

    first = base + (["--from-stage", args.from_stage] if args.from_stage else []) + ["sync"]
    if not timed("sync", first):
        return 1
    if args.repeat_sync and not timed("repeat_sync", base + ["sync"]):
        return 1
    for index, path in enumerate(extra):
        target = inside(out, source / "bench_added" / f"{index:08d}_{path.name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        if not timed(f"add_{index + 1}", base + ["add", str(target)]):
            return 1
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--fake-embeddings", action="store_true")
    parser.add_argument("--chunker", choices=["legacy", "structure"], default="legacy")
    parser.add_argument("--from-stage", choices=["bronze", "silver", "gold", "embeddings"])
    parser.add_argument("--repeat-sync", action="store_true")
    parser.add_argument("--add-new", type=int, default=0)
    parser.add_argument("--extra-dir", type=Path)
    parser.add_argument("--layers-root", type=Path, default=Path("layers"))
    parser.add_argument("--state", type=Path, default=Path("state"))
    parser.add_argument("--cache", type=Path, default=Path("cache"))
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
