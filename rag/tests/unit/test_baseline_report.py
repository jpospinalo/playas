"""Formato de las tablas del reporte de línea base
(``evaluation/baseline_report.py``). Sin red."""

from __future__ import annotations

from evaluation.baseline_report import count_by, judge_cost_line, markdown_table


def test_tabla_markdown_con_dos_decimales_y_guion_para_faltantes() -> None:
    resumen = {
        "5. Aplicación": {"n": 3, "faithfulness": 0.8333, "context_recall": None},
        "1. Extracción": {"n": 1, "faithfulness": 1.0, "context_recall": 0.5},
    }
    tabla = markdown_table(resumen, "Tipo", ["faithfulness", "context_recall"])
    assert tabla.splitlines() == [
        "| Tipo | n | faithfulness | context_recall |",
        "|---|---:|---:|---:|",
        "| 5. Aplicación | 3 | 0.83 | — |",
        "| 1. Extracción | 1 | 1.00 | 0.50 |",
    ]


def test_conteo_por_campo_en_orden_descendente() -> None:
    filas = [{"outcome": "respondida"}, {"outcome": "sin_evidencia"}, {"outcome": "respondida"}]
    assert count_by(filas, "outcome") == [("respondida", 2), ("sin_evidencia", 1)]


def test_costo_del_juez_solo_suma_costos_medidos_por_caso() -> None:
    filas = [{"cost_usd_est": 0.01}, {"cost_usd_est": 0.02}, {"cost_usd_est_aprox": 5.0}]
    assert judge_cost_line(filas) == (
        "- costo estimado del juez: $0.0300 en 2 casos medidos; "
        "1 caso(s) sin costo por caso (corrida anterior a la medición por caso)"
    )


def test_costo_del_juez_sin_casos_sin_medir() -> None:
    assert judge_cost_line([{"cost_usd_est": 0.5}]) == (
        "- costo estimado del juez: $0.5000 en 1 casos medidos"
    )
