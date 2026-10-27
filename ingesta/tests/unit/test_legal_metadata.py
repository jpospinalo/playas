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
    rows = [
        {"doc_id": "x", "campo": "magistrado_ponente", "valor": "PÉREZ", "evidencia": "JUAN PÉREZ"}
    ]
    assert (
        apply_overrides(metadata, rows, "x", TEXT)["campos"]["magistrado_ponente"]["valor"]
        == "PÉREZ"
    )
    rows[0]["evidencia"] = "inventada"
    assert (
        apply_overrides(metadata, rows, "x", TEXT)["campos"]["magistrado_ponente"]["razon"]
        == "override_sin_evidencia"
    )
