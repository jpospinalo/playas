"""CLI real del importador con gzip sintético y Chroma fake, nunca HTTP real."""

import gzip
import json
import runpy
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

import pytest

_SCRIPT = Path(__file__).resolve().parents[3] / "data" / "import_to_chromadb.py"


@pytest.fixture
def records():
    return [
        {
            "id": f"synthetic-{i}",
            "document": f"Texto sintético {i}",
            "embedding": [i / 10, 0.25, -0.5],
            **({"metadata": {"doc_type": "normativa", "index": i}} if i != 2 else {}),
        }
        for i in range(5)
    ]


def _write_export(tmp_path, records, manifest=None):
    path = tmp_path / "synthetic.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write("\n")
        if manifest is not None:
            stream.write(json.dumps({"__manifest__": manifest}) + "\n")
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


@pytest.fixture
def importer(monkeypatch):
    collection = Mock(spec=["count", "upsert"])
    client = Mock(spec=["heartbeat", "delete_collection", "get_or_create_collection"])
    client.get_or_create_collection.return_value = collection
    factory = Mock(return_value=client)
    fake_module = ModuleType("chromadb")
    fake_module.HttpClient = factory
    monkeypatch.setitem(sys.modules, "chromadb", fake_module)
    state = SimpleNamespace(
        client=client,
        collection=collection,
        factory=factory,
        failed_batches=set(),
        imported_ids=[],
    )
    collection.count.side_effect = lambda: 7 + len(state.imported_ids)

    def upsert(**payload):
        index = collection.upsert.call_count - 1
        if index in state.failed_batches:
            raise RuntimeError(f"synthetic failure {index}")
        state.imported_ids.extend(payload["ids"])

    collection.upsert.side_effect = upsert

    def run(path, *arguments):
        monkeypatch.setattr(sys, "argv", [str(_SCRIPT), str(path), *arguments])
        try:
            runpy.run_path(str(_SCRIPT), run_name="__main__")
        except SystemExit as error:
            return error.code
        return 0

    state.run = run
    return state


def _assert_payloads(importer, records, batch_size):
    batches = [records[i : i + batch_size] for i in range(0, len(records), batch_size)]
    assert importer.collection.upsert.call_args_list == [
        call(
            ids=[r["id"] for r in batch],
            documents=[r["document"] for r in batch],
            metadatas=[r.get("metadata", {}) for r in batch],
            embeddings=[r["embedding"] for r in batch],
        )
        for batch in batches
    ]


@pytest.mark.parametrize("batch_size", [1, 2, 3, 100])
def test_success_preserves_exact_payloads_and_short_final_batch(
    importer, tmp_path, records, capsys, batch_size
):
    path = _write_export(tmp_path, records)
    assert importer.run(path, "--batch-size", str(batch_size)) == 0
    _assert_payloads(importer, records, batch_size)
    assert importer.imported_ids == [r["id"] for r in records]
    importer.factory.assert_called_once_with(host="localhost", port=8000)
    importer.client.heartbeat.assert_called_once_with()
    importer.client.get_or_create_collection.assert_called_once_with(
        name="default", metadata={"hnsw:space": "cosine"}
    )
    importer.client.delete_collection.assert_not_called()
    assert importer.collection.count.call_count == 2
    output = capsys.readouterr()
    assert "5 imported, 0 errors" in output.out
    assert "now has 12 documents" in output.out
    assert output.err == ""


@pytest.mark.parametrize(("failed", "errors"), [({1}, 2), ({0, 1, 2}, 5), ({0}, 2), ({2}, 1)])
def test_failed_batches_continue_but_entrypoint_exits_one(
    importer, tmp_path, records, capsys, failed, errors
):
    path = _write_export(tmp_path, records)
    importer.failed_batches = failed
    code = importer.run(path, "--batch-size", "2")
    # Comprobar primero la continuación y el resumen, luego el nuevo exit code.
    _assert_payloads(importer, records, 2)
    assert len(importer.imported_ids) == len(records) - errors
    assert importer.collection.count.call_count == 2
    output = capsys.readouterr()
    assert f"{5 - errors} imported, {errors} errors" in output.out
    assert "now has" in output.out
    assert output.err.count("ERROR on batch") == len(failed)
    importer.client.delete_collection.assert_not_called()
    assert code == 1


def test_empty_export_still_connects_and_gets_collection_without_upsert(importer, tmp_path, capsys):
    path = _write_export(tmp_path, [])
    assert importer.run(path) == 0
    importer.factory.assert_called_once_with(host="localhost", port=8000)
    importer.client.heartbeat.assert_called_once_with()
    importer.client.get_or_create_collection.assert_called_once_with(
        name="default", metadata={"hnsw:space": "cosine"}
    )
    importer.collection.upsert.assert_not_called()
    importer.client.delete_collection.assert_not_called()
    assert importer.collection.count.call_count == 2
    assert "0 imported, 0 errors" in capsys.readouterr().out


