"""Comparaciones pareadas con bootstrap; no usa LLM ni interpreta corrección legal."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
from pathlib import Path


def bootstrap(deltas, repetitions=5000):
    rng = random.Random(20261021)
    estimates = sorted(
        statistics.mean(rng.choices(deltas, k=len(deltas))) for _ in range(repetitions)
    )
    return [
        estimates[int(0.025 * repetitions)],
        estimates[min(repetitions - 1, int(0.975 * repetitions))],
    ]


def compare(directory):
    versions = {}
    for version in ["v1", "v2a", "v2b", "v1x"]:
        path = directory / (version + ".jsonl")
        if path.exists():
            versions[version] = {
                r["id"]: r
                for line in path.read_text(encoding="utf-8").splitlines()
                if (r := json.loads(line))
            }
    if not all(v in versions and len(versions[v]) == 40 for v in ["v1", "v2a", "v2b"]):
        raise ValueError("Se requieren40casos en cada variante principal")
    configs = {row["config_hash"] for data in versions.values() for row in data.values()}
    datasets = {row["dataset_sha256"] for data in versions.values() for row in data.values()}
    if len(configs) != 1 or len(datasets) != 1:
        raise ValueError("Configuración/dataset distintos: comparación inválida")
    # Decisión preespecificada: MRR documental; empate favorece legacy por
    # menor complejidad. Se guarda ANTES de cualquier nivel1 (que no se ejecuta).
    candidates = {
        v: statistics.mean(r["scores"]["document_mrr_at_k"] for r in versions[v].values())
        for v in ["v2a", "v2b"]
    }
    selected = "v2a" if candidates["v2a"] >= candidates["v2b"] else "v2b"
    selection = {
        "utc": dt.datetime.now(dt.UTC).isoformat(),
        "criterion": "mean document_mrr_at_k; tie favors legacy v2a",
        "mrr": candidates,
        "selected": selected,
        "before_level1": True,
        "level1_executed": False,
    }
    (directory / "selection.json").write_text(json.dumps(selection, indent=2), encoding="utf-8")
    result = {
        "validado_por_abogado": False,
        "estado_validacion": "no validado por abogados",
        "config_hash": next(iter(configs)),
        "dataset_sha256": next(iter(datasets)),
        "bootstrap": {"iterations": 5000, "seed": 20261021, "confidence": 0.95, "paired": True},
        "selection": selection,
        "versions": {},
        "comparisons": {},
        "level1": "omitido para minimizar coste/cuota; no se evaluaron respuestas generadas",
    }
    for version, rows in versions.items():
        summary = {}
        for category in ["all", "contenido", "identidad", "multi_documento"]:
            group = [r for r in rows.values() if category == "all" or r["categoria"] == category]
            summary[category] = {
                "n": len(group),
                "metrics": {
                    name: {
                        "mean": statistics.mean(r["scores"][name] for r in group),
                        "median": statistics.median(r["scores"][name] for r in group),
                    }
                    for name in next(iter(rows.values()))["scores"]
                },
            }
        worst = sorted(
            rows.values(),
            key=lambda r: (
                r["scores"]["document_mrr_at_k"],
                r["scores"]["passage_mrr_at_k"],
                r["id"],
            ),
        )[:10]
        result["versions"][version] = {
            "summary": summary,
            "worst_10": [
                {"id": r["id"], "categoria": r["categoria"], "scores": r["scores"]} for r in worst
            ],
        }
    for version in versions:
        if version == "v1":
            continue
        paired = []
        for identity, current in versions[version].items():
            base = versions["v1"][identity]
            paired.append(
                {
                    "id": identity,
                    "categoria": current["categoria"],
                    "deltas": {k: current["scores"][k] - base["scores"][k] for k in base["scores"]},
                }
            )
        groups = {}
        for category in ["all", "contenido", "identidad", "multi_documento"]:
            rows = [r for r in paired if category == "all" or r["categoria"] == category]
            groups[category] = {
                k: {
                    "mean_delta": statistics.mean(r["deltas"][k] for r in rows),
                    "median_delta": statistics.median(r["deltas"][k] for r in rows),
                    "paired_bootstrap_ci95": bootstrap([r["deltas"][k] for r in rows]),
                }
                for k in paired[0]["deltas"]
            }
        result["comparisons"][version + "-v1"] = {"by_category": groups, "per_question": paired}
    (directory / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "selected": selected,
                "means": {
                    v: {k: x["mean"] for k, x in data["summary"]["all"]["metrics"].items()}
                    for v, data in result["versions"].items()
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(__file__).parent / "results")
    compare(parser.parse_args().results)
