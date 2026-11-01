"""Contratos offline entre seccionado y chunking, sin OCR, S3, RAG ni LLM."""

import pytest
from langchain_core.documents import Document

from ingest.loaders import _section_documents
from ingest.splitter_and_enrich import _build_splitter, _chunk_section

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    ("doc_type", "text"),
    [
        (
            "jurisprudencia",
            "## Antecedentes\nHechos de prueba.\n"
            "## Consideraciones\nAnálisis de prueba.\n## Falla\nDecisión de prueba.",
        ),
        (
            "normativa",
            "DECRETA\nArtículo 1. Objeto.\nContenido de prueba.\n"
            "Artículo 2. Definiciones.\nDefinición de prueba.",
        ),
    ],
)
def test_sections_feed_chunks_with_stable_ids_and_preserved_metadata(doc_type, text):
    original = Document(
        page_content=text,
        metadata={"source": "documento.md", "title": "Documento", "doc_type": doc_type},
    )
    sections = _section_documents(original, doc_type)
    splitter = _build_splitter(chunk_size=50, chunk_overlap=10)
    chunks = [
        chunk
        for section in sections
        if section.page_content.strip()
        for chunk in _chunk_section(section, splitter)
    ]

    assert chunks
    ids = [chunk.metadata["chunk_id"] for chunk in chunks]
    assert len(ids) == len(set(ids))
    for chunk in chunks:
        assert chunk.metadata["source"] == "documento.md"
        assert chunk.metadata["title"] == "Documento"
        assert chunk.metadata["doc_type"] == doc_type
        assert "section_index" in chunk.metadata
        assert chunk.metadata["total_chunks_in_section"] > chunk.metadata["chunk_index"]

    repeated = [
        chunk.metadata["chunk_id"]
        for section in _section_documents(original, doc_type)
        if section.page_content.strip()
        for chunk in _chunk_section(section, splitter)
    ]
    assert repeated == ids
    assert original.metadata == {
        "source": "documento.md",
        "title": "Documento",
        "doc_type": doc_type,
    }
