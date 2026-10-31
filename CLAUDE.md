# Repository guidance

ATLAS provides Spanish-language orientation on Colombian coastal regulations
and jurisprudence. This file contains working instructions, not a second copy
of the architecture documentation.

## Sources of truth

- Repository map and AWS operations: [README.md](README.md).
- Scope, branches and verification gates: [CONTRIBUTING.md](CONTRIBUTING.md).
- RAG architecture and commands: [rag/README.md](rag/README.md) and
  [rag/docs/ARCHITECTURE.md](rag/docs/ARCHITECTURE.md).
- Ingestion behavior and operational limits: [ingesta/README.md](ingesta/README.md)
  and [ingesta/docs/SCRIPTS.md](ingesta/docs/SCRIPTS.md).
- Corpus and evaluation sources: [data/README.md](data/README.md).
- Component Makefiles, pyproject.toml and .github/workflows/ci.yml define
  the actual commands and CI scope. Do not infer them from historical reports.

## Boundaries

- rag/ and ingesta/ are independent Python projects. Run commands from their
  respective roots; rag/backend/ is a member of the rag/ uv workspace.
- The rag package lives in rag/backend/rag/. Use make app from rag/;
  do not assume the repository root is a Python project.
- Next.js lives in rag/frontend/, within the Bun workspace at rag/.
  Read rag/frontend/AGENTS.md and the installed Next.js documentation before
  changing frontend code.
- Ingestion writes S3. ChromaDB/Ollama EC2 are managed by vector-infraestructura/;
  the application is managed by rag/infrastructure/; S3 belongs to
  ingesta/infrastructure/. Do not move Terraform files or states during cleanup.
- Authentication uses JWT and SQL, with password compatibility handled in
  rag/backend/rag/api/passwords.py. Do not restore obsolete Firebase code.
- The agent uses a deterministic LangGraph graph. Do not introduce a second
  retrieval/generation flow for evaluation; its adapter invokes the same graph.

## Safety and verification

- Preserve existing changes and unrelated functionality. Keep changes small;
  avoid generic frameworks, shared packages or extra layers without a concrete need.
- Keep Python 3.12 and existing locks for reproducible checks. Do not run an
  incidental dependency upgrade while formatting or editing documentation.
- Run unit tests without external services. RAG smoke tests and real evaluation
  have separate requirements; see the component documentation before running them.
- Do not execute AWS deployment, start/stop, ingestion, imports, migration or
  reindexing as an incidental validation step. Continue using HTTP for this deployment.
- Do not version .env, Terraform states, dumps, generated reports or execution
  plans. Maintain current documentation; Git retains implementation history.
- Report failures and unverified assumptions. Do not claim full functional or
  legal validation from static checks or skipped tests.
