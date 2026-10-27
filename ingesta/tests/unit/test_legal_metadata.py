import pytest
from langchain_core.documents import Document

from ingest.legal_metadata import apply_overrides, extract_legal_metadata
from ingest.normalize import normalize_documents

TEXT = """CONSEJO DE ESTADO
SECCIÓN PRIMERA
Magistrado ponente: JUAN PÉREZ
Radicación: 47001-23-33-000-2020-00123-01
Santa Marta, 12 de marzo de 2024
ACCIÓN POPULAR
Las playas son bienes de uso público. Decreto 2324 de 1984.
"""


def test_extracts_identity_and_preserves_references_before_cleaning():
    result = normalize_documents([Document(page_content=TEXT, metadata={"source": "fallo.md"})])[0]
    fields = result.metadata["legal_metadata"]["campos"]
    assert fields["magistrado_ponente"]["valor"] == "JUAN PÉREZ"
    assert fields["radicado"]["valor"] == "47001-23-33-000-2020-00123-01"
    assert fields["fecha_iso"]["valor"] == "2024-03-12"
    assert "Decreto 2324 de 1984" in fields["normas_citadas"]["valor"]
    for field in fields.values():
        quotes = (
            field["evidencia"] if isinstance(field["evidencia"], list) else [field["evidencia"]]
        )
        assert all(quote in TEXT for quote in quotes if quote)


def test_manual_wins_and_invalid_evidence_is_explicit():
    metadata = extract_legal_metadata(TEXT)
    metadata["conflictos"] = [{"campo": "magistrado_ponente", "valores": ["OTRO", "PÉREZ"]}]
    rows = [
        {"doc_id": "x", "campo": "magistrado_ponente", "valor": "PÉREZ", "evidencia": "JUAN PÉREZ"}
    ]
    assert (
        apply_overrides(metadata, rows, "x", TEXT)["campos"]["magistrado_ponente"]["valor"]
        == "PÉREZ"
    )
    assert not metadata["conflictos"] and metadata["conflictos_resueltos_manual"]
    rows[0]["evidencia"] = "inventada"
    assert (
        apply_overrides(metadata, rows, "x", TEXT)["campos"]["magistrado_ponente"]["razon"]
        == "override_sin_evidencia"
    )


def test_manual_csv_values_are_nfc_without_nul():
    metadata = extract_legal_metadata(TEXT)
    rows = [
        {
            "doc_id": "x",
            "campo": "magistrado_ponente",
            "valor": "JUA\x00N PE\u0301REZ",
            "evidencia": "JUAN PÉREZ",
        }
    ]
    result = apply_overrides(metadata, rows, "x", TEXT)
    assert result["campos"]["magistrado_ponente"]["valor"] == "JUAN PÉREZ"


@pytest.mark.parametrize(
    "text",
    [
        "La competencia de la Dirección.",
        "La limpieza de casco a flote.",
        "Que cumplieran con sus funciones de custodia.",
    ],
)
def test_ponente_abbreviation_does_not_match_inside_words(text):
    result = extract_legal_metadata(text)
    assert result["campos"]["magistrado_ponente"]["valor"] is None


@pytest.mark.parametrize(
    "label", ["M.P.", "M. P.", "MP", "Consejero ponente", "Magistrada ponente"]
)
def test_ponente_labels_with_word_boundaries(label):
    result = extract_legal_metadata(label + ": ANA PÉREZ\nCONSIDERACIONES")
    assert result["campos"]["magistrado_ponente"]["valor"] == "ANA PÉREZ"


@pytest.mark.parametrize("value", [None, "  \t "])
def test_blank_manual_csv_value_clears_field(value):
    metadata = extract_legal_metadata(TEXT)
    rows = [{"doc_id": "x", "campo": "magistrado_ponente", "valor": value, "evidencia": None}]
    result = apply_overrides(metadata, rows, "x", TEXT)["campos"]["magistrado_ponente"]
    assert result["valor"] is None and result["razon"] == "correccion_manual"
