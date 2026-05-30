"""Migra los objetos S3 existentes de la raíz de cada capa hacia el subnivel
``<capa>/jurisprudencia/``.

Hoy todos los objetos del bucket están directamente bajo ``data/<capa>/``
(raw, bronze, silver, gold) y todos son jurisprudencia. Este script los reubica
en ``data/<capa>/jurisprudencia/`` para dejar libre ``data/<capa>/normativa/``
para futuros documentos normativos.

Es idempotente: nunca vuelve a mover algo que ya esté bajo ``jurisprudencia/``
o ``normativa/`` justo después de la capa.

Uso:
    uv run python -m utils.migrate_doc_type            # dry-run (por defecto)
    uv run python -m utils.migrate_doc_type --apply    # ejecuta de verdad
"""

from __future__ import annotations

import argparse

from ingest import s3_client
from ingest.config import DOC_TYPES, LAYERS

DEFAULT_DOC_TYPE = "jurisprudencia"


def _remap_key(key: str, layer: str) -> str | None:
    """Calcula el destino de *key* dentro de *layer*, o None si no debe moverse.

    Devuelve None cuando la key ya está bajo alguno de los subniveles de tipo
    de documento (``jurisprudencia/`` o ``normativa/``) justo después de la capa.
    """
    layer_root = f"data/{layer}/"
    if not key.startswith(layer_root):
        return None
    remainder = key[len(layer_root) :]
    if not remainder:
        return None
    for doc_type in DOC_TYPES:
        if remainder.startswith(f"{doc_type}/"):
            return None
    return f"{layer_root}{DEFAULT_DOC_TYPE}/{remainder}"


def plan_moves() -> list[tuple[str, str]]:
    """Calcula (sin mover nada) la lista de pares (src, dst) a migrar.

    Función pura respecto a S3: solo lee (list_keys) y calcula destinos.
    """
    moves: list[tuple[str, str]] = []
    for layer in LAYERS:
        for key in s3_client.list_keys(f"data/{layer}/"):
            dst = _remap_key(key, layer)
            if dst is not None:
                moves.append((key, dst))
    return moves


def apply_moves(moves: list[tuple[str, str]]) -> None:
    """Ejecuta los movimientos en S3 (copy + delete por cada par)."""
    for src, dst in moves:
        s3_client.move_key(src, dst)


def _summarize(moves: list[tuple[str, str]]) -> dict[str, int]:
    """Cuenta los movimientos planeados por capa."""
    counts: dict[str, int] = {layer: 0 for layer in LAYERS}
    for src, _dst in moves:
        for layer in LAYERS:
            if src.startswith(f"data/{layer}/"):
                counts[layer] += 1
                break
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migra objetos S3 de data/<capa>/ a data/<capa>/jurisprudencia/.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Ejecuta los movimientos de verdad. Sin esta bandera, solo dry-run.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Solo imprime los movimientos planeados (comportamiento por defecto).",
    )
    args = parser.parse_args()

    apply = args.apply
    moves = plan_moves()
    counts = _summarize(moves)

    mode = "APLICAR" if apply else "DRY-RUN"
    print(f"[{mode}] {len(moves)} objeto(s) a migrar a '<capa>/{DEFAULT_DOC_TYPE}/'.")
    for layer in LAYERS:
        print(f"  - {layer:7s}: {counts[layer]} objeto(s)")

    for src, dst in moves:
        print(f"    {src}  ->  {dst}")

    if not moves:
        print("Nada que migrar: todo ya está bajo un subnivel de tipo de documento.")
        return

    if not apply:
        print("\nDry-run: no se modificó S3. Usa --apply para ejecutar.")
        return

    apply_moves(moves)
    print(f"\n✓ {len(moves)} objeto(s) migrado(s).")


if __name__ == "__main__":
    main()
