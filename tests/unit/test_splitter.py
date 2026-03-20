# tests/unit/test_splitter.py
from langchain_core.documents import Document
from src.ingest.splitter import chunk_documents


def test_chunks_have_chunk_id(sample_document):
    chunks = chunk_documents([sample_document])
    assert all("chunk_id" in c.metadata for c in chunks)


def test_chunks_have_chunk_index(sample_document):
    chunks = chunk_documents([sample_document])
    assert all("chunk_index" in c.metadata for c in chunks)


def test_chunks_preserve_source(sample_document):
    chunks = chunk_documents([sample_document])
    assert all(c.metadata["source"] == sample_document.metadata["source"] for c in chunks)


def test_chunk_content_not_empty(sample_document):
    chunks = chunk_documents([sample_document])
    assert all(len(c.page_content) > 0 for c in chunks)
