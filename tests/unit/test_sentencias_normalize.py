from pathlib import Path

from langchain_core.documents import Document

from src.ingest.sentencias_normalize import (
    _canonical_title,
    extract_header_fields,
    sections_from_doc_chunks,
    sections_from_markdown,
)


# ---------------------------------------------------------------------------
# _canonical_title
# ---------------------------------------------------------------------------

def test_canonical_title_exact_match():
    assert _canonical_title("Considerandos") == "Considerandos"


def test_canonical_title_case_insensitive():
    assert _canonical_title("VISTOS") == "Vistos"
    assert _canonical_title("vistos") == "Vistos"


def test_canonical_title_substring_match():
    assert _canonical_title("I. Considerandos del caso") == "Considerandos"


def test_canonical_title_fallo():
    assert _canonical_title("FALLO") == "Fallo"


def test_canonical_title_unknown_returns_otro():
    assert _canonical_title("Introducción general") == "Otro"


def test_canonical_title_empty_returns_otro():
    assert _canonical_title("") == "Otro"


def test_canonical_title_costas():
    assert _canonical_title("Costas del proceso") == "Costas"


def test_canonical_title_fundamentos():
    assert _canonical_title("Fundamentos de derecho aplicables") == "Fundamentos de derecho"


# ---------------------------------------------------------------------------
# sections_from_markdown
# ---------------------------------------------------------------------------

_MARKDOWN_DOC = """\
Texto de caratula sin encabezado.

## Vistos

Vistos los autos en la causa indicada.

## Considerandos

I. El análisis de la prueba muestra que la parte actora tiene razón.
II. Se consideran los antecedentes.

## Fallo

Se hace lugar al recurso de apelación.
"""


def test_sections_from_markdown_count():
    doc = Document(page_content=_MARKDOWN_DOC)
    sections = sections_from_markdown(doc)
    assert len(sections) >= 3


def test_sections_from_markdown_titles():
    doc = Document(page_content=_MARKDOWN_DOC)
    sections = sections_from_markdown(doc)
    titles = [s.title for s in sections]
    assert "Vistos" in titles
    assert "Considerandos" in titles
    assert "Fallo" in titles


def test_sections_from_markdown_preamble_is_otro():
    doc = Document(page_content=_MARKDOWN_DOC)
    sections = sections_from_markdown(doc)
    assert sections[0].title == "Otro"
    assert "caratula" in sections[0].text.lower()


def test_sections_from_markdown_text_not_empty():
    doc = Document(page_content=_MARKDOWN_DOC)
    sections = sections_from_markdown(doc)
    for s in sections:
        assert s.text.strip()


def test_sections_from_markdown_no_headings():
    doc = Document(page_content="Texto sin encabezados para ninguna sección.")
    sections = sections_from_markdown(doc)
    assert len(sections) == 1
    assert sections[0].title == "Otro"


# ---------------------------------------------------------------------------
# sections_from_doc_chunks
# ---------------------------------------------------------------------------

def _make_chunk(text: str, headings: list[str]) -> Document:
    return Document(page_content=text, metadata={"headings": headings})


def test_sections_from_doc_chunks_groups_by_heading():
    docs = [
        _make_chunk("Vistos los autos.", ["Vistos"]),
        _make_chunk("Continuación de vistos.", ["Vistos"]),
        _make_chunk("I. El considerando principal.", ["Considerandos"]),
    ]
    sections = sections_from_doc_chunks(docs)
    titles = [s.title for s in sections]
    assert titles.count("Vistos") == 1
    assert titles.count("Considerandos") == 1


def test_sections_from_doc_chunks_merges_text():
    docs = [
        _make_chunk("Primera parte.", ["Vistos"]),
        _make_chunk("Segunda parte.", ["Vistos"]),
    ]
    sections = sections_from_doc_chunks(docs)
    assert len(sections) == 1
    assert "Primera parte." in sections[0].text
    assert "Segunda parte." in sections[0].text


def test_sections_from_doc_chunks_no_heading_is_otro():
    docs = [
        _make_chunk("Texto sin encabezado.", []),
    ]
    sections = sections_from_doc_chunks(docs)
    assert sections[0].title == "Otro"


def test_sections_from_doc_chunks_empty_input():
    assert sections_from_doc_chunks([]) == []


def test_sections_from_doc_chunks_skips_empty_content():
    docs = [
        _make_chunk("", ["Vistos"]),
        _make_chunk("Texto real.", ["Vistos"]),
    ]
    sections = sections_from_doc_chunks(docs)
    assert len(sections) == 1
    assert sections[0].text == "Texto real."


# ---------------------------------------------------------------------------
# extract_header_fields
# ---------------------------------------------------------------------------

def test_extract_header_fields_source_file():
    path = Path("data/bronze/exp_1234_2021.pdf")
    fields = extract_header_fields(path, "Texto del documento.")
    assert fields["source_file"] == "exp_1234_2021.pdf"


def test_extract_header_fields_date_spanish():
    text = "La sentencia fue dictada el 14 de septiembre de 2021 en esta ciudad."
    fields = extract_header_fields(Path("doc.pdf"), text)
    assert fields["judgement_date"] == "2021-09-14"


def test_extract_header_fields_date_numeric():
    text = "Fecha: 05/03/2020"
    fields = extract_header_fields(Path("doc.pdf"), text)
    assert fields["judgement_date"] == "2020-03-05"


def test_extract_header_fields_case_number():
    text = "Expediente No. 1234-2021-Of-Civil. Se pide resolver el recurso."
    fields = extract_header_fields(Path("doc.pdf"), text)
    assert "1234" in fields["case_number"]


def test_extract_header_fields_no_date_returns_sentinel():
    fields = extract_header_fields(Path("doc.pdf"), "Sin fechas en este texto.")
    assert fields["judgement_date"] == "1900-01-01"


def test_extract_header_fields_no_case_returns_desconocido():
    fields = extract_header_fields(Path("doc.pdf"), "Sin número de expediente aquí.")
    assert fields["case_number"] == "DESCONOCIDO"
