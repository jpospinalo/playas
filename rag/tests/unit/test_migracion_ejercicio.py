"""La migración versionada debe coincidir con los modelos y solo agregar."""

from __future__ import annotations

import importlib.util
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parents[2]
MIG = RAIZ / "infrastructure" / "migrations"
CARPETA = MIG / "2026-10-30_ejercicio_validacion"


def _generador():
    spec = importlib.util.spec_from_file_location("generar_sql", MIG / "generar_sql.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sql_versionado_igual_al_generado(tmp_path: pathlib.Path) -> None:
    _generador().main(tmp_path)
    for nombre in ("up.sql", "down.sql"):
        assert (tmp_path / nombre).read_text() == (CARPETA / nombre).read_text(), (
            f"{nombre} desactualizado: regenerar con infrastructure/migrations/generar_sql.py"
        )


def test_up_solo_agrega_y_no_toca_tablas_de_main() -> None:
    up = (CARPETA / "up.sql").read_text().upper()
    for prohibido in ("ALTER ", "DROP ", "RENAME", "TRUNCATE", "DELETE "):
        assert prohibido not in up
    down = (CARPETA / "down.sql").read_text()
    for tabla in _generador().TABLAS_MAIN:
        assert f"DROP TABLE IF EXISTS {tabla} " not in down
