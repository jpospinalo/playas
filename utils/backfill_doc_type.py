"""Backfill del metadato ``doc_type`` en chunks ya indexados en ChromaDB.

Los documentos indexados antes de la feature de normativa no llevan el
discriminador ``doc_type``. Sin él, el filtrado explícito por tipo en el
retriever (``where={"doc_type": "jurisprudencia"}``) no los encuentra.

Este script recorre la colección, y para cada chunk que NO tenga ``doc_type``
(o lo tenga vacío) lo actualiza con el tipo indicado (por defecto
``jurisprudencia``) preservando el resto de su metadata. Solo actualiza
metadata: NO re-genera embeddings. Es idempotente.

Uso (desde la raíz del proyecto, para que cargue el .env):
    uv run python -m utils.backfill_doc_type             # dry-run (no escribe)
    uv run python -m utils.backfill_doc_type --apply     # aplica los cambios
    uv run python -m utils.backfill_doc_type --apply --doc-type jurisprudencia
"""

from __future__ import annotations

import argparse
import os
import sys

import chromadb
from dotenv import load_dotenv

load_dotenv()

CHROMA_HOST = os.getenv("CHROMA_HOST")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION_NAME = os.getenv("CHROMA_COLLECTION_NAME")

UPDATE_BATCH = 200


def backfill(doc_type: str, collection_name: str, apply: bool) -> int:
    """Etiqueta con *doc_type* los chunks que no lo tengan. Devuelve el nº afectado."""
    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    collection = client.get_collection(name=collection_name)

    total = collection.count()
    raw = collection.get(include=["metadatas"])
    ids = raw.get("ids", [])
    metas = raw.get("metadatas", [])

    pending_ids: list[str] = []
    pending_metas: list[dict] = []
    for _id, meta in zip(ids, metas, strict=False):
        meta = meta or {}
        if not meta.get("doc_type"):
            # Reenviar la metadata completa + doc_type (merge seguro,
            # independiente de la semántica replace/merge de Chroma).
            pending_ids.append(_id)
            pending_metas.append({**meta, "doc_type": doc_type})

    already = total - len(pending_ids)
    print(f"[backfill] Colección '{collection_name}': {total} chunks")
    print(f"  ya con doc_type: {already}")
    print(f"  a etiquetar como '{doc_type}': {len(pending_ids)}")

    if not pending_ids:
        print("  Nada que hacer.")
        return 0

    if not apply:
        print("\n[DRY-RUN] No se escribió nada. Ejecuta con --apply para aplicar.")
        print("  Ejemplos de ids a actualizar:")
        for _id in pending_ids[:5]:
            print(f"    - {_id}")
        return len(pending_ids)

    for start in range(0, len(pending_ids), UPDATE_BATCH):
        batch_ids = pending_ids[start : start + UPDATE_BATCH]
        batch_metas = pending_metas[start : start + UPDATE_BATCH]
        collection.update(ids=batch_ids, metadatas=batch_metas)
        print(f"  actualizado batch {start // UPDATE_BATCH + 1}: {len(batch_ids)} chunks")

    # Verificación
    tagged = len(collection.get(where={"doc_type": doc_type}, include=[])["ids"])
    print(f"\n[OK] Backfill completado. doc_type='{doc_type}' ahora en {tagged} chunks.")
    return len(pending_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill de doc_type en ChromaDB.")
    parser.add_argument(
        "--apply", action="store_true", help="Aplica los cambios (por defecto: dry-run)."
    )
    parser.add_argument(
        "--doc-type",
        default="jurisprudencia",
        help="Valor a asignar a los chunks sin doc_type (default: jurisprudencia).",
    )
    parser.add_argument(
        "--collection",
        default=CHROMA_COLLECTION_NAME,
        help="Nombre de la colección Chroma (default: CHROMA_COLLECTION_NAME del .env).",
    )
    args = parser.parse_args()

    if not args.collection:
        print("Error: no hay colección definida (CHROMA_COLLECTION_NAME).", file=sys.stderr)
        sys.exit(1)

    backfill(doc_type=args.doc_type, collection_name=args.collection, apply=args.apply)


if __name__ == "__main__":
    main()
