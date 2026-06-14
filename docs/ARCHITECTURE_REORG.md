# Propuesta de Reestructuración del Repositorio — ATLAS

> **Fecha:** Junio 2026
> **Autor:** Análisis de arquitectura
> **Estado:** Propuesta (pendiente de aprobación antes de ejecutar)
> **Alcance:** Reorganización de la estructura de carpetas. **No** modifica lógica de negocio; son movimientos de archivos + ajustes de rutas/configuración + 2 líneas de resolución de paths.
> **Decisión adoptada:** `rag/` se divide internamente en **`backend/`** (Python) y **`frontend/`** (Next.js).

---

## 1. Resumen ejecutivo

El repositorio tiene **demasiadas carpetas y archivos sueltos en la raíz** (13 directorios de trabajo + ~16 archivos de configuración/documentación). Los *scripts* operacionales y las *utilidades* Python están centralizados en `scripts/` y `utils/` sin relación con el módulo al que pertenecen, el `frontend` vive desacoplado del backend que lo sirve, y existe duplicación de código entre `rag/` e `ingest/`.

**Objetivo:** Reorganizar el proyecto en **dominios autocontenidos**, donde cada módulo es dueño de su código, sus scripts, sus utilidades, su evaluación y sus tests. El dominio de *serving* (`rag/`) se divide internamente en **backend** y **frontend**.

**Resultado esperado:**

| Métrica | Antes | Después |
|---------|-------|---------|
| Directorios de trabajo en la raíz | 13 | **5** (`rag`, `ingest`, `infra`, `docs`, `data`) + `shared` opcional |
| `rag/` separa backend / frontend | No (frontend en raíz) | **Sí** (`rag/backend/` + `rag/frontend/`) |
| Carpetas “cajón de sastre” (`scripts/`, `utils/`) | 2, mezcladas | 0 (distribuidas por función) |
| Código duplicado `llm_factory`/`s3_client` | 2 copias | 1 (`shared/`, fase 3) |
| Imports rotos (`rag.core.generator`) | 1 | 0 (corregido al mover) |
| Churn de imports `rag.*` en el código | — | **0** (el paquete sigue llamándose `rag`) |

---

## 2. Diagnóstico de la estructura actual

### 2.1 Inventario de la raíz

```
rag_playas/
├── rag/                 # Paquete Python: serving (API + agente)
├── ingest/              # Paquete Python: pipeline de ingesta
├── frontend/            # App Next.js (DESACOPLADA del backend)
├── scripts/             # 9 scripts MEZCLADOS (datos, infra, migración, deploy)
├── utils/               # 7 utilidades Python MEZCLADAS (chroma, s3, gemini)
├── evaluation/          # Evaluación RAGAS (import roto a rag.core.generator)
├── tests/               # unit + integration (raíz única)
├── docs/                # Documentación
├── docker/              # Dockerfiles + nginx.conf
├── infrastructure/      # Terraform
├── data/                # Staging del pipeline (gitignored)
├── bucket-backup/       # Backup local de S3 (gitignored)
├── node_modules/        # Workspace bun de la raíz (solo declara frontend)
└── (16 archivos sueltos: README, CLAUDE, AGENTS, DESIGN, PRODUCT,
     ARCHITECTURE_ANALYSIS, Makefile, docker-compose.yml, pyproject.toml,
     uv.lock, package.json, bun.lock, firestore.rules, firestore.indexes.json,
     firebase-service-account.json, .env*)
```

### 2.2 Problemas identificados

1. **`scripts/` es un cajón de sastre.** Mezcla cosas de naturaleza muy distinta:
   - Orquestación del pipeline de **datos** (`run_pipeline.sh`, `run_data_pipeline.sh`) → pertenece a `ingest`.
   - Migración de **feedback en Firestore** (`migrate_feedback_ratings.py`) → pertenece a `rag`.
   - Provisión de **infraestructura** (`ec2_*.sh`, `sagemaker-*.sh`, `install-docker-ubuntu.sh`) → infra.
   - Deploy de un HTML de **tutorial** (`deploy-tutorial-html.ps1`) → ops/infra.

