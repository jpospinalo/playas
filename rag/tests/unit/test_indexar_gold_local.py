"""Pruebas del indexador local de Gold, sin ChromaDB ni Ollama."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.indexar_gold_local import corpus_sha256, gold_files, load_local_records


def _write_gold(path: Path, chunk_id: str, content: str = "Texto") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "page_content": content,
        "metadata": {"chunk_id": chunk_id, "title": "Norma", "keywords": ["playa"]},
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")


def test_load_local_records_applies_production_logic(tmp_path: Path) -> None:
    path = tmp_path / "normativa" / "a.jsonl"
    _write_gold(path, "c1")

    ids, texts, embed_texts, metadatas = load_local_records(path)

    assert ids == ["c1"]
    assert texts == ["Texto"]
    assert metadatas[0]["doc_type"] == "normativa"
    assert embed_texts[0].startswith("Norma: Norma\nPalabras clave: playa")


def test_load_local_records_restores_s3_reader(tmp_path: Path) -> None:
    from rag.core import vectorstore

    original = vectorstore.read_text
    path = tmp_path / "normativa" / "a.jsonl"
    _write_gold(path, "c1")

    load_local_records(path)

    assert vectorstore.read_text is original


def test_gold_files_are_sorted_and_ignore_other_levels(tmp_path: Path) -> None:
    _write_gold(tmp_path / "normativa" / "b.jsonl", "c2")
    _write_gold(tmp_path / "jurisprudencia" / "a.jsonl", "c1")
    (tmp_path / "suelto.jsonl").write_text("{}", encoding="utf-8")

    assert [f"{p.parent.name}/{p.name}" for p in gold_files(tmp_path)] == [
        "jurisprudencia/a.jsonl",
        "normativa/b.jsonl",
    ]


def test_corpus_sha256_changes_with_content(tmp_path: Path) -> None:
    path = tmp_path / "normativa" / "a.jsonl"
    _write_gold(path, "c1")
    before = corpus_sha256(gold_files(tmp_path))
    assert before == corpus_sha256(gold_files(tmp_path))

    _write_gold(path, "c1", content="Otro texto")

    assert corpus_sha256(gold_files(tmp_path)) != before
