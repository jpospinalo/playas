"""Central configuration for the RAG package, loaded from environment variables.

All modules in rag/ should import their settings from here instead of
calling os.getenv() directly.

Resolución de ``.env``: este módulo ya no depende de
``load_dotenv(BASE_DIR / ".env")`` con ``BASE_DIR = Path(__file__).resolve()
.parent.parent`` — dos niveles arriba de ``config.py`` (``rag/backend/rag/
config.py``), lo que resuelve a ``rag/backend/.env``. Ese archivo nunca
existió: el ``.env`` real vive en ``rag/.env`` (junto a ``.env.example``),
un nivel más arriba. Ese ``load_dotenv()`` con ruta explícita no busca hacia
arriba —a diferencia de ``load_dotenv()`` sin argumentos, que sí camina el
árbol de directorios—, así que esa llamada era, en la práctica, un no-op:
las constantes de este módulo terminaban leyendo ``rag/.env`` solo si algún
otro módulo con su propio ``load_dotenv()`` correcto (p. ej.
``core/retriever.py`` o ``core/vectorstore.py``) ya se había importado
antes en el mismo proceso y había poblado ``os.environ`` como efecto
secundario — una dependencia implícita del orden de import, nunca
garantizada. Las constantes ``CHROMA_*``/``OLLAMA_*`` de este archivo se
resuelven hoy de forma confiable sin depender de ese orden:
``core/retriever.py``, ``core/vectorstore.py`` y ``core/embeddings.py`` las
importan directamente desde aquí.

Nueva resolución, en este orden:
  1. ``RAG_ENV_FILE`` si está definida — falla ruidosamente
     (``FileNotFoundError``) si apunta a un archivo inexistente, en vez de
     continuar en silencio con otra fuente.
  2. ``.env`` en el directorio de trabajo actual (cubre ``make``/``uv run``
     desde ``rag/``, el caso más común).
  3. ``.env`` en la raíz de este workspace (``rag/``), localizada subiendo
     desde este archivo hasta encontrar el marcador único
     ``pyproject.toml`` + subdirectorio ``backend/`` co-ubicados —
     verificado único en este repo: ``rag/pyproject.toml`` tiene un
     ``backend/`` al lado; ``rag/backend/pyproject.toml`` no tiene su
     propio ``backend/``; ``ingesta/pyproject.toml`` no tiene ningún
     ``backend/``. Cubre importar el paquete con un cwd distinto a
     ``rag/`` (tests, un proceso lanzado desde la raíz del repo).

Si ninguna de las tres existe, no se carga ningún ``.env`` — igual que el
comportamiento histórico de python-dotenv cuando no encuentra nada; las
variables ya presentes en el proceso (Docker, ECS, CI) siguen funcionando.
"""

import os
from pathlib import Path
from typing import Literal, cast

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # rag/backend — se mantiene
# por compatibilidad de nombre para quien ya lo importe, pero YA NO se usa
# para resolver el .env (ver _resolve_env_file más abajo).


def _find_repo_root(start: Path) -> Path | None:
    """Sube desde ``start`` hasta encontrar un directorio con ``pyproject.toml``
    y un subdirectorio ``backend/`` a la vez — la combinación que identifica
    de forma única la raíz de este workspace (``rag/``) en este repo. ``None``
    si llega a la raíz del filesystem sin encontrarlo.
    """
    current = start
    while True:
        if (current / "pyproject.toml").is_file() and (current / "backend").is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _resolve_env_file() -> Path | None:
    """Ver la resolución documentada en el docstring del módulo."""
    env_file = os.getenv("RAG_ENV_FILE")
    if env_file:
        path = Path(env_file)
        if not path.is_file():
            raise FileNotFoundError(
                f"RAG_ENV_FILE apunta a '{env_file}', que no existe o no es un archivo."
            )
        return path

    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        return cwd_env

    repo_root = _find_repo_root(Path(__file__).resolve())
    if repo_root is not None:
        root_env = repo_root / ".env"
        if root_env.is_file():
            return root_env

    return None


def _env(*names: str, default: str | None = None) -> str | None:
    """Primera variable de entorno con valor no vacío entre ``names``, en
    orden de precedencia; ``default`` si ninguna tiene valor. Una variable
    definida pero vacía o solo espacios cuenta como no definida — evita que
    un ``FOO=`` accidental en un ``.env`` o en la interpolación de
    docker-compose pise en silencio el valor por defecto."""
    for name in names:
        value = os.getenv(name)
        if value is not None and value.strip():
            return value
    return default


_env_file = _resolve_env_file()
if _env_file is not None:
    load_dotenv(_env_file)

# ── S3 ─────────────────────────────────────────────────────────────────────
S3_BUCKET_NAME: str = os.getenv("S3_BUCKET_NAME", "")
GOLD_PREFIX: str = "data/gold/"

# Tipos de documento soportados, diferenciados por subcarpeta.
# Definidos localmente: rag/ e ingest/ son paquetes independientes y no se importan
# entre sí. Mantener sincronizado con ingest/config.py.
DOC_TYPES: tuple[str, str] = ("jurisprudencia", "normativa")

