"""Central configuration for the RAG package, loaded from environment variables.

All modules in rag/ should import their settings from here instead of
calling os.getenv() directly.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[3]  # raíz del repo (rag/backend/rag/config.py → /)
load_dotenv(BASE_DIR / ".env")

S3AddressingStyle = Literal["auto", "virtual", "path"]


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _env_with_default(name: str, default: str) -> str:
    value = _optional_env(name)
    return value if value is not None else default


def _parse_s3_addressing_style(value: str | None) -> S3AddressingStyle:
    normalized = (value or "auto").strip().lower() or "auto"
    if normalized not in {"auto", "virtual", "path"}:
        raise ValueError(
            "S3_ADDRESSING_STYLE inválido: "
            f"{normalized!r}. Debe ser 'auto', 'virtual' o 'path'."
        )
    return normalized  # type: ignore[return-value]


def _parse_s3_verify_ssl(value: str | None) -> bool | str:
    normalized = (value or "").strip()
    if not normalized:
        return True

    lowered = normalized.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return normalized

# ── S3 ─────────────────────────────────────────────────────────────────────
S3_BUCKET_NAME: str = (os.getenv("S3_BUCKET_NAME") or "").strip()
S3_ENDPOINT_URL: str | None = _optional_env("S3_ENDPOINT_URL")
S3_REGION: str = _env_with_default("S3_REGION", "us-east-1")
S3_ACCESS_KEY_ID: str | None = _optional_env("S3_ACCESS_KEY_ID")
S3_SECRET_ACCESS_KEY: str | None = _optional_env("S3_SECRET_ACCESS_KEY")
S3_SESSION_TOKEN: str | None = _optional_env("S3_SESSION_TOKEN")
S3_ADDRESSING_STYLE: S3AddressingStyle = _parse_s3_addressing_style(
    os.getenv("S3_ADDRESSING_STYLE")
)
S3_VERIFY_SSL: bool | str = _parse_s3_verify_ssl(os.getenv("S3_VERIFY_SSL"))
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
CHROMA_HOST: str = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT: int = int(os.getenv("CHROMA_PORT", "8000"))
CHROMA_COLLECTION: str = os.getenv("CHROMA_COLLECTION", "rag_playas")

# ── Ollama ─────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_EMBEDDING_MODEL: str = os.getenv("OLLAMA_EMBEDDING_MODEL", "embeddinggemma:latest")
OLLAMA_RERANKER_MODEL: str = os.getenv("OLLAMA_RERANKER_MODEL", "mistral")

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
QUERY_ENRICHMENT_HYDE: bool = os.getenv("QUERY_ENRICHMENT_HYDE", "false").lower() == "true"

# ── Retriever ──────────────────────────────────────────────────────────────
DEFAULT_K: int = int(os.getenv("DEFAULT_K", "4"))
DEFAULT_K_CANDIDATES: int = int(os.getenv("DEFAULT_K_CANDIDATES", "10"))

# ── Contexto de conversación ────────────────────────────────────────────────
# Ventana de contexto del modelo de generación (tokens). Ajustar según el
# modelo activo; los avisos del frontend se derivan de este valor.
CONTEXT_LIMIT_TOKENS: int = int(os.getenv("CONTEXT_LIMIT_TOKENS", "200000"))
