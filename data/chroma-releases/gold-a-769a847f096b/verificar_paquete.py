"""Verifica esta entrega Gold usando solo archivos locales y biblioteca estándar."""

import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import struct
import sys
from collections import Counter

VERSION = "gold-a-769a847f096b"
PAYLOAD = "GOLD_A.jsonl.gz"
PROVENANCE = "PROCEDENCIA_GOLD_A.json"
MANIFEST = "manifest.json"
FILES = frozenset({PAYLOAD, PROVENANCE, MANIFEST, "README.md", "verificar_paquete.py"})
SOURCE_HASHES = {
    PAYLOAD: "769a847f096bba8a5a7269c34ddc780ca7dc35d170fde128b871fda019ebe6c8",
    PROVENANCE: "f9ec241ca9b537241ab209cc3b6ba5c11fd7adaadd845865b5601f3057a28149",
}
SOURCE_COMMIT = "23c6c5bab2e4b47dbda77f3d197ce46dab2af57a"
GENERATION_HEAD = "c642d097329bdb9904bb5b70d2e36a7e1cab8c77"
GOLD_P1 = "d82aa5ca047aa993bface1121de239e3fbf8fda637c4a1c6dbe2dcf53ab4de1f"
MODEL_DIGEST = "85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1"
MODEL_BLOB = "0800cbac9c2064dde519420e75e512a83cb360de3ad5df176185dc69652fc515"
RECIPE = "ce71bedba019d7cd54952a22fb2973fc462924f6549baec808c6f059ea531739"
RECORDS, DIMENSION = 5862, 768
DOC_TYPES = {"jurisprudencia": 4404, "normativa": 1458}


class PackageError(Exception):
    """Categoría fija de rechazo; no modifica ni repara archivos."""


def require(ok, category):
    if not ok:
        raise PackageError(category)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def finite(text):
        value = float(text)
        require(math.isfinite(value), "nonfinite_json_number")
        return value
    def reject(_):
        raise PackageError("nonfinite_json_number")
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=finite, parse_constant=reject)
    except (ValueError, TypeError, UnicodeError) as exc:
        raise PackageError("invalid_json") from exc


def validate_entry_name(name):
    require(type(name) is str and name in FILES and "/" not in name and "\\" not in name
            and not Path(name).is_absolute() and name not in (".", ".."), "unsafe_path")


def check_names(names):
    require(set(names) == FILES, "unexpected_files")


def safe_file(root, name):
    validate_entry_name(name)
    path = root / name
    require(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(), "not_regular_file")
    require(path.resolve().parent == root.resolve(), "unsafe_path")
    return path


