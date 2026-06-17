# ATLAS

**Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre playas en Colombia.**

Agente conversacional de **jurisprudencia y normativa colombiana sobre playas y dominio público marítimo-terrestre**. Procesa sentencias en PDF (Consejo de Estado, Tribunales Administrativos) y normativa (decretos, reglamentos), los indexa semánticamente diferenciados por `doc_type` y los expone como un agente **LangGraph** sobre una API FastAPI consumida por un frontend Next.js con autenticación JWT, historial de conversaciones, calificación de respuestas y panel de administración.

- [Registro de archivos indexados](ingesta/docs/archivos-indexados.md)
- [Estructura típica de sentencias](ingesta/docs/DOCUMENT_SECTIONS.md)
- [Scripts operacionales y utilidades — RAG](rag/docs/SCRIPTS.md)
- [Scripts operacionales y utilidades — Ingesta](ingesta/docs/SCRIPTS.md)

---

## Arquitectura

Dos paquetes Python independientes más un frontend, que comparten `data/` y servicios externos (ChromaDB, Ollama, proveedor LLM):

```
┌──────────────────────┐     ┌──────────────────────────────────┐     ┌──────────────────┐
│  Pipeline de ingesta │  →  │  Agente LangGraph + API FastAPI  │ ←→  │ Frontend Next.js │
│   (paquete ingesta/) │     │        (paquete rag/)            │     │  (rag/frontend/) │
└──────────────────────┘     └──────────────────────────────────┘     └──────────────────┘
```

`ingesta/ingest/` y `rag/backend/rag/` son **paquetes Python independientes** dentro de workspaces `uv` separados: no comparten código, solo el directorio `data/` y los servicios externos. El frontend (Bun) habla con la API por SSE para streaming y REST para historial/feedback.

---

## Pipeline de ingesta

![Pipeline de ingesta ATLAS](rag/docs/images/pipeline.png)

El pipeline soporta dos tipos de documento (`doc_type`), cada uno con su propia subcarpeta en todas las capas:

| Tipo | Carpeta | Estrategia de seccionado |
|---|---|---|
| `jurisprudencia` | `data/{capa}/jurisprudencia/` | 4 secciones canónicas de sentencia |
| `normativa` | `data/{capa}/normativa/` | 1 unidad por `Artículo N` |

1. **PDF/MD → Markdown** (`data/bronze/<tipo>/`) — Docling con OCR, tablas e imágenes; limpieza exhaustiva de encabezados, pies y numeraciones. La normativa puede entrar directamente como Markdown.
2. **Bronze → Silver** (`data/silver/<tipo>/`) — normalización, fusión con metadatos legales del CSV (`raw/<tipo>/metadata.csv`, opcional) y seccionado por tipo:
   - **Jurisprudencia**: `split_by_sections()` — 4 secciones canónicas (`Contexto del caso`, `Desarrollo procesal`, `Análisis del tribunal`, `Decisión`).
   - **Normativa**: `split_by_articles()` — 1 unidad por artículo, arrastrando jerarquía `TÍTULO`/`CAPÍTULO` como metadatos.
3. **Silver → Gold** (`data/gold/<tipo>/`) — chunking de ~1000 tokens (200 de overlap) y enriquecimiento con LLM (resumen, keywords, entidades), inyectado en la metadata. El `chunk_id` incluye el tipo (`{stem}_art{N}_c{idx}` para normativa).
4. **Gold → ChromaDB** — embeddings con Ollama (`embeddinggemma`) e indexación. Cada chunk lleva `doc_type` en sus metadatos, permitiendo filtrar jurisprudencia y normativa en el retriever. En runtime el retriever combina **BM25 (30%) + vector (70%)** con fusión RRF.

---

## Agente RAG (LangGraph)

El sistema **no es un pipeline RAG fijo**: es un agente compilado en LangGraph con memoria multi-turno (`MemorySaver`) y una tool de recuperación que el LLM invoca solo cuando hace falta.

**Grafo principal** (proveedores con tool calling — OpenAI, OpenRouter, Gemini estándar):

```
START → enrich_query → agent ⇆ tools(retrieve) → END
```

- `enrich_query` reescribe la consulta con terminología jurídica para mejorar el recall.
- `agent` decide si invocar la tool `retrieve` (consulta jurídica) o responder directo (saludo, meta-pregunta).
- `tools.retrieve` corre el `HybridEnsembleRetriever` y devuelve fragmentos como `ToolMessage` + actualización de `sources` en el state.
- El agente vuelve con los docs en contexto y responde citando `[docN]`.

**Grafo fallback** (proveedores sin tool calling, p. ej. Gemma):

```
START → enrich_query → retrieve_forced → generate → END
```

`build_graph()` elige uno u otro según `get_active_provider().supports_structured_output`.

**Memoria** — el `thread_id` (UUID del frontend) persiste el historial en `MemorySaver` mientras viva el proceso. Si el servidor reinicia, el endpoint hidrata el estado desde la tabla `messages` en PostgreSQL/SQLite usando el `conversation_id`.

