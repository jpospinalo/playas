"""LLM provider factory for the RAG pipeline.

Centralizes all LLM creation and selection logic. Adding a new provider only
requires implementing ``LLMProvider`` and adding one condition to
``get_provider()``. No changes are needed in ``generator.py`` or
``query_enricher.py``.

Provider selection order (first available key wins):
1. ``OPENAI_API_KEY``    → :class:`OpenAIProvider`
2. ``OPENROUTER_API_KEY`` → :class:`OpenRouterProvider`
3. ``GOOGLE_API_KEY``     → :class:`GeminiProvider`
4. None set               → :exc:`RuntimeError`
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
    """Format a token count; ``None`` means unknown (streaming/API omitted)."""
    return "?" if n is None else str(n)


def _extract_in_out_tokens(response: LLMResult) -> tuple[int | None, int | None]:
    """Resolve input/output token counts from LangChain's heterogeneous shapes.

    - Non-streaming OpenAI: ``llm_output["token_usage"]``
    - Streaming OpenAI / OpenRouter: often **empty** ``llm_output``; counts live on
      ``AIMessage.usage_metadata`` (``input_tokens`` / ``output_tokens``).
    - Google GenAI: ``llm_output["usage_metadata"]`` with ``*_token_count`` keys.
    """
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

    # Chat models (especially streaming): standardized AIMessage.usage_metadata
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
    """LangChain callback that emits one log line per LLM call with token counts.

    Handles both OpenAI-compatible (``token_usage``) and Google GenAI
    (``usage_metadata``) response formats. Reports ``"?"`` when a provider
    does not return usage data (e.g. mid-stream chunks).
    """

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
        # Log on the package logger so ``rag/__init__.py``'s StreamHandler always
        # receives the line (uvicorn leaves the root logger without handlers).
        logging.getLogger("rag").info(line)


# ---------------------------------------------------------------------------
# Abstract provider contract
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract base for LLM providers.

    Implementors expose capability flags so callers can adapt prompt
    construction and output parsing without referencing provider internals.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """The model identifier that will be sent to the API."""

    @property
    def supports_system_role(self) -> bool:
        """Whether the model accepts a dedicated system message.

        Gemma models served directly via Google GenAI do not support a system
        role; instructions must be folded into the human turn. All other
        providers (including Gemma via OpenRouter's OpenAI-compatible API)
        return ``True``.
        """
        return True

    @property
    def supports_structured_output(self) -> bool:
        """Whether the model supports function/tool calling for structured output.

        Gemma models via Google GenAI do not support tool calling; JSON must be
        requested via the prompt and parsed manually. All other providers
        return ``True``.
        """
        return True

    @abstractmethod
    def create_llm(self, temperature: float, use_case: str = "") -> BaseChatModel:
        """Instantiate a ``BaseChatModel`` with token usage logging attached."""


# ---------------------------------------------------------------------------
# OpenAI provider
# ---------------------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    """LLM provider backed by ``langchain_openai.ChatOpenAI`` using the OpenAI API.

    Model is read from ``OPENAI_MODEL`` (default ``gpt-4o-mini``).
    OpenAI models support system roles and function/tool calling natively.
    """

    def __init__(self) -> None:
        from rag import config

        if not config.OPENAI_API_KEY:
            raise RuntimeError(
                "OPENAI_API_KEY no está configurada. "
                "Agrégala a tu archivo .env antes de usar OpenAI."
            )
        self._api_key = config.OPENAI_API_KEY
        self._model = config.OPENAI_MODEL

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
# Gemini (Google GenAI) provider
# ---------------------------------------------------------------------------


class GeminiProvider(LLMProvider):
    """LLM provider backed by ``langchain_google_genai.ChatGoogleGenerativeAI``.

    Model is read from ``GEMINI_MODEL`` (default ``gemini-2.0-flash``).
    Capability flags are automatically set based on whether the selected
    model is a Gemma variant, which lacks system-role and tool-calling
    support when accessed via Google's own API.
    """

    def __init__(self) -> None:
        from rag.config import GEMINI_MODEL

        self._model = GEMINI_MODEL

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
# OpenRouter provider
# ---------------------------------------------------------------------------


class OpenRouterProvider(LLMProvider):
    """LLM provider backed by OpenRouter via ``langchain_openai.ChatOpenAI``.

    Uses OpenRouter's OpenAI-compatible endpoint so all models — including
    Gemma variants — support system roles and function calling.

    Model is read from ``OPENROUTER_MODEL`` (default ``openrouter/auto``).
    """

    _BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(self) -> None:
        from rag.config import OPENROUTER_API_KEY, OPENROUTER_MODEL

        if not OPENROUTER_API_KEY:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. "
                "Add it to your .env file or environment before using OpenRouter."
            )
        self._api_key = OPENROUTER_API_KEY
        self._model = OPENROUTER_MODEL

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
            # Request token usage in the final streaming chunk so on_llm_end
            # receives counts for both streaming and non-streaming calls.
            stream_usage=True,
            callbacks=[TokenUsageLogger(self._model, use_case)],
        )


# ---------------------------------------------------------------------------
# Factory — provider selection
# ---------------------------------------------------------------------------


def get_provider() -> LLMProvider:
    """Return the appropriate :class:`LLMProvider` based on available API keys.

    Selection order:
    1. ``OPENAI_API_KEY``     → :class:`OpenAIProvider`
    2. ``OPENROUTER_API_KEY`` → :class:`OpenRouterProvider`
    3. ``GOOGLE_API_KEY``     → :class:`GeminiProvider`
    4. Ninguna configurada    → :exc:`RuntimeError`
    """
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


# ---------------------------------------------------------------------------
# Cached convenience accessors — one instance per use-case
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_generation_llm() -> BaseChatModel:
    """Return the cached LLM instance used for RAG answer generation.

    The instance is created once and reused for all subsequent calls,
    keeping a ``TokenUsageLogger`` attached for every invocation.
    """
    return get_provider().create_llm(temperature=0.1, use_case="generation")


@lru_cache(maxsize=1)
def get_enrichment_llm() -> BaseChatModel:
    """Return the cached LLM instance used for query enrichment.

    Separate from the generation LLM to allow independent temperature and
    caching behaviour.
    """
    return get_provider().create_llm(temperature=0.0, use_case="enrichment")


@lru_cache(maxsize=1)
def get_active_provider() -> LLMProvider:
    """Return the active :class:`LLMProvider` (cached after first resolution).

    Use this when callers need to inspect provider capabilities (e.g.
    ``supports_system_role``, ``supports_structured_output``) without
    creating an LLM instance.
    """
    return get_provider()
