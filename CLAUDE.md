# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**ATLAS** (Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre playas en Colombia) — An agentic RAG system specialized in Colombian beach/coastal legal documents (playas, dominio público marítimo-terrestre). It processes two document types: court rulings (`jurisprudencia`) from the Consejo de Estado, and regulations (`normativa`) such as decrees. Each type follows a separate sectioning strategy; all share the same chunking, enrichment, and retrieval pipeline.

**Spanish-language codebase** — all comments, prompts, docs, and API responses are in Spanish.

---

## Repo Layout

The repo root holds **two independent top-level projects**, each its own `uv` workspace with its own `pyproject.toml`, `Makefile`, `.venv`, and CI job. They share no Python code — only the `data/` staging directory (mostly gitignored) and external services (S3, ChromaDB, Ollama, LLM providers).

```
playas/
├── rag/                # RAG serving: API + agent + frontend + AWS ECS infra
│   ├── backend/        # uv workspace member — the actual "rag" Python package (see below)
│   ├── frontend/       # Next.js 16 / React 19 app (bun)
│   ├── infrastructure/ # Terraform: ECS Fargate, ALB, ECR, EFS (Postgres volume)
│   ├── docker/         # Dockerfiles (backend, frontend) + nginx.conf
│   ├── evaluation/     # RAGAS eval scripts (Gemma, Ollama)
│   ├── scripts/        # Ops one-offs (Docker install, SageMaker lifecycle)
│   ├── utils/          # ChromaDB CLI utilities (count, clear), Gemini model listing
│   ├── tests/          # unit/ + integration/, run against backend/rag via pythonpath
│   ├── docker-compose.yml  # single-machine deployment alternative to ECS
│   └── pyproject.toml  # uv workspace root (members = ["backend"]); dev deps, pytest/ruff config
└── ingesta/             # Ingestion pipeline + AWS S3 bucket infra
    ├── ingest/          # the actual "ingest" Python package (see below)
    ├── infrastructure/  # Terraform: S3 bucket for data/ layers
    ├── scripts/         # run_data_pipeline.sh (3-stage), run_pipeline.sh (see note below)
    ├── utils/           # one-off migration scripts, bucket_backup.py
    ├── tests/           # unit/ + integration/
    └── pyproject.toml
```

> **Note:** `rag/pyproject.toml` is a `uv` workspace root whose only member is `backend/`; the
> actual package (`import rag...`) lives at `rag/backend/rag/`. `make`/`uv run` commands are
> issued from `rag/`, with `pythonpath = ["backend"]` set in `[tool.pytest.ini_options]`.

---

## Build/Test Commands

### `rag/` (serving)

```bash
cd rag
make install        # uv sync --group dev
make lint           # ruff check backend/rag/ tests/ evaluation/
make format         # ruff format backend/rag/ tests/ evaluation/
make typecheck      # mypy backend/rag/  (note: CI-disabled due to lingering errors)
make test           # pytest tests/unit/ -v
make test-cov       # pytest + HTML coverage report (--cov=rag)
make test-integration  # pytest -m integration -v  (requires live ChromaDB + Ollama)
make app            # uvicorn rag.api.main:app --reload --port 8080
make frontend       # cd frontend && bun run dev (Next.js on port 3000)
make -C frontend build  # production build
```

**Run a single test:**
```bash
cd rag && uv run pytest tests/unit/path/to/test_file.py::test_name -v
```

### `ingesta/` (pipeline)

```bash
cd ingesta
make install        # uv sync --group dev
make lint           # ruff check ingest/ tests/
make format         # ruff format ingest/ tests/
make typecheck      # mypy ingest/
make test           # pytest tests/unit/ -v
make test-cov       # pytest + HTML coverage report (--cov=ingest)
make test-integration  # pytest -m integration -v
make bucket-backup   # PYTHONPATH=. uv run python -m utils.bucket_backup

# Pipeline stages (can also run independently)
uv run python -m ingest.pdf_to_md           # PDF → clean Markdown (data/bronze/)
uv run python -m ingest.loaders             # bronze → silver (data/silver/)
uv run python -m ingest.splitter_and_enrich # silver → gold enriched chunks (data/gold/)
```

