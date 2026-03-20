# Improvements — Poe-RAG

Hoja de ruta técnica para llevar el proyecto a un estado de producción profesional. Cubre estructura, corrección de bugs, calidad de código, testing, CI/CD y documentación.

---

## Tabla de contenidos

1. [Estructura del proyecto](#1-estructura-del-proyecto)
2. [Gestión de dependencias con `uv`](#2-gestión-de-dependencias-con-uv)
3. [Bugs críticos a corregir](#3-bugs-críticos-a-corregir)
4. [Calidad de código — Linting, formateo y tipos](#4-calidad-de-código--linting-formateo-y-tipos)
5. [Tests con GitHub Actions](#5-tests-con-github-actions)
6. [Configuración centralizada](#6-configuración-centralizada)
7. [Testing](#7-testing)
8. [CI/CD con GitHub Actions](#8-cicd-con-github-actions)
9. [Correcciones de documentación](#9-correcciones-de-documentación)
10. [Mejoras en `.gitignore` y `.env.example`](#10-mejoras-en-gitignore-y-envexample)
11. [Makefile](#11-makefile)

---

## 1. Estructura del proyecto

### Estructura actual

```
poe_rag/
├── pyproject.toml
├── uv.lock
├── requirements.txt
├── .python-version
├── .env.example
├── .gitignore
├── README.md
├── Improvements.md
│
├── data/
│   ├── bronze/
│   ├── silver/
│   │   └── chunked/
│   └── gold/
│
├── src/
│   ├── ingest/
│   │   ├── loaders.py
│   │   ├── normalize.py
│   │   ├── spliter.py          ← typo
│   │   ├── enrich.py
│   │   └── utils.py
│   ├── backend/
│   │   ├── vectorstore.py
│   │   ├── retriever.py
│   │   └── generator.py
│   └── frontend/
│       └── gradio_app.py
│
├── scripts/
│   ├── ec2_chorma_db.sh        ← typo
│   ├── ec2_ollama_embeddings.sh
│   ├── sagemaker-on_start_lifecycle.sh
│   └── sagemaker-phi4-mini.sh
│
└── evaluation/
    ├── ragas_eval_gemma.py
    ├── ragas_eval_ollama.py
    ├── ragas_eval_dataset.json
    └── ragas_eval_summary.json
```

### Estructura propuesta

```
poe_rag/
├── pyproject.toml               ← dependencias directas + dev-deps + tool config
├── uv.lock
├── requirements.txt             ← generado con `uv export`
├── .python-version
├── .env.example                 ← incluye vars de evaluación
├── .gitignore                   ← incluye data/silver, data/gold
├── .pre-commit-config.yaml      ← nuevo: hooks de calidad
├── README.md                    ← rutas de módulos corregidas
├── Improvements.md
├── Makefile                     ← nuevo: comandos estándar
│
├── data/
│   ├── bronze/
│   ├── silver/
│   │   └── chunked/
│   └── gold/
│
├── src/
│   ├── __init__.py              ← nuevo
│   ├── config.py                ← nuevo: configuración centralizada
│   ├── ingest/
│   │   ├── __init__.py          ← nuevo
│   │   ├── loaders.py
│   │   ├── normalize.py
│   │   ├── splitter.py          ← renombrado desde spliter.py
│   │   ├── enrich.py
│   │   └── utils.py
│   ├── backend/
│   │   ├── __init__.py          ← nuevo
│   │   ├── vectorstore.py
│   │   ├── retriever.py
│   │   └── generator.py
│   └── frontend/
│       ├── __init__.py          ← nuevo
│       └── gradio_app.py
│
├── scripts/
│   ├── ec2_chroma_db.sh         ← renombrado desde ec2_chorma_db.sh
│   ├── ec2_ollama_embeddings.sh
│   ├── sagemaker-on_start_lifecycle.sh
│   ├── sagemaker-phi4-mini.sh
│   └── run_pipeline.sh          ← nuevo: pipeline completo de un solo comando
│
├── evaluation/
│   ├── __init__.py              ← nuevo
│   ├── ragas_eval_gemma.py
│   ├── ragas_eval_ollama.py
│   ├── ragas_eval_dataset.json
│   └── ragas_eval_summary.json
│
├── tests/                       ← nuevo
│   ├── __init__.py
│   ├── conftest.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_normalize.py
│   │   ├── test_splitter.py
│   │   ├── test_vectorstore.py
│   │   └── test_generator.py
│   └── integration/
│       ├── __init__.py
│       └── test_full_pipeline.py
│
└── docs/
    └── architecture.md          ← nuevo: descripción del pipeline RAG
```

---

## 2. Gestión de dependencias con `uv`

### Instalación y uso

```bash
# Instalar uv (una vez)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Instalar dependencias (crea .venv si no existe)
uv sync

# Instalar también dependencias de desarrollo
uv sync --dev

# Ejecutar el pipeline por etapas
uv run python -m src.ingest.loaders
uv run python -m src.ingest.splitter
uv run python -m src.ingest.enrich
uv run python -m src.backend.vectorstore
uv run python -m src.frontend.gradio_app

# O ejecutar el pipeline completo
bash scripts/run_pipeline.sh
```

### Mejora del `pyproject.toml`

El `pyproject.toml` actual lista todas las dependencias transitivas como si fueran directas. El estándar es listar **solo las dependencias directas** del proyecto y dejar que `uv.lock` gestione las transitivas.

Además, deben separarse las dependencias de desarrollo:

```toml
[project]
name = "poe-rag"
version = "0.1.0"
description = "RAG system over Edgar Allan Poe's short stories"
requires-python = ">=3.12"
dependencies = [
    "docling>=2.0",
    "langchain>=0.3",
    "langchain-google-genai>=3.0",
    "langchain-chroma>=1.0",
    "langchain-ollama>=0.2",
    "langchain-docling>=2.0",
    "google-genai>=1.0",
    "chromadb>=1.0",
    "rank-bm25>=0.2",
    "gradio>=5.0",
    "ragas>=0.4",
    "pydantic>=2.0",
    "python-dotenv>=1.0",
    "rich>=13.0",
]

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-v --tb=short"
markers = [
    "integration: tests that require live external services (Chroma, Ollama, Gemini)",
]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "UP", "B"]
ignore = ["E501"]

```

---

## 3. Bugs críticos a corregir

### 3.1 `TypeError` al leer `CHROMA_PORT` sin valor

**Archivos afectados:** `src/backend/vectorstore.py` y `src/backend/retriever.py`

**Problema:** `int(os.getenv("CHROMA_PORT"))` lanza `TypeError: int() argument must be a string, not 'NoneType'` cuando la variable no está definida.

**Corrección:**

```python
# Antes
port = int(os.getenv("CHROMA_PORT"))

# Después
port = int(os.getenv("CHROMA_PORT", "8000"))
```

### 3.2 `RuntimeError` al importar `generator.py` sin `GOOGLE_API_KEY`

**Archivo:** `src/backend/generator.py`

**Problema:** El LLM se inicializa en el cuerpo del módulo (nivel de importación). Cualquier `import` del módulo falla con `RuntimeError` si `GOOGLE_API_KEY` no está en el entorno, incluso en tests o scripts auxiliares.

**Corrección:** Mover la inicialización dentro de una función `_get_llm()` con caché:

```python
from functools import lru_cache
from langchain_google_genai import ChatGoogleGenerativeAI

@lru_cache(maxsize=1)
def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        temperature=0.0,
    )

def build_rag_chain(k_candidates: int = 10):
    llm = _get_llm()
    # ...
```

### 3.3 Implementación duplicada de `OllamaEmbeddings`

**Archivos:** `src/backend/vectorstore.py` (`OllamaEmbeddingFunction`) y `src/backend/retriever.py` (`OllamaEmbeddings`)

**Problema:** Ambas clases hacen exactamente la misma llamada HTTP a `/api/embeddings` de Ollama con código duplicado.

**Corrección:** Extraer una única implementación en `src/backend/embeddings.py` e importarla desde ambos módulos:

```python
# src/backend/embeddings.py
import os
import requests
from chromadb import EmbeddingFunction
from langchain_core.embeddings import Embeddings


class OllamaEmbeddingClient:
    """Shared HTTP client for Ollama embeddings."""

    def __init__(self) -> None:
        self.base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.model, "prompt": texts[0]},
        )
        response.raise_for_status()
        return [response.json()["embedding"]]


class OllamaEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible embedding function backed by Ollama."""

    def __init__(self) -> None:
        self._client = OllamaEmbeddingClient()

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._client.embed([text])[0] for text in input]


class OllamaEmbeddings(Embeddings):
    """LangChain-compatible embeddings backed by Ollama."""

    def __init__(self) -> None:
        self._client = OllamaEmbeddingClient()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._client.embed([t])[0] for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed([text])[0]
```

### 3.4 Código de depuración en `gradio_app.py`

**Archivo:** `src/frontend/gradio_app.py`

**Problema:** La función `list_models()` y la importación `from google import genai` están definidas fuera de cualquier bloque guard al final del módulo. Son restos de depuración que no deben estar en producción.

**Corrección:** Moverlos a un script de utilidades separado en `scripts/`.

### 3.5 Orden de iteración no determinista en `enrich.py`

**Archivo:** `src/ingest/enrich.py`

**Problema:** `os.listdir()` devuelve archivos en orden arbitrario según el sistema de ficheros. Esto hace que el enriquecimiento no sea reproducible entre ejecuciones.

**Corrección:**

```python
# Antes
for file_name in os.listdir(chunked_dir):

# Después
for file_name in sorted(os.listdir(chunked_dir)):
```

---

## 4. Calidad de código — Linting, formateo y tipos

### Ruff (linter + formatter)

[Ruff](https://docs.astral.sh/ruff/) reemplaza a `flake8`, `isort` y `black` en una sola herramienta, con rendimiento ~100x superior.

```bash
# Verificar errores
uv run ruff check src/ tests/ evaluation/

# Corregir automáticamente
uv run ruff check --fix src/ tests/ evaluation/

# Formatear código
uv run ruff format src/ tests/ evaluation/
```

---

## 5. Tests con GitHub Actions

Workflow dedicado a ejecutar los tests automáticamente en cada push y pull request. Se separa intencionalmente del workflow de calidad de código (sección 8) para que fallen de forma independiente y el feedback sea más claro.

### `.github/workflows/tests.yml`

```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    name: Unit Tests (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
          cache-dependency-glob: "uv.lock"

      - name: Set up Python ${{ matrix.python-version }}
        run: uv python install ${{ matrix.python-version }}

      - name: Install dependencies
        run: uv sync --dev

      - name: Run unit tests
        run: uv run pytest tests/unit/ -v --tb=short --cov=src --cov-report=xml --cov-report=term-missing

      - name: Upload coverage report
        uses: codecov/codecov-action@v4
        if: matrix.python-version == '3.12'
        with:
          file: coverage.xml
          flags: unit
          fail_ci_if_error: false

```

### Notas sobre el workflow

- Se ejecuta en todos los push y pull requests sobre `main` y `develop`.
- No requiere ningún servicio externo ni credenciales: los tests unitarios usan mocks para ChromaDB, Ollama y Gemini.
- El caché de `uv` (`enable-cache: true`) usa el `uv.lock` como clave, por lo que las dependencias solo se reinstalan cuando el lockfile cambia.
- La cobertura se sube a Codecov solo desde `python-version: 3.12` para evitar reportes duplicados.

---

## 6. Configuración centralizada

### Problema actual

Cada módulo llama a `os.getenv()` directamente con valores por defecto inconsistentes o sin ningún valor por defecto, y la lista de variables de entorno del proyecto no está documentada en un solo lugar.

### Solución: `src/config.py`

```python
# src/config.py
"""Central configuration loaded from environment variables.

All modules should import their settings from here instead of
calling os.getenv() directly.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
CHUNKED_DIR = SILVER_DIR / "chunked"
GOLD_DIR = DATA_DIR / "gold"

# ── Chroma ─────────────────────────────────────────────────────────────────
CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "poe_rag")

# ── Ollama ─────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
OLLAMA_RERANKER_MODEL: str = os.getenv("OLLAMA_RERANKER_MODEL", "mistral")

# ── Gemini ─────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_ENRICHER_MODEL: str = os.getenv("GEMINI_ENRICHER_MODEL", "gemini-2.0-flash")

# ── Retriever ──────────────────────────────────────────────────────────────
DEFAULT_K: int = int(os.getenv("DEFAULT_K", "4"))
DEFAULT_K_CANDIDATES: int = int(os.getenv("DEFAULT_K_CANDIDATES", "10"))
```

Con este módulo, los imports en el resto del código pasan de:

```python
# Antes (disperso, frágil)
host = os.getenv("CHROMA_HOST", "localhost")
port = int(os.getenv("CHROMA_PORT"))  # bug: sin default
```

```python
# Después (centralizado, seguro)
from src.config import CHROMA_HOST, CHROMA_PORT
```

---

## 7. Testing

### 7.1 Dependencias de desarrollo

Añadir en `pyproject.toml` (ver sección [2](#2-gestión-de-dependencias-con-uv)):

```toml
[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.8",
]
```

### 7.2 Estructura de tests

```
tests/
├── __init__.py
├── conftest.py               ← fixtures compartidas
├── unit/
│   ├── __init__.py
│   ├── test_normalize.py     ← sin dependencias externas
│   ├── test_splitter.py      ← sin dependencias externas
│   ├── test_vectorstore.py   ← probar sanitize_metadata (pura)
│   └── test_generator.py     ← mockear ChatGoogleGenerativeAI
└── integration/
    ├── __init__.py
    └── test_full_pipeline.py ← requiere Chroma, Ollama, Gemini
```

### 7.3 Cobertura por módulo

| Módulo | Qué probar | Requiere mock |
|--------|------------|---------------|
| `normalize.py` | `normalize_text`, `normalize_metadata`, `normalize_documents` | No |
| `splitter.py` | Tamaño de chunks, overlap correcto, metadata propagada | No |
| `utils.py` | `save_docs_jsonl_per_file`, `load_all_docs_from_dir` (con tmp dir) | No |
| `vectorstore.py` | `sanitize_metadata`, `load_gold_documents` | No |
| `generator.py` | Construcción del prompt, `build_rag_chain` | Sí (LLM) |
| `retriever.py` | RRF fusion, formato de salida de `HybridEnsembleRetriever` | Sí (Chroma, Ollama) |
| `gradio_app.py` | `format_context`, `format_sources`, `clean_answer` | No |

### 7.4 `conftest.py`

```python
# tests/conftest.py
import pytest
from langchain_core.documents import Document


@pytest.fixture
def sample_document() -> Document:
    return Document(
        page_content="El corazón delator. Texto de prueba para testing.",
        metadata={"source": "El_corazon_delator-Poe_Edgar_Allan.pdf"},
    )


@pytest.fixture
def sample_chunks() -> list[Document]:
    return [
        Document(
            page_content=f"Chunk {i}. Contenido de prueba.",
            metadata={
                "source": "El_cuervo-Poe_Edgar_Allan.pdf",
                "chunk_id": f"El_cuervo-Poe_Edgar_Allan_chunk_{i}",
                "chunk_index": i,
            },
        )
        for i in range(3)
    ]


@pytest.fixture
def tmp_gold_dir(tmp_path: Path) -> Path:
    """Temporary gold directory with sample JSONL files."""
    import json
    gold = tmp_path / "gold"
    gold.mkdir()
    record = {
        "page_content": "Texto de prueba.",
        "metadata": {
            "source": "test.pdf",
            "chunk_id": "test_chunk_0",
            "summary": "Resumen de prueba.",
            "keywords": ["prueba", "test"],
        },
    }
    (gold / "test.jsonl").write_text(json.dumps(record) + "\n", encoding="utf-8")
    return gold
```

### 7.5 `tests/unit/test_normalize.py`

```python
# tests/unit/test_normalize.py
from langchain_core.documents import Document
from src.ingest.normalize import normalize_documents, normalize_metadata, normalize_text


def test_normalize_text_removes_blank_lines():
    result = normalize_text("Línea 1\n\n\nLínea 2")
    assert "Línea 1" in result
    assert "Línea 2" in result
    assert "\n\n" not in result


def test_normalize_text_removes_noise_phrases():
    text = "Contenido útil\nVisitado en elejandria.com\nMás contenido"
    result = normalize_text(text)
    assert "elejandria" not in result.lower()


def test_normalize_metadata_extracts_title_and_author():
    meta = {"source": "El_cuervo-Poe_Edgar_Allan.pdf", "extra": "ignored"}
    result = normalize_metadata(meta)
    assert result["title"] == "El cuervo"
    assert result["author"] == "Poe Edgar Allan"
    assert "extra" not in result


def test_normalize_documents_preserves_content(sample_document):
    result = normalize_documents([sample_document])
    assert len(result) == 1
    assert result[0].page_content == sample_document.page_content


def test_normalize_documents_returns_documents(sample_document):
    result = normalize_documents([sample_document])
    assert all(isinstance(d, Document) for d in result)
```

### 7.6 `tests/unit/test_splitter.py`

```python
# tests/unit/test_splitter.py
from langchain_core.documents import Document
from src.ingest.splitter import chunk_documents  # after rename


def test_chunks_have_chunk_id(sample_document):
    chunks = chunk_documents([sample_document])
    assert all("chunk_id" in c.metadata for c in chunks)


def test_chunks_have_chunk_index(sample_document):
    chunks = chunk_documents([sample_document])
    assert all("chunk_index" in c.metadata for c in chunks)


def test_chunks_preserve_source(sample_document):
    chunks = chunk_documents([sample_document])
    assert all(c.metadata["source"] == sample_document.metadata["source"] for c in chunks)


def test_chunk_content_not_empty(sample_document):
    chunks = chunk_documents([sample_document])
    assert all(len(c.page_content) > 0 for c in chunks)
```

### 7.7 Tests de integración

```python
# tests/integration/test_full_pipeline.py
import pytest


@pytest.mark.integration
def test_rag_returns_answer():
    """End-to-end test: query → RAG chain → non-empty answer."""
    from src.backend.generator import generate_answer

    answer, docs = generate_answer("¿Quién es Pluto?", k=2, k_candidates=5)
    assert isinstance(answer, str)
    assert len(answer) > 0
    assert len(docs) > 0


@pytest.mark.integration
def test_retriever_returns_relevant_docs():
    from src.backend.retriever import get_ensemble_retriever

    retriever = get_ensemble_retriever()
    docs = retriever.invoke("El corazón delator")
    assert len(docs) > 0
    assert all(hasattr(d, "page_content") for d in docs)
```

Ejecutar solo tests de integración:

```bash
uv run pytest -m integration
```

### 7.8 Comandos de testing

```bash
# Todos los tests unitarios
uv run pytest tests/unit/

# Con informe de cobertura
uv run pytest tests/unit/ --cov=src --cov-report=term-missing --cov-report=html

# Un módulo específico
uv run pytest tests/unit/test_normalize.py -v

# Tests de integración (requiere servicios activos)
uv run pytest -m integration
```

---

## 8. CI/CD con GitHub Actions

### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  quality:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --dev

      - name: Ruff lint
        run: uv run ruff check src/ tests/ evaluation/

      - name: Ruff format check
        run: uv run ruff format --check src/ tests/ evaluation/

      - name: Mypy
        run: uv run mypy src/

  test:
    name: Unit Tests
    runs-on: ubuntu-latest
    needs: quality
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        uses: astral-sh/setup-uv@v3

      - name: Install dependencies
        run: uv sync --dev

      - name: Run unit tests
        run: uv run pytest tests/unit/ --cov=src --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
```

---

## 9. Correcciones de documentación

### 9.1 README — Rutas de módulos incorrectas

| Actual en README | Correcto | Motivo |
|------------------|----------|--------|
| `python -m src.ingest.ingest` | `python -m src.ingest.loaders` | El archivo es `loaders.py`, no `ingest.py` |
| `python -m src.spliter` | `python -m src.ingest.splitter` | Ruta completa y typo corregido |
| "Python 3.10+" | "Python 3.12+" | `.python-version` y `pyproject.toml` requieren 3.12 |

### 9.2 README — Bloque de código no cerrado

El bloque de código de la sección de instalación no tiene cierre (triple backtick de cierre), lo que hace que los comandos del pipeline aparezcan dentro del bloque de código. Debe añadirse la línea de cierre correspondiente.

### 9.3 `docs/architecture.md`

Crear un diagrama textual del pipeline para facilitar la comprensión del proyecto:

```
PDFs (data/bronze/)
      │
      ▼ loaders.py (DoclingLoader + normalize)
data/silver/*.jsonl          ← documentos normalizados por fuente
      │
      ▼ splitter.py (RecursiveCharacterTextSplitter)
data/silver/chunked/*.jsonl  ← chunks con chunk_id y chunk_index
      │
      ▼ enrich.py (Gemini JSON-mode)
data/gold/*.jsonl            ← chunks + summary + keywords + entities
      │
      ▼ vectorstore.py (Ollama embeddings → ChromaDB)
ChromaDB (HTTP)              ← colección indexada
      │
      ▼ retriever.py (BM25 + Dense → RRF → Reranker)
top-k docs
      │
      ▼ generator.py (LCEL chain → Gemini)
respuesta final              ← mostrada en Gradio
```

---

## 10. Mejoras en `.gitignore` y `.env.example`

### `.gitignore` — Añadir datos generados

El `.gitignore` actual tiene la sección `# 4) Datos del RAG` pero sin entradas. Añadir:

```gitignore
# Datos generados por el pipeline
data/silver/
data/gold/
data/bronze/

# Resultados de evaluación (pueden contener datos sensibles)
evaluation/ragas_eval_dataset.json
evaluation/ragas_eval_summary.json
```

### `.env.example` — Variables de evaluación faltantes

Añadir al `.env.example` las variables que usan los scripts de evaluación pero que no están documentadas:

```dotenv
# ── Evaluación ──────────────────────────────────────────────────────────────
# Segunda API key para el juez RAGAS (evita conflictos de rate-limit con el pipeline)
GOOGLE_API_KEY2=

# Evaluación con Ollama remoto (e.g., ngrok tunnel)
OLLAMA_EVAL_BASE_URL=http://localhost:11434
OLLAMA_EVAL_MODEL=mistral
```

---

## 11. Makefile

Un `Makefile` en la raíz permite ejecutar cualquier operación del proyecto con un único comando, sin tener que recordar los flags exactos de cada herramienta.

```makefile
.PHONY: install lint format typecheck test test-cov pipeline app clean help

install:  ## Instalar dependencias (incluidas las de desarrollo)
	uv sync --dev

lint:  ## Verificar errores de estilo y lógica con ruff
	uv run ruff check src/ tests/ evaluation/

format:  ## Formatear código con ruff
	uv run ruff format src/ tests/ evaluation/

typecheck:  ## Verificar tipos con mypy
	uv run mypy src/

test:  ## Ejecutar tests unitarios
	uv run pytest tests/unit/ -v

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest tests/unit/ --cov=src --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest -m integration -v

pipeline:  ## Ejecutar el pipeline completo de ingesta
	bash scripts/run_pipeline.sh

app:  ## Lanzar la interfaz Gradio
	uv run python -m src.frontend.gradio_app

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
```

Uso:

```bash
make install        # instalar todo
make lint           # comprobar estilo
make test           # tests unitarios
make test-cov       # tests + cobertura
make pipeline       # ingestar documentos
make app            # lanzar Gradio
make help           # ver todos los comandos
```