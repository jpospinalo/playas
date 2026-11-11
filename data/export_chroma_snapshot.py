"""Supervised, read-only Chroma snapshot CLI; importing this module does not load Chroma."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import stat
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLIENT_VERSION = "1.5.9"
PAGE_PAUSE_SECONDS = 0.1


class SnapshotError(Exception):
    """A fixed diagnostic category, never an upstream payload or exception."""


class QuietParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Argumentos inválidos; use --help.\n")


def parse_args(argv=None):
    parser = QuietParser(description=__doc__)
    for name in ("host", "tenant", "database", "collection", "output-dir"):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--port", required=True, type=int)
    parser.add_argument("--batch-size", default=100, type=int)
    parser.add_argument("--confirm-no-writes", required=True, action="store_true")
    args = parser.parse_args(argv)
    valid_host = bool(re.fullmatch(r"[A-Za-z0-9_.-]+", args.host))
    names = (args.tenant, args.database, args.collection)
    if (
        not valid_host
        or not 1 <= args.port <= 65535
        or not 1 <= args.batch_size <= 100
        or any(
            not name.strip() or any(ord(c) < 32 or ord(c) == 127 for c in name) for name in names
        )
    ):
        parser.error("invalid arguments")
    return args


def validate_output_dir(path, repo_root=REPO_ROOT):
    """Resolve the new destination without creating or following an existing leaf."""
    try:
        raw = Path(path).expanduser()
        if raw.exists() or raw.is_symlink():
            raise SnapshotError("invalid_output_directory")
        parent = raw.parent.resolve(strict=True)
        output = parent / raw.name
        if not parent.is_dir() or output.is_relative_to(repo_root.resolve()):
            raise SnapshotError("invalid_output_directory")
        return output
    except (OSError, ValueError, RuntimeError) as exc:
        raise SnapshotError("invalid_output_directory") from exc


def validate_environment():
    """Use distribution metadata and public proxy discovery, without importing the SDK."""
    if sys.version_info[:2] != (3, 12):
        raise SnapshotError("python_version_mismatch")
    if importlib.metadata.version("chromadb") != CLIENT_VERSION:
        raise SnapshotError("client_version_mismatch")
    proxies = urllib.request.getproxies()
    if not isinstance(proxies, dict):
        raise SnapshotError("proxy_discovery_failed")
    for scheme in ("http", "https", "all"):
        if proxies.get(scheme):
            raise SnapshotError(f"proxy_not_supported_{scheme}")


def create_client(args):
    """Call only from the CLI's new, private working directory; SDK imports are lazy."""
    import chromadb
    from chromadb.config import Settings

    settings = Settings(
        _env_file=None,
        is_persistent=False,
        allow_reset=False,
        anonymized_telemetry=False,
        chroma_otel_granularity="none",
        chroma_otel_collection_endpoint="",
        chroma_otel_collection_headers={},
        chroma_client_auth_provider=None,
        chroma_client_auth_credentials=None,
        chroma_overwrite_singleton_tenant_database_access_from_auth=False,
        chroma_product_telemetry_impl="chromadb.telemetry.product.posthog.Posthog",
        chroma_telemetry_impl="chromadb.telemetry.product.posthog.Posthog",
    )
    return chromadb.HttpClient(
        host=args.host,
        port=args.port,
        ssl=False,
        headers=None,
        tenant=args.tenant,
        database=args.database,
        settings=settings,
    )


def utc_now():
    return datetime.now(UTC).isoformat()


def file_receipt(path):
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def new_manifest(args):
    return {
        "schema_version": 1,
        "capture_status": "INCOMPLETE",
        "source": {
            "host": args.host,
            "port": args.port,
            "tenant": args.tenant,
            "database": args.database,
            "collection": args.collection,
            "collection_id": None,
            "client_version": CLIENT_VERSION,
            "server_version": None,
        },
        "exporter": file_receipt(Path(__file__).resolve()),
        "started_at": utc_now(),
        "finished_at": None,
        "method": "collection.get_offset_limit",
        "filters": None,
        "embeddings_included": False,
        "batch_size": args.batch_size,
        "page_pause_seconds": PAGE_PAUSE_SECONDS,
        "count_before": None,
        "count_after": None,
        "rows_written": 0,
        "unique_ids": 0,
        "anomalies": dict.fromkeys(
            (
                "null_document",
                "empty_document",
                "unexpected_document_type",
                "null_metadata",
                "unexpected_metadata_type",
                "metadata_chunk_id_mismatch",
            ),
            0,
        ),
        "snapshot": {"path": "snapshot.jsonl", "sha256": None, "size_bytes": None},
        "consistency_basis": "operator_declared_no_writes",
        "atomic_snapshot": False,
        "no_writes_verified_by_exporter": False,
    }


