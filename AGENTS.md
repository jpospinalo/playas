## Project Overview

**RAG Playas** — A RAG system specialized in Colombian beach/coastal jurisprudence (playas, dominio público marítimo-terrestre). It processes PDF court rulings (from Consejo de Estado), transforms them into searchable semantic chunks, and exposes a REST API consumed by a Next.js frontend.

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
├── config.py                # Env vars: Gemini, Docling
├── pdf_to_md/              # PDF → Markdown via Docling (OCR, tables, images)
├── loaders.py              # bronze → silver (JSONL per file)
├── normalize.py            # Metadata cleanup
├── sections.py             # Split by markdown heading hierarchy
└── splitter_and_enrich.py  # Chunk (1000 tokens, 200 overlap) + Gemini enrichment
```

### Data Flow

```
raw PDFs
  └─→ pdf_to_md (Docling)         → data/bronze/ (clean Markdown + images)
       └─→ loaders (normalize)   → data/silver/ (JSONL, sectioned)
            └─→ splitter_and_enrich (Gemini) → data/gold/ (enriched chunks)
                 └─→ vectorstore (Ollama embeddings) → ChromaDB
```

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

Colombian court rulings follow a 4-section structure documented in `docs/DOCUMENT_SECTIONS.md`:

1. **Contexto del caso** — case background
2. **Desarrollo procesal** — procedural history
3. **Argumentación jurídica** — legal reasoning
4. **Decisión** — ruling/decision

---

## Key Conventions

- **Env vars** — all in `.env` at root. Two independent `config.py` files read only what they need.
- **Workspace managers** — `uv` (Python, root), `bun` (Node, root + frontend)
- **Integration tests** — marked `@pytest.mark.integration`, skipped in `make test`
- **Tests location** — `tests/unit/` and `tests/integration/` at project root
- **Next.js** — uses Next.js 16.2.3 (React 19). Breaking changes may differ from prior versions. See `frontend/AGENTS.md`.
