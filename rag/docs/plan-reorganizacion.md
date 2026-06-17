# Plan de reorganización: dos subsistemas

## Objetivo

Reorganizar el proyecto en dos carpetas independientes —`ingesta/` y `rag/`— donde cada una contiene todo lo necesario para operar y desplegarse de forma autónoma con `docker compose`.

---

## Estructura objetivo

```
playas/
├── ingesta/
│   ├── ingest/                     ← paquete Python (módulo: ingest, sin cambio)
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── loaders.py
│   │   ├── normalize.py
│   │   ├── sections.py
│   │   ├── sections_normativa.py
│   │   ├── splitter_and_enrich.py
│   │   ├── metadata_csv.py
│   │   ├── utils.py
│   │   ├── s3_client.py
│   │   ├── llm_factory.py
│   │   └── pdf_to_md/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   └── unit/
│   │       ├── test_layer_prefix.py
│   │       ├── test_metadata_csv.py
│   │       ├── test_migrate_doc_type.py
│   │       ├── test_normalize.py
│   │       ├── test_sections_normativa.py
│   │       ├── test_splitter_doctype.py
│   │       └── test_splitter.py
│   ├── pyproject.toml
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── .env.example
│
├── rag/
│   ├── backend/
│   │   ├── rag/                    ← paquete Python (módulo: rag, sin cambio)
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── s3_client.py
│   │   │   ├── core/
│   │   │   │   ├── agent.py
│   │   │   │   ├── embeddings.py
│   │   │   │   ├── llm_factory.py
│   │   │   │   ├── prompts.py
│   │   │   │   ├── query_enricher.py
│   │   │   │   ├── retriever.py
│   │   │   │   ├── tools.py
│   │   │   │   └── vectorstore.py
│   │   │   └── api/
│   │   │       ├── auth.py
│   │   │       ├── database.py     ← nuevo (Fase 1)
│   │   │       ├── models.py       ← nuevo (Fase 1)
│   │   │       ├── main.py
│   │   │       ├── schemas.py
│   │   │       └── routes/
│   │   └── pyproject.toml
│   ├── frontend/                   ← movido desde frontend/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   └── unit/
│   │       ├── test_context_block_doctype.py
│   │       ├── test_generator.py
│   │       ├── test_retriever_balance.py
│   │       └── test_vectorstore.py
│   ├── evaluation/                 ← movido desde evaluation/
│   ├── docker/                     ← movido desde docker/
│   │   ├── Dockerfile.backend
│   │   ├── Dockerfile.frontend
│   │   └── nginx.conf
│   ├── docker-compose.yml
│   └── .env.example
│
├── pyproject.toml                  ← workspace root (rutas actualizadas)
├── Makefile                        ← rutas actualizadas
├── infrastructure/                 ← Terraform (sin cambios)
├── docs/
└── .github/
    └── workflows/
        └── ci.yml                  ← rutas actualizadas
```

---

## Regla clave sobre los módulos Python

Los nombres de módulo **no cambian**. Los imports en todo el código fuente quedan intactos:

```python
from rag.core.agent import build_graph      # sin cambio
from ingest.config import DOC_TYPES         # sin cambio
```

Lo que cambia es únicamente la ubicación de los archivos en disco y los ficheros de configuración que apuntan a esas rutas.

---

## Archivos de configuración a actualizar

### `pyproject.toml` (raíz)

```toml
# Antes
[tool.uv.workspace]
members = ["rag", "ingest"]

# Después
[tool.uv.workspace]
members = ["rag/backend", "ingesta"]

[tool.pytest.ini_options]
testpaths = ["rag/tests", "ingesta/tests"]
pythonpath = ["."]
```

### `ingesta/pyproject.toml`

El `pyproject.toml` se mueve desde `ingest/pyproject.toml` a `ingesta/pyproject.toml`.
Se agrega configuración de build para que hatchling encuentre el paquete en `ingest/`:

```toml
[project]
name = "ingest"
version = "0.1.0"
# ... dependencias sin cambio

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["ingest"]
```

### `rag/backend/pyproject.toml`

El `pyproject.toml` se mueve desde `rag/pyproject.toml` a `rag/backend/pyproject.toml`.
Se agrega configuración de build para que hatchling encuentre el paquete en `rag/`:

```toml
[project]
name = "rag"
version = "0.1.0"
# ... dependencias sin cambio

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["rag"]
```

### `Makefile` (rutas actualizadas)

