"""Rutas por corrida de la evaluación (``evaluation/run_paths.py``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation.run_paths import tagged

_BASE = Path("evaluation/results/generation-cache-v0.2.jsonl")


def test_sin_etiqueta_la_ruta_no_cambia() -> None:
    assert tagged(_BASE, None) == _BASE


def test_la_etiqueta_va_antes_de_la_extension() -> None:
    assert tagged(_BASE, "gemma4-e2b") == Path(
        "evaluation/results/generation-cache-v0.2-gemma4-e2b.jsonl"
    )


@pytest.mark.parametrize("mala", ["", " ", "../x", "Gemma 4", "a/b", "-x"])
def test_etiqueta_invalida_falla_en_vez_de_pisar_archivos(mala: str) -> None:
    with pytest.raises(ValueError):
        tagged(_BASE, mala)