2. **`utils/` es otro cajón de sastre.** Las utilidades pertenecen a módulos distintos según lo que tocan:
   - ChromaDB (almacén de `rag`): `chroma_clear.py`, `chroma_count.py`, `backfill_doc_type.py`.
   - S3 (dominio de `ingest`): `backfill_doc_type_s3.py`, `migrate_doc_type.py`, `bucket_backup.py`.
   - Diagnóstico de modelos LLM (compartido): `list_gemini_models.py`.

3. **`frontend/` está desacoplado de su backend.** El frontend Next.js consume exclusivamente la API de `rag`, pero vive a la par de ella en la raíz, como si fuera un tercer dominio independiente. Conceptualmente, **API + UI = el producto de serving**.

4. **Duplicación de código entre paquetes** (ya documentada en `ARCHITECTURE_ANALYSIS.md` §2.1, severidad Alta): `rag/core/llm_factory.py` ≈ `ingest/llm_factory.py`, y `rag/s3_client.py` ≈ `ingest/s3_client.py`.

5. **Imports rotos / mal nombrados** (deuda detectada al analizar):
   - `evaluation/ragas_eval_*.py` importan `from rag.core.generator import generate_answer`, pero **`generator.py` no existe** y **`generate_answer` no está definido en ninguna parte de `rag/`**. La evaluación está rota.
   - `tests/unit/test_generator.py` no prueba ningún “generator”: prueba `rag.core.tools.build_context_block`. Nombre engañoso.

6. **Acoplamiento de los tests a `utils/` por ruta.** `tests/unit/test_migrate_doc_type.py` hace `from utils.migrate_doc_type import ...`. Mover `utils/` rompe ese import (cambio controlado, listado abajo).

---

## 3. Principios de diseño

1. **Separación por dominio.** El repositorio se organiza en dominios de alto nivel: **ingesta** (producir datos), **serving** (servir el producto), **infra** (desplegar) y **compartido** (código común).

2. **El dominio de serving se divide en backend y frontend.** Dentro de `rag/`, el código Python (API + agente) vive en `rag/backend/` y la UI Next.js en `rag/frontend/`. Son las dos caras del mismo producto, juntas pero claramente separadas.

3. **Colocación por función (co-location).** Cada artefacto vive junto al código al que sirve. Un script que limpia ChromaDB vive en `rag/backend/`; uno que migra objetos S3 vive en `ingest/`; uno que aprovisiona EC2 vive en `infra/`. Se elimina el concepto de carpeta “utils global”.

4. **`data/` es la frontera-contrato entre dominios.** `ingest` **escribe** en `data/` (S3); `rag` **lee** de `data/`. Por eso `data/` permanece en la raíz, como zona neutral de staging.

5. **Convención `scripts/` vs `tools/`** dentro de cada módulo:
   - **`scripts/`** → ejecutables de shell / orquestación / ops (se corren con `bash`).
   - **`tools/`** → utilidades Python de mantenimiento (importables y testeables, `python -m <pkg>.tools.<x>`).

6. **El paquete Python sigue llamándose `rag`.** Para evitar reescribir docenas de imports (`rag.api.main:app`, `rag.core.agent`, …), el paquete importable se conserva con el nombre `rag`, ahora ubicado en `rag/backend/rag/`. **Cero churn de imports en el código**; solo cambian rutas de configuración y 2 resoluciones de path basadas en `__file__` (ver §6.1).

---

## 4. Estructura objetivo

