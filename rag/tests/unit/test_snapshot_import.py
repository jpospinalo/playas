"""ING-09: errores visibles e importaciones repetibles sin borrar colecciones."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "snapshot_import", Path(__file__).resolve().parents[3] / "data/import_to_chromadb.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Collection:
    def __init__(self, failures=0, discard=False):
        self.ids = set()
        self.failures = failures
        self.calls = 0
        self.discard = discard

    def count(self):
        return len(self.ids)

    def get(self, ids, include):
        return {"ids": list(set(ids) & self.ids)}

    def upsert(self, ids, **kwargs):
        self.calls += 1
        if self.failures:
            self.failures -= 1
            raise ConnectionError("fake")
        if not self.discard:
            self.ids.update(ids)


RECORDS = [{"id": "a", "document": "texto", "metadata": {}, "embedding": [1.0]}]


def test_repeat_is_idempotent():
    collection = Collection()
    assert module.import_records(collection, RECORDS) == 1
    assert module.import_records(collection, RECORDS) == 1


def test_retry_is_bounded(monkeypatch):
    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    collection = Collection(failures=10)
    with pytest.raises(RuntimeError):
        module.import_records(collection, RECORDS)
    assert collection.calls == 2


def test_silent_discard_fails_reconciliation():
    with pytest.raises(RuntimeError, match="conteo"):
        module.import_records(Collection(discard=True), RECORDS)


def test_invalid_batch_rejected_before_write():
    with pytest.raises(ValueError):
        module.import_records(Collection(), RECORDS, batch_size=0)
    with pytest.raises(SystemExit):
        module.parse_args(["file.gz", "--batch-size", "0"])