# Capas del pipeline de ingesta.
LAYERS: tuple[str, ...] = ("raw", "bronze", "silver", "gold")


def layer_prefix(layer: str, doc_type: str) -> str:
    """Devuelve el prefijo S3 para una capa y tipo de documento, p.ej. 'data/bronze/normativa/'."""
    if layer not in LAYERS:
        raise ValueError(f"Capa inválida: {layer!r}. Debe ser una de {LAYERS}.")
    if doc_type not in DOC_TYPES:
        raise ValueError(f"Tipo de documento inválido: {doc_type!r}. Debe ser uno de {DOC_TYPES}.")
    return f"data/{layer}/{doc_type}/"


# ── Chroma ─────────────────────────────────────────────────────────────────
# CHROMA_COLLECTION tiene precedencia sobre el alias legado CHROMA_COLLECTION_NAME
# (mismo orden que ya usan core/retriever.py y core/vectorstore.py).
CHROMA_HOST: str = cast(str, _env("CHROMA_HOST", default="localhost"))
CHROMA_PORT: int = int(cast(str, _env("CHROMA_PORT", default="8000")))
CHROMA_COLLECTION: str = cast(
    str, _env("CHROMA_COLLECTION", "CHROMA_COLLECTION_NAME", default="rag_playas")
)

# ── Ollama ─────────────────────────────────────────────────────────────────
# OLLAMA_BASE_URL/OLLAMA_EMBEDDING_MODEL tienen precedencia sobre los alias
# legados OLLAMA_EMBED_BASE_URL/OLLAMA_EMBED_MODEL (mismo orden que ya usa
# core/embeddings.py).
OLLAMA_BASE_URL: str = cast(
    str, _env("OLLAMA_BASE_URL", "OLLAMA_EMBED_BASE_URL", default="http://localhost:11434")
)
OLLAMA_EMBEDDING_MODEL: str = cast(
    str,
    _env("OLLAMA_EMBEDDING_MODEL", "OLLAMA_EMBED_MODEL", default="embeddinggemma:latest"),
)
# Reranker opcional (OllamaReranker en core/retriever.py; no usado en el flujo
# principal). Sin valor por defecto — igual que retriever.py hoy, que exige
# ambas variables explícitamente y falla si faltan; un default aquí
# habilitaría en silencio un reranker que nadie configuró. OLLAMA_RERANK_MODEL
# es el nombre realmente usado por retriever.py; OLLAMA_RERANKER_MODEL se
# conserva como alias secundario por compatibilidad con configuraciones
# existentes.
OLLAMA_RERANK_BASE_URL: str | None = _env("OLLAMA_RERANK_BASE_URL")
OLLAMA_RERANK_MODEL: str | None = _env("OLLAMA_RERANK_MODEL", "OLLAMA_RERANKER_MODEL")

# ── Gemini ─────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

# ── OpenAI ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY") or None
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")

# ── OpenRouter ──────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY") or None
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "gpt-5.4-mini")

# ── Query enrichment ────────────────────────────────────────────────────────
QUERY_ENRICHMENT_ENABLED: bool = os.getenv("QUERY_ENRICHMENT_ENABLED", "true").lower() == "true"
# QUERY_ENRICHMENT_HYDE y DEFAULT_K/DEFAULT_K_CANDIDATES no existen en este
# módulo: ningún módulo de api/, core/, evaluation/, scripts/ ni utils/ las
# lee — código muerto demostrable, retirado. La generación HyDE nunca se
# conectó al enriquecimiento real; el `k`/`k_candidates` que sí se usan en
# el flujo de retrieval vienen del `QueryRequest` de la API y de los
# defaults inline de `agent.py::retrieve_forced_node`, nunca de estas
# constantes. Ver `tests/unit/test_config_no_dead_code.py`.

# ── Contexto de conversación ────────────────────────────────────────────────
# Ventana de contexto del modelo de generación (tokens). Ajustar según el
# modelo activo; los avisos del frontend se derivan de este valor.
CONTEXT_LIMIT_TOKENS: int = int(os.getenv("CONTEXT_LIMIT_TOKENS", "200000"))