```
rag_playas/
│
├── rag/                          # ── DOMINIO: SERVING (producto) ──
│   ├── backend/                  #    Subproyecto Python (API + agente)
│   │   ├── pyproject.toml        #    (movido desde rag/pyproject.toml; name = "rag")
│   │   ├── rag/                  #    Paquete importable "rag" (imports SIN cambios)
│   │   │   ├── __init__.py
│   │   │   ├── config.py         #    ← ajustar BASE_DIR (profundidad, §6.1)
│   │   │   ├── s3_client.py      #    (→ shared/ en fase 3)
│   │   │   ├── api/              #    FastAPI (firebase_admin.py: ajustar parents, §6.1)
│   │   │   ├── core/            #    agente, retriever, vectorstore, ...
│   │   │   ├── tools/           # ← utilidades Python de rag
│   │   │   │   ├── chroma_count.py
│   │   │   │   ├── chroma_clear.py
│   │   │   │   ├── backfill_doc_type.py        # (ChromaDB)
│   │   │   │   └── migrate_feedback_ratings.py # (Firestore)
│   │   │   └── evaluation/      # ← RAGAS (import corregido, §6.2)
│   │   │       ├── ragas_eval_gemma.py
│   │   │       └── ragas_eval_ollama.py
│   │   └── tests/               # ← tests de rag (opcional, §6.4)
│   └── frontend/                 # ←  MOVIDO desde la raíz (Next.js autocontenido)
│
├── ingest/                       # ── DOMINIO: INGESTA ──
│   ├── pyproject.toml
│   ├── config.py
│   ├── loaders.py, sections*.py, splitter_and_enrich.py, ...
│   ├── pdf_to_md/
│   ├── scripts/                  # ← orquestación del pipeline de datos
│   │   └── run_pipeline.sh
│   ├── tools/                    # ← utilidades Python de ingesta (S3)
│   │   ├── backfill_doc_type_s3.py
│   │   ├── migrate_doc_type.py
│   │   └── bucket_backup.py
│   └── tests/                    # ← tests de ingest (opcional, §6.4)
│
├── shared/                       # ── DOMINIO: CÓDIGO COMÚN (fase 3, opcional) ──
│   ├── pyproject.toml
│   ├── llm_factory.py            #    única copia (dedup rag/ingest)
│   ├── s3_client.py
│   ├── config_base.py
│   └── tools/
│       └── list_gemini_models.py # ← diagnóstico LLM (era utils/)
│
├── infra/                        # ── DOMINIO: INFRAESTRUCTURA / OPS ──
│   ├── terraform/                # ← era infrastructure/
│   ├── docker/                   # ← era docker/ (Dockerfiles + nginx.conf)
│   └── scripts/                  # ← provisioning y deploy
│       ├── ec2_chroma_db.sh
│       ├── ec2_ollama_embeddings.sh
│       ├── install-docker-ubuntu.sh
│       ├── sagemaker-on_start_lifecycle.sh
│       ├── sagemaker-phi4-mini.sh
│       └── deploy-tutorial-html.ps1
│
├── docs/                         # Documentación (recibe DESIGN.md y PRODUCT.md)
├── data/                         # Staging del pipeline (frontera ingest↔rag, gitignored)
│
├── README.md  CLAUDE.md  AGENTS.md     # Permanecen en raíz (los lee el tooling)
├── Makefile  docker-compose.yml         # Orquestación a nivel repo
├── pyproject.toml  uv.lock              # Workspace uv (raíz)
└── .env  .env.example  firestore.*      # Config / secretos
```

> **Sobre `rag/backend/rag/`:** la doble aparición de `rag` es intencional y de bajo costo: `rag/backend/` es la carpeta del *subproyecto* (contiene su `pyproject.toml` y sus tests), y `rag/backend/rag/` es el *paquete Python* importable. Así se preserva `import rag.*` intacto. Quien prefiera evitarlo puede usar *src-layout* (`rag/backend/src/rag/`) o renombrar el paquete a `backend.*` (variante B2, §13) — esta última implica reescribir todos los imports.

---

## 5. Mapa de movimientos detallado

### 5.1 División de `rag/` en backend + frontend

| Origen | Destino | Notas |
|--------|---------|-------|
| `rag/` (api, core, config.py, s3_client.py, __init__.py) | `rag/backend/rag/` | El paquete importable se mantiene como `rag`. |
| `rag/pyproject.toml` | `rag/backend/pyproject.toml` | `name = "rag"` sin cambios. |
| `frontend/` (todo) | `rag/frontend/` | App Next.js completa. |
| `package.json` (raíz) | **eliminar** | Solo declaraba el workspace bun `["frontend"]`, sin deps propias. |
| `bun.lock` (raíz) | `rag/frontend/bun.lock` | El frontend pasa a ser **autocontenido**. |
| `node_modules/` (raíz) | **eliminar** | Subproducto del workspace bun de la raíz. |

