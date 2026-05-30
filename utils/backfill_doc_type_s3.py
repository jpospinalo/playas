"""Backfill del metadato ``doc_type`` en los chunks ya almacenados en S3.

Los documentos ingeridos antes de la feature de normativa no llevan el
discriminador ``doc_type`` en su metadata. El backfill de ChromaDB
(``utils.backfill_doc_type``) ya los etiquetó en la colección, pero las capas
``silver`` y ``gold`` del bucket S3 siguen sin el campo. Sin él, regenerar gold
(re-corriendo el pipeline) reintroduciría el problema.

Este script recorre los ``.jsonl`` de cada capa para el ``doc_type`` indicado y,
para cada chunk que NO tenga ``doc_type`` (o lo tenga vacío), lo etiqueta
preservando el resto de su metadata. Reescribe el objeto S3 completo por archivo
(un ``.jsonl`` es un único objeto). Es idempotente.

Uso (desde la raíz del proyecto, para que cargue el .env):
    uv run python -m utils.backfill_doc_type_s3                       # dry-run
    uv run python -m utils.backfill_doc_type_s3 --apply               # aplica
    uv run python -m utils.backfill_doc_type_s3 --apply --doc-type jurisprudencia
    uv run python -m utils.backfill_doc_type_s3 --apply --layers gold # solo gold
"""

from __future__ import annotations

import argparse
import json

from ingest.config import DOC_TYPES, layer_prefix
from ingest.s3_client import list_keys, read_text, write_text

DEFAULT_LAYERS: tuple[str, ...] = ("silver", "gold")


def _backfill_key(key: str, doc_type: str) -> tuple[int, int, str]:
    """Procesa un único .jsonl. Devuelve (total_chunks, etiquetados, contenido_nuevo)."""
    total = 0
    tagged = 0
    out_lines: list[str] = []
    for line in read_text(key).splitlines():
        line = line.strip()
        if not line:
            continue
        total += 1
        row = json.loads(line)
        meta = row.get("metadata") or {}
        if not meta.get("doc_type"):
            meta["doc_type"] = doc_type
            row["metadata"] = meta
            tagged += 1
        out_lines.append(json.dumps(row, ensure_ascii=False))
    return total, tagged, "\n".join(out_lines) + "\n"


def backfill(doc_type: str, layers: tuple[str, ...], apply: bool) -> int:
    """Etiqueta con *doc_type* los chunks sin él en cada capa. Devuelve el nº afectado."""
    grand_tagged = 0
    for layer in layers:
        prefix = layer_prefix(layer, doc_type)
        keys = list_keys(prefix, suffix=".jsonl")
        print(f"\n[{layer}/{doc_type}] {len(keys)} archivos en s3://{prefix}")

        for key in keys:
            total, tagged, new_content = _backfill_key(key, doc_type)
            filename = key.split("/")[-1]
            if tagged == 0:
                print(f"  [ok] {filename}: {total} chunks, todos ya con doc_type")
                continue

            grand_tagged += tagged
            if apply:
                write_text(key, new_content)
                print(f"  [apply] {filename}: {tagged}/{total} chunks etiquetados")
            else:
                print(f"  [dry-run] {filename}: {tagged}/{total} chunks a etiquetar")

    if not apply:
        print(f"\n[DRY-RUN] No se escribió nada. {grand_tagged} chunks se etiquetarían.")
        print("  Ejecuta con --apply para aplicar.")
    else:
        print(f"\n[OK] Backfill S3 completado. {grand_tagged} chunks etiquetados como '{doc_type}'.")
    return grand_tagged


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill de doc_type en S3 (silver/gold).")
    parser.add_argument(
        "--apply", action="store_true", help="Aplica los cambios (por defecto: dry-run)."
    )
    parser.add_argument(
        "--doc-type",
        default="jurisprudencia",
        choices=DOC_TYPES,
        help="Valor a asignar a los chunks sin doc_type (default: jurisprudencia).",
    )
    parser.add_argument(
        "--layers",
        nargs="+",
        default=list(DEFAULT_LAYERS),
        choices=("silver", "gold"),
        help="Capas a procesar (default: silver gold).",
    )
    args = parser.parse_args()

    backfill(doc_type=args.doc_type, layers=tuple(args.layers), apply=args.apply)


if __name__ == "__main__":
    main()
