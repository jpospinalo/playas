# evaluation/ground_truth.py
"""Cargador mínimo del dataset ``legal-ground-truth-v0.1``.

Localiza, carga y valida el JSON versionado en
``evaluation/data/legal-ground-truth-v0.1.json`` — la fuente única de las
21 preguntas jurídicas que hoy alimentan tanto la regresión de alcance
(``tests/unit/test_query_analysis.py``) como la evaluación offline/online
en ``evaluation/``. Cada caso proviene de una fila del registro de ground
truth original que tenía diligenciados los cinco campos requeridos
(documento principal, documento secundario, pregunta, respuesta y
ubicación de la evidencia); el filtro y la extracción ya se aplicaron al
construir el JSON, este módulo solo valida que el archivo en disco sigue
cumpliendo ese contrato antes de entregarlo a quien lo use.

Solo usa la biblioteca estándar. No importa ``ragas``, ``datasets``,
LangChain, el backend, la API ni ningún servicio externo — se puede
importar y ejecutar sin red, sin credenciales y sin que el paquete
``rag`` esté disponible.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATASET_NAME = "legal-ground-truth-v0.1"
DATASET_ANNOTATION = "Esperando validación final"
EXPECTED_CASE_COUNT = 21

# Campos que debe tener cada caso, en el mismo orden que la regla de
# selección original (id + los cinco campos que esa regla exige no vacíos).
CASE_FIELDS = (
    "id",
    "doc_principal",
    "doc_secundario",
    "pregunta",
    "respuesta",
    "ubicacion_evidencia",
)

_DATASET_FILENAME = f"{DATASET_NAME}.json"


class GroundTruthValidationError(ValueError):
    """El dataset en disco no cumple el contrato que este módulo exige."""


def default_dataset_path() -> Path:
    """Ruta relativa estable del dataset: junto a este archivo, en ``data/``."""
    return Path(__file__).resolve().parent / "data" / _DATASET_FILENAME


def load_ground_truth_cases(path: Path | None = None) -> list[dict[str, str]]:
    """Carga y valida ``legal-ground-truth-v0.1``, y retorna sus 21 casos.

    Cada caso es un ``dict`` plano con exactamente las claves de
    ``CASE_FIELDS``, todas cadenas no vacías. Lanza
    ``GroundTruthValidationError`` con un mensaje específico ante
    cualquier desviación del contrato (archivo ausente, JSON inválido,
    nombre/anotación distintos, conteo de casos distinto de 21, campos
    faltantes o vacíos, tipos incorrectos, o IDs/preguntas duplicados).
    """
    dataset_path = path if path is not None else default_dataset_path()
    data = _read_json(dataset_path)
    _validate_top_level(data, dataset_path)
    cases_raw = data["cases"]
    _validate_case_count(cases_raw, dataset_path)
    cases = [_validate_case(i, raw, dataset_path) for i, raw in enumerate(cases_raw)]
    _validate_uniqueness(cases, dataset_path)
    return cases


def _read_json(dataset_path: Path) -> Any:
    try:
        raw_text = dataset_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise GroundTruthValidationError(
            f"No se encontró el dataset de ground truth en {dataset_path}."
        ) from exc
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path} no es JSON válido: {exc}"
        ) from exc


def _validate_top_level(data: Any, dataset_path: Path) -> None:
    if not isinstance(data, dict):
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path} debe ser un objeto JSON en la raíz."
        )
    missing = {"name", "annotation", "cases"} - data.keys()
    if missing:
        raise GroundTruthValidationError(
            f"Al dataset en {dataset_path} le faltan las claves {sorted(missing)}."
        )
    if data["name"] != DATASET_NAME:
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path} declara name={data['name']!r}, "
            f"se esperaba {DATASET_NAME!r}."
        )
    if data["annotation"] != DATASET_ANNOTATION:
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path} declara annotation={data['annotation']!r}, "
            f"se esperaba {DATASET_ANNOTATION!r}."
        )
    if not isinstance(data["cases"], list):
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path}: 'cases' debe ser una lista."
        )


def _validate_case_count(cases_raw: list[Any], dataset_path: Path) -> None:
    if len(cases_raw) != EXPECTED_CASE_COUNT:
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path} tiene {len(cases_raw)} casos, "
            f"se esperaban exactamente {EXPECTED_CASE_COUNT}."
        )


def _validate_case(index: int, raw: Any, dataset_path: Path) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise GroundTruthValidationError(
            f"El caso en la posición {index} de {dataset_path} debe ser un objeto JSON."
        )
    actual_keys = set(raw.keys())
    expected_keys = set(CASE_FIELDS)
    if actual_keys != expected_keys:
        raise GroundTruthValidationError(
            f"El caso en la posición {index} de {dataset_path} tiene las claves "
            f"{sorted(actual_keys)}, se esperaban exactamente {sorted(expected_keys)}."
        )
    case: dict[str, str] = {}
    for field_name in CASE_FIELDS:
        value = raw[field_name]
        if not isinstance(value, str):
            raise GroundTruthValidationError(
                f"El campo {field_name!r} del caso en la posición {index} de "
                f"{dataset_path} debe ser string, no {type(value).__name__}."
            )
        # "No aplica" es un valor diligenciado válido y se conserva tal cual;
        # solo se rechaza una cadena vacía o compuesta solo por espacios.
        if value.strip() == "":
            raise GroundTruthValidationError(
                f"El campo {field_name!r} del caso en la posición {index} de "
                f"{dataset_path} está vacío."
            )
        case[field_name] = value
    return case


def _validate_uniqueness(cases: list[dict[str, str]], dataset_path: Path) -> None:
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise GroundTruthValidationError(f"El dataset en {dataset_path} tiene IDs duplicados.")
    preguntas = [case["pregunta"] for case in cases]
    if len(preguntas) != len(set(preguntas)):
        raise GroundTruthValidationError(
            f"El dataset en {dataset_path} tiene preguntas duplicadas."
        )
