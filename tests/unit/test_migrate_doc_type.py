"""Tests de la lógica pura de cálculo de destinos en utils.migrate_doc_type.

No tocan S3: se mockea ingest.s3_client.list_keys.
"""

from __future__ import annotations

from unittest.mock import patch

from utils.migrate_doc_type import _remap_key, plan_moves


def test_remap_key_root_object_goes_to_jurisprudencia() -> None:
    assert (
        _remap_key("data/bronze/Caso A/file.md", "bronze")
        == "data/bronze/jurisprudencia/Caso A/file.md"
    )


def test_remap_key_metadata_csv_special_case() -> None:
    assert (
        _remap_key("data/raw/metadata.csv", "raw")
        == "data/raw/jurisprudencia/metadata.csv"
    )


def test_remap_key_already_under_jurisprudencia_is_skipped() -> None:
    assert _remap_key("data/bronze/jurisprudencia/ya.md", "bronze") is None


def test_remap_key_already_under_normativa_is_skipped() -> None:
    assert _remap_key("data/gold/normativa/ley.json", "gold") is None


def test_remap_key_wrong_layer_returns_none() -> None:
    assert _remap_key("data/silver/x.jsonl", "bronze") is None


def test_remap_key_layer_root_itself_returns_none() -> None:
    assert _remap_key("data/bronze/", "bronze") is None


def test_plan_moves_remaps_only_unmigrated_keys() -> None:
    sample = {
        "data/raw/": [
            "data/raw/metadata.csv",
            "data/raw/Caso A/doc.pdf",
            "data/raw/jurisprudencia/ya.pdf",
        ],
        "data/bronze/": [
            "data/bronze/Caso A/file.md",
            "data/bronze/jurisprudencia/ya.md",
        ],
        "data/silver/": [],
        "data/gold/": ["data/gold/normativa/ley.json"],
    }

    def fake_list_keys(prefix: str, suffix: str = "") -> list[str]:
        return sample[prefix]

    with patch("ingest.s3_client.list_keys", side_effect=fake_list_keys):
        moves = plan_moves()

    assert moves == [
        ("data/raw/metadata.csv", "data/raw/jurisprudencia/metadata.csv"),
        ("data/raw/Caso A/doc.pdf", "data/raw/jurisprudencia/Caso A/doc.pdf"),
        ("data/bronze/Caso A/file.md", "data/bronze/jurisprudencia/Caso A/file.md"),
    ]

    # No re-mueve nada que ya esté bajo jurisprudencia/ o normativa/.
    srcs = [src for src, _ in moves]
    assert "data/raw/jurisprudencia/ya.pdf" not in srcs
    assert "data/bronze/jurisprudencia/ya.md" not in srcs
    assert "data/gold/normativa/ley.json" not in srcs
