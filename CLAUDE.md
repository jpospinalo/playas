# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ATLAS** (Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre playas en Colombia) — An agentic RAG system specialized in Colombian beach/coastal legal documents (playas, dominio público marítimo-terrestre). It processes two document types: court rulings (`jurisprudencia`) from the Consejo de Estado, and regulations (`normativa`) such as decrees. Each type follows a separate sectioning strategy; all share the same chunking, enrichment, and retrieval pipeline.

**Spanish-language codebase** — all comments, prompts, docs, and API responses are in Spanish.

---

## Build/Test Commands

```bash
# Python (uv workspace)
make install        # uv sync --group dev
make lint           # ruff check rag/ ingest/ tests/ evaluation/
make format         # ruff format rag/ ingest/ tests/ evaluation/
make typecheck      # mypy rag/ ingest/  (note: CI-disabled due to lingering errors)
make test           # pytest tests/unit/ -v
make test-cov       # pytest + HTML coverage report
make test-integration  # pytest -m integration -v  (requires live ChromaDB + Ollama)

# Pipeline stages (can run independently)
uv run python -m ingest.pdf_to_md           # PDF → clean Markdown (data/bronze/)
uv run python -m ingest.loaders            # bronze → silver (data/silver/)
uv run python -m ingest.splitter_and_enrich # silver → gold enriched chunks (data/gold/)
uv run python -m rag.core.vectorstore       # gold → ChromaDB index
make pipeline   # run_pipeline.sh (all 4 stages)

# API
make app         # uvicorn rag.api.main:app --reload --port 8080

# Frontend
make frontend    # bun run dev (Next.js on port 3000)
make -C frontend build  # production build
```

**Run a single test:**
```bash
uv run pytest tests/unit/path/to/test_file.py::test_name -v
```

---

## Architecture

### Two Independent Python Packages

`rag/` and `ingest/` are **fully independent packages**. Each has its own `pyproject.toml` and `config.py`. They share no code — they only share the `data/` staging directory and external services (ChromaDB, Ollama, Gemini).

```
rag/                          # RAG serving (API + core)
├── config.py                # Env vars: Chroma, Ollama, LLM, query enrichment
├── core/
│   ├── embeddings.py        # Ollama embedding client
│   ├── vectorstore.py       # ChromaDB collection build/update
│   ├── retriever.py         # BM25 + vector + HybridEnsembleRetriever (RRF c=160)
│   ├── generator.py         # RAG chain: retriever → LLM → answer
│   ├── query_enricher.py   # LLM query rewriting (legal terminology, sub-questions)
│   └── llm_factory.py      # Provider factory: OpenRouter → Gemini → error
└── api/
    ├── main.py              # FastAPI app (/api/health, /api/query, /api/query/stream)
    └── schemas.py           # Pydantic request/response models

ingest/                       # Ingestion pipeline
├── config.py                # Env vars + DOC_TYPES + layer_prefix(layer, doc_type)
├── pdf_to_md/              # PDF → Markdown via Docling (OCR, tables, images)
├── loaders.py              # bronze/<type>/ → silver/<type>/ (dispatches by doc_type)
├── normalize.py            # Metadata cleanup
├── sections.py             # split_by_sections() — 4-section jurisprudencia strategy
├── sections_normativa.py   # split_by_articles() — per-article normativa strategy
├── metadata_csv.py         # Loads raw/<type>/metadata.csv (optional per doc_type)
└── splitter_and_enrich.py  # Chunk (1000 tokens, 200 overlap) + LLM enrichment
```

### Data Flow

Each pipeline layer is split by `doc_type` subfolder (`jurisprudencia` / `normativa`):

```
raw PDFs / MDs
  └─→ pdf_to_md (Docling)              → data/bronze/<type>/ (clean Markdown)
       └─→ loaders (normalize + CSV)  → data/silver/<type>/ (JSONL, sectioned)
            │  jurisprudencia → split_by_sections()  (4 canonical sections)
            │  normativa      → split_by_articles()  (1 unit per Artículo N)
            └─→ splitter_and_enrich   → data/gold/<type>/ (enriched chunks)
                 └─→ vectorstore      → ChromaDB  (doc_type in each chunk's metadata)
```

The `doc_type` is fixed once at load time from the source folder and propagates through all layers. The ChromaDB collection is shared; filtering by `doc_type` enables serving both types from the same retriever.

### RAG Query Flow

1. User question → **Query Enricher** (LLM rewrite with legal terminology + sub-questions)
2. Enriched query → **Hybrid Retriever** (BM25 30% + Vector 70%, RRF fusion)
3. Top-k docs → **Generator LLM** (original question + context → answer)

### LLM Provider Fallback

`llm_factory.py` tries providers in order: **OpenRouter** → **Gemini** → error. Structured output only works with Gemini via Google API (no tool calling for Gemma models).

### External Infrastructure (EC2)

- **ChromaDB** — remote EC2, port 8000 (collection: `rag_playas_5_docs`)
- **Ollama** — remote EC2, port 11434 (embedding model: `embeddinggemma:latest`)
- Optional reranker: Ollama `llama3.2:3b`

### Document Structure

**Jurisprudencia** (Colombian court rulings) follow a 4-section structure documented in `docs/DOCUMENT_SECTIONS.md`:
1. **Contexto del caso** — case background
2. **Desarrollo procesal** — procedural history
3. **Argumentación jurídica** — legal reasoning
4. **Decisión** — ruling/decision

**Normativa** (decrees, regulations) is segmented by `Artículo N` (regex over plain text), with `TÍTULO`/`CAPÍTULO` hierarchy preserved as metadata. A `"Preámbulo"` unit captures text before the first article.

---

## Key Conventions

- **Env vars** — all in `.env` at root. Two independent `config.py` files read only what they need.
- **Workspace managers** — `uv` (Python, root), `bun` (Node, root + frontend)
- **Integration tests** — marked `@pytest.mark.integration`, skipped in `make test`
- **Tests location** — `tests/unit/` and `tests/integration/` at project root
- **Next.js** — uses Next.js 16.2.3 (React 19). Breaking changes may differ from prior versions. See `frontend/AGENTS.md`.
