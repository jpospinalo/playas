# evaluation/citation_coverage.py
"""C1.3 — Cobertura sintáctica de citas offline.

Utilidad de evaluación (Ola C — no un guard online, no cambia comportamiento
de producción). Vive en ``evaluation/`` junto al resto de la infraestructura
de evaluación existente en vez de crear un segundo framework.

Mide, sobre respuestas ya generadas (reales o sintéticas), cuatro señales
puramente sintácticas — nunca semánticas, no requiere ningún LLM adicional:

- presencia de citas (¿la respuesta cita al menos un documento?);
- índices válidos / citas inexistentes (¿cada ``[docN]`` referencia un
  documento realmente entregado, ``1 <= N <= doc_count``?);
- párrafos jurídicos sin cita (¿qué párrafos de la respuesta no incluyen
  ninguna cita?).

Reutiliza el mismo patrón de cita, ``_CITATION_RE`` de ``core/agent.py`` —
la única fuente de la verdad de lo que production reconoce como cita, usada
hoy por ``_validate_citations()`` en la ruta online (gate binario:
pasa/no-pasa) — para que esta utilidad offline nunca pueda divergir en
silencio de lo que el backend realmente reconoce como cita. A diferencia de
``_validate_citations()``, esta utilidad no decide pasa/no-pasa: reporta
métricas descriptivas por respuesta y agregadas sobre un dataset sintético,
pensadas como evidencia para el informe de Ola C (sección 14 del plan), no
para bloquear ni modificar ninguna respuesta real. No se importa ni se
invoca desde ``core/agent.py`` ni desde ninguna ruta de ``api/``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any

from rag.core.agent import _CITATION_RE

# ============================================================
#  1. Análisis sintáctico de una sola respuesta
# ============================================================


@dataclass
class CitationCoverageResult:
    has_any_citation: bool
    citation_indices: list[int]
    valid_indices: list[int]
    invalid_indices: list[int]  # citas fuera de rango [1, doc_count] — "citas inexistentes"
    paragraph_count: int
    uncited_paragraphs: list[str] = field(repr=False)

    @property
    def uncited_paragraph_count(self) -> int:
        return len(self.uncited_paragraphs)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _split_paragraphs(answer: str) -> list[str]:
    """Divide la respuesta en párrafos por línea en blanco, descartando los
    que quedan vacíos tras recortar espacios. Es una heurística sintáctica
    simple (no NLP): suficiente para "¿qué bloques de texto no llevan
    ninguna cita?", que es la pregunta que C1.3 pide medir — no intenta
    identificar oraciones jurídicas individuales.
    """
    return [p.strip() for p in answer.split("\n\n") if p.strip()]


def analyze_citation_coverage(answer: str, doc_count: int) -> CitationCoverageResult:
    """Analiza una única respuesta (real o sintética) y devuelve las cuatro
    señales sintácticas de cobertura de citas.

    ``doc_count`` es el mismo parámetro que ``_validate_citations(answer,
    doc_count)`` ya recibe en producción: cuántos documentos se entregaron
    como contexto para esta respuesta (los índices válidos van de 1 a
    ``doc_count`` inclusive).
    """
    indices = [int(value) for value in _CITATION_RE.findall(answer)]
    valid = [value for value in indices if 1 <= value <= doc_count]
    invalid = [value for value in indices if not (1 <= value <= doc_count)]

    paragraphs = _split_paragraphs(answer)
    uncited = [p for p in paragraphs if not _CITATION_RE.search(p)]

    return CitationCoverageResult(
        has_any_citation=bool(indices),
        citation_indices=indices,
        valid_indices=valid,
        invalid_indices=invalid,
        paragraph_count=len(paragraphs),
        uncited_paragraphs=uncited,
    )


# ============================================================
#  2. Agregación sobre un dataset sintético de respuestas
# ============================================================


@dataclass
class SyntheticAnswerCase:
    """Un caso sintético: una respuesta ya generada (no se llama a ningún
    LLM aquí) más el ``doc_count`` con el que se generó."""

    name: str
    answer: str
    doc_count: int


# Dataset sintético general — cubre las cuatro señales por separado y
# combinadas, para que el resumen agregado sea legible como evidencia:
# 1 caso sin ninguna cita, 1 con todos los párrafos citados correctamente,
# 1 con un párrafo sin cita, 1 con una cita fuera de rango (inexistente),
# 1 con varias citas válidas repetidas al mismo documento, 1 con múltiples
# párrafos y cobertura mixta.
SYNTHETIC_ANSWER_DATASET: list[SyntheticAnswerCase] = [
    SyntheticAnswerCase(
        name="sin_ninguna_cita",
        answer="La normativa vigente regula el dominio público marítimo-terrestre en Colombia.",
        doc_count=3,
    ),
    SyntheticAnswerCase(
        name="parrafo_unico_citado_correctamente",
        answer="El Decreto 1076 de 2015 regula la materia [doc1].",
        doc_count=2,
    ),
    SyntheticAnswerCase(
        name="dos_parrafos_uno_sin_cita",
        answer=(
            "El primer párrafo cita correctamente la fuente [doc1].\n\n"
            "El segundo párrafo no incluye ninguna referencia a los documentos entregados."
        ),
        doc_count=2,
    ),
    SyntheticAnswerCase(
        name="cita_fuera_de_rango",
        answer="Según el análisis jurídico [doc5], la norma aplica al caso.",
        doc_count=2,  # solo se entregaron 2 documentos: [doc5] no existe
    ),
    SyntheticAnswerCase(
        name="citas_repetidas_validas",
        answer="El Consejo de Estado se pronunció [doc1] y reiteró el criterio [doc1] en el mismo fallo [doc2].",
        doc_count=2,
    ),
    SyntheticAnswerCase(
        name="tres_parrafos_cobertura_mixta",
        answer=(
            "Primer párrafo con cita válida [doc1].\n\n"
            "Segundo párrafo con cita inexistente [doc9].\n\n"
            "Tercer párrafo sin ninguna cita."
        ),
        doc_count=3,
    ),
]


def analyze_dataset(
    cases: list[SyntheticAnswerCase] = SYNTHETIC_ANSWER_DATASET,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        result = analyze_citation_coverage(case.answer, case.doc_count)
        rows.append({"caso": case.name, "doc_count": case.doc_count, **result.as_dict()})
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Resumen agregado — las cuatro señales de C1.3 sobre el dataset completo."""
    n = len(rows)
    with_citation = sum(1 for r in rows if r["has_any_citation"])
    total_paragraphs = sum(r["paragraph_count"] for r in rows)
    total_uncited_paragraphs = sum(len(r["uncited_paragraphs"]) for r in rows)
    total_invalid_citations = sum(len(r["invalid_indices"]) for r in rows)
    total_valid_citations = sum(len(r["valid_indices"]) for r in rows)
    cases_with_invalid_citation = sum(1 for r in rows if r["invalid_indices"])

    return {
        "n_respuestas": n,
        "respuestas_con_al_menos_una_cita": with_citation,
        "respuestas_sin_ninguna_cita": n - with_citation,
        "parrafos_totales": total_paragraphs,
        "parrafos_sin_cita": total_uncited_paragraphs,
        "citas_validas_totales": total_valid_citations,
        "citas_inexistentes_totales": total_invalid_citations,
        "respuestas_con_alguna_cita_inexistente": cases_with_invalid_citation,
    }


# ============================================================
#  3. Punto de entrada — guarda evidencia JSON reproducible
# ============================================================


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def main(report_json_path: str = "evaluation/citation_coverage_report.json") -> None:
    rows = analyze_dataset()
    summary = summarize(rows)
    report = {"resumen": summary, "casos": rows}

    _ensure_parent_dir(report_json_path)
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"Cobertura de citas guardada en: {report_json_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