### 5.2 `scripts/` → distribuido por función

| Origen | Destino | Razón |
|--------|---------|-------|
| `scripts/run_data_pipeline.sh` | `ingest/scripts/run_pipeline.sh` | Pipeline puro de datos (4 etapas de ingesta). |
| `scripts/run_pipeline.sh` | *(eliminar / fundir en Makefile)* | Es el anterior + arranque de la API. La orquestación cruzada vive en el `Makefile` (§7). |
| `scripts/migrate_feedback_ratings.py` | `rag/backend/rag/tools/migrate_feedback_ratings.py` | Migra *feedback* en Firestore → dominio de `rag`. |
| `scripts/ec2_chroma_db.sh` | `infra/scripts/ec2_chroma_db.sh` | Provisión de ChromaDB en EC2. |
| `scripts/ec2_ollama_embeddings.sh` | `infra/scripts/ec2_ollama_embeddings.sh` | Provisión de Ollama en EC2. |
| `scripts/install-docker-ubuntu.sh` | `infra/scripts/install-docker-ubuntu.sh` | Provisión del host. |
| `scripts/sagemaker-on_start_lifecycle.sh` | `infra/scripts/` | Ciclo de vida de SageMaker. |
| `scripts/sagemaker-phi4-mini.sh` | `infra/scripts/` | Arranque de modelo en SageMaker. |
| `scripts/deploy-tutorial-html.ps1` | `infra/scripts/deploy-tutorial-html.ps1` | Deploy del tutorial HTML. |

### 5.3 `utils/` → distribuido por función

| Origen | Destino | Razón (qué toca) |
|--------|---------|------------------|
| `utils/chroma_count.py` | `rag/backend/rag/tools/chroma_count.py` | ChromaDB = almacén de `rag`. |
| `utils/chroma_clear.py` | `rag/backend/rag/tools/chroma_clear.py` | ChromaDB = almacén de `rag`. |
| `utils/backfill_doc_type.py` | `rag/backend/rag/tools/backfill_doc_type.py` | Backfill de `doc_type` en chunks **de ChromaDB**. |
| `utils/backfill_doc_type_s3.py` | `ingest/tools/backfill_doc_type_s3.py` | Backfill en **S3**; importa `ingest.config` / `ingest.s3_client`. |
| `utils/migrate_doc_type.py` | `ingest/tools/migrate_doc_type.py` | Migra objetos **S3**; importa `ingest.*`. |
| `utils/bucket_backup.py` | `ingest/tools/bucket_backup.py` | Backup del bucket **S3** (usa `ingest.s3_client`). |
| `utils/list_gemini_models.py` | `shared/tools/list_gemini_models.py` | Diagnóstico de modelos LLM (común). Si no se adopta `shared/`, va a `ingest/tools/`. |

> Tras el movimiento, las utilidades se invocan como módulos del paquete:
> `python -m rag.tools.chroma_count`, `python -m ingest.tools.bucket_backup`.

### 5.4 `evaluation/`, `infrastructure/`, `docker/`, docs sueltos

| Origen | Destino | Notas |
|--------|---------|-------|
| `evaluation/ragas_eval_gemma.py` | `rag/backend/rag/evaluation/ragas_eval_gemma.py` | **Corregir import roto** `rag.core.generator` (§6.2). |
| `evaluation/ragas_eval_ollama.py` | `rag/backend/rag/evaluation/ragas_eval_ollama.py` | Ídem. |
| `evaluation/__init__.py` | `rag/backend/rag/evaluation/__init__.py` | |
| `infrastructure/*.tf` + `terraform.tfstate` | `infra/terraform/` | Renombrado `infrastructure/` → `infra/terraform/`. |
| `docker/Dockerfile.backend` | `infra/docker/Dockerfile.backend` | |
| `docker/Dockerfile.frontend` | `infra/docker/Dockerfile.frontend` | |
| `docker/nginx.conf` | `infra/docker/nginx.conf` | |
| `DESIGN.md` | `docs/DESIGN.md` | Declutter de la raíz. |
| `PRODUCT.md` | `docs/PRODUCT.md` | Declutter de la raíz. |