> `make pipeline` runs `scripts/run_pipeline.sh`, which chains all 5 stages: the 3 ingest
> stages run with `ingesta/`'s venv, then indexing (`rag.core.vectorstore`) and the API
> (`uvicorn`) run with `rag/`'s venv (`ingesta/` and `rag/` are separate uv workspaces, so
> the script `cd`s into each directory for its respective steps). Use
> `scripts/run_data_pipeline.sh` instead if you only want the 3 ingest-only stages without
> touching ChromaDB or starting the API.

---

## Architecture

### `rag/backend/rag/` — RAG serving package

```
rag/backend/rag/
├── config.py                 # Env vars: S3, Chroma, Ollama, LLM, query enrichment, context limit
├── s3_client.py              # S3 read-only helpers (list, read)
├── core/
│   ├── agent.py              # LangGraph: single deterministic graph (enrich_query → route → retrieve/respond → generate)
│   ├── tools.py               # build_context_block (formats retrieved docs) + sanitize_replacement_chars (encoding patch)
│   ├── prompts.py             # System/human prompts for agent + enricher
│   ├── embeddings.py          # Ollama embedding client (ChromaDB + LangChain)
│   ├── vectorstore.py         # ChromaDB collection build/update from gold (run via -m)
│   ├── retriever.py           # BM25 + vector + HybridEnsembleRetriever (RRF c=160)
│   ├── query_enricher.py      # LLM query rewriting (legal terminology, sub-questions)
│   └── llm_factory.py         # Provider factory: OpenAI → OpenRouter → Gemini → error
└── api/
    ├── main.py                # FastAPI app (lifespan builds graph + init_db, health, ready, query, query/stream)
    ├── auth.py                 # JWT dependencies: get_optional_user / get_current_user / require_admin
    ├── database.py             # Async SQLAlchemy engine/session (Postgres in prod, SQLite fallback)
    ├── models.py                # SQLAlchemy models: User, Conversation, Message, Feedback, MessageFeedback
    ├── schemas.py               # Pydantic request/response models
    └── routes/
        ├── auth.py              # POST /api/auth/login, /register, GET /me — JWT issuance
        ├── conversations.py     # CRUD conversaciones/mensajes, POST .../generate-title
        ├── feedback.py          # POST /api/feedback, POST /api/feedback/message
        └── admin.py             # GET/POST /api/admin/* (feedback, message-feedback, users)
```

Auth is **self-hosted JWT + PostgreSQL**, not Firebase (Firebase was fully removed in June 2026).
`rag/api/auth.py` issues/validates HS256 tokens (`JWT_SECRET_KEY` / `JWT_ALGORITHM` /
`JWT_EXPIRE_MINUTES` env vars); passwords are SHA-256-then-bcrypt hashed (`routes/auth.py`).

### `ingesta/ingest/` — Ingestion pipeline package

```
ingesta/ingest/
├── config.py                # Env vars + DOC_TYPES + layer_prefix(layer, doc_type)
├── s3_client.py              # Full S3 client (read/write/copy/delete)
├── llm_factory.py            # Provider factory (mirror of rag/, uses enricher models)
├── utils.py                  # JSONL I/O helpers
├── loaders.py                # bronze/<type>/ → silver/<type>/ (dispatches by doc_type)
├── normalize.py               # Metadata cleanup
├── sections.py                # split_by_sections() — 4-section jurisprudencia strategy
├── sections_normativa.py      # split_by_articles() — per-article normativa strategy
├── metadata_csv.py            # Loads raw/<type>/metadata.csv (optional per doc_type)
├── splitter_and_enrich.py     # Chunk (1000 tokens, 200 overlap) + LLM enrichment
└── pdf_to_md/                 # PDF → Markdown via Docling (OCR, tables, images)
    ├── pipeline.py            # Main entry: convert_pdfs_to_markdown()
    ├── config.py              # Tunable constants (image, OCR, profiling thresholds)
    ├── models.py               # LegalDocumentProfile, LegalBlock, DocumentQualityReport
    ├── profiler.py             # Document profiling (density, noise, layout)
    ├── cleaner.py               # 12-step adaptive cleanup orchestrator
    ├── text_cleanup.py          # OCR correction, noise removal, footnote stripping
    ├── layout.py                # Paragraph reconstruction from multi-column PDFs
    ├── references.py            # Internal reference/citation removal
    ├── furniture.py             # Repeated page header/footer detection
    ├── images.py                # Image filtering (size, variance, context)
    ├── segmenter.py             # Semantic section classification + entity extraction
    └── quality.py                # 6-dimension quality scoring
```

