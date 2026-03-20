"""Bronze → Silver pipeline for judicial PDFs (sentencias).

Usage:
    uv run python -m src.ingest.sentencias_loader

Reads all PDFs from data/bronze/, converts each to the Silver JSONL contract
format, and writes one .jsonl file per document to data/silver/.
"""

from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import List

from langchain_core.documents import Document
from langchain_docling import DoclingLoader
from langchain_docling.loader import ExportType

from src.config import BRONZE_DIR, SILVER_DIR
from .sentencias_normalize import (
    extract_header_fields,
    sections_from_doc_chunks,
    sections_from_markdown,
)
from .sentencias_schema import Section, Sentencia

warnings.filterwarnings("ignore", category=FutureWarning)
logging.getLogger("docling").setLevel(logging.WARNING)
logging.getLogger("rapidocr").setLevel(logging.WARNING)
logging.getLogger("onnxruntime").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DOC_CHUNKS validity check
# ---------------------------------------------------------------------------

def _chunks_are_valid(docs: List[Document]) -> bool:
    """Return True when DOC_CHUNKS produced at least one non-empty chunk."""
    return any(d.page_content.strip() for d in docs)


# ---------------------------------------------------------------------------
# Core loader
# ---------------------------------------------------------------------------

def load_sentencia(pdf_path: Path) -> Sentencia:
    """Load a single PDF and return a validated Sentencia.

    Strategy:
      1. Try DOC_CHUNKS (primary).
      2. If invalid or empty, fall back to MARKDOWN.
    Raises ValidationError from Pydantic if the result doesn't pass the contract.
    """
    # --- Primary: DOC_CHUNKS ---
    try:
        loader = DoclingLoader(file_path=str(pdf_path), export_type=ExportType.DOC_CHUNKS)
        chunks = loader.load()
    except Exception as exc:
        logger.warning("DOC_CHUNKS failed for %s: %s — falling back to MARKDOWN", pdf_path.name, exc)
        chunks = []

    if _chunks_are_valid(chunks):
        logger.info("Using DOC_CHUNKS for %s (%d chunks)", pdf_path.name, len(chunks))
        sections = sections_from_doc_chunks(chunks)
        full_text = " ".join(d.page_content for d in chunks)
    else:
        # --- Fallback: MARKDOWN ---
        logger.info("DOC_CHUNKS empty/invalid for %s — using MARKDOWN fallback", pdf_path.name)
        loader = DoclingLoader(file_path=str(pdf_path), export_type=ExportType.MARKDOWN)
        md_docs = loader.load()
        if not md_docs:
            raise RuntimeError(f"No content extracted from {pdf_path.name}")
        doc = md_docs[0]
        sections = sections_from_markdown(doc)
        full_text = doc.page_content

    if not sections:
        sections = [Section(title="Otro", text=full_text.strip() or pdf_path.stem)]

    header = extract_header_fields(pdf_path, full_text)

    return Sentencia(
        source_file=header["source_file"],
        case_number=header["case_number"],
        judgement_date=header["judgement_date"],
        sections=sections,
    )


# ---------------------------------------------------------------------------
# JSONL writer
# ---------------------------------------------------------------------------

def save_sentencia_jsonl(sentencia: Sentencia, silver_dir: Path) -> Path:
    """Write one .jsonl file (single line) for the given Sentencia.

    The file is named after the PDF stem, e.g.:
        data/silver/AP Gerardo ... .jsonl
    """
    silver_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(sentencia.source_file).stem
    out_path = silver_dir / f"{stem}.jsonl"

    record = sentencia.model_dump()
    with out_path.open("w", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return out_path


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run(
    bronze_dir: Path = BRONZE_DIR,
    silver_dir: Path = SILVER_DIR,
    *,
    force: bool = False,
) -> List[Path]:
    """Process all PDFs in bronze_dir and write Silver JSONL to silver_dir.

    Idempotent by default: skips PDFs whose .jsonl already exists unless
    force=True.

    Returns the list of written .jsonl paths.
    """
    pdf_files = sorted(bronze_dir.glob("*.pdf"))
    if not pdf_files:
        logger.warning("No PDFs found in %s", bronze_dir)
        return []

    written: List[Path] = []
    for pdf_path in pdf_files:
        out_path = silver_dir / f"{pdf_path.stem}.jsonl"
        if out_path.exists() and not force:
            logger.info("Skipping %s (already in silver)", pdf_path.name)
            continue

        logger.info("Processing %s …", pdf_path.name)
        try:
            sentencia = load_sentencia(pdf_path)
            out = save_sentencia_jsonl(sentencia, silver_dir)
            written.append(out)
            logger.info("Saved → %s", out)
        except Exception as exc:
            logger.error("Failed to process %s: %s", pdf_path.name, exc)

    return written


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    paths = run()
    if paths:
        print(f"Wrote {len(paths)} silver file(s):")
        for p in paths:
            print(f"  {p}")
    else:
        print("Nothing new to process.")


if __name__ == "__main__":
    main()
