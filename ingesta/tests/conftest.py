# tests/conftest.py
import json
from pathlib import Path

import pytest
from langchain_core.documents import Document


@pytest.fixture
def sample_document() -> Document:
    return Document(
        page_content="Sentencia de prueba. Fundamentos juridicos para validacion.",
        metadata={"source": "sentencia_camara_federal_2024.pdf"},
    )


@pytest.fixture
def sample_chunks() -> list[Document]:
    return [
        Document(
            page_content=f"Chunk {i}. Extracto juridico de prueba.",
            metadata={
                "source": "fallo_laboral_2023.pdf",
                "chunk_id": f"fallo_laboral_2023_chunk_{i}",
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
