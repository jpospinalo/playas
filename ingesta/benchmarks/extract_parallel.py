"""Extracción y OCR reales con procesos y caché vacía por documento y medición."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .common import emit, inside, isolated_env, measured_process, output_dir, positive, rate, sizes


def extract_one(task):
    from ingest.offline.extract import read_document

    filename, cache = task
    started = time.perf_counter()
    try:
        document = read_document(Path(filename), Path(cache))
        return {
            "file": filename,
            "wall_seconds": time.perf_counter() - started,
            "cpu_seconds": document["cpu_seconds"],
            "ocr_seconds": document["ocr_seconds"],
            "ocr_pages": len(document["ocr_pages"]),
            "new_ocr_pages": document["new_ocr_pages"],
            "ocr_failed_pages": document["ocr_failed_pages"],
            "extraction_cache_hit": document["extraction_cache_hit"],
        }
    except Exception as exc:
        return {"file": filename, "error": f"{type(exc).__name__}: {exc}"}


def worker_run(files, workers, out):
    cache = inside(out, f"cache/extract_{workers}_{uuid.uuid4().hex}")
    cache.mkdir(parents=True, exist_ok=False)
    tasks = [(str(path), str(cache / f"doc_{index:08d}")) for index, path in enumerate(files)]
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        documents = list(pool.map(extract_one, tasks, chunksize=1))
    elapsed = time.perf_counter() - started
    successful = sum(not d.get("error") and not d.get("ocr_failed_pages") for d in documents)
    result = {
        "benchmark": "extract_parallel_worker",
        "workers": workers,
        "documents": len(files),
        "successful_documents": successful,
        "wall_seconds": elapsed,
        "docs_per_hour": rate(successful * 3600, elapsed),
        "document_cpu_seconds": sum(d.get("cpu_seconds", 0) for d in documents),
        "cache": str(cache),
        "documents_detail": documents,
    }
    emit(result, out, f"extract_worker_{workers}.json")
    return int(successful != len(files))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--workers", type=sizes, default=sizes("1,2,4"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--limit", type=positive)
    parser.add_argument("--_worker-run", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    source = args.input.resolve()
    out = output_dir(args.out, [source])
    files = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
    if args.limit:
        files = files[: args.limit]
    if not files:
        raise ValueError("No se encontraron PDFs")
    if args._worker_run:
        if len(args.workers) != 1:
            parser.error("El subproceso debe recibir un único número de workers")
        return worker_run(files, args.workers[0], out)
    result = {"benchmark": "extract_parallel", "input": str(source), "rows": []}
    env = isolated_env(out)
    for workers in args.workers:
        name = f"extract_worker_{workers}.json"
        # Impide leer resultados antiguos si el subproceso falla antes de escribir.
        inside(out, name).unlink(missing_ok=True)
        command = [
            sys.executable,
            "-B",
            "-m",
            "benchmarks.extract_parallel",
            "--input",
            str(source),
            "--workers",
            str(workers),
            "--out",
            str(out),
            "--_worker-run",
        ]
        if args.limit:
            command.extend(["--limit", str(args.limit)])
        resources = measured_process(command, out, f"extract_{workers}", env)
        path = inside(out, name)
        row = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"workers": workers}
        )
        row.update(
            resources=resources,
            success=resources["returncode"] == 0,
            total_cpu_seconds=resources.get("cpu_seconds"),
            max_rss_bytes=resources.get("max_rss_bytes"),
        )
        result["rows"].append(row)
        emit(result, out, "extract_parallel.json")
    return int(any(not r["success"] for r in result["rows"]))


if __name__ == "__main__":
    raise SystemExit(main())