def collection_identity(collection, args):
    if (
        collection.name != args.collection
        or collection.tenant != args.tenant
        or collection.database != args.database
        or not collection.id
    ):
        raise SnapshotError("collection_identity_mismatch")
    return str(collection.id)


def checked_count(value):
    if type(value) is not int or value < 0:
        raise SnapshotError("invalid_count")
    return value


def checked_page(page):
    if not isinstance(page, dict) or not isinstance(page.get("ids"), list):
        raise SnapshotError("invalid_page")
    ids = page["ids"]
    documents, metadatas = page.get("documents"), page.get("metadatas")
    if not ids:
        if any(column is not None and column != [] for column in (documents, metadatas)):
            raise SnapshotError("invalid_empty_page")
        return [], [], []
    if any(
        not isinstance(column, list) or len(column) != len(ids) for column in (documents, metadatas)
    ):
        raise SnapshotError("incomplete_page_columns")
    return ids, documents, metadatas


def count_anomalies(anomalies, record_id, document, metadata):
    if document is None:
        anomalies["null_document"] += 1
    elif document == "":
        anomalies["empty_document"] += 1
    elif not isinstance(document, str):
        anomalies["unexpected_document_type"] += 1
    if metadata is None:
        anomalies["null_metadata"] += 1
    elif not isinstance(metadata, dict):
        anomalies["unexpected_metadata_type"] += 1
    elif "chunk_id" in metadata and metadata["chunk_id"] != record_id:
        anomalies["metadata_chunk_id_mismatch"] += 1


def capture(client, args, run_dir, manifest, *, sleep=None):
    """Read pages into a new JSONL candidate. No final names are published here."""
    pause = time.sleep if sleep is None else sleep
    if client.tenant != args.tenant or client.database != args.database:
        raise SnapshotError("client_namespace_mismatch")
    manifest["source"]["server_version"] = client.get_version()
    collection = client.get_collection(
        name=args.collection, embedding_function=None, data_loader=None
    )
    identity = collection_identity(collection, args)
    manifest["source"]["collection_id"] = identity
    total = checked_count(collection.count())
    manifest["count_before"] = total
    seen = set()
    offset = 0
    with (run_dir / "snapshot.jsonl.partial").open("x", encoding="utf-8", newline="\n") as stream:
        while True:
            if offset:
                pause(PAGE_PAUSE_SECONDS)
            page = collection.get(
                include=["documents", "metadatas"], limit=args.batch_size, offset=offset
            )
            ids, documents, metadatas = checked_page(page)
            if not ids:
                if offset != total:
                    raise SnapshotError("premature_empty_page")
                break
            if offset + len(ids) > total or len(ids) > args.batch_size:
                raise SnapshotError("excess_records")
            for index, record_id in enumerate(ids):
                if not isinstance(record_id, str) or not record_id or record_id in seen:
                    raise SnapshotError("invalid_or_duplicate_id")
                document, metadata = documents[index], metadatas[index]
                row = {"id": record_id, "document": document, "metadata": metadata}
                line = json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
                stream.write(line)
                seen.add(record_id)
                manifest["rows_written"] += 1
                manifest["unique_ids"] = len(seen)
                count_anomalies(manifest["anomalies"], record_id, document, metadata)
            offset += len(ids)
    manifest["count_after"] = checked_count(collection.count())
    if manifest["count_after"] != total or len(seen) != total:
        raise SnapshotError("count_changed")
    final_collection = client.get_collection(
        name=args.collection, embedding_function=None, data_loader=None
    )
    if collection_identity(final_collection, args) != identity:
        raise SnapshotError("collection_replaced")


def manifest_bytes(manifest):
    return (json.dumps(manifest, ensure_ascii=False, allow_nan=False, indent=2) + "\n").encode(
        "utf-8"
    )


