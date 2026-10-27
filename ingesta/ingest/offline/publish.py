"""Publicación local por documento; nunca permite escribir la línea base."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from .storage import writer_lock


def chroma_lock_directory(collection, port=8000, host="127.0.0.1"):
    """Identidad compartida entre procesos, independiente del directorio de trabajo."""
    root = Path(
        os.environ.get("ATLAS_CHROMA_LOCK_DIR")
        or Path(tempfile.gettempdir()) / "atlas-chroma-writers"
    )
    if not root.is_absolute():
        raise ValueError("ATLAS_CHROMA_LOCK_DIR debe ser una ruta absoluta")
    return root.resolve() / hashlib.sha256(f"{host}/{port}/{collection}".encode()).hexdigest()


def retry(operation):
    for attempt in range(2):
        try:
            return operation()
        except Exception:
            if attempt == 1:
                raise
            time.sleep(0.5)


class ChromaPublisher:
    def __init__(self, collection, config_hash, port=8000, fake_embeddings=False, legacy_hashes=()):
        if fake_embeddings and not collection.startswith("bench_"):
            raise ValueError("Embeddings ficticios requieren colección bench_")
        self.collection_name = collection
        if collection in {"v1", "atlas_v1", "rag_playas", "rag_playas_magdalena"}:
            raise ValueError("Colección base protegida; usa otro nombre")
        import chromadb

        self.lock_directory = chroma_lock_directory(collection, port)
        self._publishing = False
        with writer_lock(self.lock_directory):
            client = chromadb.HttpClient(host="127.0.0.1", port=port)
            try:
                self.collection = client.get_collection(collection)
            except chromadb.errors.NotFoundError:
                self.collection = client.create_collection(
                    collection,
                    metadata={"hnsw:space": "cosine", "atlas_offline_config": config_hash},
                )
            previous_hash = self.collection.metadata.get("atlas_offline_config")
            if previous_hash in legacy_hashes:
                self.collection.modify(
                    metadata={**self.collection.metadata, "atlas_offline_config": config_hash}
                )
            elif previous_hash != config_hash:
                raise ValueError("Colección de otra versión/modelo; crea una colección nueva")

    @contextmanager
    def publish_phase(self):
        # El sync/add conserva el bloqueo también entre documentos y eliminaciones.
        if self._publishing:
            yield
            return
        with writer_lock(self.lock_directory):
            self._publishing = True
            try:
                yield
            finally:
                self._publishing = False

    def upsert_document(self, doc_id, records, vectors):
        if not self.collection_name.startswith("bench_") and any(
            r.get("metadata", {}).get("embedding_model_digest", "").startswith("bench-")
            for r in records
        ):
            raise ValueError("Embeddings ficticios requieren colección bench_")
        with self.publish_phase():
            return self._upsert_document(doc_id, records, vectors)

    def _upsert_document(self, doc_id, records, vectors):
        wanted = {r["id"] for r in records}
        before = set(self.collection.get(where={"doc_id": doc_id}, include=[])["ids"])
        for offset in range(0, len(records), 100):
            batch = records[offset : offset + 100]
            retry(
                lambda batch=batch, offset=offset: self.collection.upsert(
                    ids=[r["id"] for r in batch],
                    documents=[r["document"] for r in batch],
                    metadatas=[r["metadata"] for r in batch],
                    embeddings=vectors[offset : offset + 100],
                )
            )
        observed = set(self.collection.get(where={"doc_id": doc_id}, include=[])["ids"])
        if not wanted <= observed:
            raise RuntimeError("Publicación incompleta; no borrar chunks anteriores")
        stale = before - wanted
        if stale:
            retry(lambda: self.collection.delete(ids=sorted(stale)))
        if set(self.collection.get(where={"doc_id": doc_id}, include=[])["ids"]) != wanted:
            raise RuntimeError("No coincide el conteo por documento")

    def delete_document(self, doc_id):
        with self.publish_phase():
            retry(lambda: self.collection.delete(where={"doc_id": doc_id}))
