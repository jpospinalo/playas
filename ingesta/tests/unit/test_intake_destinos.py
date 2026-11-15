"""Regresiones de la revisión: sufijo de preparación reservado y borrado seguro del arnés E2E."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from ingest.offline.intake_safety import ConfiguracionInvalida, cargar_destinos, validar_destino

E2E = Path(__file__).resolve().parents[2] / "benchmarks" / "intake" / "e2e_local.py"


def test_una_coleccion_viva_no_puede_llevar_el_sufijo_de_preparacion():
    destinos = cargar_destinos()
    validar_destino("bench_intake_demo", "127.0.0.1", destinos)
    for nombre in ("bench_intake_demo__staging", "atlas_intake_x__staging_y"):
        with pytest.raises(ConfiguracionInvalida, match="__staging"):
            validar_destino(nombre, "127.0.0.1", destinos)


@pytest.fixture(params=[E2E, E2E.parents[1] / "demo_aws/e2e_aws.py"])
def e2e(request):
    spec = importlib.util.spec_from_file_location("arnes_e2e", request.param)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_trabajo_e2e_no_puede_solaparse_con_rutas_protegidas(e2e, tmp_path):
    raw = tmp_path / "raw"
    (raw / "normativa").mkdir(parents=True)
    for trabajo in (raw, raw / "normativa", tmp_path):
        with pytest.raises(SystemExit, match="se solapa"):
            e2e.validar_trabajo(trabajo, [raw])


def test_trabajo_e2e_ajeno_y_no_vacio_no_se_borra(e2e, tmp_path):
    ajeno = tmp_path / "ajeno"
    ajeno.mkdir()
    (ajeno / "importante.txt").write_text("no borrar", encoding="utf-8")
    with pytest.raises(SystemExit, match="ni lo creó este arnés"):
        e2e.validar_trabajo(ajeno, [tmp_path / "raw"])
    (ajeno / e2e.MARCADOR).write_text("", encoding="utf-8")
    e2e.validar_trabajo(ajeno, [tmp_path / "raw"])
    e2e.validar_trabajo(tmp_path / "nuevo", [tmp_path / "raw"])


def test_nombre_visible_saneado_para_metadatos():
    from ingest.offline.intake_safety import nombre_visible

    h = "a" * 64
    assert nombre_visible("AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros.pdf", h) == (
        "AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros.pdf"
    )
    assert nombre_visible("inbox/sub/Decreto 1766.PDF", h) == "Decreto 1766.pdf"
    raro = nombre_visible("..\u202efdp.exe\tnombre\x01 " + "x" * 300 + ".pdf", h)
    assert "\u202e" not in raro and "\t" not in raro and "\x01" not in raro
    assert not raro.startswith(".") and len(raro) <= 124
    assert nombre_visible("../../etc/passwd", h) == "passwd.pdf"
    assert nombre_visible("...", h) == "aaaaaaaaaaaa.pdf"


def test_nombre_visible_limita_bytes_utf8_sin_cortar_caracteres():
    from ingest.offline.intake_safety import nombre_visible

    nombre = nombre_visible("漢" * 120 + ".pdf", "a" * 64)
    assert len(nombre.encode("utf-8")) <= 180
    assert nombre == "漢" * 58 + ".pdf"
