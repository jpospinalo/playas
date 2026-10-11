"""Dataset ``legal-ground-truth-v0.2``: construcción desde el Excel del equipo
jurídico y cargador validado del JSON versionado.

Fuente: ``evaluation/data/legal-ground-truth-v0.2.xlsx``, hoja «Registros»
(fila 3 = encabezados). Se incluye todo registro con pregunta y respuesta
diligenciadas: 66 casos.

Diferencias deliberadas frente a la v0.1 (``ground_truth.py``, que no se
modifica):

- Se conserva el **tipo de pregunta**, normalizado a los seis tipos de la
  hoja «Instrucciones», para poder reportar la línea base por tipo.
- Se agrega ``revisado`` (``True`` si la columna «Revisión» tiene contenido).
  No se importan nombres de autores ni revisores, ni el usuario de playa ni
  la nota: mismo criterio que la v0.1.
- Se agrega ``documentos_esperados``: títulos de la capa gold del corpus. El
  cruce es **por título**, con una tabla explícita, porque la numeración
  SM-XX del Excel no coincide con el metadato ``Nº`` del corpus (ver
  ``docs/EVALUACION_LINEA_BASE.md``, hallazgo D1). No se hace búsqueda difusa: una
  referencia desconocida es un error.

El Excel se lee solo con la biblioteca estándar (un ``.xlsx`` es un ZIP de
XML), igual que ``ground_truth.py``: sin ``openpyxl`` ni ``pandas``.

Uso:
    uv run python -m evaluation.ground_truth_v02   # regenera el JSON desde el Excel
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

DATASET_NAME = "legal-ground-truth-v0.2"
EXPECTED_CASE_COUNT = 66
SHEET_NAME = "Registros"
HEADER_ROW = 3

CASE_FIELDS = (
    "id",
    "tipo",
    "doc_principal",
    "doc_secundario",
    "documentos_esperados",
    "pregunta",
    "respuesta",
    "ubicacion_evidencia",
    "revisado",
)

TIPOS: dict[int, str] = {
    1: "1. Extracción puntual",
    2: "2. Síntesis dentro de un documento",
    3: "3. Cruce entre documentos",
    4: "4. Comparación jurídica",
    5: "5. Aplicación normativa o jurisprudencial",
    6: "6. Secuencia, trámite u orden jurídico",
}

# Valor exacto de la lista desplegable del Excel (hoja «_listas») → título
# del documento en la capa gold (metadato ``title`` de cada chunk).
DOC_REFERENCE_TO_CORPUS_TITLE: dict[str, str] = {
    "SM-01 · AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Marta y otros": (
        "AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Mata y otros"
    ),
    "SM-02 · AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros": (
        "AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros"
    ),
    "SM-03 · AP Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros": (
        "AP  Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros"
    ),
    "SM-04 · AP Rodrigo Martínez Silva VS Minambiente y otros": (
        "AP Rodrigo Martínez Silva VS Minambiente y otros"
    ),
    "SM-05 · AP Gabriel Antonio Carrero VS DIMAR y otros": (
        "AP Gabriel Antonio Carrero VS DIMAR y otros"
    ),
    "SM-06 · AP Miguel Ángel Enciso VS Distrito y otros": (
        "AP Miguel Ángel Enciso VS Distrito y otros"
    ),
    "SM-07 · AP Felipe José Campo Fernández VS Corpamag y otros": (
        "AP Felipe José Campo Fernández VS Corpamag y otros"
    ),
    "SM-08 · AP Inversiones E y D S.A.S VS DIMAR y otros": (
        "AP Inversiones E y D S.A.S VS DIMAR y otros"
    ),
    "SM-09 · AP Procuraduría General de la Nación VS Corpamag y otros": (
        "AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS"
    ),
    "SM-10 · Sentencia de Segunda Instancia AP Gabriel Antonio Carrero (segunda instancia SM-05)": (
        "SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO"
    ),
    "N-01 · Decreto 2324 de 1984": "decreto-2324-de-1984",
    "N-02 · REMAC 5 — Reglamento Marítimo Colombiano (edición 2021)": (
        "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)"
    ),
}

_NO_APLICA = "no aplica"

# Columnas de la hoja «Registros» (fila de encabezados = HEADER_ROW).
_COLUMNS = {
    "A": "numero",
    "B": "tipo",
    "C": "doc_principal",
    "D": "doc_secundario",
    "F": "pregunta",
    "G": "respuesta",
    "H": "ubicacion_evidencia",
    "K": "revision",
}

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "rel": "http://schemas.openxmlformats.org/package/2006/relationships",
}


class GroundTruthV02Error(ValueError):
    """El Excel o el JSON de la v0.2 no cumplen el contrato de este módulo."""


def default_xlsx_path() -> Path:
    return Path(__file__).resolve().parent / "data" / f"{DATASET_NAME}.xlsx"


def default_json_path() -> Path:
    return Path(__file__).resolve().parent / "data" / f"{DATASET_NAME}.json"


# ============================================================
#  1. Normalización
# ============================================================


def _plain(text: str) -> str:
    """Minúsculas, sin tildes y con espacios colapsados (solo para comparar)."""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", no_accents).strip().lower()


def same_title(a: str, b: str) -> bool:
    """``True`` si dos títulos son el mismo documento. Compara en NFC porque
    parte del corpus trae los títulos en NFD (tilde separada de la letra):
    se ven iguales pero ``==`` los distingue."""
    return unicodedata.normalize("NFC", a) == unicodedata.normalize("NFC", b)


def normalize_tipo(raw: str) -> str:
    """Lleva una etiqueta de tipo del Excel a uno de los seis ``TIPOS``.

    El Excel trae variantes de la misma categoría: mayúsculas y tildes
    distintas, espacios sobrantes, y el tipo 6 partido en dos celdas
    ("6. Secuencia" y "trámite u orden jurídico")."""
    plain = _plain(raw or "")
    if plain.startswith("trámite") or plain.startswith("tramite"):
        return TIPOS[6]
    match = re.match(r"^([1-6])\.", plain)
    if match is None:
        raise GroundTruthV02Error(f"Tipo de pregunta desconocido: {raw!r}")
    return TIPOS[int(match.group(1))]


def resolve_corpus_title(reference: str | None) -> str | None:
    """Título gold del documento referido, o ``None`` si no hay documento
    ("No aplica" o celda vacía). Una referencia que no está en la tabla es un
    error explícito, nunca una coincidencia aproximada."""
    value = (reference or "").strip()
    if not value or value.lower() == _NO_APLICA:
        return None
    try:
        return DOC_REFERENCE_TO_CORPUS_TITLE[value]
    except KeyError as exc:
        raise GroundTruthV02Error(f"Referencia documental desconocida: {value!r}") from exc


# ============================================================
#  2. Lectura del Excel con la biblioteca estándar
# ============================================================


def _shared_strings(book: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in book.namelist():
        return []
    root = ElementTree.fromstring(book.read("xl/sharedStrings.xml"))
    # Cada <si> puede ser texto simple (<t>) o texto enriquecido (<r><t>…).
    return ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")) for si in root]


def _sheet_path(book: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ElementTree.fromstring(book.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.get("Id"): rel.get("Target") for rel in rels.findall("rel:Relationship", _NS)}
    for sheet in workbook.iterfind("m:sheets/m:sheet", _NS):
        if sheet.get("name") == sheet_name:
            target = targets[sheet.get(f"{{{_NS['r']}}}id")] or ""
            return target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    raise GroundTruthV02Error(f"El Excel no tiene la hoja {sheet_name!r}.")


def _cell_text(cell: ElementTree.Element, shared: list[str]) -> str:
    kind = cell.get("t")
    if kind == "inlineStr":
        return "".join(t.text or "" for t in cell.iter(f"{{{_NS['m']}}}t"))
    value = cell.find("m:v", _NS)
    if value is None or value.text is None:
        return ""
    if kind == "s":
        return shared[int(value.text)]
    return value.text


def read_registros_xlsx(path: Path) -> list[dict[str, str]]:
    """Filas de datos de la hoja «Registros» (las que siguen a la fila de
    encabezados), con las columnas de ``_COLUMNS`` como cadenas recortadas."""
    try:
        book = zipfile.ZipFile(path)
    except (FileNotFoundError, zipfile.BadZipFile) as exc:
        raise GroundTruthV02Error(f"No se pudo abrir el Excel {path}: {exc}") from exc
    with book:
        shared = _shared_strings(book)
        sheet = ElementTree.fromstring(book.read(_sheet_path(book, SHEET_NAME)))
    rows: list[dict[str, str]] = []
    for row in sheet.iterfind("m:sheetData/m:row", _NS):
        if int(row.get("r", "0")) <= HEADER_ROW:
            continue
        record = dict.fromkeys(_COLUMNS.values(), "")
        for cell in row.iterfind("m:c", _NS):
            column = re.sub(r"\d", "", cell.get("r", ""))
            if column in _COLUMNS:
                record[_COLUMNS[column]] = _cell_text(cell, shared).strip()
        rows.append(record)
    return rows


# ============================================================
#  3. Construcción de casos
# ============================================================


def _case_id(numero: str) -> str:
    try:
        return f"registro-{int(float(numero)):03d}"
    except ValueError as exc:
        raise GroundTruthV02Error(f"N.º de registro inválido: {numero!r}") from exc


def build_cases(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Casos de la v0.2: solo filas con pregunta y respuesta, en el orden del
    Excel. Cada caso tiene exactamente las claves de ``CASE_FIELDS``."""
    cases: list[dict[str, Any]] = []
    for row in rows:
        if not (row["pregunta"] and row["respuesta"]):
            continue
        esperados = [
            title
            for title in (
                resolve_corpus_title(row["doc_principal"]),
                resolve_corpus_title(row["doc_secundario"]),
            )
            if title is not None
        ]
        cases.append(
            {
                "id": _case_id(row["numero"]),
                "tipo": normalize_tipo(row["tipo"]),
                "doc_principal": row["doc_principal"],
                "doc_secundario": row["doc_secundario"],
                "documentos_esperados": list(dict.fromkeys(esperados)),
                "pregunta": row["pregunta"],
                "respuesta": row["respuesta"],
                "ubicacion_evidencia": row["ubicacion_evidencia"],
                "revisado": bool(row["revision"]),
            }
        )
    return cases