# ── Protección de consultas RAG ─────────────────────────────────────────────
# off: sin cambio funcional; observe: solo registra; enforce: responde 429.
_rate_limit_mode = os.getenv("RAG_RATE_LIMIT_MODE", "off").strip().lower()
RateLimitMode = Literal["off", "observe", "enforce"]
RATE_LIMIT_MODE: RateLimitMode = (
    cast(RateLimitMode, _rate_limit_mode)
    if _rate_limit_mode in {"off", "observe", "enforce"}
    else "off"
)
RATE_LIMIT_REQUESTS: int = int(os.getenv("RAG_RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SECONDS: float = float(os.getenv("RAG_RATE_LIMIT_WINDOW_SECONDS", "60"))

# ── Protección de generación de título con IA ───────────────────────────────
# Límite independiente del de consultas RAG: mismo modelo (off/observe/enforce),
# pero con su propia ventana, ya que generar título es una operación distinta
# y más barata. off por defecto: sin cambio funcional.
_title_rate_limit_mode = os.getenv("TITLE_RATE_LIMIT_MODE", "off").strip().lower()
TITLE_RATE_LIMIT_MODE: RateLimitMode = (
    cast(RateLimitMode, _title_rate_limit_mode)
    if _title_rate_limit_mode in {"off", "observe", "enforce"}
    else "off"
)
TITLE_RATE_LIMIT_REQUESTS: int = int(os.getenv("TITLE_RATE_LIMIT_REQUESTS", "5"))
TITLE_RATE_LIMIT_WINDOW_SECONDS: float = float(os.getenv("TITLE_RATE_LIMIT_WINDOW_SECONDS", "60"))

# ── Protección de login ──────────────────────────────────────────────────────
# Límite reversible sobre /api/auth/login, independiente de los anteriores.
# La clave combina el email normalizado y la IP de origen (ver routes/auth.py);
# request.client.host no considera un proxy de confianza (no hay política de
# X-Forwarded-For configurada), así que enforce no debe activarse en entornos
# detrás de un proxy/LB sin revisar esa política primero. off por defecto.
_auth_rate_limit_mode = os.getenv("AUTH_RATE_LIMIT_MODE", "off").strip().lower()
AUTH_RATE_LIMIT_MODE: RateLimitMode = (
    cast(RateLimitMode, _auth_rate_limit_mode)
    if _auth_rate_limit_mode in {"off", "observe", "enforce"}
    else "off"
)
AUTH_RATE_LIMIT_REQUESTS: int = int(os.getenv("AUTH_RATE_LIMIT_REQUESTS", "10"))
AUTH_RATE_LIMIT_WINDOW_SECONDS: float = float(os.getenv("AUTH_RATE_LIMIT_WINDOW_SECONDS", "300"))

# ── Backpressure de concurrencia ─────────────────────────────────────────
# Distinto del rate limiting de arriba: esos limitan CUÁNTAS solicitudes por
# ventana de tiempo puede hacer una MISMA clave (usuario/IP/email). Esto
# limita cuántas consultas RAG pueden estar EN VUELO simultáneamente en todo
# el proceso, sin importar de qué usuario sean — protege a Chroma/Ollama/el
# proveedor LLM de saturarse bajo carga concurrente alta, no bajo ráfagas de
# un mismo usuario. Reusa el mismo modelo off/observe/enforce por
# consistencia, pero es un mecanismo distinto (semáforo de concurrencia, no
# ventana deslizante) — ver rag.api.rate_limit.ConcurrencyBackpressure.
# off por defecto: sin cambio funcional.
_backpressure_mode = os.getenv("RAG_BACKPRESSURE_MODE", "off").strip().lower()
BACKPRESSURE_MODE: RateLimitMode = (
    cast(RateLimitMode, _backpressure_mode)
    if _backpressure_mode in {"off", "observe", "enforce"}
    else "off"
)
BACKPRESSURE_MAX_CONCURRENT: int = int(os.getenv("RAG_BACKPRESSURE_MAX_CONCURRENT", "20"))

# ── Base de datos ────────────────────────────────────────────────────────────
# Centralizada aquí, no como `os.getenv("DATABASE_URL", ...)` a nivel de
# módulo en api/database.py: api/rate_limit.py importa api/auth.py (que
# importa api/database.py) ANTES de importar este módulo — si
# api/database.py leyera DATABASE_URL directamente y se importara primero
# en el proceso (como ocurre al importar rag.api.main), esa constante
# quedaría fijada a partir de os.environ *antes* de que el .env resuelto
# por RAG_ENV_FILE se hubiera cargado. Centralizarla aquí garantiza que
# cualquier módulo que la use dispare primero la carga del .env de este
# archivo, sin importar el orden de imports.
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/atlas.db")

# ── Autenticación JWT ──────────────────────────────────────────────────────
# Mismo problema de orden de imports que DATABASE_URL (ver arriba):
# api/auth.py leería JWT_ALGORITHM/JWT_EXPIRE_MINUTES con os.getenv()
# directo si no estuvieran centralizadas aquí. JWT_SECRET_KEY se deja fuera
# a propósito: auth.py ya lo lee de forma perezosa dentro de una función
# (_secret()), evaluada en cada request, no al importar el módulo — no
# sufre este bug, y no hay razón para mover una constante sensible sin
# necesidad.
JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 días

# ── Registro de nuevas cuentas ─────────────────────────────────────────────
# api/routes/auth.py se importa en main.py después de que algo más ya
# fuerza la carga de este módulo, así que en la práctica no sufriría el
# mismo bug de orden que DATABASE_URL/JWT_* — se centraliza aquí de todas
# formas por consistencia, con el mismo default y el mismo parseo exacto.
REGISTER_ENABLED: bool = os.getenv("REGISTER_ENABLED", "false").lower() == "true"
