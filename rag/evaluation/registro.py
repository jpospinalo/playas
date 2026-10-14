"""Registro versionado de evaluaciones de ATLAS.

Cada corrida (modelo generador + juez + versión del sistema) agrega una fila a
``evaluation/registro/evaluaciones.csv``, que sí se versiona, y regenera la
tabla de ``docs/REGISTRO_EVALUACIONES.md``. Así queda trazable cómo cambia la
calidad del sistema entre versiones y modelos.

Uso:
    uv run python -m evaluation.registro --modelo "gpt-5-nano (OpenAI)" --fecha 2026-10-08  # línea base
    uv run python -m evaluation.registro --tag gemma4-e2b --modelo "gemma4:e2b (local)"
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

from evaluation.generation_cache import CACHE_PATH, load_cache
from evaluation.ragas_v02 import JUDGE_MODEL, RESULTS_PATH, aggregate_scores
from evaluation.retrieval_baseline import first_relevant_rank
from evaluation.run_paths import tagged

CSV_PATH = Path("evaluation/registro/evaluaciones.csv")
MD_PATH = Path("docs/REGISTRO_EVALUACIONES.md")

FIELDS = [
    "fecha",
    "version_sistema",
    "etiqueta",
    "modelo_generador",
    "juez",
    "casos",
    "respondidas",
    "correctas",
    "respaldo_enricher",
    "hit_at_4",
    "context_recall",
    "faithfulness",
    "factual_f1",
    "answer_accuracy",
    "latencia_media_s",
    "costo_generacion_usd",
]
_METRICS = ["context_recall", "faithfulness", "factual_f1", "answer_accuracy"]


def system_version() -> str:
    """Último commit que tocó ``backend/``: la versión del sistema evaluado.
    No es el HEAD de la rama, que cambia con el código de evaluación."""
    backend = Path(__file__).resolve().parents[1] / "backend"
    return subprocess.run(  # noqa: S603, S607
        ["git", "log", "-1", "--format=%h", "--abbrev=7", "--", str(backend)],
        cwd=backend,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _fmt(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else ""


def summarize_run(
    generation_rows: list[dict[str, Any]],
    ragas_rows: list[dict[str, Any]],
    meta: dict[str, str],
) -> dict[str, str]:
    """Una fila del registro: conteos, hit@4 sobre los fragmentos que de verdad
    recibió el modelo, promedios RAGAS, latencia y costo de generación."""
    with_doc = [r for r in generation_rows if r["documentos_esperados"]]
    hits = [
        first_relevant_rank(r["context_titles"], r["documentos_esperados"]) is not None
        for r in with_doc
    ]
    rows_all = [{**r, "todos": "todos"} for r in ragas_rows]
    means = aggregate_scores(rows_all, "todos", _METRICS).get("todos", {})
    n = len(generation_rows)
    return {
        **{
            k: meta[k] for k in ("fecha", "version_sistema", "etiqueta", "modelo_generador", "juez")
        },
        "casos": str(n),
        "respondidas": str(sum(1 for r in generation_rows if r["outcome"] == "respondida")),
        "correctas": str(sum(1 for r in ragas_rows if r["diagnostico"] == "correcta")),
        "respaldo_enricher": str(sum(1 for r in generation_rows if r.get("enrichment_fallback"))),
        "hit_at_4": _fmt(sum(hits) / len(hits) if hits else None),
        **{m: _fmt(means.get(m)) for m in _METRICS},
        "latencia_media_s": f"{sum(r['duration_seconds'] for r in generation_rows) / n:.1f}",
        "costo_generacion_usd": f"{sum(r['cost_usd_est'] for r in generation_rows):.4f}",
    }


def append_run(row: dict[str, str], path: Path = CSV_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(row)


def render_markdown(rows: list[dict[str, str]]) -> str:
    header = "| " + " | ".join(FIELDS) + " |"
    sep = "|" + "---|" * len(FIELDS)
    body = ["| " + " | ".join(r[k] for k in FIELDS) + " |" for r in rows]
    return "\n".join(
        [
            "# Registro de evaluaciones de ATLAS",
            "",
            "Generado por `evaluation/registro.py` desde `evaluation/registro/evaluaciones.csv`.",
            "",
            header,
            sep,
            *body,
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="etiqueta de la corrida")
    parser.add_argument("--modelo", required=True, help="nombre legible del modelo generador")
    parser.add_argument(
        "--fecha", default=None, help="fecha de la corrida (AAAA-MM-DD); hoy si se omite"
    )
    args = parser.parse_args()
    with tagged(RESULTS_PATH, args.tag).open(encoding="utf-8") as f:
        ragas_rows = [json.loads(line) for line in f if line.strip()]
    meta = {
        "fecha": date.fromisoformat(args.fecha).isoformat()
        if args.fecha
        else date.today().isoformat(),
        "version_sistema": system_version(),
        "etiqueta": args.tag or "linea-base",
        "modelo_generador": args.modelo,
        "juez": JUDGE_MODEL,
    }
    append_run(summarize_run(load_cache(tagged(CACHE_PATH, args.tag)), ragas_rows, meta))
    with CSV_PATH.open(encoding="utf-8") as f:
        MD_PATH.write_text(render_markdown(list(csv.DictReader(f))), encoding="utf-8")
    print(f"Registro: {CSV_PATH} · {MD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
