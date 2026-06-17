"""Backup y restauración remota de una colección de Chroma hacia/desde S3.

A diferencia de un backup a nivel de volumen Docker, este script funciona
**de forma remota**: se conecta a la API de Chroma (igual que ``chroma_count``),
exporta la colección completa (ids, documentos, metadatos y embeddings) a un
archivo ``.jsonl.gz`` y lo sube a S3. También permite listar, descargar y
restaurar esos backups.

Como exporta los embeddings, la restauración no necesita Ollama ni re-embeber.

Uso (desde la raíz del repo, igual que los demás scripts de tools):

    # Crear backup y subirlo a S3 (deja también una copia local opcional)
    PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_backup backup
    PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_backup backup --keep-local ./backups

    # Listar backups disponibles en S3
    PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_backup list

    # Descargar un backup de S3 a local
    PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_backup download <s3-key> -o ./backups

    # Restaurar un backup (desde S3 o desde un archivo local) a una colección
    PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_backup restore --s3-key <s3-key>
    PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_backup restore --file ./backups/chroma-XXXX.jsonl.gz
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import chromadb

from rag import config
from rag.s3_client import get_bucket, get_client

# ── Configuración ────────────────────────────────────────────────────────────
CHROMA_HOST = config.CHROMA_HOST
CHROMA_PORT = config.CHROMA_PORT
CHROMA_COLLECTION = config.CHROMA_COLLECTION
S3_BACKUP_PREFIX = os.getenv("CHROMA_BACKUP_PREFIX", "backups/chroma/")

FORMAT_VERSION = 1
PAGE_SIZE = 500  # registros por página al leer/escribir en Chroma


# ── Utilidades ───────────────────────────────────────────────────────────────
def _require_bucket() -> str:
    try:
        return get_bucket()
    except RuntimeError as exc:
        sys.exit(f"ERROR: {exc}")


def _s3():
    return get_client()


def _chroma() -> chromadb.api.ClientAPI:
    return chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def _to_list(value: Any) -> Any:
    """Convierte arrays de numpy (embeddings) a listas serializables a JSON."""
    if value is None:
        return None
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024 or unit == "GB":
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} GB"


# ── backup ───────────────────────────────────────────────────────────────────
def _iter_records(collection: Any, total: int) -> Iterator[dict[str, Any]]:
    """Lee la colección por páginas y emite un registro por documento."""
    fetched = 0
    offset = 0
    while offset < total:
        batch = collection.get(
            limit=PAGE_SIZE,
            offset=offset,
            include=["documents", "metadatas", "embeddings"],
        )
        ids = batch.get("ids") or []
        if not ids:
            break
        documents = batch.get("documents") or [None] * len(ids)
        metadatas = batch.get("metadatas") or [None] * len(ids)
        embeddings = batch.get("embeddings")
        embeddings = embeddings if embeddings is not None else [None] * len(ids)
        for i, doc_id in enumerate(ids):
            yield {
                "id": doc_id,
                "document": documents[i],
                "metadata": metadatas[i],
                "embedding": _to_list(embeddings[i]),
            }
        fetched += len(ids)
        offset += len(ids)
        print(f"  · exportados {fetched}/{total} registros", end="\r", flush=True)
    print()


def cmd_backup(args: argparse.Namespace) -> None:
    bucket = _require_bucket()
    collection_name = args.collection or CHROMA_COLLECTION
    collection = _chroma().get_collection(name=collection_name)
    total = collection.count()
    print(f"Colección '{collection_name}' en {CHROMA_HOST}:{CHROMA_PORT} → {total} documentos")
    if total == 0:
        print("La colección está vacía; no se genera backup.")
        return

    timestamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    filename = f"chroma-{collection_name}-{timestamp}.jsonl.gz"
    tmp_path = Path(args.keep_local or ".") / filename
    tmp_path.parent.mkdir(parents=True, exist_ok=True)

    embedding_dim: int | None = None
    written = 0
    with gzip.open(tmp_path, "wt", encoding="utf-8") as fh:
        manifest = {
            "__manifest__": {
                "format_version": FORMAT_VERSION,
                "collection": collection_name,
                "count": total,
                "created_at": dt.datetime.now(dt.UTC).isoformat(),
                "chroma_host": CHROMA_HOST,
                "chroma_port": CHROMA_PORT,
            }
        }
        # La primera línea es el manifest; las siguientes, un registro cada una.
        fh.write(json.dumps(manifest, ensure_ascii=False) + "\n")
        for record in _iter_records(collection, total):
            if embedding_dim is None and record["embedding"]:
                embedding_dim = len(record["embedding"])
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1

    local_size = tmp_path.stat().st_size
    print(f"Archivo local: {tmp_path} ({_human_size(local_size)}, {written} registros)")

    key = S3_BACKUP_PREFIX + filename
    print(f"Subiendo a s3://{bucket}/{key} …")
    _s3().upload_file(
        Filename=str(tmp_path),
        Bucket=bucket,
        Key=key,
        ExtraArgs={
            "Metadata": {
                "collection": collection_name,
                "count": str(total),
                "embedding_dim": str(embedding_dim or ""),
                "format_version": str(FORMAT_VERSION),
            }
        },
    )
    print(f"✓ Backup subido: s3://{bucket}/{key}")

    if not args.keep_local:
        tmp_path.unlink(missing_ok=True)
    else:
        print(f"✓ Copia local conservada en {tmp_path}")


# ── list ─────────────────────────────────────────────────────────────────────
def cmd_list(args: argparse.Namespace) -> None:
    bucket = _require_bucket()
    paginator = _s3().get_paginator("list_objects_v2")
    rows: list[tuple[str, int, dt.datetime]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=S3_BACKUP_PREFIX):
        for obj in page.get("Contents", []):
            rows.append((obj["Key"], obj["Size"], obj["LastModified"]))
    if not rows:
        print(f"No hay backups bajo s3://{bucket}/{S3_BACKUP_PREFIX}")
        return
    rows.sort(key=lambda r: r[2], reverse=True)
    print(f"Backups en s3://{bucket}/{S3_BACKUP_PREFIX} (más recientes primero):\n")
    for key, size, modified in rows:
        print(f"  {modified:%Y-%m-%d %H:%M}  {_human_size(size):>10}  {key}")


# ── download ─────────────────────────────────────────────────────────────────
def cmd_download(args: argparse.Namespace) -> None:
    bucket = _require_bucket()
    key = args.key if args.key.startswith(S3_BACKUP_PREFIX) else S3_BACKUP_PREFIX + args.key
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / Path(key).name
    print(f"Descargando s3://{bucket}/{key} → {dest} …")
    _s3().download_file(Bucket=bucket, Key=key, Filename=str(dest))
    print(f"✓ Descargado: {dest} ({_human_size(dest.stat().st_size)})")


# ── restore ──────────────────────────────────────────────────────────────────
def _open_backup(args: argparse.Namespace, bucket: str) -> Path:
    if args.file:
        path = Path(args.file)
        if not path.exists():
            sys.exit(f"ERROR: no existe el archivo local {path}")
        return path
    # Descargar desde S3 a un temporal junto al cwd.
    key = args.s3_key if args.s3_key.startswith(S3_BACKUP_PREFIX) else S3_BACKUP_PREFIX + args.s3_key
    dest = Path(Path(key).name)
    print(f"Descargando s3://{bucket}/{key} → {dest} …")
    _s3().download_file(Bucket=bucket, Key=key, Filename=str(dest))
    return dest


def cmd_restore(args: argparse.Namespace) -> None:
    bucket = _require_bucket() if args.s3_key else ""
    path = _open_backup(args, bucket)

    with gzip.open(path, "rt", encoding="utf-8") as fh:
        first = fh.readline()
        manifest = json.loads(first).get("__manifest__")
        if not manifest:
            sys.exit("ERROR: el archivo no tiene manifest válido en la primera línea.")
        target = args.collection or manifest["collection"]
        print(f"Manifest: colección '{manifest['collection']}', {manifest['count']} registros")
        print(f"Restaurando hacia '{target}' en {CHROMA_HOST}:{CHROMA_PORT}")

        client = _chroma()
        collection = client.get_or_create_collection(name=target)
        existing = collection.count()
        if existing > 0 and not args.force:
            sys.exit(
                f"ERROR: la colección '{target}' ya tiene {existing} documentos. "
                "Usa --force para hacer upsert sobre ella."
            )

        ids: list[str] = []
        docs: list[Any] = []
        metas: list[Any] = []
        embs: list[Any] = []
        restored = 0

        def flush() -> None:
            nonlocal restored
            if not ids:
                return
            collection.upsert(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
            restored += len(ids)
            print(f"  · restaurados {restored}/{manifest['count']} registros", end="\r", flush=True)
            ids.clear()
            docs.clear()
            metas.clear()
            embs.clear()

        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            ids.append(rec["id"])
            docs.append(rec.get("document"))
            metas.append(rec.get("metadata"))
            embs.append(rec.get("embedding"))
            if len(ids) >= PAGE_SIZE:
                flush()
        flush()
        print()
        print(f"✓ Restauración completa: {restored} registros en '{target}' (total: {collection.count()})")


# ── CLI ──────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backup/restauración remota de una colección de Chroma hacia/desde S3."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_backup = sub.add_parser("backup", help="Exporta la colección y la sube a S3.")
    p_backup.add_argument("--collection", help=f"Colección a respaldar (default: {CHROMA_COLLECTION}).")
    p_backup.add_argument(
        "--keep-local",
        metavar="DIR",
        help="Conserva una copia local del backup en DIR (por defecto se elimina tras subir).",
    )
    p_backup.set_defaults(func=cmd_backup)

    p_list = sub.add_parser("list", help="Lista los backups disponibles en S3.")
    p_list.set_defaults(func=cmd_list)

    p_dl = sub.add_parser("download", help="Descarga un backup de S3 a local.")
    p_dl.add_argument("key", help="Key del backup en S3 (con o sin el prefijo de backups).")
    p_dl.add_argument("-o", "--output", default=".", help="Directorio de destino (default: cwd).")
    p_dl.set_defaults(func=cmd_download)

    p_rs = sub.add_parser("restore", help="Restaura un backup a una colección de Chroma.")
    src = p_rs.add_mutually_exclusive_group(required=True)
    src.add_argument("--s3-key", help="Key del backup en S3 a restaurar.")
    src.add_argument("--file", help="Ruta a un backup local .jsonl.gz a restaurar.")
    p_rs.add_argument("--collection", help="Colección destino (default: la del manifest).")
    p_rs.add_argument(
        "--force",
        action="store_true",
        help="Permite upsert aunque la colección destino ya tenga documentos.",
    )
    p_rs.set_defaults(func=cmd_restore)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
