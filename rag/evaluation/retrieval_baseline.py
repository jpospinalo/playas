"""Fase 1 de la línea base: recuperación determinista por documento esperado,
sin LLM, sobre ``legal-ground-truth-v0.2``.

Para cada caso con ``documentos_esperados`` ejecuta el retriever híbrido de
producción (``rag.core.retriever.get_ensemble_retriever``: BM25 + vectores,
fusión RRF) con la **pregunta original**, sin la reescritura del LLM ni el
filtro por ``doc_type`` que aplica el grafo. Es una aproximación gratuita de
la recuperación real; la recuperación exacta de producción (con la pregunta
reescrita) se mide con ``generation_cache.py``.

Dos pasadas por caso:
- **producción** (``k=4``, ``k_candidates=8``, los valores por defecto del
  grafo): qué documentos llegan efectivamente al modelo → ``hit@4`` y
  ``doc_recall@4``;
- **profunda** (``k=20``): en qué posición aparece el documento esperado
  aunque no alcance el top-4 → ``hit@20`` y MRR.

El cruce chunk → documento se hace por el metadato ``title`` y en NFC (ver
``ground_truth_v02.same_title``).

Uso (requiere ChromaDB y Ollama accesibles; ver ``docs/SCRIPTS.md``):
    CHROMA_HOST=… OLLAMA_BASE_URL=… uv run python -m evaluation.retrieval_baseline
"""

from __future__ import annotations

import argparse
import json
import time
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROD_K = 4
PROD_K_CANDIDATES = 8
DEEP_K = 20
REPORT_PATH = Path("evaluation/results/retrieval-baseline-v0.2.json")


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def first_relevant_rank(retrieved_titles: list[str], expected_titles: Iterable[str]) -> int | None:
    """Posición (base 1) del primer chunk que pertenece a un documento
    esperado, o ``None`` si ninguno aparece."""
    expected = {_nfc(t) for t in expected_titles}
    for position, title in enumerate(retrieved_titles, start=1):
        if _nfc(title) in expected:
            return position
    return None


def doc_recall_at_k(retrieved_titles: list[str], expected_titles: list[str], k: int) -> float:
    """Fracción de documentos esperados (distintos) presentes en el top-k."""
    expected = {_nfc(t) for t in expected_titles}
    if not expected:
        return 0.0
    found = {_nfc(t) for t in retrieved_titles[:k]} & expected
    return len(found) / len(expected)


def summarize_retrieval(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    """Agrega por ``key``: n, hit@4, hit@20, MRR (sobre el rango profundo) y
    doc_recall@4 promedio."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    summary: dict[str, dict[str, Any]] = {}
    for group, items in sorted(groups.items()):
        n = len(items)
        ranks = [row["rank"] for row in items]
        summary[group] = {
            "n": n,
            "hit_at_4": sum(1 for r in ranks if r is not None and r <= PROD_K) / n,
            "hit_at_20": sum(1 for r in ranks if r is not None and r <= DEEP_K) / n,
            "mrr": sum(1 / r for r in ranks if r is not None) / n,
            "doc_recall_at_4": sum(row["doc_recall_at_4"] for row in items) / n,
        }
    return summary


def _titles(docs: list[Any]) -> list[str]:
    return [str((d.metadata or {}).get("title", "")) for d in docs]


def run(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from rag.core.retriever import get_ensemble_retriever, init_retrievers

    init_retrievers()
    prod = get_ensemble_retriever(k=PROD_K, k_candidates=PROD_K_CANDIDATES)
    deep = get_ensemble_retriever(k=DEEP_K, k_candidates=DEEP_K)
    rows = []
    for case in cases:
        if not case["documentos_esperados"]:
            continue
        start = time.monotonic()
        top_prod = _titles(prod.invoke(case["pregunta"]))
        top_deep = _titles(deep.invoke(case["pregunta"]))
        rows.append(
            {
                "case_id": case["id"],
                "tipo": case["tipo"],
                "revisado": case["revisado"],
                "documentos_esperados": case["documentos_esperados"],
                "top_prod": top_prod,
                "rank": first_relevant_rank(top_deep, case["documentos_esperados"]),
                "doc_recall_at_4": doc_recall_at_k(top_prod, case["documentos_esperados"], PROD_K),
                "duration_seconds": round(time.monotonic() - start, 2),
            }
        )
        print(f"{case['id']}: rank={rows[-1]['rank']}")
    return rows


def main() -> int:
    from evaluation.ground_truth_v02 import load_ground_truth_v02
    from evaluation.ragas_common import git_state
    from evaluation.run_paths import tagged

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="etiqueta de la corrida (p. ej. local-infra)")
    args = parser.parse_args()
    report_path = tagged(REPORT_PATH, args.tag)

    rows = run(load_ground_truth_v02())
    report = {
        "dataset": "legal-ground-truth-v0.2",
        "fecha": datetime.now(UTC).isoformat(),
        "git": git_state(),
        "tag": args.tag,
        "config": {
            "consulta": "pregunta original (sin reescritura ni filtro doc_type)",
            "prod_k": PROD_K,
            "prod_k_candidates": PROD_K_CANDIDATES,
            "deep_k": DEEP_K,
        },
        "global": summarize_retrieval([{**r, "todos": "todos"} for r in rows], "todos"),
        "por_tipo": summarize_retrieval(rows, "tipo"),
        "por_revision": summarize_retrieval(rows, "revisado"),
        "cases": rows,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Reporte: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