```makefile
lint:
    uv run ruff check rag/backend/rag/ ingesta/ingest/ rag/tests/ ingesta/tests/ rag/evaluation/

format:
    uv run ruff format rag/backend/rag/ ingesta/ingest/ rag/tests/ ingesta/tests/ rag/evaluation/

test:
    uv run pytest ingesta/tests/unit/ rag/tests/unit/ -v

app:
    uv run uvicorn rag.api.main:app --reload --port 8080

frontend:
    cd rag/frontend && bun run dev

pipeline:
    bash ingesta/scripts/run_pipeline.sh
```

### `.github/workflows/ci.yml` (rutas actualizadas)

```yaml
- name: Ruff lint
  run: uv run ruff check rag/backend/rag/ ingesta/ingest/ rag/tests/ ingesta/tests/

- name: Run unit tests
  run: uv run pytest ingesta/tests/unit/ rag/tests/unit/ --cov=rag --cov=ingest --cov-report=xml
```

### `rag/docker-compose.yml` (contextos actualizados)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    # ... (nuevo — Fase 1 del plan de arquitectura)

  backend:
    build:
      context: ..          # raíz del proyecto
      dockerfile: rag/docker/Dockerfile.backend

  frontend:
    build:
      context: rag/frontend
      dockerfile: ../docker/Dockerfile.frontend

  nginx:
    volumes:
      - ./docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro
```

### `ingesta/docker-compose.yml`

```yaml
services:
  ingest:
    build:
      context: ..
      dockerfile: ingesta/Dockerfile
    env_file: ingesta/.env
    # Uso: docker compose -f ingesta/docker-compose.yml run ingest <etapa>
    # Etapas disponibles:
    #   ingest.pdf_to_md
    #   ingest.loaders
    #   ingest.splitter_and_enrich
    #   rag.core.vectorstore
    command: ["ingest.loaders"]
```

---

## Distribución de los tests existentes

| Archivo actual | Destino |
|---|---|
| `tests/unit/test_layer_prefix.py` | `ingesta/tests/unit/` |
| `tests/unit/test_metadata_csv.py` | `ingesta/tests/unit/` |
| `tests/unit/test_migrate_doc_type.py` | `ingesta/tests/unit/` |
| `tests/unit/test_normalize.py` | `ingesta/tests/unit/` |
| `tests/unit/test_sections_normativa.py` | `ingesta/tests/unit/` |
| `tests/unit/test_splitter_doctype.py` | `ingesta/tests/unit/` |
| `tests/unit/test_splitter.py` | `ingesta/tests/unit/` |
| `tests/unit/test_context_block_doctype.py` | `rag/tests/unit/` |
| `tests/unit/test_generator.py` | `rag/tests/unit/` |
| `tests/unit/test_retriever_balance.py` | `rag/tests/unit/` |
| `tests/unit/test_vectorstore.py` | `rag/tests/unit/` |
| `tests/integration/test_full_pipeline.py` | `ingesta/tests/integration/` |
| `tests/conftest.py` | copiar en ambos subsistemas (fixtures compartidas) |

---

## Distribución de scripts y utilidades

| Archivo actual | Destino |
|---|---|
| `scripts/run_pipeline.sh` | `ingesta/scripts/` |
| `scripts/run_data_pipeline.sh` | `ingesta/scripts/` |
| `scripts/ec2_chroma_db.sh` | `ingesta/scripts/` |
| `scripts/ec2_ollama_embeddings.sh` | `ingesta/scripts/` |
| `scripts/install-docker-ubuntu.sh` | `rag/scripts/` |
| `scripts/deploy-tutorial-html.ps1` | `docs/` |
| `scripts/sagemaker-*.sh` | `rag/scripts/` |
| `scripts/migrate_feedback_ratings.py` | `rag/scripts/` |
| `utils/chroma_clear.py` | `rag/utils/` |
| `utils/chroma_count.py` | `rag/utils/` |
| `utils/backfill_doc_type.py` | `ingesta/utils/` |
| `utils/backfill_doc_type_s3.py` | `ingesta/utils/` |
| `utils/migrate_doc_type.py` | `ingesta/utils/` |
| `utils/bucket_backup.py` | `ingesta/utils/` |
| `utils/list_gemini_models.py` | `rag/utils/` |

---

## Pasos de ejecución

### Paso 1 — Crear la estructura de carpetas

```bash
mkdir -p ingesta/ingest
mkdir -p ingesta/tests/unit ingesta/tests/integration
mkdir -p ingesta/scripts ingesta/utils
mkdir -p rag/backend/rag
mkdir -p rag/tests/unit rag/tests/integration
mkdir -p rag/scripts rag/utils
```

### Paso 2 — Mover el paquete `ingest`

```bash
# Mover archivos del paquete Python
mv ingest/__init__.py        ingesta/ingest/
mv ingest/config.py          ingesta/ingest/
mv ingest/loaders.py         ingesta/ingest/
mv ingest/normalize.py       ingesta/ingest/
mv ingest/sections.py        ingesta/ingest/
mv ingest/sections_normativa.py ingesta/ingest/
mv ingest/splitter_and_enrich.py ingesta/ingest/
mv ingest/metadata_csv.py    ingesta/ingest/
mv ingest/utils.py           ingesta/ingest/
mv ingest/s3_client.py       ingesta/ingest/
mv ingest/llm_factory.py     ingesta/ingest/
mv ingest/pdf_to_md/         ingesta/ingest/

