# tests/conftest.py
import json
from pathlib import Path

import pytest
from langchain_core.documents import Document


@pytest.fixture
def sample_document() -> Document:
    return Document(
        page_content="El corazón delator. Texto de prueba para testing.",
        metadata={"source": "El_corazon_delator-Poe_Edgar_Allan.pdf"},
    )


@pytest.fixture
def sample_chunks() -> list[Document]:
    return [
        Document(
            page_content=f"Chunk {i}. Contenido de prueba.",
            metadata={
                "source": "El_cuervo-Poe_Edgar_Allan.pdf",
                "chunk_id": f"El_cuervo-Poe_Edgar_Allan_chunk_{i}",
                "chunk_index": i,
            },
        )
        for i in range(3)
    ]


@pytest.fixture
def tmp_gold_dir(tmp_path: Path) -> Path:
    """Temporary gold directory with sample JSONL files."""
    gold = tmp_path / "gold"
    gold.mkdir()
    record = {
        "page_content": "Texto de prueba.",
        "metadata": {
            "source": "test.pdf",
            "chunk_id": "test_chunk_0",
            "summary": "Resumen de prueba.",
            "keywords": ["prueba", "test"],
        },
    }
    (gold / "test.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return gold
