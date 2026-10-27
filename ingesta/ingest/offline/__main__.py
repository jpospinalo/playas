"""Comandos add/sync/export, locales y sin claves de proveedores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..offline_embeddings import FakeBatchEmbeddings, OllamaBatchEmbeddings
from .pipeline import Pipeline, config_hash, configuration, legacy_config_hashes
from .publish import ChromaPublisher
from .quality import report_quality
from .storage import guard_output, input_scope, writer_lock


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/documents/raw"))
    parser.add_argument("--collection")
    parser.add_argument("--state", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(".offline/cache"))
    parser.add_argument("--ollama", default="http://localhost:11434")
    parser.add_argument("--allow-remote-ollama", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--chunker", choices=["legacy", "structure"], default="legacy")
    parser.add_argument("--token-budget", type=int)
    parser.add_argument("--enforce", action="store_true")
    parser.add_argument("--overrides", type=Path, default=Path("data/metadata_overrides.csv"))
    parser.add_argument("--layers-root", type=Path, default=Path("data/documents-v2"))
    parser.add_argument("--from-stage", choices=["bronze", "silver", "gold", "embeddings"])
    parser.add_argument("--fake-embeddings", action="store_true")
    commands = parser.add_subparsers(dest="command", required=True)
    sync = commands.add_parser("sync")
    add = commands.add_parser("add")
    add.add_argument("file", type=Path)
    commands.add_parser("export").add_argument("file", type=Path)
    quality = commands.add_parser("quality")
    quality.add_argument("--compare-v1", type=Path)
    for command in (sync, add, quality):
        command.add_argument("--layers-root", type=Path, default=argparse.SUPPRESS)
        command.add_argument(
            "--from-stage",
            choices=["bronze", "silver", "gold", "embeddings"],
            default=argparse.SUPPRESS,
        )
        command.add_argument("--fake-embeddings", action="store_true", default=argparse.SUPPRESS)
    for name, kind in (("state", Path), ("cache", Path), ("input-dir", Path)):
        quality.add_argument("--" + name, type=kind, default=argparse.SUPPRESS)
    quality.add_argument("--enforce", action="store_true", default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.command != "quality" and not args.collection:
        parser.error("--collection es obligatorio para sync/add/export")
    if (
        args.fake_embeddings
        and args.command != "quality"
        and not args.collection.startswith("bench_")
    ):
        parser.error("--fake-embeddings requiere una colección bench_")
    if args.token_budget is None:
        args.token_budget = 1024 if args.chunker == "structure" else 512
    if args.token_budget < 128 or args.batch_size <= 0:
        parser.error("token-budget >=128 y batch-size positivo requeridos")
    embedder = None
    pipeline = None
    try:
        guard_output(args.layers_root, args.input_dir)
        guard_output(args.cache, args.input_dir)
        if args.command == "quality":
            state = args.state or (Path(".offline") / args.collection if args.collection else None)
            # El subcomando quality no crea estado, caché, ni conexiones a servicios.
            result = report_quality(
                args.layers_root,
                state,
                args.cache
                / ("bench_embeddings.sqlite" if args.fake_embeddings else "embeddings.sqlite"),
                args.compare_v1,
                args.enforce,
                input_root=args.input_dir,
            )
            print(json.dumps(result["resumen"], ensure_ascii=False))
            return int(result["enforce_failed"])
        state = guard_output(args.state or Path(".offline") / args.collection, args.input_dir)
        config = configuration(args.chunker, args.token_budget)
        if args.fake_embeddings:
            config.update(model="bench_hash", digest="bench-sha256-768-1")
        with input_scope(args.input_dir):
            publisher = ChromaPublisher(
                args.collection,
                config_hash(config),
                args.port,
                fake_embeddings=args.fake_embeddings,
                legacy_hashes=legacy_config_hashes(config),
            )
        with input_scope(args.input_dir), writer_lock(args.cache):
            embedder = (
                FakeBatchEmbeddings(args.cache / "bench_embeddings.sqlite")
                if args.fake_embeddings
                else OllamaBatchEmbeddings(
                    args.cache / "embeddings.sqlite",
                    args.ollama,
                    args.allow_remote_ollama,
                    args.batch_size,
                )
            )
        pipeline = Pipeline(
            args.input_dir,
            state,
            args.cache,
            embedder,
            publisher,
            args.chunker,
            args.token_budget,
            args.enforce,
            args.overrides,
            args.layers_root,
            args.from_stage,
        )
        if args.command == "export":
            print(json.dumps({"exported_records": pipeline.export(args.file), "llm_api_calls": 0}))
            return 0
        report = pipeline.run(args.file if args.command == "add" else None)
        print(
            json.dumps(
                {k: v for k, v in report.items() if k != "documents_detail"}, ensure_ascii=False
            )
        )
        return 1 if report["errors"] or report["quality_enforce_failed"] else 0
    except Exception as exc:
        print(f"ERROR offline ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    finally:
        if pipeline:
            pipeline.close()
        if embedder:
            embedder.close()


if __name__ == "__main__":
    raise SystemExit(main())
