"""Indexa ``data/documents/gold`` en un ChromaDB local para evaluar el corpus
versionado en Git, sin pasar por S3 ni tocar el índice desplegado.

Reutiliza ``load_gold_records`` de producción (mismos ids, texto aumentado de
embedding y metadata). La colección se crea con distancia coseno, igual que la
del export histórico que se usó para la línea base anterior.

Uso (apuntar CHROMA_PORT a un ChromaDB de evaluación, nunca al desplegado):
    CHROMA_PORT=8001 OLLAMA_BASE_URL=… uv run python -m evaluation.indexar_gold_local
"""

from __future__ import annotations

import argparse
import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

GOLD_DIR = Path("../data/documents/gold")
BATCH_SIZE = 32
COLLECTION_METADATA = {"hnsw:space": "cosine"}


def gold_files(gold_dir: Path) -> list[Path]:
    """Archivos Gold por tipo documental, en orden estable."""
    return sorted(gold_dir.glob("*/*.jsonl"))


def corpus_sha256(files: Iterable[Path]) -> str:
    """Huella del contenido del corpus, independiente de la ruta absoluta."""
    digest = hashlib.sha256()
    for path in files:
        digest.update(f"{path.parent.name}/{path.name}".encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_local_records(path: Path) -> tuple[list[str], list[str], list[str], list[Any]]:
    """Aplica el ``load_gold_records`` de producción a un archivo local."""
    from rag.core import vectorstore

    original = vectorstore.read_text
    vectorstore.read_text = lambda key: Path(key).read_text(encoding="utf-8")
    try:
        return vectorstore.load_gold_records(str(path))
    finally:
        vectorstore.read_text = original


def index_gold(gold_dir: Path = GOLD_DIR) -> int:
    """Agrega a la colección configurada los fragmentos que aún no tenga."""
    import chromadb

    from rag.config import CHROMA_COLLECTION, CHROMA_HOST, CHROMA_PORT
    from rag.core.vectorstore import EMBED_FN

    files = gold_files(gold_dir)
    if not files:
        raise RuntimeError(f"No hay archivos Gold en {gold_dir}")
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_or_create_collection(
        name=CHROMA_COLLECTION, metadata=COLLECTION_METADATA
    )
    print(f"corpus_sha256={corpus_sha256(files)} archivos={len(files)}", flush=True)
    for position, path in enumerate(files, start=1):
        ids, texts, embed_texts, metadatas = load_local_records(path)
        existing = set(collection.get(ids=ids, include=[])["ids"])
        pending = [i for i, chunk_id in enumerate(ids) if chunk_id not in existing]
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            collection.add(
                ids=[ids[i] for i in batch],
                documents=[texts[i] for i in batch],
                metadatas=cast(Any, [metadatas[i] for i in batch]),
                embeddings=EMBED_FN([embed_texts[i] for i in batch]),
            )
        print(f"[{position}/{len(files)}] {len(ids)} chunks, {len(pending)} nuevos", flush=True)
    total = collection.count()
    print(f"total={total}", flush=True)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold-dir", type=Path, default=GOLD_DIR)
    index_gold(parser.parse_args().gold_dir)


if __name__ == "__main__":
    main()
