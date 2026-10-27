"""Fixtures de ciclo de vida, OCR y ejecución sin proveedores/API con cuota."""

import json
import shutil
import socket

import pytest

from ingest.offline.chunks import make_chunks, token_estimate
from ingest.offline.extract import clean_pages, read_document
from ingest.offline.pipeline import Pipeline
from ingest.offline.publish import ChromaPublisher

TEXT = (
    "CONSEJO DE ESTADO\nMagistrado ponente: JUAN PEREZ\nRadicado: 47001-23-33-000-2020-00123-01\nSanta Marta, 12 de marzo de 2024\nCONSIDERACIONES\n"
    + "Las playas son bienes de uso publico y su acceso debe protegerse. " * 30
)


class FakeEmbeddings:
    def __init__(self):
        self.cache = {}
        self.new_embeddings = 0

    def embed(self, texts):
        for text in texts:
            if text not in self.cache:
                self.cache[text] = [0.1] * 768
                self.new_embeddings += 1
        return [self.cache[text] for text in texts]

    def manifest(self):
        return {"new_embeddings": self.new_embeddings, "llm_api_calls": 0}


class FakePublisher:
    def __init__(self):
        self.docs = {}

    def upsert_document(self, identity, records, vectors):
        assert len(records) == len(vectors)
        self.docs[identity] = records

    def delete_document(self, identity):
        self.docs.pop(identity, None)


@pytest.fixture
def system(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    embeddings, publisher = FakeEmbeddings(), FakePublisher()
    pipeline = Pipeline(root, tmp_path / "state", tmp_path / "cache", embeddings, publisher)
    yield root, pipeline, embeddings, publisher
    pipeline.close()


def test_lifecycle_zero_reembeddings_on_repeat_and_rename(system):
    root, pipeline, embeddings, publisher = system
    path = root / "fallo.md"
    path.write_text(TEXT)
    first = pipeline.run()
    assert first["new_embeddings"] > 0
    assert pipeline.run()["new_embeddings"] == 0
    path.rename(root / "renombrado.md")
    assert pipeline.run()["new_embeddings"] == 0
    (root / "nuevo.md").write_text(TEXT + " Documento adicional y diferente.")
    added = pipeline.run(add=root / "nuevo.md")
    assert added["processed"] == 1 and added["new_embeddings"] > 0
    (root / "renombrado.md").write_text(TEXT + " Modificado.")
    modified = pipeline.run()
    assert modified["deleted"] == 1
    assert len(publisher.docs) == 2
    (root / "nuevo.md").unlink()
    deleted = pipeline.run()
    assert deleted["deleted"] == 1 and deleted["new_embeddings"] == 0
    assert len(publisher.docs) == 1


def test_homonyms_and_exact_duplicates_are_retained(system):
    root, pipeline, _, publisher = system
    for folder in ["a", "b", "c"]:
        (root / folder).mkdir()
    (root / "a/fallo.md").write_text(TEXT)
    (root / "b/fallo.md").write_text(TEXT + " Otro caso.")
    (root / "c/copia.md").write_text(TEXT)
    assert pipeline.run()["documents"] == 2
    assert len(publisher.docs) == 2
    assert len(list(root.rglob("*.md"))) == 3
    report = json.loads((pipeline.state / "duplicates.json").read_text())
    assert len(report["exact"][0]) == 2


def test_pipeline_runs_with_empty_keys_and_all_sockets_blocked(system, monkeypatch):
    root, pipeline, _, _ = system
    for name in ["GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY"]:
        monkeypatch.setenv(name, "")

    def forbidden(*args, **kwargs):
        raise AssertionError("No puede acceder a APIs ni LLM")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    (root / "fallo.md").write_text(TEXT)
    result = pipeline.run()
    assert result["llm_api_calls"] == 0
    assert not result["errors"] and result["new_embeddings"] > 0


def test_protected_baseline_refused_before_connection():
    with pytest.raises(ValueError, match="protegida"):
        ChromaPublisher("atlas_v1", "x")


def test_changed_pipeline_version_requires_new_state(system):
    root, pipeline, embeddings, publisher = system
    with pytest.raises(ValueError, match="versión"):
        Pipeline(root, pipeline.state, pipeline.cache, embeddings, publisher, chunker="structure")


def test_enforce_is_opt_in_and_quarantines(tmp_path):
    root = tmp_path / "raw"
    root.mkdir()
    (root / "corto.md").write_text("Texto corto sin identidad")
    embeddings, publisher = FakeEmbeddings(), FakePublisher()
    pipeline = Pipeline(
        root, tmp_path / "state", tmp_path / "cache", embeddings, publisher, enforce=True
    )
    result = pipeline.run()
    assert result["new_embeddings"] == 0 and publisher.docs == {}
    assert result["documents_detail"][0]["quarantined"]
    pipeline.close()


def test_offsets_furniture_and_structure_budget():
    pages = ["CABECERA REPETIDA\n" + TEXT + f"\nPágina {i}\n" for i in range(3)]
    cleaned = clean_pages(pages)
    assert "CABECERA REPETIDA" not in cleaned["text"]
    from ingest.legal_metadata import extract_legal_metadata

    metadata = extract_legal_metadata("\n".join(pages))
    chunks = make_chunks("x", cleaned, metadata, "fallo.pdf", "jurisprudencia", "structure", 256)
    assert chunks
    for chunk in chunks:
        assert token_estimate(chunk["document"]) <= 256
        start, end = chunk["metadata"]["clean_start"], chunk["metadata"]["clean_end"]
        assert cleaned["text"][start:end] == chunk["raw_text"]
        assert chunk["metadata"]["source_start"] >= 0


def test_digital_and_scanned_pdf_with_cached_local_ocr(tmp_path):
    import fitz

    assert shutil.which("tesseract"), "Instalar Tesseract + spa para el caso escaneado"
    digital = fitz.open()
    page = digital.new_page()
    page.insert_text(
        (30, 50),
        "CONSEJO DE ESTADO\nMagistrado ponente: JUAN PEREZ\nLas playas son bienes de uso publico.\nEl acceso de las personas a las playas debe protegerse.",
        fontsize=14,
    )
    path = tmp_path / "digital.pdf"
    digital.save(path)
    image = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
    scanned = fitz.open()
    scan_page = scanned.new_page()
    scan_page.insert_image(scan_page.rect, stream=image)
    scan_path = tmp_path / "escaneado.pdf"
    scanned.save(scan_path)
    scanned.close()
    digital.close()
    direct = read_document(path, tmp_path / "cache")
    assert direct["ocr_pages"] == []
    ocr = read_document(scan_path, tmp_path / "cache")
    assert ocr["ocr_pages"] == [1] and "playas" in ocr["original"].casefold()
    assert read_document(scan_path, tmp_path / "cache")["new_ocr_pages"] == 0