---

## 6. Cambios que tocan código

Esta sección recoge lo que **no** es un simple `git mv`.

### 6.1 Ajustar resoluciones de path basadas en `__file__` (obligatorio)

Dos archivos calculan la raíz del repo contando niveles desde su ubicación. Al bajar el paquete de `rag/` a `rag/backend/rag/`, su profundidad aumenta en **2 niveles**:

| Archivo | Antes | Después |
|---------|-------|---------|
| `rag/backend/rag/config.py:12` | `Path(__file__).resolve().parent.parent` | `Path(__file__).resolve().parents[3]` *(sube 2 niveles más)* |
| `rag/backend/rag/api/firebase_admin.py:20` | `Path(__file__).resolve().parents[2]` | `Path(__file__).resolve().parents[4]` |

> Estas dos líneas son **el único cambio de lógica** que exige la división backend/frontend. El resto son movimientos de archivos y ajustes de configuración. Las rutas `data/*` no se ven afectadas porque son **prefijos S3** (keys), no rutas de filesystem.
>
> **Mejora opcional (robustez):** sustituir el conteo de niveles por `find_dotenv()` de `python-dotenv`, que busca el `.env` hacia arriba y deja de ser frágil ante futuros movimientos.

### 6.2 Corregir el import roto de evaluación (obligatorio)

`evaluation/ragas_eval_*.py` hacen `from rag.core.generator import generate_answer`, pero **no existe** `rag/core/generator.py` ni `generate_answer` en el código. Al mover la evaluación hay que **reconectarla al punto de generación real** (el agente LangGraph en `rag/core/agent.py`, o un wrapper fino `generate()` sobre el grafo). Sin esto, RAGAS no corre.

> **Acción:** definir un *entrypoint* de generación estable (p. ej. `rag.core.agent.answer(query) -> (texto, fuentes)`) y apuntar ambos scripts de evaluación a él.

### 6.3 Actualizar el import del test de migración (obligatorio)

```python
# tests/unit/test_migrate_doc_type.py
- from utils.migrate_doc_type import _remap_key, plan_moves
+ from ingest.tools.migrate_doc_type import _remap_key, plan_moves
```

### 6.4 Co-locación de tests (recomendado, opcional)

Para coherencia con el principio de co-locación, dividir `tests/unit/` por dominio:

| Test | Prueba | Destino sugerido |
|------|--------|------------------|
| `test_sections_normativa.py`, `test_splitter*.py`, `test_normalize.py`, `test_metadata_csv.py`, `test_layer_prefix.py`, `test_migrate_doc_type.py` | módulos de `ingest` | `ingest/tests/` |
| `test_generator.py` (en realidad prueba `tools.build_context_block`), `test_context_block_doctype.py`, `test_retriever_balance.py`, `test_vectorstore.py` | módulos de `rag` | `rag/backend/tests/` |
| `tests/integration/test_full_pipeline.py` | extremo a extremo | `tests/integration/` (se mantiene a nivel repo) |

> Si se prefiere **menos disrupción**, los tests pueden quedarse en `tests/` a nivel raíz; solo cambia el import del §6.3. La co-locación obliga a tocar `pyproject.toml` (`testpaths` y `pythonpath`).
> **Renombrar** `test_generator.py` → `test_context_block.py` para que el nombre refleje lo que prueba.

### 6.5 Paquete `shared/` para deduplicar (recomendado, fase 3)

Resuelve `ARCHITECTURE_ANALYSIS.md` §2.1. Nuevo miembro del workspace uv con la **única** copia de `llm_factory.py`, `s3_client.py` y una `config_base.py` común. `rag` e `ingest` lo declaran como dependencia. Se aísla en una fase posterior por su impacto en imports internos y en el build de Docker.

---

## 7. Blast radius — configuración a actualizar

