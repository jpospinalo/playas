# rag/core/query_enricher.py
"""Query enrichment step for the RAG pipeline.

Before retrieval, the user's raw query is rewritten into a richer, domain-specific
string that improves both BM25 keyword matching and dense vector search.

The original question is never modified; it continues to be used verbatim in the
final LLM generation prompt.

Configuration (via .env or environment):
    QUERY_ENRICHMENT_ENABLED  – "true" (default) | "false"
"""

from __future__ import annotations

import json
import logging
import re
from typing import cast

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from rag.config import QUERY_ENRICHMENT_ENABLED as ENRICHMENT_ENABLED

from .domain_scope import (
    DocumentType as DocumentType,
)
from .domain_scope import (
    EnrichedQuery,
    _apply_domain_guard,
    _fallback,
)
from .domain_scope import (
    QueryRoute as QueryRoute,
)
from .domain_scope import (
    _has_legal_signal as _has_legal_signal,
)
from .domain_scope import (
    _normalize_expanded_query as _normalize_expanded_query,
)
from .llm_factory import get_active_provider, get_enrichment_llm
from .prompts import (
    ENRICHER_HUMAN_BODY,
    ENRICHER_SYSTEM,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompt construction — strings importados desde rag/core/prompts.py
# ---------------------------------------------------------------------------

_ENRICHMENT_SYSTEM = ENRICHER_SYSTEM


def _build_human_body() -> str:
    """Devuelve las instrucciones del analizador."""
    return ENRICHER_HUMAN_BODY


# ---------------------------------------------------------------------------
# JSON parsing for models that don't support function calling (e.g. Gemma)
# ---------------------------------------------------------------------------

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def _parse_json_response(
    text: str,
    question: str,
    history_context: str = "",
) -> EnrichedQuery:
    """Extract and validate JSON from a plain-text LLM response.

    Strips markdown code fences if the model added them, then validates
    against :class:`EnrichedQuery`. Falls back to the original question
    on any parse or validation error.
    """
    # Strip markdown fences if present
    fence_match = _JSON_FENCE_RE.search(text)
    json_text = fence_match.group(1).strip() if fence_match else text.strip()

    try:
        data = json.loads(json_text)
        result = EnrichedQuery(**data)
        if not result.expanded_query.strip():
            return _fallback(question, history_context)
        return _apply_domain_guard(result, question, history_context)
    except (json.JSONDecodeError, ValidationError, TypeError):
        logger.warning(
            "Failed to parse enrichment JSON response; using fallback.\nRaw output: %s",
            text[:300],
        )
        return _fallback(question, history_context)


def _build_prompt() -> ChatPromptTemplate:
    """Return the appropriate prompt template for the active provider.

    When the provider does not support a dedicated system role (e.g. Gemma via
    Google GenAI), instructions are folded into the single human turn.
    """
    human_body = _build_human_body()
    if not get_active_provider().supports_system_role:
        return ChatPromptTemplate.from_messages(
            [("human", f"INSTRUCCIONES:\n{{instructions}}\n\n{human_body}")]
        ).partial(instructions=_ENRICHMENT_SYSTEM)
    return ChatPromptTemplate.from_messages(
        [
            ("system", _ENRICHMENT_SYSTEM),
            ("human", human_body),
        ]
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_query(question: str, history_context: str = "") -> EnrichedQuery:
    """Synchronously enrich *question* for better RAG retrieval.

    Uses ``with_structured_output`` when the active provider supports tool
    calling, otherwise requests JSON via the prompt and parses it manually
    (e.g. Gemma via Google GenAI).

    If enrichment is disabled or any error occurs, returns a fallback
    :class:`EnrichedQuery` whose ``expanded_query`` equals the original
    question so the pipeline is unaffected.
    """
    if not ENRICHMENT_ENABLED:
        return _fallback(question, history_context)

    try:
        provider = get_active_provider()
        prompt = _build_prompt()
        llm = get_enrichment_llm()

        if not provider.supports_structured_output:
            raw: str = (prompt | llm | StrOutputParser()).invoke(
                {"question": question, "history": history_context or "(sin historial)"}
            )
            return _parse_json_response(raw, question, history_context)

        result = cast(
            EnrichedQuery,
            (prompt | llm.with_structured_output(EnrichedQuery)).invoke(
                {"question": question, "history": history_context or "(sin historial)"}
            ),
        )
        if not result.expanded_query.strip():
            logger.warning("Enrichment returned an empty expanded_query; using fallback.")
            return _fallback(question, history_context)
        return _apply_domain_guard(result, question, history_context)
    except Exception:
        logger.warning("Query enrichment failed; falling back to original query.", exc_info=True)
        return _fallback(question, history_context)


async def enrich_query_async(question: str, history_context: str = "") -> EnrichedQuery:
    """Async variant of :func:`enrich_query`."""
    if not ENRICHMENT_ENABLED:
        return _fallback(question, history_context)

    try:
        provider = get_active_provider()
        prompt = _build_prompt()
        llm = get_enrichment_llm()

        if not provider.supports_structured_output:
            raw: str = await (prompt | llm | StrOutputParser()).ainvoke(
                {"question": question, "history": history_context or "(sin historial)"}
            )
            return _parse_json_response(raw, question, history_context)

        result = cast(
            EnrichedQuery,
            await (prompt | llm.with_structured_output(EnrichedQuery)).ainvoke(
                {"question": question, "history": history_context or "(sin historial)"}
            ),
        )
        if not result.expanded_query.strip():
            logger.warning("Enrichment returned an empty expanded_query; using fallback.")
            return _fallback(question, history_context)
        return _apply_domain_guard(result, question, history_context)
    except Exception:
        logger.warning("Query enrichment failed; falling back to original query.", exc_info=True)
        return _fallback(question, history_context)
