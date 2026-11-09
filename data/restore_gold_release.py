#!/usr/bin/env python3
"""Restore the pinned Gold release; without --execute all checks stay local."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import http.client
import importlib.util
import io
import json
import math
import os
import signal
import stat
import struct
import sys
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urlsplit

DEFAULT_PACKAGE = Path(__file__).resolve().parent / "chroma-releases/gold-a-cc7bf44b54a9"
REPO_ROOT = Path(__file__).resolve().parents[1]
COLLECTION_NAME = "rag_playas_gold_a_cc7bf44b54a9"
COLS = "/api/v2/tenants/default_tenant/databases/default_database/collections"
MANIFEST_SHA256 = "6386e128c1bde3564215732a11b1521fbb9f0346a8569390ae8ebeac979a7f97"
VERIFIER_SHA256 = "eedaf648011513aa6cca5c84042ceba53f0c0ed4bee986f4f0f5d2b48cbe234d"
PAYLOAD_SHA256 = "cc7bf44b54a9309d67e52d77cf7e41fd5e4cd7063168dfc70ffd57785ba7657d"
MODEL = "embeddinggemma:latest"
DIGEST = "85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1"
OLLAMA_VERSION = "0.40.13"
HNSW = {
    "space": "cosine",
    "ef_construction": 100,
    "ef_search": 100,
    "max_neighbors": 16,
    "resize_factor": 1.2,
    "sync_threshold": 1000,
}
INCLUDE = ["documents", "metadatas", "embeddings"]
BATCH_SIZE = 25


class Stop(RuntimeError):
    pass


def require(ok, reason):
    if not ok:
        raise Stop(reason)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    def invalid(_):
        raise Stop("nonfinite_json")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def load_package(root=DEFAULT_PACKAGE):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "package_directory")
    for name, expected in [
        ("manifest.json", MANIFEST_SHA256),
        ("verificar_paquete.py", VERIFIER_SHA256),
    ]:
        path = root / name
        require(
            not path.is_symlink() and path.is_file() and sha(path.read_bytes()) == expected,
            "package_code_or_manifest_pin",
        )
    spec = importlib.util.spec_from_file_location(
        "_pinned_gold_verifier", root / "verificar_paquete.py"
    )
    module = importlib.util.module_from_spec(spec)
    old = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
        module.verify_package(root)
    finally:
        sys.dont_write_bytecode = old
    manifest_bytes = (root / "manifest.json").read_bytes()
    payload_bytes = (root / "GOLD_A.jsonl.gz").read_bytes()
    require(
        sha(manifest_bytes) == MANIFEST_SHA256 and sha(payload_bytes) == PAYLOAD_SHA256,
        "package_snapshot_pins",
    )
    manifest = decode(manifest_bytes)
    with gzip.GzipFile(fileobj=io.BytesIO(payload_bytes), mode="rb") as stream:
        header = decode(next(stream))
        require(
            header == {"__manifest__": manifest["content"]["payload_manifest"]}, "package_header"
        )
        records = [decode(line) for line in stream if line.strip()]
    require(len(records) == 5862 and len({r["id"] for r in records}) == 5862, "package_records")
    return manifest, records


def f32_bytes(vector):
    require(
        type(vector) is list
        and len(vector) == 768
        and all(type(x) in (int, float) and math.isfinite(x) for x in vector),
        "vector_shape",
    )
    raw = struct.pack("<768f", *vector)
    rounded = struct.unpack("<768f", raw)
    require(all(math.isfinite(x) for x in rounded) and math.hypot(*rounded) > 0, "vector_float32")
    return raw


def read_representation(vector):
    values = struct.unpack("<768f", f32_bytes(vector))

    def f32(x):
        return struct.unpack("<f", struct.pack("<f", x))[0]

    lanes = [0.0] * 4
    for i, value in enumerate(values):
        lanes[i % 4] = f32(lanes[i % 4] + f32(value * value))
    total = f32(f32(lanes[0] + lanes[2]) + f32(lanes[1] + lanes[3]))
    length = f32(math.sqrt(total))
    require(math.isfinite(length) and length > 0, "representation_norm")
    inverse = f32(1.0 / f32(length + f32(1e-30)))
    return [f32(f32(value * inverse) * length) for value in values]


def compare_rows(expected, actual):
    require(type(actual) is dict, "readback_object")
    ids = actual.get("ids")
    require(
        type(ids) is list
        and all(type(i) is str for i in ids)
        and len(ids) == len(set(ids)) == len(expected),
        "readback_ids",
    )
    wanted = {r["id"]: r for r in expected}
    require(set(ids) == set(wanted), "readback_coverage")
    require(
        all(type(actual.get(k)) is list and len(actual[k]) == len(ids) for k in INCLUDE),
        "readback_columns",
    )
    for i, ident in enumerate(ids):
        row = wanted[ident]
        require(
            actual["documents"][i] == row["document"]
            and canonical(actual["metadatas"][i]) == canonical(row["metadata"]),
            "readback_payload",
        )
        require(
            f32_bytes(actual["embeddings"][i]) == f32_bytes(read_representation(row["embedding"])),
            "readback_vector_T",
        )


class Journal:
    def __init__(self, path):
        path = Path(path)
        require(not path.resolve().is_relative_to(REPO_ROOT), "receipt_in_repository")
        require(
            path.is_absolute()
            and path.parent.is_dir()
            and stat.S_IMODE(path.parent.stat().st_mode) == 0o700,
            "receipt_private_parent",
        )
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.stream = os.fdopen(fd, "wb")
        self.pending = False
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def note(self, kind, data):
        self.stream.write(canonical({"kind": kind, "data": data}) + b"\n")
        self.stream.flush()
        os.fsync(self.stream.fileno())
        if kind in ("CREATE_INTENT", "ADD_INTENT"):
            self.pending = True
        elif kind in ("CREATE_ACK", "ADD_ACK"):
            self.pending = False

    def close(self):
        self.stream.close()


class HTTP:
    """Direct, finite HTTP requests: no ambient proxies, redirects or retries."""

    def __init__(self, host, port=8000, scheme="http", deadline=None):
        require(
            type(host) is str
            and host
            and not any(c in host for c in "/@?#\r\n")
            and type(port) is int
            and 0 < port < 65536
            and scheme in ("http", "https"),
            "endpoint",
        )
        self.host, self.port, self.scheme = host, port, scheme
        self.deadline = deadline or time.monotonic() + 3600

    def request(self, method, path, payload=None, missing=False):
        require(method in ("GET", "POST") and path.startswith("/api/"), "http_method_path")
        require(
            not missing or method == "GET" and path == COLS + "/" + COLLECTION_NAME, "missing_scope"
        )
        require(
            method != "POST"
            or path == "/api/show"
            or path == COLS
            or path.startswith(COLS + "/")
            and path.endswith(("/get", "/add")),
            "http_post_route",
        )
        remaining = min(60, self.deadline - time.monotonic())
        require(remaining > 0, "deadline")
        connection = (
            http.client.HTTPSConnection if self.scheme == "https" else http.client.HTTPConnection
        )(self.host, self.port, timeout=min(30, remaining))
        alarm = (
            hasattr(signal, "setitimer") and threading.current_thread() is threading.main_thread()
        )

        def expired(*_):
            raise Stop("http_total_timeout")

        previous = signal.getsignal(signal.SIGALRM) if alarm else None
        try:
            if alarm:
                signal.signal(signal.SIGALRM, expired)
                signal.setitimer(signal.ITIMER_REAL, remaining)
            body = canonical(payload) if payload is not None else None
            connection.request(method, path, body, {"Content-Type": "application/json"})
            response = connection.getresponse()
            lengths = response.headers.get_all("Content-Length") or []
            transfer = response.headers.get("Transfer-Encoding")
            require(len(lengths) <= 1 and not (lengths and transfer), "http_framing")
            expected = int(lengths[0]) if lengths else None
            require(expected is None or 0 <= expected <= 16 * 1024**2, "http_size")
            chunks, size = [], 0
            while True:
                block = response.read1(65536)
                if not block:
                    break
                size += len(block)
                require(
                    size <= 16 * 1024**2 and time.monotonic() < self.deadline,
                    "http_size_or_deadline",
                )
                chunks.append(block)
            require(expected is None or size == expected, "http_partial_body")
            value = decode(b"".join(chunks)) if size else None
            if response.status == 404 and missing:
                require(
                    type(value) is dict and value.get("error") == "NotFoundError",
                    "untyped_not_found",
                )
                return None
            require(response.status in (200, 201, 204), "http_status")
            require(not missing or value is not None, "untyped_missing_response")
            return value
        finally:
            connection.close()
            if alarm:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)


def check_model(ollama):
    version = ollama.request("GET", "/api/version")
    require(type(version) is dict and version.get("version") == OLLAMA_VERSION, "ollama_version")
    response = ollama.request("GET", "/api/tags")
    require(type(response) is dict, "ollama_tags")
    tags = response.get("models")
    require(type(tags) is list, "ollama_tags")
    matches = [r for r in tags if r.get("model", r.get("name")) == MODEL]
    require(len(matches) == 1 and matches[0].get("digest") == DIGEST, "model_digest")
    info = ollama.request("POST", "/api/show", {"model": MODEL}).get("model_info")
    require(type(info) is dict, "model_info")
    for suffix, value in [(".embedding_length", 768), (".context_length", 2048)]:
        found = [v for k, v in info.items() if k.endswith(suffix)]
        require(
            len(found) == 1 and type(found[0]) is int and found[0] == value,
            "model_dimensions_context",
        )
    return {
        "model": MODEL,
        "digest": DIGEST,
        "ollama_version": OLLAMA_VERSION,
        "dimension": 768,
        "context_length": 2048,
        "inferences": 0,
    }


def inventory(client):
    result = {}
    for offset in range(0, 100000, 100):
        page = client.request("GET", f"{COLS}?limit=100&offset={offset}")
        require(type(page) is list and len(page) <= 100, "collection_inventory")
        for row in page:
            ident, name = row["id"], row["name"]
            require(
                str(uuid.UUID(ident)) == ident
                and type(name) is str
                and name
                and ident not in result
                and name not in result.values(),
                "inventory_identity",
            )
            result[ident] = name
        if len(page) < 100:
            return result
    raise Stop("inventory_limit")


def count(client, ident):
    result = client.request("GET", f"{COLS}/{ident}/count")
    require(type(result) is int and result >= 0, "collection_count")
    return result


def descriptor(client, ident):
    result = client.request("GET", COLS + "/" + quote(COLLECTION_NAME, safe=""))
    require(
        result["id"] == ident
        and result["name"] == COLLECTION_NAME
        and result.get("tenant") == "default_tenant"
        and result.get("database") == "default_database",
        "target_identity",
    )
    config = result.get("configuration_json", {}).get("hnsw") or {}
    require(canonical({k: config.get(k) for k in HNSW}) == canonical(HNSW), "hnsw_configuration")
    return result


def verify_rows(client, ident, records):
    require(count(client, ident) == len(records), "target_count")
    for start in range(0, len(records), BATCH_SIZE):
        batch = records[start : start + BATCH_SIZE]
        compare_rows(
            batch,
            client.request(
                "POST", f"{COLS}/{ident}/get", {"ids": [r["id"] for r in batch], "include": INCLUDE}
            ),
        )
    require(count(client, ident) == len(records), "target_count_after_readback")


def restore(client, records, journal, verify_only=False):
    require(records and len({r["id"] for r in records}) == len(records), "source_unique_ids")
    for row in records:
        require(
            set(row) == {"id", "document", "metadata", "embedding"}
            and type(row["id"]) is str
            and row["id"]
            and type(row["document"]) is str
            and type(row["metadata"]) is dict,
            "source_record",
        )
        f32_bytes(row["embedding"])
        canonical(row["metadata"])
    client.request("GET", "/api/v2/heartbeat")
    version = client.request("GET", "/api/v2/version")  # API metadata, not an image attestation.
    before = inventory(client)
    counts = {ident: count(client, ident) for ident in before}
    journal.note("BEFORE", {"collections": before, "counts": counts, "API_version": version})
    existing = client.request("GET", COLS + "/" + COLLECTION_NAME, missing=True)
    writes = 0
    if existing is not None:
        ident = existing["id"]
        require(before.get(ident) == COLLECTION_NAME, "existing_target_inventory")
        descriptor(client, ident)
    else:
        require(
            not verify_only and COLLECTION_NAME not in before.values(),
            "target_missing_for_verify_only",
        )
        require(
            inventory(client) == before and all(count(client, i) == n for i, n in counts.items()),
            "protected_changed_before_create",
        )
        body = {
            "name": COLLECTION_NAME,
            "get_or_create": False,
            "configuration": {"hnsw": HNSW},
            "metadata": {
                "hnsw:space": "cosine",
                "hnsw:M": 16,
                "hnsw:construction_ef": 100,
                "hnsw:search_ef": 100,
            },
        }
        journal.note(
            "CREATE_INTENT", {"name": COLLECTION_NAME, "body_sha256": sha(canonical(body))}
        )
        created = client.request("POST", COLS, body)
        ident = created["id"]
        require(
            str(uuid.UUID(ident)) == ident
            and ident not in before
            and created["name"] == COLLECTION_NAME,
            "created_target",
        )
        journal.note("CREATE_ACK", {"id": ident})
        writes += 1
        descriptor(client, ident)
        require(count(client, ident) == 0, "created_nonempty")
        for start in range(0, len(records), BATCH_SIZE):
            batch = records[start : start + BATCH_SIZE]
            require(count(client, ident) == start, "count_before_add")
            descriptor(client, ident)
            body = {
                key: [row[field] for row in batch]
                for key, field in [
                    ("ids", "id"),
                    ("documents", "document"),
                    ("metadatas", "metadata"),
                ]
            }
            body["embeddings"] = [
                base64.b64encode(f32_bytes(r["embedding"])).decode("ascii") for r in batch
            ]
            journal.note(
                "ADD_INTENT",
                {
                    "id": ident,
                    "start": start,
                    "ids": body["ids"],
                    "body_sha256": sha(canonical(body)),
                },
            )
            ack = client.request("POST", f"{COLS}/{ident}/add", body)
            require(ack is None or ack is True or ack == {}, "add_ack")
            journal.note("ADD_ACK", {"start": start, "count": len(batch)})
            writes += 1
            compare_rows(
                batch,
                client.request(
                    "POST", f"{COLS}/{ident}/get", {"ids": body["ids"], "include": INCLUDE}
                ),
            )
            require(count(client, ident) == start + len(batch), "count_after_add")
            journal.note("ADD_READBACK_ACCEPTED", {"start": start, "count": len(batch)})
    verify_rows(client, ident, records)
    require(descriptor(client, ident).get("dimension") == 768, "target_dimension")
    expected = before if existing is not None else {**before, ident: COLLECTION_NAME}
    require(
        inventory(client) == expected and all(count(client, i) == n for i, n in counts.items()),
        "protected_inventory_or_count_changed",
    )
    result = {
        "status": "REUSED_VERIFIED" if existing is not None else "NEW_VERIFIED",
        "collection": COLLECTION_NAME,
        "id": ident,
        "records": len(records),
        "Chroma_writes": writes,
        "document_embeddings": 0,
        "protected_collections": len(before),
        "preservation": "UUID/name/count plus no writes to preexisting UUIDs",
        "readback": "exact Float32 T for every record; not an image or durability attestation",
    }
    journal.note("VERIFIED", result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ollama-base-url")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args(argv)
    journal = None
    try:
        require(not args.execute or not (args.check or args.describe), "exclusive_mode")
        if args.describe:
            print(
                json.dumps(
                    {
                        "package": str(DEFAULT_PACKAGE),
                        "collection": COLLECTION_NAME,
                        "model": MODEL,
                        "digest": DIGEST,
                        "network_calls": 0,
                    }
                )
            )
            return 0
        _, records = load_package()
        if not args.execute:
            print(
                json.dumps(
                    {
                        "status": "CHECKED",
                        "records": len(records),
                        "package": str(DEFAULT_PACKAGE),
                        "collection": COLLECTION_NAME,
                        "payload_sha256": PAYLOAD_SHA256,
                        "network_calls": 0,
                    }
                )
            )
            return 0
        require(args.host and args.ollama_base_url and args.receipt, "execution_arguments")
        url = urlsplit(args.ollama_base_url)
        require(
            url.scheme in ("http", "https")
            and url.hostname
            and url.username is None
            and url.password is None
            and url.path in ("", "/")
            and not url.query
            and not url.fragment,
            "ollama_endpoint",
        )
        deadline = time.monotonic() + 3600
        client = HTTP(args.host, args.port, deadline=deadline)
        ollama = HTTP(
            url.hostname,
            url.port or (443 if url.scheme == "https" else 80),
            url.scheme,
            deadline=deadline,
        )
        journal = Journal(args.receipt)
        journal.note(
            "START",
            {
                "payload_sha256": PAYLOAD_SHA256,
                "manifest_sha256": MANIFEST_SHA256,
                "release": "gold-a-cc7bf44b54a9",
                "at_utc": datetime.now(UTC).isoformat(),
                "host": args.host,
                "port": args.port,
                "ollama_base_url": args.ollama_base_url,
                "collection": COLLECTION_NAME,
                "verify_only": args.verify_only,
            },
        )
        profile = check_model(ollama)
        journal.note("MODEL_METADATA_VERIFIED", profile)
        result = restore(client, records, journal, args.verify_only)
        print(json.dumps(result))
        return 0
    except Exception as exc:
        result = {
            "status": "BLOCKED",
            "error": str(exc) if type(exc) is Stop else type(exc).__name__,
            "uncertain_write": journal.pending if journal else False,
            "automatic_retry": False,
        }
        if journal:
            journal.note("BLOCKED", result)
        print(json.dumps(result))
        return 1
    finally:
        if journal:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