`rag/backend/rag/config.py` and `ingesta/ingest/config.py` each define their own `DOC_TYPES` /
`layer_prefix()` — keep them manually in sync, since the packages don't import each other.

### Data Flow

Each pipeline layer is split by `doc_type` subfolder (`jurisprudencia` / `normativa`):

```
raw PDFs / MDs
  └─→ pdf_to_md (Docling)              → data/bronze/<type>/ (clean Markdown)     [ingesta]
       └─→ loaders (normalize + CSV)  → data/silver/<type>/ (JSONL, sectioned)   [ingesta]
            │  jurisprudencia → split_by_sections()  (4 canonical sections)
            │  normativa      → split_by_articles()  (1 unit per Artículo N)
            └─→ splitter_and_enrich   → data/gold/<type>/ (enriched chunks)      [ingesta]
                 └─→ vectorstore      → ChromaDB  (doc_type in each chunk's metadata) [rag]
```

The `doc_type` is fixed once at load time from the source folder and propagates through all layers. The ChromaDB collection is shared; filtering by `doc_type` enables serving both types from the same retriever.

### RAG Agent (LangGraph)

The system is **not tool-calling / ReAct**: `build_graph()` compiles a single deterministic graph, the same one for every LLM provider — there is no branching by `supports_structured_output` or any other provider capability, and the LLM never decides whether to retrieve.

```
START → enrich_query → route_after_analysis → {retrieve_forced → generate, respond_without_retrieval} → END
```

- `enrich_query` rewrites the query with legal terminology for recall and classifies it into one of four routes (`in_scope`, `out_of_scope`, `conversation`, `needs_clarification`).
- `route_after_analysis` is a plain conditional edge: `in_scope` → `retrieve_forced`, anything else → `respond_without_retrieval`.
- `retrieve_forced` runs the `HybridEnsembleRetriever` unconditionally — exactly once, only for `in_scope` queries — and stores the fragments in `sources`.
- `generate` builds the answer from `sources` (`build_context_block`), validates its citations (`_validate_citations`), and falls back to a fixed no-evidence/invalid-citations response if either check fails.
- `respond_without_retrieval` answers greetings/meta-questions, asks for clarification, or returns the fixed out-of-scope response — without ever calling the retriever or the generation LLM.

**Memory** — `thread_id` (frontend UUID) persists history in `MemorySaver` while the process lives. If the server restarts, `main.py` hydrates state from the `messages` table (via SQLAlchemy, `rag/api/models.py::Message`) filtered by `conversation_id`.

**SSE Streaming** — `/api/query/stream` does **not** stream tokens live from the LLM. `generate_node` awaits the full completion (`chain.ainvoke`, not `.astream()`), validates its citations, and only then does `main.py`'s `event_generator()` slice the already-complete, already-validated answer into fixed-size text fragments emitted as consecutive `token` events (no delay between them — not real incremental generation). The endpoint emits `status` (node stage, live via `get_stream_writer()`), then those `token` fragments, then a final `sources` event with grouped sources and context metrics.

### LLM Provider Fallback

`llm_factory.py` tries providers in order: **OpenAI** → **OpenRouter** → **Gemini** → error. The first provider with a configured API key wins. Structured output and system roles are auto-detected based on model name (Gemma variants lack both via Google GenAI).

### External Infrastructure (AWS)

