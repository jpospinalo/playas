"""C6 — el bucle de reintentos de build_or_load_vectorstore debe salir en
cuanto `collection.add()` tiene éxito.

Defecto confirmado por lectura de código: el `for attempt in
range(MAX_RETRIES): try: ... except Exception: ...` de
`core/vectorstore.py` nunca hace `break` tras un intento exitoso — sale del
`for` únicamente cuando se agotan los `MAX_RETRIES` intentos. Eso significa
que un batch que tiene éxito en el PRIMER intento se re-embebe y se vuelve
a enviar a Chroma dos veces más (MAX_RETRIES=3 en total), sin ningún error
de por medio: trabajo redundante silencioso, no solo ineficiencia — cada
reintento vuelve a llamar a Ollama (embeddings) y a Chroma (`add`) con los
mismos ids, aunque `add` sea idempotente en la práctica por id repetido.

Estas pruebas usan dobles locales (sin red real) para el cliente de Chroma
y la función de embeddings, controlando exactamente cuántas veces se debe
invocar cada uno según el escenario:
  1. Éxito en el primer intento → exactamente 1 llamada a embed y a add.
  2. Dos fallos y éxito al tercer intento → exactamente 3 llamadas a cada
     uno (recuperación correcta, sin exceder MAX_RETRIES).
  3. Fallo persistente → RuntimeError tras exactamente MAX_RETRIES intentos.
`time.sleep` se parchea a no-op para que las pruebas no esperen los
backoffs reales.
"""

from __future__ import annotations

import json

import pytest

import rag.core.vectorstore as vectorstore_module
from rag.core.vectorstore import MAX_RETRIES, build_or_load_vectorstore

_GOLD_KEY = "gold/jurisprudencia/exp1.jsonl"


def _gold_jsonl() -> str:
    records = [
        {
            "page_content": "Texto del fragmento uno.",
            "metadata": {"chunk_id": "exp1_chunk_0", "source": "exp1.pdf"},
        },
        {
            "page_content": "Texto del fragmento dos.",
            "metadata": {"chunk_id": "exp1_chunk_1", "source": "exp1.pdf"},
        },
    ]
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"


class _FakeCollection:
    """Colección Chroma mínima: sin ids preexistentes, `add()` delega en un
    callback controlado por la prueba para decidir cuándo fallar."""

    def __init__(self, on_add) -> None:
        self._on_add = on_add
        self.add_calls = 0

    def count(self) -> int:
        return 0

    def get(self, ids: list[str], include: list[str] | None = None) -> dict:
        return {"ids": []}  # nada preexistente: todos los ids son "nuevos"

    def add(self, *, ids, documents, metadatas, embeddings) -> None:
        self.add_calls += 1
        self._on_add(self.add_calls)


class _FakeEmbedFn:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[0.0, 0.0] for _ in texts]


class _FakeHttpClient:
    def __init__(self, collection: _FakeCollection) -> None:
        self._collection = collection

    def get_or_create_collection(self, name: str) -> _FakeCollection:
        return self._collection


def _wire_common(monkeypatch: pytest.MonkeyPatch, collection: _FakeCollection, embed_fn):
    monkeypatch.setattr(vectorstore_module, "list_keys", lambda prefix, suffix=None: [_GOLD_KEY])
    monkeypatch.setattr(vectorstore_module, "read_text", lambda key: _gold_jsonl())
    monkeypatch.setattr(vectorstore_module, "EMBED_FN", embed_fn)
    monkeypatch.setattr(
        vectorstore_module.chromadb, "HttpClient", lambda **kwargs: _FakeHttpClient(collection)
    )
    monkeypatch.setattr(vectorstore_module.time, "sleep", lambda seconds: None)


def test_successful_batch_is_embedded_and_added_exactly_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un batch que tiene éxito en el primer intento no debe reintentarse:
    ni el embedding ni el `add` deben repetirse."""
    embed_fn = _FakeEmbedFn()
    collection = _FakeCollection(on_add=lambda attempt: None)  # siempre tiene éxito
    _wire_common(monkeypatch, collection, embed_fn)

    build_or_load_vectorstore(gold_prefix="gold/jurisprudencia/", collection_name="test-coll")

    assert embed_fn.calls == 1, f"se esperaba 1 llamada de embedding, hubo {embed_fn.calls}"
    assert collection.add_calls == 1, f"se esperaba 1 llamada a add, hubo {collection.add_calls}"


def test_batch_recovers_after_two_failures_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dos fallos de red seguidos de éxito deben recuperarse dentro de
    MAX_RETRIES, sin excederlo ni levantar excepción."""
    embed_fn = _FakeEmbedFn()

    def on_add(attempt: int) -> None:
        if attempt < 3:
            raise ConnectionError("fallo de red simulado")

    collection = _FakeCollection(on_add=on_add)
    _wire_common(monkeypatch, collection, embed_fn)

    build_or_load_vectorstore(gold_prefix="gold/jurisprudencia/", collection_name="test-coll")

    assert collection.add_calls == 3
    assert embed_fn.calls == 3


def test_batch_raises_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un fallo persistente debe agotar exactamente MAX_RETRIES intentos y
    propagar un RuntimeError con contexto del batch."""
    embed_fn = _FakeEmbedFn()

    def on_add(attempt: int) -> None:
        raise ConnectionError("connection refused: fallo de red simulado persistente")

    collection = _FakeCollection(on_add=on_add)
    _wire_common(monkeypatch, collection, embed_fn)

    with pytest.raises(RuntimeError, match="ChromaDB"):
        build_or_load_vectorstore(gold_prefix="gold/jurisprudencia/", collection_name="test-coll")

    assert collection.add_calls == MAX_RETRIES
    assert embed_fn.calls == MAX_RETRIES