### `Makefile`
```make
# El paquete rag ya no está en el cwd raíz; se expone vía PYTHONPATH.
RAG_PY := PYTHONPATH=rag/backend

lint:        uv run ruff check rag/backend/rag ingest shared      # + tests co-locados
format:      uv run ruff format rag/backend/rag ingest shared
typecheck:   uv run mypy rag/backend/rag ingest shared
pipeline:    bash ingest/scripts/run_pipeline.sh                  # antes: scripts/run_pipeline.sh
app:         $(RAG_PY) uv run uvicorn rag.api.main:app --reload --port 8080
frontend:    cd rag/frontend && bun run dev                       # antes: cd frontend
bucket-backup: uv run python -m ingest.tools.bucket_backup        # antes: utils.bucket_backup
chroma-count:  $(RAG_PY) uv run python -m rag.tools.chroma_count
```

> El `cwd` se mantiene en la **raíz** del repo (no se hace `cd rag/backend`). Así `.env` y `data/` se resuelven igual, e `ingest` sigue importable desde `.`. El paquete `rag` se localiza con `PYTHONPATH=rag/backend`.

### `pyproject.toml` (raíz)
```toml
[tool.uv.workspace]
members = ["rag/backend", "ingest", "shared"]    # antes: ["rag", "ingest"]

[tool.pytest.ini_options]
pythonpath = [".", "rag/backend"]                # "." → ingest ; "rag/backend" → rag
testpaths = ["rag/backend/tests", "ingest/tests", "tests/integration"]  # si se co-localizan

[tool.ruff.lint.isort]
known-first-party = ["rag", "ingest", "shared"]
```

### `.github/workflows/ci.yml` y `tests.yml`
- `ruff check`/`format` → `rag/backend/rag ingest shared` (+ rutas de tests).
- Exportar `PYTHONPATH=rag/backend` (o configurar `pythonpath` en `pyproject.toml`) antes de `pytest`.

### `docker-compose.yml`
```yaml
backend:
  build:
    context: .
    dockerfile: infra/docker/Dockerfile.backend     # antes: docker/Dockerfile.backend
frontend:
  build:
    context: ./rag/frontend                          # antes: ./frontend
    dockerfile: ../../infra/docker/Dockerfile.frontend
nginx:
  volumes:
    - ./infra/docker/nginx.conf:/etc/nginx/conf.d/default.conf:ro   # antes: ./docker/nginx.conf
```

### `infra/docker/Dockerfile.backend`
```dockerfile
# Manifiestos del workspace (la ruta del member cambió)
COPY pyproject.toml uv.lock ./
COPY rag/backend/pyproject.toml rag/backend/      # antes: COPY rag/pyproject.toml rag/
COPY ingest/pyproject.toml ingest/
RUN uv sync --frozen --no-dev --package rag        # el package sigue llamándose "rag"
# ...
# Runtime: copiar el paquete a /app/rag para que `import rag` funcione con WORKDIR /app
COPY rag/backend/rag/ rag/                          # antes: COPY rag/ rag/
# (+ COPY shared/ shared/ si se adopta la fase 3)
CMD ["uvicorn", "rag.api.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
```

### `infra/docker/Dockerfile.frontend`
- Copia `package.json` + `bun.lock` desde el contexto `./rag/frontend` (ahora autocontenido).

### Imports / código
- `rag/backend/rag/config.py` y `…/api/firebase_admin.py`: ajustar profundidad (§6.1).
- `tests/.../test_migrate_doc_type.py`: `utils.` → `ingest.tools.` (§6.3).
- `rag/backend/rag/evaluation/ragas_eval_*.py`: corregir `rag.core.generator` (§6.2).

### Documentación
- `docs/SCRIPTS.md`: actualizar las 15 rutas a su nuevo hogar (o dividir en READMEs por módulo).
- `README.md`, `CLAUDE.md`, `AGENTS.md`: actualizar los diagramas de estructura y los comandos (`cd rag/frontend`, `PYTHONPATH=rag/backend`).

---

## 8. Plan de migración por fases

> Cada movimiento usa `git mv` para **preservar el historial**. Ejecutar en una rama (`chore/reorg-estructura`), no en `main`.

### Fase 1 — División de `rag/` en backend + frontend

