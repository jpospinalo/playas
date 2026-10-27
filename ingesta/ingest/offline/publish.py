"""Publicación local por documento; nunca permite escribir la línea base."""

from __future__ import annotations

import time


def retry(operation):
    for attempt in range(2):
        try:
            return operation()
        except Exception:
            if attempt == 1:
                raise
            time.sleep(0.5)


class ChromaPublisher:
    def __init__(self, collection, config_hash, port=8000):
        if collection in {"v1", "atlas_v1", "rag_playas", "rag_playas_magdalena"}:
            raise ValueError("Colección base protegida; usa otro nombre")
        import chromadb

        client = chromadb.HttpClient(host="127.0.0.1", port=port)
        try:
            self.collection = client.get_collection(collection)
        except chromadb.errors.NotFoundError:
            self.collection = client.create_collection(
                collection, metadata={"hnsw:space": "cosine", "atlas_offline_config": config_hash}
            )
        if self.collection.metadata.get("atlas_offline_config") != config_hash:
            raise ValueError("Colección de otra versión/modelo; crea una colección nueva")

    def upsert_document(self, doc_id, records, vectors):
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
        retry(lambda: self.collection.delete(where={"doc_id": doc_id}))
