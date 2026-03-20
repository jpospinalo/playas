import pytest
from pydantic import ValidationError

from src.ingest.sentencias_schema import Section, Sentencia


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_sentencia(**overrides) -> dict:
    base = {
        "source_file": "exp_1234_2021.pdf",
        "case_number": "EXP 1234/2021",
        "judgement_date": "2021-09-14",
        "sections": [
            {"title": "Vistos", "text": "Se analizan los autos."},
            {"title": "Fallo", "text": "Se hace lugar al recurso."},
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Section tests
# ---------------------------------------------------------------------------

def test_section_valid():
    s = Section(title="Vistos", text="Texto de la sección.")
    assert s.title == "Vistos"
    assert s.text == "Texto de la sección."


def test_section_empty_title_raises():
    with pytest.raises(ValidationError):
        Section(title="", text="Contenido válido.")


def test_section_blank_title_raises():
    with pytest.raises(ValidationError):
        Section(title="   ", text="Contenido válido.")


def test_section_empty_text_raises():
    with pytest.raises(ValidationError):
        Section(title="Vistos", text="")


def test_section_blank_text_raises():
    with pytest.raises(ValidationError):
        Section(title="Vistos", text="   ")


def test_section_extra_field_raises():
    with pytest.raises(ValidationError):
        Section(title="Vistos", text="Contenido.", extra_field="no permitido")


# ---------------------------------------------------------------------------
# Sentencia tests
# ---------------------------------------------------------------------------

def test_sentencia_valid():
    s = Sentencia(**_valid_sentencia())
    assert s.source_file == "exp_1234_2021.pdf"
    assert s.case_number == "EXP 1234/2021"
    assert s.judgement_date == "2021-09-14"
    assert len(s.sections) == 2


def test_sentencia_empty_source_file_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(source_file=""))


def test_sentencia_blank_source_file_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(source_file="   "))


def test_sentencia_empty_case_number_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(case_number=""))


def test_sentencia_bad_date_format_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(judgement_date="14-09-2021"))


def test_sentencia_date_without_dashes_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(judgement_date="20210914"))


def test_sentencia_empty_sections_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(sections=[]))


def test_sentencia_extra_field_raises():
    with pytest.raises(ValidationError):
        Sentencia(**_valid_sentencia(extra_field="no permitido"))


def test_sentencia_model_dump_matches_schema():
    s = Sentencia(**_valid_sentencia())
    d = s.model_dump()
    assert set(d.keys()) == {"source_file", "case_number", "judgement_date", "sections"}
    for section in d["sections"]:
        assert set(section.keys()) == {"title", "text"}
