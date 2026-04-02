# tests/unit/test_splitter.py
from langchain_core.documents import Document

from src.ingest.splitter import chunk_documents


def test_chunk_documents_sets_required_metadata_and_non_empty_content(sample_document):
    chunks = chunk_documents([sample_document])

    assert chunks
    assert all("chunk_id" in c.metadata for c in chunks)
    assert all("chunk_index" in c.metadata for c in chunks)
    assert all(c.metadata["source"] == sample_document.metadata["source"] for c in chunks)
    assert all(c.page_content.strip() for c in chunks)


def test_chunk_documents_indexes_chunks_sequentially():
    text = " ".join([f"Parrafo {i}" for i in range(80)])
    doc = Document(page_content=text, metadata={"source": "sentencia_larga.pdf"})
    chunks = chunk_documents([doc], chunk_size=120, chunk_overlap=10)

    assert len(chunks) > 1
    assert [c.metadata["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert len({c.metadata["chunk_id"] for c in chunks}) == len(chunks)
