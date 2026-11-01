"""Fase 5 de la línea base: consolida en tablas Markdown los resultados de
las fases 1 (``retrieval_baseline``), 2 (``generation_cache``) y 4
(``ragas_v02``) sobre ``legal-ground-truth-v0.2``.

Escribe ``evaluation/results/linea-base-v0.2.md`` (no versionado, como el
resto de ``results/``). El análisis versionado para los revisores está en
``docs/EVALUACION_LINEA_BASE.md``.

Uso:
    uv run python -m evaluation.baseline_report [--tag <etiqueta>]
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.generation_cache import CACHE_PATH, load_cache
from evaluation.ragas_v02 import METRIC_NAMES, RESULTS_PATH, aggregate_scores
from evaluation.retrieval_baseline import REPORT_PATH as RETRIEVAL_PATH
from evaluation.run_paths import tagged

OUTPUT_PATH = Path("evaluation/results/linea-base-v0.2.md")


def markdown_table(summary: dict[str, dict[str, Any]], label: str, columns: list[str]) -> str:
    """Tabla con una fila por grupo: n y cada columna con dos decimales
    (``—`` si no hay valor)."""
    lines = [
        f"| {label} | n | " + " | ".join(columns) + " |",
        "|---|---:|" + "---:|" * len(columns),
    ]
    for group, values in summary.items():
        cells = [f"{values[c]:.2f}" if values.get(c) is not None else "—" for c in columns]
        lines.append(f"| {group} | {values['n']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def comparison_table(runs: dict[str, list[dict[str, Any]]], metric: str) -> str:
    """Promedio de ``metric`` por tipo de pregunta, una columna por corrida."""
    names = list(runs)
    by_run = {name: aggregate_scores(rows, "tipo", [metric]) for name, rows in runs.items()}
    tipos = sorted({tipo for summary in by_run.values() for tipo in summary})
    lines = ["| Tipo | " + " | ".join(names) + " |", "|---|" + "---:|" * len(names)]
    for tipo in tipos:
        cells = []
        for name in names:
            value = by_run[name].get(tipo, {}).get(metric)
            cells.append(f"{value:.2f}" if value is not None else "—")
        lines.append(f"| {tipo} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def count_by(rows: list[dict[str, Any]], key: str) -> list[tuple[str, int]]:
    return Counter(str(row[key]) for row in rows).most_common()


def judge_cost_line(rows: list[dict[str, Any]]) -> str:
    """Costo del juez sumando solo los costos medidos por caso. Las filas sin
    ``cost_usd_est`` (corridas anteriores a la medición por caso) se cuentan
    aparte, nunca se estiman."""
    measured = [row["cost_usd_est"] for row in rows if "cost_usd_est" in row]
    line = f"- costo estimado del juez: ${sum(measured):.4f} en {len(measured)} casos medidos"
    missing = len(rows) - len(measured)
    if missing:
        line += f"; {missing} caso(s) sin costo por caso (corrida anterior a la medición por caso)"
    return line


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def build_report(tag: str | None = None) -> str:
    retrieval = json.loads(tagged(RETRIEVAL_PATH, tag).read_text(encoding="utf-8"))
    generation = load_cache(tagged(CACHE_PATH, tag))
    ragas_rows = _load_jsonl(tagged(RESULTS_PATH, tag))
    retrieval_cols = ["hit_at_4", "hit_at_20", "mrr", "doc_recall_at_4"]

    sections = [
        "# Línea base ATLAS — legal-ground-truth-v0.2 (tablas generadas)",
        "## Fase 1 · Recuperación por documento esperado (pregunta original)",
        markdown_table(retrieval["global"], "Alcance", retrieval_cols),
        markdown_table(retrieval["por_tipo"], "Tipo", retrieval_cols),
        markdown_table(retrieval["por_revision"], "Revisado", retrieval_cols),
        "## Fase 2 · Resultado del grafo",
        "\n".join(f"- {name}: {n}" for name, n in count_by(generation, "outcome")),
        "\n".join(f"- ruta {name}: {n}" for name, n in count_by(generation, "route")),
        "- costo estimado de generación: "
        f"${sum(r['cost_usd_est'] for r in generation):.4f} · latencia media "
        f"{sum(r['duration_seconds'] for r in generation) / max(len(generation), 1):.1f}s",
        "## Fase 4 · RAGAS (solo casos respondidos)",
        markdown_table(
            aggregate_scores([{**r, "todos": "todos"} for r in ragas_rows], "todos", METRIC_NAMES),
            "Alcance",
            METRIC_NAMES,
        ),
        markdown_table(aggregate_scores(ragas_rows, "tipo", METRIC_NAMES), "Tipo", METRIC_NAMES),
        markdown_table(
            aggregate_scores(ragas_rows, "revisado", METRIC_NAMES), "Revisado", METRIC_NAMES
        ),
        "### Diagnóstico por caso",
        "\n".join(f"- {name}: {n}" for name, n in count_by(ragas_rows, "diagnostico")),
        judge_cost_line(ragas_rows),
    ]
    return "\n\n".join(sections) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="etiqueta de la corrida")
    tag = parser.parse_args().tag
    output_path = tagged(OUTPUT_PATH, tag)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_report(tag), encoding="utf-8")
    print(f"Reporte: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
