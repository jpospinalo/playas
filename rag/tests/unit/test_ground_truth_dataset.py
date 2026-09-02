"""Validación del dataset ``legal-ground-truth-v0.1`` y de su cargador
(``evaluation/ground_truth.py``).

El dataset es la fuente única de las 21 preguntas jurídicas usadas tanto
por la regresión de alcance (``test_query_analysis.py``) como por la
evaluación offline/online en ``evaluation/``. Estas pruebas fijan su
contrato — no reprocesan el Excel original ni dependen de él: solo leen
el JSON ya versionado en ``evaluation/data/legal-ground-truth-v0.1.json``.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from evaluation.ground_truth import (
    CASE_FIELDS,
    DATASET_ANNOTATION,
    DATASET_NAME,
    EXPECTED_CASE_COUNT,
    GroundTruthValidationError,
    default_dataset_path,
    load_ground_truth_cases,
)

_REQUIRED_CONTENT_FIELDS = (
    "doc_principal",
    "doc_secundario",
    "pregunta",
    "respuesta",
    "ubicacion_evidencia",
)

# Campos del registro original que la Ola A decidió no importar (datos
# personales o puramente editoriales, ajenos al contenido jurídico).
_FORBIDDEN_KEYS = ("tipo", "usuario", "nota", "elaborado_por", "revisado_por")

# El registro N.º 1 del Excel original no tenía pregunta, respuesta ni
# evidencia diligenciadas y por eso queda fuera del dataset — el primer
# caso incluido es el registro N.º 2.
_EXCLUDED_INCOMPLETE_ID = "registro-001"


def test_carga_exactamente_21_casos() -> None:
    cases = load_ground_truth_cases()
    assert len(cases) == EXPECTED_CASE_COUNT == 21


def test_nombre_del_dataset_es_exacto() -> None:
    with open(default_dataset_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["name"] == DATASET_NAME == "legal-ground-truth-v0.1"


def test_anotacion_del_dataset_es_exacta() -> None:
    with open(default_dataset_path(), encoding="utf-8") as f:
        data = json.load(f)
    assert data["annotation"] == DATASET_ANNOTATION == "Esperando validación final"


@pytest.mark.parametrize("field_name", _REQUIRED_CONTENT_FIELDS)
def test_los_cinco_campos_obligatorios_no_estan_vacios_en_ningun_caso(
    field_name: str,
) -> None:
    cases = load_ground_truth_cases()
    for case in cases:
        assert case[field_name].strip() != "", f"{case['id']}.{field_name} está vacío"


def test_no_aplica_es_un_valor_diligenciado_valido() -> None:
    """'No aplica' no es un campo vacío: al menos un caso real del dataset
    lo usa como valor legítimo en más de un campo, y debe seguir presente
    verbatim (no filtrado, no reemplazado)."""
    cases = load_ground_truth_cases()
    valores = {case[field] for case in cases for field in _REQUIRED_CONTENT_FIELDS}
    assert "No aplica" in valores


def test_ids_unicos() -> None:
    cases = load_ground_truth_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)) == EXPECTED_CASE_COUNT


def test_preguntas_unicas() -> None:
    cases = load_ground_truth_cases()
    preguntas = [case["pregunta"] for case in cases]
    assert len(preguntas) == len(set(preguntas)) == EXPECTED_CASE_COUNT


def test_ningun_caso_tiene_campos_personales_o_editoriales() -> None:
    """El registro original tenía 'Tipo', 'Usuario de Playa Vinculado',
    'Nota', 'Elaborado por' y 'Revisado por'; ninguno de esos campos debe
    haberse importado al dataset versionado."""
    with open(default_dataset_path(), encoding="utf-8") as f:
        data = json.load(f)
    for case in data["cases"]:
        keys = set(case.keys())
        assert keys == set(CASE_FIELDS), f"{case.get('id')}: claves inesperadas {keys}"
        for forbidden in _FORBIDDEN_KEYS:
            assert forbidden not in keys


def test_no_contiene_ninguna_palabra_de_estado_provisional() -> None:
    """El dataset no debe usar 'draft', 'provisional', 'approved' ni
    equivalentes como marca de estado — 'annotation' es la única anotación
    permitida y ya se valida por su valor exacto en otra prueba."""
    with open(default_dataset_path(), encoding="utf-8") as f:
        raw_text = f.read()
    lowered = raw_text.lower()
    for forbidden_word in ("draft", "provisional", "approved"):
        assert forbidden_word not in lowered


def test_el_registro_incompleto_no_esta_en_el_dataset() -> None:
    cases = load_ground_truth_cases()
    ids = {case["id"] for case in cases}
    assert _EXCLUDED_INCOMPLETE_ID not in ids
    assert min(ids) == "registro-002"


def test_carga_sin_excel_red_ni_credenciales(monkeypatch: pytest.MonkeyPatch) -> None:
    """El cargador solo lee el JSON local: bloquear la creación de sockets
    y confirmar que la carga sigue funcionando prueba que no intenta
    ninguna llamada de red (ni, por construcción, abrir el Excel — el
    cargador no sabe que ese archivo existe)."""

    def _no_sockets(*args: object, **kwargs: object) -> None:
        raise AssertionError("load_ground_truth_cases() no debe abrir sockets de red")

    monkeypatch.setattr(socket, "socket", _no_sockets)
    cases = load_ground_truth_cases()
    assert len(cases) == EXPECTED_CASE_COUNT


def test_ruta_faltante_produce_error_especifico(tmp_path: Path) -> None:
    missing = tmp_path / "no-existe.json"
    with pytest.raises(GroundTruthValidationError):
        load_ground_truth_cases(path=missing)


def test_json_malformado_produce_error_especifico(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{no es json", encoding="utf-8")
    with pytest.raises(GroundTruthValidationError):
        load_ground_truth_cases(path=bad)


def test_nombre_incorrecto_produce_error_especifico(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"name": "otro-nombre", "annotation": DATASET_ANNOTATION, "cases": []}),
        encoding="utf-8",
    )
    with pytest.raises(GroundTruthValidationError):
        load_ground_truth_cases(path=bad)


def test_conteo_de_casos_incorrecto_produce_error_especifico(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"name": DATASET_NAME, "annotation": DATASET_ANNOTATION, "cases": []}),
        encoding="utf-8",
    )
    with pytest.raises(GroundTruthValidationError):
        load_ground_truth_cases(path=bad)
