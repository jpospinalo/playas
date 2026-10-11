"""Construcción y contrato del dataset ``legal-ground-truth-v0.2``
(``evaluation/ground_truth_v02.py``).

A diferencia de la v0.1, la v0.2 conserva el **tipo de pregunta** (necesario
para reportar la línea base por tipo) y agrega, por caso, la bandera
``revisado`` y los títulos del corpus de los documentos esperados. El mapeo
de documentos se hace por **título**, nunca por el código SM-XX: la
numeración del Excel no coincide con el metadato ``Nº`` del corpus (ver
``docs/EVALUACION_LINEA_BASE.md``, hallazgo D1).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from evaluation.ground_truth_v02 import (
    CASE_FIELDS,
    DOC_REFERENCE_TO_CORPUS_TITLE,
    TIPOS,
    GroundTruthV02Error,
    build_cases,
    default_json_path,
    default_xlsx_path,
    load_ground_truth_v02,
    normalize_tipo,
    read_registros_xlsx,
    resolve_corpus_title,
    same_title,
)

_GOLD_DIR = Path(__file__).resolve().parents[3] / "data" / "documents" / "gold"

# Datos personales o editoriales del registro original que no se importan,
# con el mismo criterio de la v0.1.
_FORBIDDEN_KEYS = ("usuario", "nota", "elaborado_por", "revisado_por")


# ── Tipos de pregunta ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("1. Extracción puntual", 1),
        ("2. Síntesis dentro de un documento", 2),
        ("3. Cruce entre documentos", 3),
        ("4. Comparación jurídica", 4),
        ("5. Aplicación normativa o jurisprudencial", 5),
        ("5. aplicacion normativa o jurisprudencial ", 5),
        ("6. Secuencia", 6),
        ("trámite u orden jurídico", 6),
    ],
)
def test_normaliza_las_etiquetas_sucias_a_los_seis_tipos(raw: str, esperado: int) -> None:
    assert normalize_tipo(raw) == TIPOS[esperado]


def test_tipo_desconocido_falla_explicitamente() -> None:
    with pytest.raises(GroundTruthV02Error):
        normalize_tipo("7. Tipo inventado")


# ── Mapeo de documentos por título ─────────────────────────────────────────


def test_mapea_el_codigo_del_excel_al_titulo_del_corpus_y_no_al_codigo() -> None:
    # En el Excel SM-01 es Lemus Orozco; en el corpus Lemus Orozco es SM-04.
    titulo = resolve_corpus_title(
        "SM-01 · AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Marta y otros"
    )
    assert titulo == "AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Mata y otros"


@pytest.mark.parametrize("vacio", [None, "", "No aplica", "  No aplica  "])
def test_referencia_vacia_o_no_aplica_no_tiene_documento(vacio: str | None) -> None:
    assert resolve_corpus_title(vacio) is None


def test_referencia_desconocida_falla_explicitamente() -> None:
    with pytest.raises(GroundTruthV02Error):
        resolve_corpus_title("SM-99 · Documento que no existe")


def test_todo_titulo_mapeado_existe_en_la_capa_gold() -> None:
    titulos_gold = set()
    for path in _GOLD_DIR.glob("*/*.jsonl"):
        with path.open(encoding="utf-8") as f:
            titulos_gold.add(json.loads(f.readline())["metadata"]["title"])
    for titulo in DOC_REFERENCE_TO_CORPUS_TITLE.values():
        assert any(same_title(titulo, gold) for gold in titulos_gold), titulo


def test_compara_titulos_sin_importar_la_forma_unicode() -> None:
    # Parte del corpus viene en NFD (tilde separada de la letra) y parte en NFC.
    nfd = unicodedata.normalize("NFD", "AP Felipe José Campo Fernández VS Corpamag y otros")
    assert same_title(nfd, "AP Felipe José Campo Fernández VS Corpamag y otros")
    assert not same_title(nfd, "AP Miguel Ángel Enciso VS Distrito y otros")


# ── Lectura del Excel y construcción de casos ──────────────────────────────


def test_lee_la_hoja_registros_del_xlsx_sin_dependencias() -> None:
    filas = read_registros_xlsx(default_xlsx_path())
    completas = [f for f in filas if f["pregunta"] and f["respuesta"]]
    assert len(completas) == 66


def test_construye_66_casos_con_el_contrato_exacto() -> None:
    cases = build_cases(read_registros_xlsx(default_xlsx_path()))
    assert len(cases) == 66
    for case in cases:
        assert tuple(case.keys()) == CASE_FIELDS
        for key in _FORBIDDEN_KEYS:
            assert key not in case


def test_ids_conservan_la_numeracion_del_registro_original() -> None:
    cases = build_cases(read_registros_xlsx(default_xlsx_path()))
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    # Mismo esquema que la v0.1 para poder cruzar ambas versiones.
    assert ids[0] == "registro-002"


def test_distribucion_de_tipos_y_revision() -> None:
    cases = build_cases(read_registros_xlsx(default_xlsx_path()))
    por_tipo = {t: sum(1 for c in cases if c["tipo"] == t) for t in TIPOS.values()}
    assert por_tipo == {
        TIPOS[1]: 2,
        TIPOS[2]: 7,
        TIPOS[3]: 5,
        TIPOS[4]: 7,
        TIPOS[5]: 37,
        TIPOS[6]: 8,
    }
    assert sum(1 for c in cases if c["revisado"]) == 27


def test_documentos_esperados_son_titulos_del_corpus() -> None:
    cases = build_cases(read_registros_xlsx(default_xlsx_path()))
    con_documento = [c for c in cases if c["documentos_esperados"]]
    # 8 casos sin ninguna referencia. Los registros 017–019 tienen "No aplica"
    # como principal pero sí un documento secundario (Decreto 2324).
    assert len(con_documento) == 66 - 8
    validos = set(DOC_REFERENCE_TO_CORPUS_TITLE.values())
    for case in con_documento:
        assert set(case["documentos_esperados"]) <= validos


# ── JSON versionado ───────────────────────────────────────────────────────


def test_json_versionado_coincide_con_lo_construido_desde_el_excel() -> None:
    desde_excel = build_cases(read_registros_xlsx(default_xlsx_path()))
    assert load_ground_truth_v02(default_json_path()) == desde_excel


def test_json_con_conteo_distinto_falla(tmp_path: Path) -> None:
    data = json.loads(default_json_path().read_text(encoding="utf-8"))
    data["cases"] = data["cases"][:-1]
    roto = tmp_path / "roto.json"
    roto.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(GroundTruthV02Error):
        load_ground_truth_v02(roto)
