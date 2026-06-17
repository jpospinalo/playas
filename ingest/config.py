"""Configuration for the ingest package, loaded from environment variables.

All modules in ingest/ should import their settings from here instead of
calling os.getenv() directly.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # project root
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

# Prefijos de keys S3 (espejan la estructura local anterior data/*)
# Raíces base por capa (compatibilidad). Para prefijos por tipo de documento
# usar layer_prefix(layer, doc_type).
RAW_PREFIX: str = "data/raw/"
BRONZE_PREFIX: str = "data/bronze/"
SILVER_PREFIX: str = "data/silver/"
GOLD_PREFIX: str = "data/gold/"

# Tipos de documento soportados, diferenciados por subcarpeta.
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


# ── Gemini ─────────────────────────────────────────────────────────────────
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
GEMINI_ENRICHER_MODEL: str = os.getenv("GEMINI_ENRICHER_MODEL", GEMINI_MODEL)

# ── OpenAI ──────────────────────────────────────────────────────────────────
OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY") or None
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
OPENAI_ENRICHER_MODEL: str = os.getenv("OPENAI_ENRICHER_MODEL", OPENAI_MODEL)

# ── OpenRouter ──────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str | None = os.getenv("OPENROUTER_API_KEY") or None
OPENROUTER_MODEL: str = os.getenv("OPENROUTER_MODEL", "gpt-5.4-mini")
OPENROUTER_ENRICHER_MODEL: str = os.getenv("OPENROUTER_ENRICHER_MODEL", OPENROUTER_MODEL)
