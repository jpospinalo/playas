"""IDs y metadata de artículos sin ejecutar enriquecimiento, S3 ni LLM."""

from decimal import Decimal

import pytest
from langchain_core.documents import Document

from ingest.splitter_and_enrich import _build_splitter, _chunk_section, _sanitize_articulo

_ABSENT = object()


@pytest.mark.parametrize(
    ("article", "normalized"),
    [
        ("12", "12"),
        (12, "12"),
        (5.2, "5-2"),
        (Decimal("5.2"), "5-2"),
        ("5.2-A", "5-2-A"),
        (" 5 / 2 bis ", "5-2-bis"),
        (0, "0"),
        (None, None),
        ("", None),
        (_ABSENT, None),
    ],
)
@pytest.mark.parametrize("doc_type", ["normativa", "jurisprudencia"])
def test_article_values_preserve_ids_content_metadata_and_absence(article, normalized, doc_type):
    metadata = {
        "source": "norma_prueba.md",
        "title": "Norma de prueba",
        "doc_type": doc_type,
        "section_index": 3,
    }
    if article is not _ABSENT:
        metadata["articulo"] = article
    original_metadata = dict(metadata)
    document = Document(page_content="Contenido de prueba sobre playas.", metadata=metadata)
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)

    chunks = _chunk_section(document, splitter)

    prefix = "norma_prueba_s3"
    if doc_type == "normativa" and normalized is not None:
        assert _sanitize_articulo(article) == normalized
        prefix += f"_art{normalized}"
    assert len(chunks) == 1
    assert chunks[0].page_content == document.page_content
    assert chunks[0].metadata == {
        **original_metadata,
        "chunk_index": 0,
        "chunk_id": f"{prefix}_c0",
        "total_chunks_in_section": 1,
    }
    assert document.metadata == original_metadata