def verify_file(path, entry):
    require(type(entry) is dict and set(entry) == {"sha256", "bytes", "preparation_mode"}, "file_entry")
    require(type(entry["bytes"]) is int and entry["bytes"] > 0
            and type(entry["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
            and type(entry["preparation_mode"]) is int and entry["preparation_mode"] == 0o600, "file_entry")
    require(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(), "not_regular_file")
    require(path.stat().st_size == entry["bytes"], "file_size")
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    require(h.hexdigest() == entry["sha256"], "file_hash")
    # El modo de preparación es histórico: un clone Git puede crear archivos 0644.


def validate_record(row):
    require(type(row) is dict and set(row) == {"id", "document", "metadata", "embedding"}, "record_fields")
    require(type(row["id"]) is str and bool(row["id"]), "record_id")
    require(type(row["document"]) is str and bool(row["document"].strip()), "record_body")
    meta = row["metadata"]
    require(type(meta) is dict and type(meta.get("chunk_id")) is str and meta["chunk_id"] == row["id"], "metadata_id")
    require(all(type(k) is str and k and type(v) in (str, int, float, bool)
                and (type(v) is not float or math.isfinite(v)) for k, v in meta.items()), "metadata_scalar")
    require(meta.get("doc_type") in DOC_TYPES, "doc_type")
    vector = row["embedding"]
    require(type(vector) is list and len(vector) == DIMENSION, "vector_dimension")
    require(all(type(x) in (int, float) and math.isfinite(x) for x in vector), "vector_number")
    require(math.isfinite(math.hypot(*vector)) and math.hypot(*vector) > 0, "vector_norm")
    try:
        rounded = struct.unpack("<768f", struct.pack("<768f", *vector))
    except (OverflowError, struct.error) as exc:
        raise PackageError("vector_float32") from exc
    require(all(math.isfinite(x) for x in rounded) and math.hypot(*rounded) > 0, "vector_float32")
    return row["id"]


def check_new_id(ident, seen):
    require(ident not in seen, "duplicate_id")


def validate_manifest(m):
    required = {"schema_version", "version", "kind", "created_at_utc", "source", "content", "embedding",
                "index", "readback_contract", "evidence", "state_at_packaging", "files", "historical_collection_observations"}
    require(type(m) is dict and set(m) == required, "manifest_fields")
    require(type(m["schema_version"]) is int and m["schema_version"] == 1
            and m["version"] == VERSION and m["kind"] == "gold_logical_input_backup", "manifest_identity")
    require(type(m["files"]) is dict and set(m["files"]) == FILES - {MANIFEST}, "manifest_file_list")
    for name in m["files"]:
        validate_entry_name(name)
        require(type(m["files"][name]) is dict, "file_entry")
    require(all(m["files"][n].get("sha256") == h for n, h in SOURCE_HASHES.items()), "source_hash_contract")
    content = m["content"]
    require(type(content) is dict and canonical(content.get("records")) == b"5862"
            and canonical(content.get("dimension")) == b"768" and canonical(content.get("doc_types")) == canonical(DOC_TYPES)
            and content.get("Gold_P1_sha256") == GOLD_P1, "content_contract")
    require(type(m["source"]) is dict and m["source"].get("source_gold_commit") == SOURCE_COMMIT
            and m["source"].get("repository_head_at_generation") == GENERATION_HEAD
            and m["source"].get("repository_head_at_packaging") == GENERATION_HEAD, "source_commit_contract")
    header = content.get("payload_manifest")
    require(type(header) is dict and header.get("source_commit") == SOURCE_COMMIT and header.get("HEAD") == GENERATION_HEAD
            and header.get("manifest_sha256") == GOLD_P1 and header.get("model_digest") == MODEL_DIGEST
            and header.get("model_blob_sha256") == MODEL_BLOB and header.get("recipe_source_sha256") == RECIPE
            and header.get("kind") == "not_loaded", "payload_manifest_contract")
    require(type(m["embedding"]) is dict and m["embedding"].get("model") == "embeddinggemma:latest"
            and m["embedding"].get("model_digest") == MODEL_DIGEST and m["embedding"].get("model_blob_sha256") == MODEL_BLOB
            and m["embedding"].get("recipe_source_sha256") == RECIPE
            and m["embedding"].get("vector_input") == "original_generation_vectors", "embedding_contract")
    require(canonical(m["index"]) == canonical({"space": "cosine", "ef_construction": 100, "ef_search": 100,
            "max_neighbors": 16, "resize_factor": 1.2, "sync_threshold": 1000}), "index_contract")
    require(type(m["readback_contract"]) is dict and m["readback_contract"].get("image_id") ==
            "sha256:111a6bd768be19721f5b4e88567d0e1d1f5c2ab5161129e711c0a431e667b128"
            and m["readback_contract"].get("architecture") == "x86_64"
            and m["readback_contract"].get("hnsw_revision") == "312991cf9e640d5ccab879906a51e7612ce6fcf1",
            "readback_contract")
    require(type(m["state_at_packaging"]) is dict
            and m["state_at_packaging"].get("independent_restore_tested") is False
            and m["state_at_packaging"].get("durability_tested") is False
            and m["state_at_packaging"].get("remote_state_rechecked_at_packaging") is False, "state_contract")
    require(type(m["evidence"]) is dict and m["evidence"].get("full_forensic_chain_included") is False, "evidence_contract")


def verify_package(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), "package_directory")
    check_names(p.name for p in root.iterdir())
    paths = {name: safe_file(root, name) for name in FILES}
    manifest = strict_json(paths[MANIFEST].read_bytes())
    validate_manifest(manifest)
    for name, entry in manifest["files"].items():
        verify_file(paths[name], entry)
    provenance = strict_json(paths[PROVENANCE].read_bytes())
    require(type(provenance) is dict and type(provenance.get("vector_records")) is list
            and len(provenance["vector_records"]) == RECORDS and provenance.get("partial_sources") == [], "provenance_contract")
    refs = {}
    for row in provenance["vector_records"]:
        require(type(row) is dict and type(row.get("id")) is str and row["id"] not in refs, "provenance_id")
        refs[row["id"]] = row
    header = manifest["content"]["payload_manifest"]
    require(all(k in provenance and canonical(provenance[k]) == canonical(v) for k, v in header.items()), "provenance_header")
    seen, counts, vector_hashes = set(), Counter(), Counter()
    try:
        with gzip.open(paths[PAYLOAD], "rb") as stream:
            require(canonical(strict_json(stream.readline())) == canonical({"__manifest__": header}), "payload_header")
            for line in stream:
                row = strict_json(line)
                ident = validate_record(row)
                check_new_id(ident, seen)
                ref = refs.get(ident)
                require(ref is not None, "provenance_id")
                vhash = digest(canonical(row["embedding"]))
                require(digest(row["document"].encode("utf-8")) == ref["page_content_sha256"]
                        and digest(canonical(row["metadata"])) == ref["metadata_payload_sha256"]
                        and vhash == ref["vector_sha256"], "provenance_hash")
                seen.add(ident)
                counts[row["metadata"]["doc_type"]] += 1
                vector_hashes[vhash] += 1
    except (gzip.BadGzipFile, EOFError) as exc:
        raise PackageError("gzip_integrity") from exc
    require(len(seen) == RECORDS and seen == set(refs) and dict(counts) == DOC_TYPES, "record_count")
    require(len(vector_hashes) == 5859 and sorted(v for v in vector_hashes.values() if v > 1) == [2, 2, 2], "duplicate_vector_contract")
    return {"status": "RESPALDO_LOGICO_VERIFICADO_RECUPERACION_NO_ENSAYADA", "version": VERSION,
            "records": len(seen), "dimension": DIMENSION, "doc_types": dict(counts), "unique_vectors": len(vector_hashes),
            "duplicate_vector_pairs_preserved": 3, "manifest_sha256": digest(paths[MANIFEST].read_bytes()),
            "payload_sha256": SOURCE_HASHES[PAYLOAD], "network_calls": 0, "files_changed": 0}


def main():
    if len(sys.argv) != 1:
        print(json.dumps({"status": "ERROR", "category": "unexpected_arguments"}))
        return 2
    try:
        script = Path(__file__).absolute()
        require(not script.is_symlink(), "not_regular_file")
        result = verify_package(script.parent)
    except PackageError as exc:
        print(json.dumps({"status": "ERROR", "category": str(exc)}))
        return 1
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        print(json.dumps({"status": "ERROR", "category": "incompatible_local_file"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
