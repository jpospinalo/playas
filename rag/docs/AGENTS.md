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
make pipeline   # run_pipeline.sh (all 4 stages + starts API)

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

`rag/` and `ingest/` are **fully independent packages**. Each has its own `pyproject.toml` and `config.py`. They share no code — they only share the `data/` staging directory and external services (ChromaDB, Ollama, LLM providers).

```
rag/                          # RAG serving (API + agent)
├── config.py                # Env vars: Chroma, Ollama, LLM, query enrichment
├── s3_client.py             # S3 read-only helpers (list, read)
├── core/
│   ├── agent.py             # LangGraph: grafo único determinista (no ReAct/tool-calling)
│   ├── tools.py             # build_context_block + sanitize_replacement_chars (helpers de retrieve_forced)
│   ├── prompts.py           # System/human prompts for agent + enricher
│   ├── embeddings.py        # Ollama embedding client (ChromaDB + LangChain)
│   ├── vectorstore.py       # ChromaDB collection build/update from gold
│   ├── retriever.py         # BM25 + vector + HybridEnsembleRetriever (RRF c=160)
│   ├── query_enricher.py   # LLM query rewriting (legal terminology, sub-questions)
│   └── llm_factory.py      # Provider factory: OpenAI → OpenRouter → Gemini → error
└── api/
    ├── main.py              # FastAPI app (health, query, query/stream)
    ├── schemas.py           # Pydantic request/response models
    ├── database.py          # SQLAlchemy async session/engine (SQLite/Postgres via DATABASE_URL)
    ├── models.py            # SQLAlchemy models: User, Conversation, Message, Feedback, ...
    ├── auth.py              # JWT auth dependencies (get_current_user, require_admin)
    ├── passwords.py         # Password hashing/verification
    ├── rate_limit.py        # Reversible sliding-window rate limiters (query, title, login)
    └── routes/
        ├── auth.py          # POST /api/auth/login, /register; GET /api/auth/me
        ├── conversations.py # CRUD conversaciones + POST /generate-title
        ├── feedback.py      # POST /api/feedback, POST /api/feedback/message
        └── admin.py         # GET/POST /api/admin/*

ingest/                       # Ingestion pipeline
├── config.py                # Env vars + DOC_TYPES + layer_prefix(layer, doc_type)
├── s3_client.py             # Full S3 client (read/write/copy/delete)
├── llm_factory.py           # Provider factory (mirror of rag/, uses enricher models)
├── utils.py                 # JSONL I/O helpers
├── loaders.py              # bronze/<type>/ → silver/<type>/ (dispatches by doc_type)
├── normalize.py            # Metadata cleanup
├── sections.py             # split_by_sections() — 4-section jurisprudencia strategy
├── sections_normativa.py   # split_by_articles() — per-article normativa strategy
├── metadata_csv.py         # Loads raw/<type>/metadata.csv (optional per doc_type)
├── splitter_and_enrich.py  # Chunk (1000 tokens, 200 overlap) + LLM enrichment
└── pdf_to_md/              # PDF → Markdown via Docling (OCR, tables, images)
    ├── pipeline.py         # Main entry: convert_pdfs_to_markdown()
    ├── config.py           # Tunable constants (image, OCR, profiling thresholds)
    ├── models.py           # LegalDocumentProfile, LegalBlock, DocumentQualityReport
    ├── profiler.py         # Document profiling (density, noise, layout)
    ├── cleaner.py          # 12-step adaptive cleanup orchestrator
    ├── text_cleanup.py     # OCR correction, noise removal, footnote stripping
    ├── layout.py           # Paragraph reconstruction from multi-column PDFs
    ├── references.py       # Internal reference/citation removal
    ├── furniture.py        # Repeated page header/footer detection
    ├── images.py           # Image filtering (size, variance, context)
    ├── segmenter.py        # Semantic section classification + entity extraction
    └── quality.py          # 6-dimension quality scoring
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

### RAG Agent (LangGraph)

The system is a **single deterministic graph**, the same for every LLM provider — there is no ReAct loop and the LLM never decides whether to retrieve. `build_graph()` (`core/agent.py`) always compiles:

```
START → enrich_query → route_after_analysis → {retrieve_forced → generate, respond_without_retrieval} → END
```

- `enrich_query` classifies the query's scope/route and rewrites it with legal terminology for better recall.
- `route_after_analysis` sends in-domain legal queries to `retrieve_forced`; greetings/meta-questions/out-of-scope queries go straight to `respond_without_retrieval` (no retrieval call at all).
- `retrieve_forced` always runs the `HybridEnsembleRetriever` exactly once for in-domain queries — retrieval is not optional, unlike a ReAct agent that could invoke a tool zero, one, or many times. It fills `sources` and, via `tools.build_context_block`, the formatted context the LLM sees.
- `generate` produces the final answer citing `[docN]`.

**Memory** — `thread_id` (frontend UUID) persists in-process history in `MemorySaver` while the server runs. If the server restarts, the endpoint re-hydrates state from `conversations/{id}/messages` in the application database (SQLAlchemy async, see `api/database.py` and `api/models.py`) using `conversation_id`.

**SSE Streaming** — `/api/query/stream` emits `status` (node stage), `token` (live LLM tokens), and a final `sources` event with grouped sources and context metrics.

### LLM Provider Fallback

`llm_factory.py` tries providers in order: **OpenAI** → **OpenRouter** → **Gemini** → error. The first provider with a configured API key wins. Structured output and system roles are auto-detected based on model name (Gemma variants lack both via Google GenAI).

### External Infrastructure (EC2)

- **ChromaDB** — remote EC2, port 8000 (collection: `rag_playas`)
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

## CI/CD

One GitHub Actions workflow, **`ci.yml`** (`.github/workflows/`). Runs on push to `main`/`develop`
and PRs to `main`. Two jobs:
  - `quality`: Ruff lint + format check
  - `test`: Unit tests with coverage upload to Codecov (depends on `quality`)

> There used to be a second workflow, `tests.yml`, duplicating the same unit test run with minor
> differences (uv caching, `--cov-report=term-missing`). Merged into `ci.yml` (T4.1) after
> confirming both ran the same tests — no coverage was lost.

Type checking (`mypy`) runs in CI as of T4.1 (`backend/rag/` has no outstanding errors, verified
locally with `make typecheck`).

---

## Docker

`docker-compose.yml` provides a 3-service stack designed for **single-machine deployment** (frontend + backend + reverse proxy on the same host):

- **backend** — FastAPI via uvicorn, port 8080 (internal), healthcheck at `/api/health`
- **frontend** — Next.js production build, port 3000 (internal)
- **nginx** — Reverse proxy, port 80 (public entry point), routes `/api/` to backend and `/` to frontend, SSE-aware (buffering disabled for streaming)

```bash
# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f

# Stop
docker compose down
```

The backend reads its config from `.env` at root. The frontend can receive `NEXT_PUBLIC_API_URL` as a build arg during `docker build` (see `docker/Dockerfile.frontend`) — no other build-time variables are required by the current Dockerfiles.

---

## Key Conventions

- **Env vars** — all in `.env` at root. Two independent `config.py` files read only what they need.
- **Workspace managers** — `uv` (Python, root), `bun` (Node, root + frontend)
- **Integration tests** — marked `@pytest.mark.integration`, skipped in `make test`
- **Tests location** — `tests/unit/` and `tests/integration/` at project root
- **Next.js** — uses Next.js 16.2.3 (React 19). Breaking changes may differ from prior versions. See `frontend/AGENTS.md`.
- **Operational scripts** — see `docs/SCRIPTS.md` for pipeline, infrastructure, migration, and utility scripts.