# Mover pyproject.toml
mv ingest/pyproject.toml     ingesta/

# Eliminar carpeta vacía
rmdir ingest/
```

### Paso 3 — Mover el paquete `rag`

```bash
# Mover archivos del paquete Python
mv rag/__init__.py   rag/backend/rag/
mv rag/config.py     rag/backend/rag/
mv rag/s3_client.py  rag/backend/rag/
mv rag/core/         rag/backend/rag/
mv rag/api/          rag/backend/rag/

# Mover pyproject.toml
mv rag/pyproject.toml rag/backend/
```

### Paso 4 — Mover frontend, docker, tests, evaluation

```bash
mv frontend/         rag/frontend/
mv docker/           rag/docker/
mv evaluation/       rag/evaluation/
```

### Paso 5 — Distribuir tests

```bash
# Tests de ingesta
mv tests/unit/test_layer_prefix.py       ingesta/tests/unit/
mv tests/unit/test_metadata_csv.py       ingesta/tests/unit/
mv tests/unit/test_migrate_doc_type.py   ingesta/tests/unit/
mv tests/unit/test_normalize.py          ingesta/tests/unit/
mv tests/unit/test_sections_normativa.py ingesta/tests/unit/
mv tests/unit/test_splitter_doctype.py   ingesta/tests/unit/
mv tests/unit/test_splitter.py           ingesta/tests/unit/
mv tests/integration/                    ingesta/tests/

# Tests del RAG
mv tests/unit/test_context_block_doctype.py rag/tests/unit/
mv tests/unit/test_generator.py             rag/tests/unit/
mv tests/unit/test_retriever_balance.py     rag/tests/unit/
mv tests/unit/test_vectorstore.py           rag/tests/unit/

# conftest en ambos subsistemas
cp tests/conftest.py ingesta/tests/
cp tests/conftest.py rag/tests/
rm -rf tests/
```

### Paso 6 — Distribuir scripts y utils

```bash
# Scripts de ingesta
mv scripts/run_pipeline.sh          ingesta/scripts/
mv scripts/run_data_pipeline.sh     ingesta/scripts/
mv scripts/ec2_chroma_db.sh         ingesta/scripts/
mv scripts/ec2_ollama_embeddings.sh ingesta/scripts/

# Utils de ingesta
mv utils/backfill_doc_type.py       ingesta/utils/
mv utils/backfill_doc_type_s3.py    ingesta/utils/
mv utils/migrate_doc_type.py        ingesta/utils/
mv utils/bucket_backup.py           ingesta/utils/

# Scripts y utils del RAG
mv scripts/install-docker-ubuntu.sh rag/scripts/
mv scripts/sagemaker-*.sh           rag/scripts/
mv scripts/migrate_feedback_ratings.py rag/scripts/
mv utils/chroma_clear.py            rag/utils/
mv utils/chroma_count.py            rag/utils/
mv utils/list_gemini_models.py      rag/utils/

rmdir scripts/ utils/
```

### Paso 7 — Actualizar archivos de configuración

- Actualizar `pyproject.toml` raíz: `members`, `testpaths`, `pythonpath`
- Actualizar `ingesta/pyproject.toml`: agregar `[build-system]` y `[tool.hatch.build]`
- Actualizar `rag/backend/pyproject.toml`: agregar `[build-system]` y `[tool.hatch.build]`
- Actualizar `Makefile`: rutas de lint, format, test, app, frontend, pipeline
- Actualizar `.github/workflows/ci.yml`: rutas de ruff y pytest
- Actualizar `docker-compose.yml` → mover a `rag/docker-compose.yml` con contextos nuevos
- Crear `ingesta/docker-compose.yml`

### Paso 8 — Verificar

```bash
uv sync --group dev
uv run pytest ingesta/tests/unit/ rag/tests/unit/ -v
uv run ruff check rag/backend/rag/ ingesta/ingest/
```

---

## Lo que no cambia

- Todo el código Python (cero imports modificados)
- Lógica del agente, retriever, pipeline de ingesta
- Infraestructura Terraform (`infrastructure/` en raíz)
- Nombre de los módulos Python: `rag` e `ingest`
