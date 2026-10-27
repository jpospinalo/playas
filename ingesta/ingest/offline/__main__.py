"""Comandos add/sync/export, locales y sin claves de proveedores."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..offline_embeddings import OllamaBatchEmbeddings
from .pipeline import Pipeline, config_hash, configuration
from .publish import ChromaPublisher


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("data/documents/raw"))
    parser.add_argument("--collection", required=True)
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
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sync")
    commands.add_parser("add").add_argument("file", type=Path)
    commands.add_parser("export").add_argument("file", type=Path)
    args = parser.parse_args(argv)
    if args.token_budget is None:
        args.token_budget = 1024 if args.chunker == "structure" else 512
    if args.token_budget < 128 or args.batch_size <= 0:
        parser.error("token-budget >=128 y batch-size positivo requeridos")
    embedder = None
    pipeline = None
    try:
        config = configuration(args.chunker, args.token_budget)
        publisher = ChromaPublisher(args.collection, config_hash(config), args.port)
        embedder = OllamaBatchEmbeddings(
            args.cache / "embeddings.sqlite", args.ollama, args.allow_remote_ollama, args.batch_size
        )
        pipeline = Pipeline(
            args.input_dir,
            args.state or Path(".offline") / args.collection,
            args.cache,
            embedder,
            publisher,
            args.chunker,
            args.token_budget,
            args.enforce,
            args.overrides,
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
        return 1 if report["errors"] else 0
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