# ============================================================
#  4. JSON versionado
# ============================================================


def write_json(cases: list[dict[str, Any]], xlsx_path: Path, json_path: Path) -> None:
    data = {
        "name": DATASET_NAME,
        "source": xlsx_path.name,
        "source_sha256": hashlib.sha256(xlsx_path.read_bytes()).hexdigest(),
        "tipos": list(TIPOS.values()),
        "cases": cases,
    }
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_ground_truth_v02(path: Path | None = None) -> list[dict[str, Any]]:
    """Carga y valida el JSON versionado: nombre, conteo exacto, claves de
    cada caso, tipos válidos e IDs únicos."""
    json_path = path if path is not None else default_json_path()
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise GroundTruthV02Error(f"No se pudo leer {json_path}: {exc}") from exc
    if data.get("name") != DATASET_NAME:
        raise GroundTruthV02Error(f"{json_path} declara name={data.get('name')!r}.")
    cases = data.get("cases")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        count = len(cases) if isinstance(cases, list) else "?"
        raise GroundTruthV02Error(
            f"{json_path} tiene {count} casos; se esperaban {EXPECTED_CASE_COUNT}."
        )
    tipos_validos = set(TIPOS.values())
    for case in cases:
        if tuple(case.keys()) != CASE_FIELDS:
            raise GroundTruthV02Error(f"Caso con claves inesperadas: {sorted(case.keys())}")
        if case["tipo"] not in tipos_validos:
            raise GroundTruthV02Error(f"Caso {case['id']} con tipo inválido: {case['tipo']!r}")
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise GroundTruthV02Error(f"{json_path} tiene IDs duplicados.")
    return cases


def main() -> int:
    xlsx_path = default_xlsx_path()
    cases = build_cases(read_registros_xlsx(xlsx_path))
    write_json(cases, xlsx_path, default_json_path())
    print(f"{DATASET_NAME}: {len(cases)} casos → {default_json_path()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