```bash
# 1) Crear el subproyecto backend y mover el paquete rag dentro
mkdir -p rag/backend
git mv rag/pyproject.toml        rag/backend/pyproject.toml
# Mover el paquete python: rag/{api,core,config.py,s3_client.py,__init__.py} → rag/backend/rag/
mkdir -p rag/backend/rag
git mv rag/api rag/core rag/config.py rag/s3_client.py rag/__init__.py  rag/backend/rag/

# 2) Frontend → rag/frontend
git mv frontend rag/frontend
git rm package.json bun.lock        # workspace bun raíz; frontend pasa a autocontenido
# (regenerar rag/frontend/bun.lock con `cd rag/frontend && bun install`)
```

Luego ajustar §6.1 (2 líneas de path) y §7 (Makefile, pyproject, Dockerfiles, compose).

### Fase 2 — Distribuir scripts, tools y evaluation

```bash
# ingest
mkdir -p ingest/scripts ingest/tools
git mv scripts/run_data_pipeline.sh   ingest/scripts/run_pipeline.sh
git mv utils/backfill_doc_type_s3.py  utils/migrate_doc_type.py  utils/bucket_backup.py  ingest/tools/

# rag (dentro del paquete)
mkdir -p rag/backend/rag/tools rag/backend/rag/evaluation
git mv utils/chroma_count.py utils/chroma_clear.py utils/backfill_doc_type.py  rag/backend/rag/tools/
git mv scripts/migrate_feedback_ratings.py                                     rag/backend/rag/tools/
git mv evaluation/ragas_eval_gemma.py evaluation/ragas_eval_ollama.py evaluation/__init__.py  rag/backend/rag/evaluation/

# infra
mkdir -p infra/scripts
git mv infrastructure infra/terraform
git mv docker          infra/docker
git mv scripts/ec2_chroma_db.sh scripts/ec2_ollama_embeddings.sh \
       scripts/install-docker-ubuntu.sh scripts/sagemaker-on_start_lifecycle.sh \
       scripts/sagemaker-phi4-mini.sh scripts/deploy-tutorial-html.ps1  infra/scripts/

# docs sueltos + limpieza
git mv DESIGN.md PRODUCT.md docs/
git rm scripts/run_pipeline.sh
rmdir scripts utils evaluation 2>/dev/null || true
```

Luego: §6.2 (fix evaluación) y §6.3 (import del test).

### Fase 3 — (Opcional) Co-locación de tests (§6.4) y paquete `shared/` (§6.5)

---

## 9. Validación (checklist por fase)

- [ ] `make lint` y `make format` pasan con las nuevas rutas.
- [ ] `make test` (unit) verde — en especial `test_migrate_doc_type`.
- [ ] `PYTHONPATH=rag/backend python -c "import rag.api.main"` funciona.
- [ ] `make app` levanta la API y `.env` se carga (verificar §6.1: `config.BASE_DIR` apunta a la raíz real).
- [ ] `python -m rag.tools.chroma_count` y `python -m ingest.tools.bucket_backup` se invocan sin `ModuleNotFoundError`.
- [ ] `cd rag/frontend && bun run build` compila.
- [ ] `docker compose build && docker compose up` → `/api/health` responde.
- [ ] `git log --follow rag/backend/rag/api/main.py` y `rag/frontend/app/page.tsx` conservan el historial.
- [ ] (Fase 2) RAGAS corre contra el nuevo *entrypoint* de generación.

---

## 10. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| `.env` no se carga porque `BASE_DIR` quedó mal | API arranca sin config (claves vacías) | Aplicar §6.1 y validar con el checklist; preferir `find_dotenv()`. |
| `import rag` falla por falta de `PYTHONPATH` | `ModuleNotFoundError` en API/tests/CI | Definir `PYTHONPATH=rag/backend` en Makefile, `pythonpath` en pytest y `env` en CI. |
| Rutas hardcodeadas no detectadas | Build/deploy roto | `grep -rn "scripts/\|utils/\|infrastructure/\|docker/\|\./frontend\|COPY rag/"` antes de cerrar la rama. |
| El frontend autocontenido pierde deps del workspace raíz | `bun run build` falla | El root `package.json` no tenía dependencias propias; regenerar `bun.lock` dentro de `rag/frontend`. |
| `Dockerfile.backend` no copia `shared/` (fase 3) | Backend no arranca en contenedor | Añadir los `COPY shared/...` junto con la extracción de `shared`. |
| Mover con `mv` en vez de `git mv` | Pérdida de `blame`/`log` | Usar **siempre** `git mv`; verificar con `git log --follow`. |

