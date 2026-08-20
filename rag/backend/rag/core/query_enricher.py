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
from typing import Literal, cast

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from rag.config import QUERY_ENRICHMENT_ENABLED as ENRICHMENT_ENABLED

from .llm_factory import get_active_provider, get_enrichment_llm
from .prompts import (
    ENRICHER_HUMAN_BODY,
    ENRICHER_SYSTEM,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------


QueryRoute = Literal["in_scope", "out_of_scope", "conversation", "needs_clarification"]
DocumentType = Literal["jurisprudencia", "normativa"]


class EnrichedQuery(BaseModel):
    """Resultado estructurado del análisis de alcance y enriquecimiento."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    route: QueryRoute = Field(description="Ruta determinista que debe seguir la consulta.")
    standalone_question: str = Field(
        min_length=1,
        max_length=4000,
        description="Pregunta autosuficiente, resuelta con ayuda del historial reciente.",
    )
    expanded_query: str = Field(
        min_length=1,
        max_length=1000,
        description="Consulta compacta usada por el recuperador híbrido.",
    )
    doc_types: list[DocumentType] = Field(
        default_factory=list,
        max_length=2,
        description="Tipos documentales pertinentes para una consulta dentro del ámbito.",
    )

    @model_validator(mode="after")
    def validate_route_payload(self) -> EnrichedQuery:
        self.doc_types = list(dict.fromkeys(self.doc_types))
        words = self.expanded_query.split()
        if len(words) > 45:
            self.expanded_query = " ".join(words[:45])
        if self.route == "in_scope" and not self.doc_types:
            raise ValueError("Una consulta in_scope debe seleccionar al menos un tipo documental.")
        if self.route != "in_scope" and self.doc_types:
            raise ValueError(
                "Las consultas sin recuperación no deben seleccionar tipos documentales."
            )
        return self


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
# Fallback
# ---------------------------------------------------------------------------


_GREETING_RE = re.compile(
    r"^\s*(hola|buen(?:os|as)\s+(?:d[ií]as|tardes|noches)|gracias|adi[oó]s|hasta luego)[!.?\s]*$",
    re.IGNORECASE,
)
_CAPABILITIES_RE = re.compile(
    r"\b(qu[eé]\s+(?:puedes|haces|eres)|c[oó]mo\s+(?:funcionas|ayudas)|tus\s+capacidades)\b",
    re.IGNORECASE,
)
_STRONG_SCOPE_RE = re.compile(
    r"\b(playas?|zona(?:s)?\s+costeras?|costa(?:s)?|litoral|mar[ií]tim[oa]s?|"
    r"terrenos?\s+de\s+bajamar|bajamar|dimar|capitan[ií]a\s+de\s+puerto|"
    r"aguas?\s+mar[ií]timas?|bienes?\s+de\s+uso\s+p[uú]blico|acceso\s+al\s+mar|"
    r"orilla(?:s)?\s+del\s+mar|franja(?:s)?\s+de\s+arena)\b",
    re.IGNORECASE,
)
_RELATED_SCOPE_RE = re.compile(
    r"\b(pesca|pescadores?|turismo|tur[ií]stic[oa]s?|concesi[oó]n|permisos?|"
    r"licencias?|sanciones?|procedimientos?|derechos?|ocupaci[oó]n|construcci[oó]n|"
    r"autoridad\s+competente|uso\s+p[uú]blico|jurisprudencia|normatividad|normas?|"
    r"acceso|plazos?)\b",
    re.IGNORECASE,
)
_CLEARLY_OUT_OF_SCOPE_RE = re.compile(
    r"\b(capital\s+de|receta|cocinar|programar|c[oó]digo\s+(?:python|javascript)|"
    r"resultado\s+(?:de\s+)?f[uú]tbol|tabla\s+de\s+posiciones|pron[oó]stico\s+del\s+tiempo)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_RE = re.compile(
    r"(?:^\s*[¿?¡!]*\s*y\b|\b(ese|esa|eso|esos|esas|all[ií]|tambi[eé]n|"
    r"anterior|mencionad[oa]s?|dich[oa]s?|aplica(?:r[ií]a)?)\b)",
    re.IGNORECASE,
)


def _fallback(question: str, history_context: str = "") -> EnrichedQuery:
    """Clasificación conservadora usada si el LLM falla o está deshabilitado."""
    clean_question = question.strip()
    combined = f"{history_context}\n{clean_question}"

    if _GREETING_RE.search(clean_question) or _CAPABILITIES_RE.search(clean_question):
        route: QueryRoute = "conversation"
    elif _CLEARLY_OUT_OF_SCOPE_RE.search(clean_question):
        route = "out_of_scope"
    elif _STRONG_SCOPE_RE.search(clean_question):
        route = "in_scope"
    elif (
        history_context
        and _STRONG_SCOPE_RE.search(combined)
        and (_FOLLOW_UP_RE.search(clean_question) or _RELATED_SCOPE_RE.search(clean_question))
    ):
        route = "in_scope"
    elif _RELATED_SCOPE_RE.search(clean_question):
        route = "needs_clarification"
    else:
        route = "out_of_scope"

    return EnrichedQuery(
        route=route,
        standalone_question=clean_question,
        expanded_query=clean_question,
        doc_types=["jurisprudencia", "normativa"] if route == "in_scope" else [],
    )


def _apply_domain_guard(
    result: EnrichedQuery,
    question: str,
    history_context: str,
) -> EnrichedQuery:
    """Corrige errores evidentes del clasificador sin sustituir su análisis semántico."""
    heuristic = _fallback(question, history_context)
    if heuristic.route == "conversation" or _CLEARLY_OUT_OF_SCOPE_RE.search(question):
        return heuristic
    if heuristic.route == "out_of_scope" and result.route == "in_scope":
        return heuristic
    if heuristic.route == "in_scope" and result.route != "in_scope":
        return EnrichedQuery(
            route="in_scope",
            standalone_question=result.standalone_question,
            expanded_query=result.expanded_query,
            doc_types=result.doc_types or ["jurisprudencia", "normativa"],
        )
    return result


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