**Streaming SSE** — `/api/query/stream` emite eventos `status` (etapa del nodo), `token` (tokens del LLM en vivo) y un `sources` final con fuentes agrupadas y métricas de contexto.

**Selección de proveedor LLM** — `rag/core/llm_factory.py` resuelve en orden: `OPENAI_API_KEY` → `OPENROUTER_API_KEY` → `GOOGLE_API_KEY`.

---

## Autenticación y persistencia

Autenticación, historial, calificaciones y roles se gestionan en el propio backend mediante **JWT + SQLAlchemy async** (SQLite en desarrollo, PostgreSQL en producción).

`rag/backend/rag/api/auth.py` ofrece tres dependencias FastAPI: `get_optional_user` (token opcional), `get_current_user` (obligatorio) y `require_admin` (verifica el campo `role` en el payload JWT).

**Modelo relacional:**

| Tabla | Propósito |
|---|---|
| `users` | `email`, `display_name`, `role` (`user`/`admin`/`super-admin`), `hashed_password`, `created_at` |
| `conversations` | `user_id`, `thread_id`, `title`, `created_at`, `updated_at` |
| `messages` | `conversation_id`, `role`, `text`, `sources`, `created_at` |
| `feedback` | Calificaciones de conversación (tone, length, usability, overall) |
| `message_feedback` | Calificaciones por mensaje (pertinence, accuracy, expected_answer) |

**Endpoints de autenticación:**

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/auth/register` | Registro con email + contraseña (bcrypt) → JWT |
| `POST` | `/api/auth/login` | Login → JWT |
| `GET` | `/api/auth/me` | Datos del usuario autenticado |

El token se almacena en `localStorage` en el frontend y se envía como `Authorization: Bearer <token>` en cada petición.

---

## Estructura del repositorio

```
playas/
├── rag/                              ← Sistema RAG (API + agente + frontend)
│   ├── backend/                      ← Paquete Python (uv workspace)
│   │   └── rag/
│   │       ├── core/                 ← agent, tools, retriever, llm_factory, ...
│   │       └── api/                  ← FastAPI: main, auth, models, database, routes/
│   ├── frontend/                     ← Next.js 16 (React 19, Bun)
│   │   └── lib/
│   │       ├── auth.ts               ← JWT helpers (localStorage)
│   │       └── api.ts                ← Cliente REST con token JWT
│   ├── docker/                       ← Dockerfiles (backend, frontend)
│   ├── docker-compose.yml            ← Stack: postgres + backend + frontend + nginx
│   ├── docs/                         ← Guías, diseño, scripts
│   ├── evaluation/                   ← RAGAS + ground truth
│   ├── tests/                        ← Tests unitarios e integración
│   ├── scripts/                      ← Scripts de despliegue y utilidades
│   └── Makefile
├── ingesta/                          ← Pipeline de ingesta (paquete independiente)
│   ├── ingest/                       ← Paquete Python
│   │   ├── pdf_to_md/                ← PDF → Markdown (Docling, OCR)
│   │   ├── loaders.py                ← Bronze → Silver
│   │   ├── splitter_and_enrich.py    ← Silver → Gold (chunks + LLM)
│   │   └── sections*.py              ← Estrategias de seccionado por doc_type
│   ├── infrastructure/               ← Terraform S3
│   ├── docs/
│   ├── scripts/                      ← run_pipeline.sh
│   └── Makefile
├── vector-infraestructura/           ← Terraform: ChromaDB + Ollama en EC2
│   ├── chromadb.tf
│   ├── ollama.tf
│   ├── providers.tf / terraform.tf / variables.tf / locals.tf / outputs.tf
│   └── scripts/
│       ├── ec2_chroma_db.sh
│       └── ec2_ollama_embeddings.sh
└── data/                             ← Staging del pipeline (gitignored)
    ├── raw/{jurisprudencia,normativa}/
    ├── bronze/{jurisprudencia,normativa}/
    ├── silver/{jurisprudencia,normativa}/
    └── gold/{jurisprudencia,normativa}/
