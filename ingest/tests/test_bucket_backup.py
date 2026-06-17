"""Pruebas TDD para el backup del bucket usando el cliente central."""

from __future__ import annotations

import importlib
from pathlib import Path


class _FixedNow:
    def strftime(self, _format: str) -> str:
        return "20260617-120000"


class _FixedDateTime:
    @staticmethod
    def now() -> _FixedNow:
        return _FixedNow()


def test_bucket_backup_uses_central_s3_client(monkeypatch, tmp_path, capsys):
    import ingest.tools.bucket_backup as bucket_backup

    bucket_backup = importlib.reload(bucket_backup)

    downloaded: list[tuple[str, str, str]] = []

    class FakePaginator:
        def paginate(self, Bucket: str):
            assert Bucket == "playas-local"
            return [{"Contents": [{"Key": "data/gold/doc.jsonl"}, {"Key": "data/raw/"}]}]

    class FakeClient:
        def get_paginator(self, name: str):
            assert name == "list_objects_v2"
            return FakePaginator()

        def download_file(self, bucket: str, key: str, destination: str):
            downloaded.append((bucket, key, destination))
            Path(destination).write_text("ok", encoding="utf-8")

    monkeypatch.setattr(bucket_backup, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(bucket_backup, "datetime", _FixedDateTime)
    monkeypatch.setattr(bucket_backup, "get_client", lambda: FakeClient(), raising=False)
    monkeypatch.setattr(bucket_backup, "get_bucket", lambda: "playas-local", raising=False)

    bucket_backup.main()

    output = capsys.readouterr().out
    assert "Bucket:  playas-local" in output
    assert "✓ 1 objeto(s) descargado(s)" in output
    assert downloaded == [
        (
            "playas-local",
            "data/gold/doc.jsonl",
            str(tmp_path / "bucket-backup-20260617-120000" / "data/gold/doc.jsonl"),
        )
    ]
