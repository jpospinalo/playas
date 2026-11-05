"""Metadato de distancia de la colección Chroma creada por producción.

Las colecciones vivas del proyecto usan distancia coseno; sin el metadato,
Chroma crearía la colección con su espacio por defecto (l2). Estos tests usan
un doble local del cliente (sin red, sin Chroma real) que replica el contrato
de chromadb 1.5.9: al crear, el metadato se persiste; si la colección ya
existe, `get_or_create_collection` ignora el metadato recibido.
"""

from __future__ import annotations

import json

import pytest

import rag.core.vectorstore as vectorstore_module
from evaluation.indexar_gold_local import COLLECTION_METADATA as EVAL_COLLECTION_METADATA
from rag.core.vectorstore import COLLECTION_METADATA, build_or_load_vectorstore

_GOLD_KEY = "gold/jurisprudencia/exp1.jsonl"


def _gold_jsonl() -> str:
    records = [
        {
            "page_content": "Texto del fragmento uno.",
            "metadata": {"chunk_id": "exp1_chunk_0", "source": "exp1.pdf"},
        },
    ]
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"


class _FakeCollection:
    def __init__(self, metadata: dict | None) -> None:
        self.metadata = metadata

    def count(self) -> int:
        return 0

    def get(self, ids: list[str], include: list[str] | None = None) -> dict:
        return {"ids": []}

    def add(self, *, ids, documents, metadatas, embeddings) -> None:
        return None


class _FakeClient:
    """Doble del cliente: registra los argumentos de `get_or_create_collection`."""

    def __init__(self, existing_metadata: dict | None = None) -> None:
        self.calls: list[dict] = []
        self.collection = (
            _FakeCollection(existing_metadata) if existing_metadata is not None else None
        )

    def get_or_create_collection(self, name: str, metadata: dict | None = None) -> _FakeCollection:
        self.calls.append({"name": name, "metadata": metadata})
        if self.collection is None:
            self.collection = _FakeCollection(metadata)
        # Igual que chromadb 1.5.9: si ya existe, el metadato recibido se ignora.
        return self.collection


def _wire(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(vectorstore_module, "list_keys", lambda prefix, suffix=None: [_GOLD_KEY])
    monkeypatch.setattr(vectorstore_module, "read_text", lambda key: _gold_jsonl())
    monkeypatch.setattr(vectorstore_module, "EMBED_FN", lambda texts: [[0.0, 0.0] for _ in texts])
    monkeypatch.setattr(vectorstore_module.chromadb, "HttpClient", lambda **kwargs: client)


def test_new_collection_is_created_with_cosine_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient()
    _wire(monkeypatch, client)

    build_or_load_vectorstore(gold_prefix="gold/jurisprudencia/", collection_name="test-coll")

    assert client.calls == [{"name": "test-coll", "metadata": {"hnsw:space": "cosine"}}]
    assert client.collection.metadata == {"hnsw:space": "cosine"}


def test_existing_collection_is_reused_without_touching_its_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existente = {"hnsw:space": "cosine", "otra_clave": "valor"}
    client = _FakeClient(existing_metadata=existente)
    _wire(monkeypatch, client)

    collection = build_or_load_vectorstore(
        gold_prefix="gold/jurisprudencia/", collection_name="test-coll"
    )

    assert collection is client.collection
    assert collection.metadata == existente
    assert client.calls[0]["metadata"] == COLLECTION_METADATA


def test_production_metadata_matches_evaluation_indexer() -> None:
    assert COLLECTION_METADATA["hnsw:space"] == EVAL_COLLECTION_METADATA["hnsw:space"]