```

`uv` gestiona cada workspace Python por separado (`rag/` e `ingesta/`); `bun` gestiona el workspace Node (`rag/frontend/`). El `.env` vive en `rag/`.

---

## Requisitos

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/)
- Docker (para despliegue completo con PostgreSQL)
- ChromaDB y Ollama en EC2 (ver `vector-infraestructura/`)
- API key de al menos un proveedor LLM: OpenAI, OpenRouter o Gemini

Diseñado para Linux. Compatible con WSL aplicando `dos2unix ingesta/scripts/*.sh`.

---

## Instalación

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/camilousa/playas.git
cd playas

# Dependencias Python (RAG)
cd rag && uv sync --group dev

# Dependencias Python (Ingesta)
cd ../ingesta && uv sync --group dev

# Dependencias Node
cd ../rag && bun install

cp .env.example .env
# Editar .env con las variables requeridas
```

---

## Variables de entorno

**Backend (`rag/.env`):**

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/atlas.db` | SQLite (dev) o `postgresql+asyncpg://...` (prod) |
| `POSTGRES_PASSWORD` | — | Contraseña PostgreSQL (solo Docker Compose) |
| `JWT_SECRET_KEY` | — | Clave secreta para firmar tokens JWT |
| `JWT_ALGORITHM` | `HS256` | Algoritmo JWT |
| `JWT_EXPIRE_MINUTES` | `10080` | Expiración del token (7 días) |
| `CHROMA_HOST` | `localhost` | Host de ChromaDB |
| `CHROMA_PORT` | `8000` | Puerto de ChromaDB |
| `CHROMA_COLLECTION` | `rag_playas` | Nombre de la colección |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL de Ollama |
| `OLLAMA_EMBEDDING_MODEL` | `embeddinggemma:latest` | Modelo de embeddings |
| `OLLAMA_RERANKER_MODEL` | `llama3.2:3b` | Modelo reranker (opcional) |
| `OPENAI_API_KEY` | — | API key de OpenAI (máxima prioridad) |
| `OPENAI_MODEL` | `gpt-5.4-mini` | Modelo de OpenAI |
| `OPENROUTER_API_KEY` | — | API key de OpenRouter (segunda prioridad) |
| `OPENROUTER_MODEL` | `gpt-5.4-mini` | Modelo de OpenRouter |
| `GOOGLE_API_KEY` | — | API key de Gemini (tercera prioridad) |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Modelo de Gemini |
| `QUERY_ENRICHMENT_ENABLED` | `true` | Activar reescritura de consultas |
| `QUERY_ENRICHMENT_HYDE` | `false` | Activar HyDE (fragmento hipotético) |

Orden de prioridad de proveedores LLM: **OpenAI** → **OpenRouter** → **Gemini** → error.

**Frontend (`rag/frontend/.env.local`):**

| Variable | Descripción |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | URL del backend (`http://localhost:8080` en local, `/api` con Docker) |

---

## Infraestructura en AWS

Dos instancias EC2 con IP elástica. La carpeta `vector-infraestructura/` provisiona ambas con Terraform:

| Máquina  | Tipo        | Almacenamiento | Puerto | Servicio    |
| -------- | ----------- | -------------- | ------ | ----------- |
| ChromaDB | `t3.medium` | 12 GB gp3      | 8000   | ChromaDB    |
| Ollama   | `t3.large`  | 20 GB gp3      | 11434  | Ollama      |

```bash
cd vector-infraestructura/
terraform init
terraform apply
```

Setup manual alternativo:

```bash
bash vector-infraestructura/scripts/ec2_chroma_db.sh
bash vector-infraestructura/scripts/ec2_ollama_embeddings.sh
```

El bucket S3 del pipeline de ingesta se gestiona por separado desde `ingesta/infrastructure/`.

---

## Ejecución

```bash
# Pipeline de ingesta (todas las etapas)
cd ingesta && make pipeline

# API FastAPI (docs interactivas en http://localhost:8080/docs)
cd rag && make app

# Frontend (http://localhost:3000)
cd rag && make frontend
```

La documentación de los endpoints está disponible automáticamente en `/docs` y `/redoc` (Swagger UI / ReDoc generadas por FastAPI).

---

## Docker (despliegue en una sola máquina)

`rag/docker-compose.yml` despliega cuatro servicios (postgres, backend, frontend, nginx) en una sola máquina. Nginx actúa como reverse proxy en el puerto 80, enruta `/api/` al backend y `/` al frontend, y desactiva el buffering para streaming SSE.

```bash
cd rag

# Construir y levantar
docker compose up -d --build

# Ver logs
docker compose logs -f

# Detener
docker compose down
```

Requiere `rag/.env` con `DATABASE_URL` apuntando al servicio `postgres` y `JWT_SECRET_KEY` configurado. Los Dockerfiles están en `rag/docker/`.

**Arquitectura de la stack Docker:**

```
Puerto 80 (host)
    └── nginx (reverse proxy)
        ├── /api/*  → backend:8080  (FastAPI + uvicorn)
        └── /*      → frontend:3000 (Next.js)

postgres:5432       (interno, no expuesto)
```

---

## CI/CD

Dos workflows de GitHub Actions en `.github/workflows/`:

| Workflow | Trigger | Jobs |
|----------|---------|------|
| `ci.yml` | Push a `main`/`develop`, PRs a `main` | `quality` (Ruff lint + format check) → `test` (unit tests + Codecov) |
| `tests.yml` | Mismos triggers | Unit tests con cobertura en Python 3.12 |

Type checking (`mypy`) está deshabilitado en CI debido a errores pendientes en módulos de producción.

---

## Comandos útiles

```bash
# Desde rag/
make install          # dependencias Python
make lint / format    # ruff
make test             # pytest unitarios
make test-cov         # pytest + cobertura HTML
make test-integration # tests con servicios reales (Chroma + Ollama)
make app              # API FastAPI
make frontend         # Next.js dev server

# Desde ingesta/
make install          # dependencias Python
make pipeline         # pipeline completo de ingesta
make lint / format    # ruff
make test             # pytest unitarios
```
