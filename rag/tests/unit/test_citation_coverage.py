"""Pruebas de la utilidad offline de cobertura sintáctica de citas
(``evaluation/citation_coverage.py``).

Esta utilidad no es un guard online — no se importa desde ``core/agent.py``
ni desde ninguna ruta de ``api/`` — así que estas pruebas verifican
únicamente que la utilidad misma sea correcta y determinista, ya que su
salida se usa como evidencia de evaluación offline.

También confirma que reutiliza exactamente el mismo patrón de cita que
``_validate_citations()`` usa en la ruta online (``_CITATION_RE`` de
``core/agent.py``), para que no pueda divergir en silencio de lo que
producción realmente reconoce como cita.
"""

from __future__ import annotations

from evaluation.citation_coverage import (
    SYNTHETIC_ANSWER_DATASET,
    analyze_citation_coverage,
    analyze_dataset,
    summarize,
)
from rag.core.agent import _CITATION_RE, _validate_citations


def test_uses_the_exact_same_citation_pattern_as_the_online_gate() -> None:
    """No es una reimplementación paralela: usa el mismo objeto regex que
    ``core/agent.py::_validate_citations`` importa internamente."""
    from evaluation import citation_coverage

    assert citation_coverage._CITATION_RE is _CITATION_RE


def test_answer_with_no_citations_is_flagged_correctly() -> None:
    result = analyze_citation_coverage("Texto sin ninguna referencia a documentos.", doc_count=3)
    assert result.has_any_citation is False
    assert result.citation_indices == []
    assert result.valid_indices == []
    assert result.invalid_indices == []
    assert result.paragraph_count == 1
    assert result.uncited_paragraph_count == 1


def test_answer_with_a_valid_citation_is_flagged_correctly() -> None:
    result = analyze_citation_coverage("El decreto aplica al caso [doc1].", doc_count=2)
    assert result.has_any_citation is True
    assert result.citation_indices == [1]
    assert result.valid_indices == [1]
    assert result.invalid_indices == []
    assert result.uncited_paragraph_count == 0


def test_citation_referencing_a_document_beyond_doc_count_is_invalid() -> None:
    """'Cita inexistente': referencia un índice que nunca fue entregado
    como contexto (doc_count=2, pero cita [doc5])."""
    result = analyze_citation_coverage("Según el análisis [doc5].", doc_count=2)
    assert result.citation_indices == [5]
    assert result.valid_indices == []
    assert result.invalid_indices == [5]
    # La validación online (_validate_citations) rechazaría esta misma
    # respuesta por la misma razón — confirma que ambas piezas están de
    # acuerdo sobre qué cuenta como cita inexistente.
    assert _validate_citations("Según el análisis [doc5].", 2) is False


def test_citation_index_zero_or_negative_is_invalid() -> None:
    result = analyze_citation_coverage("Ver referencia [doc0].", doc_count=3)
    assert result.citation_indices == [0]
    assert result.invalid_indices == [0]
    assert result.valid_indices == []


def test_paragraphs_are_split_on_blank_lines_and_checked_independently() -> None:
    answer = "Primer párrafo con cita [doc1].\n\nSegundo párrafo sin ninguna cita."
    result = analyze_citation_coverage(answer, doc_count=2)
    assert result.paragraph_count == 2
    assert result.uncited_paragraph_count == 1
    assert result.uncited_paragraphs == ["Segundo párrafo sin ninguna cita."]


def test_a_paragraph_with_only_an_invalid_citation_still_counts_as_cited() -> None:
    """'Párrafo sin cita' es una señal puramente sintáctica (¿hay algún
    token [docN]?), independiente de si ese índice es válido — la validez
    se reporta por separado en invalid_indices."""
    answer = "Párrafo con una cita fuera de rango [doc9]."
    result = analyze_citation_coverage(answer, doc_count=1)
    assert result.uncited_paragraph_count == 0
    assert result.invalid_indices == [9]


def test_repeated_valid_citations_to_the_same_document_are_all_counted() -> None:
    answer = "Primero [doc1]. Después se reitera [doc1] y se añade [doc2]."
    result = analyze_citation_coverage(answer, doc_count=2)
    assert result.citation_indices == [1, 1, 2]
    assert result.valid_indices == [1, 1, 2]
    assert result.invalid_indices == []


def test_empty_paragraphs_from_extra_blank_lines_are_not_counted() -> None:
    answer = "Único párrafo con contenido [doc1].\n\n\n\n   \n\n"
    result = analyze_citation_coverage(answer, doc_count=1)
    assert result.paragraph_count == 1


def test_synthetic_dataset_summary_matches_a_hand_count() -> None:
    """El dataset sintético fue diseñado para cubrir las cuatro señales por
    separado — este conteo a mano documenta exactamente qué se espera de
    cada caso, y protege el resumen agregado de una regresión silenciosa."""
    rows = analyze_dataset()
    summary = summarize(rows)

    assert summary["n_respuestas"] == len(SYNTHETIC_ANSWER_DATASET) == 6
    assert summary["respuestas_sin_ninguna_cita"] == 1  # "sin_ninguna_cita"
    assert summary["respuestas_con_al_menos_una_cita"] == 5
    # Párrafos sin cita: "dos_parrafos_uno_sin_cita" (1) + "sin_ninguna_cita" (1)
    # + "tres_parrafos_cobertura_mixta" (1, el tercer párrafo) = 3.
    assert summary["parrafos_sin_cita"] == 3
    # Citas inexistentes: "cita_fuera_de_rango" ([doc5]) +
    # "tres_parrafos_cobertura_mixta" ([doc9]) = 2.
    assert summary["citas_inexistentes_totales"] == 2
    assert summary["respuestas_con_alguna_cita_inexistente"] == 2
    # Citas válidas: doc1 (parrafo_unico) + doc1 (dos_parrafos) +
    # doc1,doc1,doc2 (citas_repetidas) + doc1 (tres_parrafos) = 6.
    assert summary["citas_validas_totales"] == 6


def test_analyze_dataset_is_deterministic_across_runs() -> None:
    assert analyze_dataset() == analyze_dataset()