- **ChromaDB + Ollama** — EC2, provisioned by Terraform in `vector-infraestructura/` (collection: `rag_playas`, port 8000; embedding model `embeddinggemma:latest` on port 11434). Optional reranker: Ollama `mistral`.
- **RAG app (backend + frontend)** — ECS Fargate, provisioned by Terraform in `rag/infrastructure/`. The `app` service runs the FastAPI backend and a `postgres:16-alpine` sidecar container (data on an EFS-backed volume) in the same task; `DATABASE_URL` points at `localhost:5432`. See `rag/infrastructure/scripts/deploy.sh` and `export_postgres.sh`.
- **Data bucket** — S3, provisioned by Terraform in `ingesta/infrastructure/`, holds the `raw/bronze/silver/gold` layers.

### Document Structure

**Jurisprudencia** (Colombian court rulings) follow a 4-section structure documented in `ingesta/docs/DOCUMENT_SECTIONS.md`:
1. **Contexto del caso** — case background
2. **Desarrollo procesal** — procedural history
3. **Argumentación jurídica** — legal reasoning
4. **Decisión** — ruling/decision

**Normativa** (decrees, regulations) is segmented by `Artículo N` (regex over plain text), with `TÍTULO`/`CAPÍTULO` hierarchy preserved as metadata. A `"Preámbulo"` unit captures text before the first article.

---

## CI/CD

One GitHub Actions workflow, **`ci.yml`** (`.github/workflows/`), running **separate jobs per package**
(`working-directory: ingesta` and `working-directory: rag`) on push to `main`/`develop`/`v2` and PRs to
`main`. Per package:
  - `quality`: Ruff lint + format check
  - `test`: Unit tests with coverage upload to Codecov (depends on `quality`)

> There used to be a second workflow, `tests.yml`, that duplicated the same unit test run per
> package with minor differences (uv caching, `--cov-report=term-missing`). It was merged into
> `ci.yml` (T4.1) after confirming the two ran the exact same tests — `ci.yml` kept its stricter
> quality-gated job structure and picked up `tests.yml`'s caching and `fail_ci_if_error: false`.

Type checking (`mypy`) runs in CI for `rag/` (T4.1 — `backend/rag/` has no outstanding errors). It
remains disabled in CI for `ingesta/`, which still has a handful of lingering errors (missing
`boto3`/`botocore` stubs, two pre-existing type issues in `pdf_to_md/images.py` and
`splitter_and_enrich.py`) outside this plan's scope.

---

## Docker

`rag/docker-compose.yml` provides a 4-service stack designed for **single-machine deployment** (as an alternative to the ECS Fargate setup) — Postgres + backend + frontend + reverse proxy on the same host:

- **postgres** — `postgres:16-alpine`, healthcheck via `pg_isready`
- **backend** — FastAPI via uvicorn, port 8080 (internal), healthcheck at `/api/health`, waits on `postgres` being healthy
- **frontend** — Next.js production build, port 3000 (internal), waits on `backend` being healthy
- **nginx** — Reverse proxy, port 80 (public entry point), routes `/api/` to backend and `/` to frontend, SSE-aware (buffering disabled for streaming)

```bash
cd rag
docker compose up -d --build   # Build and start
docker compose logs -f         # View logs
docker compose down            # Stop (add -v to also drop the postgres volume)
```

---

## Key Conventions

- **Env vars** — `rag/.env` and `ingesta/.env` (see the `.env.example` in each). Two independent `config.py` files read only what they need.
- **Workspace managers** — `uv` (Python, one workspace per package root), `bun` (Node, `rag/` + `rag/frontend/`)
- **Integration tests** — marked `@pytest.mark.integration`, skipped in `make test`
- **Tests location** — `<package>/tests/unit/` and `<package>/tests/integration/`, e.g. `rag/tests/unit/`
- **Next.js** — uses Next.js 16.2.3 (React 19). Breaking changes may differ from prior versions. See `rag/frontend/AGENTS.md`.
- **Operational scripts** — see `rag/docs/SCRIPTS.md` and `ingesta/docs/SCRIPTS.md` for pipeline, infrastructure, migration, and utility scripts.