def publication_is_own(run_dir, expected_manifest_bytes):
    """Recognize a committed pair, even if a signal arrived immediately after link()."""
    try:
        for name in ("snapshot.jsonl", "manifest.json"):
            candidate, final = run_dir / f"{name}.partial", run_dir / name
            if not all(stat.S_ISREG(path.lstat().st_mode) for path in (candidate, final)):
                return False
            if not os.path.samefile(candidate, final):
                return False
        if (run_dir / "manifest.json").read_bytes() != expected_manifest_bytes:
            return False
        expected = json.loads(expected_manifest_bytes)
        observed = file_receipt(run_dir / "snapshot.jsonl")
        return expected["capture_status"] == "COMPLETE" and all(
            expected["snapshot"][key] == value for key, value in observed.items()
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def publish(run_dir, expected_manifest_bytes):
    for name in ("snapshot.jsonl.partial", "manifest.json.partial"):
        if not stat.S_ISREG((run_dir / name).lstat().st_mode):
            raise SnapshotError("invalid_candidate_file")
    if (run_dir / "manifest.json.partial").read_bytes() != expected_manifest_bytes:
        raise SnapshotError("manifest_candidate_changed")
    expected = json.loads(expected_manifest_bytes)
    observed = file_receipt(run_dir / "snapshot.jsonl.partial")
    if any(expected["snapshot"][key] != value for key, value in observed.items()):
        raise SnapshotError("snapshot_candidate_changed")
    os.link(run_dir / "snapshot.jsonl.partial", run_dir / "snapshot.jsonl")
    os.link(run_dir / "manifest.json.partial", run_dir / "manifest.json")
    if not publication_is_own(run_dir, expected_manifest_bytes):
        raise SnapshotError("publication_unverified")


def record_incomplete(run_dir, manifest, stage, category):
    """Exclusive creation only; a closed candidate is never reopened for writing."""
    manifest = {**manifest, "capture_status": "INCOMPLETE", "finished_at": utc_now()}
    manifest["error"] = {"stage": stage, "category": category}
    try:
        with (run_dir / "manifest.json.partial").open("xb") as stream:
            stream.write(manifest_bytes(manifest))
    except (OSError, ValueError, TypeError):
        pass


def main(argv=None):
    try:
        args = parse_args(argv)
    except SystemExit as exc:
        return exc.code
    try:
        run_dir = validate_output_dir(args.output_dir)
    except SnapshotError:
        print(
            "Destino inválido; se requiere una carpeta nueva fuera del repositorio.",
            file=sys.stderr,
        )
        return 2

    manifest = None
    expected = None
    client = None
    created = False
    stage = "environment"
    try:
        validate_environment()
        stage = "output_directory"
        try:
            run_dir.mkdir(mode=0o700)
        except OSError:
            print("No se pudo crear una carpeta nueva privada.", file=sys.stderr)
            return 2
        created = True
        manifest = new_manifest(args)
        original_cwd = Path.cwd()
        error = None
        try:
            stage = "client"
            os.chdir(run_dir)
            client = create_client(args)
            stage = "capture"
            capture(client, args, run_dir, manifest)
        except BaseException as exc:
            error = exc
        finally:
            try:
                if client is not None:
                    stage = "close" if error is None else stage
                    client.close()
            except BaseException as exc:
                if error is None:
                    error = exc
            finally:
                try:
                    os.chdir(original_cwd)
                except BaseException as exc:
                    if error is None:
                        stage, error = "restore_cwd", exc
        if error is not None:
            raise error
        stage = "candidates"
        manifest["snapshot"].update(file_receipt(run_dir / "snapshot.jsonl.partial"))
        manifest["finished_at"] = utc_now()
        manifest["capture_status"] = "COMPLETE"
        expected = manifest_bytes(manifest)
        with (run_dir / "manifest.json.partial").open("xb") as stream:
            stream.write(expected)
        stage = "publication"
        publish(run_dir, expected)
        stage = "console"
        print(f"COMPLETE: {manifest['rows_written']} registros; publicación local verificada.")
        return 0
    except (Exception, KeyboardInterrupt) as exc:
        committed = expected is not None and publication_is_own(run_dir, expected)
        category = str(exc) if isinstance(exc, SnapshotError) else type(exc).__name__
        if created and manifest is not None and not committed:
            record_incomplete(run_dir, manifest, stage, category)
        try:
            state = "COMPLETE publicado; conservar para revisión" if committed else "INCOMPLETE"
            print(f"{state}; etapa={stage}; categoría={category}.", file=sys.stderr)
        except (Exception, KeyboardInterrupt):
            pass
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    sys.exit(main())