@pytest.mark.parametrize("batch_size", ["0", "-1", "-100"])
@pytest.mark.parametrize("recreate", [False, True])
def test_nonpositive_batch_size_exits_two_before_constructing_client(
    importer, tmp_path, records, capsys, batch_size, recreate
):
    path = _write_export(tmp_path, records)
    flags = ["--batch-size", batch_size] + (["--recreate"] if recreate else [])
    code = importer.run(path, *flags)
    assert code == 2
    importer.factory.assert_not_called()
    assert importer.client.mock_calls == []
    assert "--batch-size" in capsys.readouterr().err


def test_invalid_batch_size_is_checked_before_reading_export(importer, tmp_path, capsys):
    assert importer.run(tmp_path / "missing.jsonl.gz", "--batch-size", "-1") == 2
    importer.factory.assert_not_called()
    output = capsys.readouterr()
    assert "--batch-size" in output.err
    assert "File not found" not in output.err


def test_nonnumeric_batch_size_preserves_parser_error(importer, tmp_path):
    assert importer.run(tmp_path / "missing.jsonl.gz", "--batch-size", "invalid") == 2
    importer.factory.assert_not_called()


def test_missing_file_preserves_failure_without_client(importer, tmp_path, capsys):
    assert importer.run(tmp_path / "missing.jsonl.gz") == 1
    importer.factory.assert_not_called()
    assert "File not found" in capsys.readouterr().err


def test_invalid_gzip_preserves_exception_before_connection(importer, tmp_path):
    path = tmp_path / "invalid.jsonl.gz"
    path.write_bytes(b"not gzip")
    with pytest.raises(gzip.BadGzipFile):
        importer.run(path)
    importer.factory.assert_not_called()


def test_invalid_json_preserves_exception_before_connection(importer, tmp_path):
    path = tmp_path / "invalid.jsonl.gz"
    with gzip.open(path, "wt") as stream:
        stream.write("invalid json\n")
    with pytest.raises(json.JSONDecodeError):
        importer.run(path)
    importer.factory.assert_not_called()


def test_heartbeat_failure_exits_one_without_collection_or_writes(
    importer, tmp_path, records, capsys
):
    path = _write_export(tmp_path, records)
    importer.client.heartbeat.side_effect = RuntimeError("synthetic unavailable")
    assert importer.run(path) == 1
    importer.client.get_or_create_collection.assert_not_called()
    importer.client.delete_collection.assert_not_called()
    importer.collection.upsert.assert_not_called()
    assert "Could not connect" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("flags", "host", "port", "collection"),
    [
        ([], "manifest-host", 8123, "manifest-collection"),
        (
            ["--host", "cli-host", "--port", "8999", "--collection", "cli-collection"],
            "cli-host",
            8999,
            "cli-collection",
        ),
        (["--host", "cli-host"], "cli-host", 8123, "manifest-collection"),
    ],
)
def test_manifest_and_cli_precedence_are_unchanged(
    importer, tmp_path, records, flags, host, port, collection
):
    path = _write_export(
        tmp_path,
        records,
        {
            "chroma_host": "manifest-host",
            "chroma_port": 8123,
            "collection": "manifest-collection",
        },
    )
    assert importer.run(path, *flags) == 0
    importer.factory.assert_called_once_with(host=host, port=port)
    importer.client.get_or_create_collection.assert_called_once_with(
        name=collection, metadata={"hnsw:space": "cosine"}
    )
    importer.client.delete_collection.assert_not_called()
    _assert_payloads(importer, records, 100)


@pytest.mark.parametrize("delete_fails", [False, True])
def test_recreate_preserves_delete_then_create_and_import(
    importer, tmp_path, records, delete_fails
):
    path = _write_export(tmp_path, records)
    if delete_fails:
        importer.client.delete_collection.side_effect = RuntimeError("synthetic absent collection")
    assert importer.run(path, "--recreate", "--collection", "synthetic") == 0
    assert importer.client.method_calls == [
        call.heartbeat(),
        call.delete_collection("synthetic"),
        call.get_or_create_collection(name="synthetic", metadata={"hnsw:space": "cosine"}),
    ]
    _assert_payloads(importer, records, 100)


def test_missing_embedding_fails_that_batch_without_recalculating(
    importer, tmp_path, records, capsys
):
    del records[2]["embedding"]
    path = _write_export(tmp_path, records)
    code = importer.run(path, "--batch-size", "2")
    assert importer.collection.upsert.call_count == 2
    assert importer.imported_ids == ["synthetic-0", "synthetic-1", "synthetic-4"]
    assert "3 imported, 2 errors" in capsys.readouterr().out
    assert code == 1
