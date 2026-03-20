# tests/unit/test_normalize.py
from langchain_core.documents import Document
from src.ingest.normalize import normalize_documents, normalize_metadata, normalize_text


def test_normalize_text_removes_blank_lines():
    result = normalize_text("Línea 1\n\n\nLínea 2")
    assert "Línea 1" in result
    assert "Línea 2" in result
    assert "\n\n" not in result


def test_normalize_text_removes_noise_phrases():
    text = "Contenido útil\nVisitado en elejandria.com\nMás contenido"
    result = normalize_text(text)
    assert "elejandria" not in result.lower()


def test_normalize_metadata_extracts_title_and_author():
    meta = {"source": "El_cuervo-Poe_Edgar_Allan.pdf", "extra": "ignored"}
    result = normalize_metadata(meta)
    assert result["title"] == "El cuervo"
    assert result["author"] == "Poe Edgar Allan"
    assert "extra" not in result


def test_normalize_documents_preserves_content(sample_document):
    result = normalize_documents([sample_document])
    assert len(result) == 1
    assert result[0].page_content == sample_document.page_content


def test_normalize_documents_returns_documents(sample_document):
    result = normalize_documents([sample_document])
    assert all(isinstance(d, Document) for d in result)
