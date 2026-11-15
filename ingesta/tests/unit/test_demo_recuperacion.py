"""Compatibilidad de las métricas del demo con resultados guardados antiguos."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[2] / "benchmarks/demo_aws"
spec = importlib.util.spec_from_file_location("recuperacion_rag", DEMO / "recuperacion_rag.py")
recuperacion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recuperacion)


def test_comparar_recalcula_hit_produccion_antiguo_con_nfc_y_limite_cuatro():
    def caso(identidad, top, **metricas):
        return {
            "case_id": identidad,
            "documentos_esperados": ["Resolucio\u0301n"],
            "top_prod": top,
            "hit4": 0,
            "rr": 0.0,
            **metricas,
        }

    antes = {"casos": [caso("a", ["otro"] * 4 + ["Resolución"])]}
    despues = {"casos": [caso("a", ["Resolución"]), caso("sin_pareja", ["Resolución"])]}
    resultado = recuperacion.comparar(antes, despues, ["Resolución"], repeticiones=100)
    nuevos = resultado["nuevos"]
    assert nuevos["n"] == 1
    assert nuevos["hit4_produccion_antes"] == 0
    assert nuevos["hit4_produccion_despues"] == 1
    assert nuevos["ic95_delta_hit4_produccion"] == [1.0, 1.0]
    assert nuevos["hit4_despues"] == 0
    assert "hit4_produccion" not in antes["casos"][0]
    assert resultado["resto"]["n"] == 0

    despues["casos"][0]["hit4_produccion"] = 0
    assert (
        recuperacion.comparar(antes, despues, ["Resolución"], repeticiones=100)["nuevos"][
            "hit4_produccion_despues"
        ]
        == 0
    )


def test_comparar_cli_con_resultados_guardados():
    nuevos = [
        "AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros",
        "AP Inversiones E y D S.A.S VS DIMAR y otros",
    ]
    resultado = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "recuperacion_rag.py",
            "comparar",
            "resultados/recuperacion_antes.json",
            "resultados/recuperacion_despues.json",
            "--nuevos",
            *nuevos,
        ],
        cwd=DEMO,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    comparacion = json.loads(resultado.stdout)
    assert comparacion["nuevos"]["n"] == 10
    assert comparacion["nuevos"]["hit4_produccion_antes"] == 0
    assert comparacion["nuevos"]["hit4_produccion_despues"] == pytest.approx(0.9)
