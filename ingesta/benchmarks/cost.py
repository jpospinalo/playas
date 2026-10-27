"""Costo por mil documentos a partir de una tarifa explícita y trazable."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from .common import emit, finite_positive, output_dir


def cost_per_1000(docs_per_hour, price_per_hour):
    finite_positive(docs_per_hour)
    if not math.isfinite(price_per_hour) or price_per_hour < 0:
        raise ValueError("La tarifa debe ser finita y no negativa")
    return 1000 * price_per_hour / docs_per_hour


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--docs-per-hour", type=finite_positive, required=True)
    parser.add_argument("--price-per-hour", type=float, required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if not args.source.strip():
        parser.error("--source debe identificar la procedencia de la tarifa")
    result = {
        "benchmark": "cost",
        "docs_per_hour": args.docs_per_hour,
        "price_per_hour": args.price_per_hour,
        "price_source": args.source,
        "cost_per_1000_docs": cost_per_1000(args.docs_per_hour, args.price_per_hour),
        "currency": "misma unidad monetaria que --price-per-hour",
    }
    emit(result, output_dir(args.out) if args.out else None, "cost.json")


if __name__ == "__main__":
    main()