---

## 11. Qué permanece en la raíz (y por qué)

| Elemento | Por qué se queda |
|----------|------------------|
| `rag/`, `ingest/`, `infra/`, `docs/`, `data/` | Los 5 dominios de primer nivel. |
| `data/` | Frontera-contrato entre `ingest` (escribe) y `rag` (lee). No pertenece a ningún módulo. |
| `README.md`, `CLAUDE.md`, `AGENTS.md` | Los lee el tooling (humano y agentes) en la raíz por convención. |
| `Makefile`, `docker-compose.yml` | Orquestación a nivel de repositorio completo. |
| `pyproject.toml`, `uv.lock` | Raíz del workspace uv (declara los members `rag/backend`, `ingest`, `shared`). |
| `.env`, `.env.example`, `.env.production` | Configuración compartida por ambos `config.py` (cargada vía ruta absoluta). |
| `firestore.rules`, `firestore.indexes.json`, `firebase-service-account.json` | Config/secreto de Firebase; el `service-account` está montado por ruta en `docker-compose.yml`. *(Opcional: agrupar `firestore.*` bajo `rag/firebase/`.)* |

---

## 12. Resumen visual antes → después

```
ANTES (13 carpetas + 16 archivos en raíz)        DESPUÉS (5 carpetas, raíz limpia)

rag/         frontend/    tests/                 rag/
ingest/      scripts/     docs/                  ├─ backend/
evaluation/  utils/       docker/                │  ├─ pyproject.toml
infrastructure/  data/    bucket-backup/         │  ├─ rag/  (api, core, config, ...)
node_modules/                                    │  │   ├─ tools/       (← utils rag + scripts rag)
                                                 │  │   └─ evaluation/  (← evaluation, import fix)
+ Makefile, docker-compose, pyproject,           │  └─ tests/
  package.json, bun.lock, DESIGN, PRODUCT,       └─ frontend/          (← frontend)
  README, CLAUDE, AGENTS, firestore.*, .env*
                                                 ingest/
                                                 ├─ pdf_to_md/ loaders.py ...
                                                 ├─ scripts/  (← run_pipeline)
                                                 └─ tools/    (← utils s3)

                                                 infra/
                                                 ├─ terraform/ (← infrastructure)
                                                 ├─ docker/    (← docker)
                                                 └─ scripts/   (← ec2/sagemaker/deploy)

                                                 docs/  (← + DESIGN, PRODUCT)
                                                 data/  (frontera ingest↔rag)
                                                 shared/  (fase 3: llm_factory, s3_client)
```

---

## 13. Variante de naming del paquete backend

La división backend/frontend está **decidida**. Queda una sub-decisión menor sobre el nombre del paquete Python, ya resuelta en esta propuesta:

- **B1 — paquete `rag` (adoptado, recomendado):** el paquete importable se conserva como `rag` en `rag/backend/rag/`. **Cero churn de imports**; solo se ajustan 2 líneas de path (§6.1) y configuración de rutas. Único “costo”: la ruta `rag/backend/rag/` repite el nombre (mitigable con *src-layout*: `rag/backend/src/rag/`).
- **B2 — paquete `backend`:** el código va directo en `rag/backend/{api,core,...}` y se importa como `backend.*` (`uvicorn backend.api.main:app`). Imports más “planos”, pero obliga a **reescribir todos los imports `rag.` → `backend.`** en código, tests, evaluación, Dockerfile, Makefile y CI. Mayor churn y riesgo, sin beneficio funcional.

Esta propuesta asume **B1**. Cambiar a B2 solo afecta el nombre del paquete y multiplica el blast radius de imports.
```
