"""Registro versionado de evaluaciones (``evaluation/registro.py``)."""

from __future__ import annotations

import csv
from pathlib import Path

from evaluation.registro import FIELDS, append_run, render_markdown, summarize_run

_GEN = [
    {
        "case_id": "registro-002",
        "outcome": "respondida",
        "documentos_esperados": ["A"],
        "context_titles": ["A", "B"],
        "duration_seconds": 10.0,
        "cost_usd_est": 0.0,
        "enrichment_fallback": True,
    },
    {
        "case_id": "registro-003",
        "outcome": "sin_recuperacion:out_of_scope",
        "documentos_esperados": ["A"],
        "context_titles": [],
        "duration_seconds": 30.0,
        "cost_usd_est": 0.0,
        "enrichment_fallback": False,
    },
]
_RAGAS = [
    {
        "case_id": "registro-002",
        "diagnostico": "correcta",
        "scores": {
            "faithfulness": 0.9,
            "factual_f1": 0.5,
            "answer_accuracy": 0.75,
            "context_recall": 1.0,
        },
    }
]
_META = {
    "fecha": "2026-10-15",
    "version_sistema": "abc1234",
    "etiqueta": "gemma4-e2b",
    "modelo_generador": "gemma4:e2b (local)",
    "juez": "gpt-5-nano",
}


def test_resumen_de_una_corrida() -> None:
    row = summarize_run(_GEN, _RAGAS, _META)
    assert row["casos"] == "2"
    assert row["respondidas"] == "1"
    assert row["correctas"] == "1"
    assert row["hit_at_4"] == "0.50"
    assert row["respaldo_enricher"] == "1"
    assert row["faithfulness"] == "0.90"
    assert row["latencia_media_s"] == "20.0"
    assert row["costo_generacion_usd"] == "0.0000"


def test_agregar_corrida_crea_el_csv_con_encabezado(tmp_path: Path) -> None:
    path = tmp_path / "evaluaciones.csv"
    append_run(summarize_run(_GEN, _RAGAS, _META), path)
    append_run(summarize_run(_GEN, _RAGAS, {**_META, "etiqueta": "otra"}), path)
    with path.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [r["etiqueta"] for r in rows] == ["gemma4-e2b", "otra"]
    assert list(rows[0].keys()) == FIELDS


def test_tabla_markdown_del_registro() -> None:
    md = render_markdown([summarize_run(_GEN, _RAGAS, _META)])
    assert "| 2026-10-15 |" in md
    assert "gemma4:e2b (local)" in md


def test_la_version_del_sistema_es_el_ultimo_commit_del_backend() -> None:
    import re
    import subprocess

    from evaluation.registro import system_version

    esperado = subprocess.run(
        ["git", "log", "-1", "--format=%h", "--abbrev=7", "--", "backend"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    version = system_version()
    assert re.fullmatch(r"[0-9a-f]{7}", version)
    assert version == esperado


def test_la_linea_base_sin_medicion_de_respaldo_dice_no_disponible() -> None:
    sin_campo = [{k: v for k, v in r.items() if k != "enrichment_fallback"} for r in _GEN]
    assert summarize_run(sin_campo, _RAGAS, _META)["respaldo_enricher"] == "n/d"
