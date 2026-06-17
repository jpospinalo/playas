"""Fábrica de proveedores LLM para el pipeline de ingest.

Centraliza la selección del LLM usado en el enriquecimiento (silver → gold).
Orden de selección (primera clave disponible gana):
1. ``OPENAI_API_KEY``     → :class:`OpenAIProvider`
2. ``OPENROUTER_API_KEY`` → :class:`OpenRouterProvider`
3. ``GOOGLE_API_KEY``     → :class:`GeminiProvider`
4. Ninguna configurada    → :exc:`RuntimeError`
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseChatModel
from langchain_core.outputs import LLMResult

# ---------------------------------------------------------------------------
# Token usage logging callback
# ---------------------------------------------------------------------------


def _fmt_tok(n: int | None) -> str:
    return "?" if n is None else str(n)


def _extract_in_out_tokens(response: LLMResult) -> tuple[int | None, int | None]:
    llm_out: dict[str, Any] = response.llm_output or {}

    tu: dict[str, Any] = llm_out.get("token_usage") or {}
    pt: int | None = tu.get("prompt_tokens")
    ct: int | None = tu.get("completion_tokens")
    if pt is not None or ct is not None:
        return pt, ct

    meta: dict[str, Any] = llm_out.get("usage_metadata") or {}
    it = meta.get("input_token_count") or meta.get("prompt_token_count")
    ot = meta.get("output_token_count") or meta.get("candidates_token_count")
    if it is not None or ot is not None:
        return it, ot  # type: ignore[return-value]

    try:
        gen0 = response.generations[0][0]
        msg = getattr(gen0, "message", None)
        if msg is not None:
            um = getattr(msg, "usage_metadata", None)
            if isinstance(um, dict):
                inp = um.get("input_tokens")
                out = um.get("output_tokens")
                if inp is not None or out is not None:
                    return inp, out
            rm = getattr(msg, "response_metadata", None) or {}
            if isinstance(rm, dict):
                tu2: dict[str, Any] = rm.get("token_usage") or {}
                pt2 = tu2.get("prompt_tokens")
                ct2 = tu2.get("completion_tokens")
                if pt2 is not None or ct2 is not None:
                    return pt2, ct2
    except (IndexError, TypeError):
        pass

    return None, None


class TokenUsageLogger(BaseCallbackHandler):
    def __init__(self, model_name: str, use_case: str = "") -> None:
        super().__init__()
        self._model_name = model_name
        self._use_case = use_case

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        inp, out = _extract_in_out_tokens(response)
        line = (
            f"LLM | {self._use_case} | model={self._model_name} | "
            f"in={_fmt_tok(inp)} | out={_fmt_tok(out)}"
        )
        logging.getLogger("ingest").info(line)


# ---------------------------------------------------------------------------
# Abstract provider contract
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    def supports_system_role(self) -> bool:
        return True

    @property
    def supports_structured_output(self) -> bool:
        return True

    @abstractmethod
    def create_llm(self, temperature: float, use_case: str = "") -> BaseChatModel: ...


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        from ingest import config

        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY no está configurada. "
                "Agrégala a tu archivo .env antes de usar OpenAI."
            )
        self._api_key = config.OPENAI_API_KEY
        self._model = config.OPENAI_ENRICHER_MODEL

    @property
    def model_name(self) -> str:
        return self._model

    def create_llm(self, temperature: float, use_case: str = "") -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self._model,
            temperature=temperature,
            api_key=self._api_key,  # type: ignore[arg-type]
            stream_usage=True,
            callbacks=[TokenUsageLogger(self._model, use_case)],
        )


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------


class OpenRouterProvider(LLMProvider):
    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self) -> None:
        from ingest import config

        if not config.OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY no está configurada. "
                "Agrégala a tu archivo .env antes de usar OpenRouter."
            )
        self._api_key = config.OPENROUTER_API_KEY
        self._model = config.OPENROUTER_ENRICHER_MODEL

    @property
    def model_name(self) -> str:
        return self._model

    def create_llm(self, temperature: float, use_case: str = "") -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=self._model,
            temperature=temperature,
            api_key=self._api_key,  # type: ignore[arg-type]
            base_url=self._BASE_URL,
            stream_usage=True,
            callbacks=[TokenUsageLogger(self._model, use_case)],
        )


# ---------------------------------------------------------------------------
# Gemini (Google GenAI) provider
# ---------------------------------------------------------------------------


class GeminiProvider(LLMProvider):
    def __init__(self) -> None:
        from ingest import config

        self._model = config.GEMINI_ENRICHER_MODEL

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_system_role(self) -> bool:
        return not self._model.lower().startswith("gemma-")

    @property
    def supports_structured_output(self) -> bool:
        return not self._model.lower().startswith("gemma-")

    def create_llm(self, temperature: float, use_case: str = "") -> BaseChatModel:
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=self._model,
            temperature=temperature,
            callbacks=[TokenUsageLogger(self._model, use_case)],
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_provider() -> LLMProvider:
    """Devuelve el :class:`LLMProvider` activo según las claves de API disponibles."""
    if os.environ.get("OPENAI_API_KEY"):
        return OpenAIProvider()
    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterProvider()
    if os.environ.get("GOOGLE_API_KEY"):
        return GeminiProvider()
    raise RuntimeError(
        "No se encontró ninguna API key de LLM. "
        "Configura OPENAI_API_KEY, OPENROUTER_API_KEY o GOOGLE_API_KEY en tu archivo .env."
    )


@lru_cache(maxsize=1)
def get_enrichment_llm() -> BaseChatModel:
    """Devuelve el LLM cacheado para enriquecimiento de chunks."""
    return get_provider().create_llm(temperature=0.2, use_case="ingest_enrichment")


@lru_cache(maxsize=1)
def get_active_provider() -> LLMProvider:
    """Devuelve el :class:`LLMProvider` activo (cacheado tras la primera resolución)."""
    return get_provider()
