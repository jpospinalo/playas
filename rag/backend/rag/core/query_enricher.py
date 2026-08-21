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

# Meta-preguntas completas sobre el asistente ("¿Qué puedes hacer?", "¿Cómo
# ayudas?"). Se ancla al inicio y al final de la pregunta (permitiendo
# signos ¿?!. sueltos) para que NO dispare cuando la misma frase es apenas
# el arranque de un supuesto jurídico más largo, p. ej. "¿Qué haces SI UN
# HOTEL CIERRA EL ACCESO...?" o "¿Cómo ayudas A EXIGIR QUE RETIREN UNA
# EMBARCACIÓN?": en ambos casos queda texto adicional antes del final de la
# cadena, así que el `$` final no puede cerrar la coincidencia.
_CAPABILITIES_RE = re.compile(
    r"^[¿]?\s*(?:"
    r"qu[eé]\s+puedes\s+hacer"
    r"|qu[eé]\s+haces"
    r"|qu[eé]\s+eres"
    r"|c[oó]mo\s+funcionas"
    r"|c[oó]mo\s+(?:me\s+)?puedes\s+ayudar(?:me)?"
    r"|c[oó]mo\s+(?:me\s+)?ayudas"
    r"|cu[aá]les?\s+son\s+tus\s+capacidades"
    r"|qu[eé]\s+capacidades\s+tienes"
    r")\s*[¿?!.]*\s*$",
    re.IGNORECASE,
)


def _is_meta_question(text: str) -> bool:
    """Familia #6 — conversación o meta-pregunta: saludo o meta-pregunta
    completa sobre el asistente."""
    return bool(_GREETING_RE.search(text) or _CAPABILITIES_RE.search(text))


# ---------------------------------------------------------------------------
# Clasificador de alcance — organizado en siete familias reutilizables
# ---------------------------------------------------------------------------
#
# En vez de una única expresión regular gigante o condiciones específicas
# por pregunta, la clasificación se apoya en funciones pequeñas por familia
# de señal. `_fallback()` y `_apply_domain_guard()` llaman a las MISMAS
# funciones — ninguna de las dos mantiene su propia copia de las señales:
#
#   1. contexto costero explícito        -> _has_explicit_coastal_signal
#   2. actividad acuática/marítima ambigua -> _has_ambiguous_aquatic_signal
#   3. contexto interior o ajeno          -> _has_inland_or_unrelated_context
#   4. intención jurídica o regulatoria   -> _has_legal_signal
#   5. solicitud inequívocamente ajena    -> _has_unambiguous_off_topic_intent
#   6. conversación o meta-pregunta       -> _is_meta_question (arriba)
#   7. seguimiento que hereda contexto    -> _inherit_context_from_history
#
# `_has_coastal_signal()` combina las familias 1-3 en la regla de alcance
# marítimo que usan tanto `_fallback()` como `_apply_domain_guard()`.

# --- Familia #1: contexto costero explícito --------------------------------
#
# Palabras que por sí mismas ya indican una conexión razonable con el
# dominio marítimo/costero. Deliberadamente NO incluye una lista de
# municipios, departamentos, playas ni destinos turísticos: "El Rodadero" es
# la única excepción auxiliar explícita ya admitida en rondas anteriores;
# "Santa Marta" a secas no cuenta.
_EXPLICIT_COASTAL_RE = re.compile(
    r"\b("
    r"playas?|costas?|coster[oa]s?|litoral(?:es)?|bajamar|bah[ií]as?|mar|mar[ií]tim[oa]s?|"
    r"aguas?\s+mar[ií]timas?|terrenos?\s+de\s+bajamar|"
    r"dimar|capitan[ií]a\s+de\s+puerto|"
    r"el\s+rodadero|"
    r"orilla(?:s)?\s+del\s+mar|franja(?:s)?\s+de\s+arena|"
    r"acceso\s+al\s+mar|bienes?\s+de\s+uso\s+p[uú]blico"
    r")\b",
    re.IGNORECASE,
)


def _has_explicit_coastal_signal(text: str) -> bool:
    """Familia #1: contexto costero/marítimo explícito e inequívoco."""
    return bool(_EXPLICIT_COASTAL_RE.search(text))


# --- Familia #2: actividad acuática o marítima ambigua ---------------------
#
# Estas actividades y objetos también existen en ríos, lagos, lagunas,
# represas, embalses o piscinas: por sí solas NO demuestran conexión
# costera. Solo cuentan como parte del dominio cuando no hay, además, un
# contexto interior explícito (familia #3) — ver _has_coastal_signal().
_AMBIGUOUS_AQUATIC_RE = re.compile(
    r"\b("
    r"pesca|pescador(?:a|es|as)?|"
    r"embarcaci[oó]n(?:es)?|naves?|buques?|artefactos?\s+naval(?:es)?|"
    r"kayak(?:s)?|surf(?:ing)?|"
    r"motos?\s+acu[aá]ticas?|parasailing|muelles?(?:\s+flotantes?)?|"
    r"deportes?\s+n[aá]uticos?|actividades?\s+n[aá]uticas?"
    r")\b",
    re.IGNORECASE,
)


def _has_ambiguous_aquatic_signal(text: str) -> bool:
    """Familia #2: actividad acuática/náutica que también podría darse en un
    río, lago, laguna, represa, embalse o piscina."""
    return bool(_AMBIGUOUS_AQUATIC_RE.search(text))


# --- Familia #3: contexto interior o claramente ajeno -----------------------
#
# Neutraliza una señal acuática ambigua (familia #2) cuando la propia
# consulta ya indica un entorno interior o manifiestamente ajeno al mar. No
# es una lista de lugares: son categorías genéricas de entorno.
_INLAND_OR_UNRELATED_CONTEXT_RE = re.compile(
    r"\b(lagos?|lagunas?|represas?|embalses?|r[ií]os?|piscinas?|espacial(?:es)?)\b",
    re.IGNORECASE,
)


def _has_inland_or_unrelated_context(text: str) -> bool:
    """Familia #3: entorno interior (lago/laguna/represa/embalse/río/
    piscina) o manifiestamente ajeno (p. ej. "nave espacial")."""
    return bool(_INLAND_OR_UNRELATED_CONTEXT_RE.search(text))


def _has_coastal_signal(text: str) -> bool:
    """Combina las familias #1-#3 en la regla de contexto costero.

    Una señal costera explícita (familia #1) siempre cuenta, incluso si en
    la misma consulta también aparece una palabra de entorno interior —
    p. ej. la desembocadura de un río en el mar, o una pregunta sobre la
    competencia de DIMAR que también menciona un río: debe prevalecer la
    conexión marítima explícita, no rechazarse automáticamente. Una
    actividad acuática ambigua (familia #2) solo cuenta como costera cuando
    no hay, además, un contexto interior o ajeno explícito (familia #3).
    """
    if _has_explicit_coastal_signal(text):
        return True
    if _has_ambiguous_aquatic_signal(text):
        return not _has_inland_or_unrelated_context(text)
    return False


# --- Familia #4: intención jurídica o regulatoria ---------------------------
#
# Organizada en subfamilias temáticas pequeñas — no una única expresión
# gigante — para poder razonarla y ampliarla sin duplicar palabras. Ninguna
# subfamilia por sí sola implica el dominio: siempre se combina con la
# familia de contexto costero (#1-#3) en _fallback()/_apply_domain_guard().

# Pedir autorización, permiso, licencia o concesión.
_PERMISSION_INTENT_RE = re.compile(
    r"\b(permis\w*|permit\w*|autoriz\w*|licencias?|concesi[oó]n\w*|solicit\w*)\b",
    re.IGNORECASE,
)

# Requisitos, trámites, plazos, vencimientos o renovaciones.
_PROCEDURE_TIMELINE_INTENT_RE = re.compile(
    r"\b(requisit\w*|tr[aá]mit\w*|procedimient\w*|plazo\w*|t[eé]rmino\w*|"
    r"venc\w*|renuev\w*|renovaci[oó]n\w*|retir\w*|"
    r"cu[aá]nto\s+tiempo\s+(?:tiene|tienen|hay|debe|deben|dan))\b",
    re.IGNORECASE,
)

# Prohibición o legalidad explícita ("¿está prohibido?", "¿es legal?").
_PROHIBITION_RE = re.compile(
    r"\b(proh[ií]b\w*|es\s+legal|es\s+ilegal|est[aá]\s+permitido)\b",
    re.IGNORECASE,
)

# Competencia de una autoridad o a quién corresponde actuar.
_AUTHORITY_COMPETENCE_RE = re.compile(
    r"\b(autoridad(?:es)?|"
    r"qui[eé]n\s+(?:debe|tiene\s+que|es\s+responsable|autoriza))\b",
    re.IGNORECASE,
)

# Reclamo por inacción, contaminación, riesgo o afectación de derechos.
# `(?:in)?cumpl(?!ea)\w*` reconoce "cumple/cumplen/cumplimiento/incumple",
# pero excluye "cumpleaños" mediante el lookahead negativo.
_COMPLAINT_RISK_RE = re.compile(
    r"\b(quej\w*|reclam\w*|omisi[oó]n\w*|inacci[oó]n\w*|denunci\w*|"
    r"contaminaci[oó]n\w*|contamina\w*|riesgo\w*|erosi[oó]n\w*|"
    r"medidas?\s+(?:urgentes?|cautelares?)|(?:in)?cumpl(?!ea)\w*)\b",
    re.IGNORECASE,
)

# Acceso público, propiedad, uso u ocupación.
_ACCESS_PROPERTY_RE = re.compile(
    r"\b(acceso\w*|ocupaci[oó]n\w*|construcci[oó]n\w*|instalaci[oó]n\w*|"
    r"uso\s+p[uú]blico|dueñ\w*|propietari\w*|propiedad\w*|dominio\w*)\b",
    re.IGNORECASE,
)

# Sanciones, multas y obligaciones/responsabilidades.
_SANCTION_OBLIGATION_RE = re.compile(
    r"\b(sanci[oó]n\w*|multa\w*|oblig\w*|responsab\w*)\b",
    re.IGNORECASE,
)

# Participación, consulta previa, protección de derechos (comunidades,
# medio ambiente).
_PARTICIPATION_PROTECTION_RE = re.compile(
    r"\b(derech\w*|participaci[oó]n\w*|consulta\s+previa|protecci[oó]n\w*)\b",
    re.IGNORECASE,
)

# Referencia normativa o jurisprudencial. `normas?|normativ\w*` reconoce
# "norma", "normas", "normativa/o" y "normatividad", pero ya NO "normal" ni
# "normalmente": ninguna de las dos ramas comparte el límite de palabra que
# envuelve la alternancia con esas dos palabras.
_NORMATIVE_REFERENCE_RE = re.compile(
    r"\b(normas?|normativ\w*|jurisprudencia)\b",
    re.IGNORECASE,
)

_LEGAL_INTENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    _PERMISSION_INTENT_RE,
    _PROCEDURE_TIMELINE_INTENT_RE,
    _PROHIBITION_RE,
    _AUTHORITY_COMPETENCE_RE,
    _COMPLAINT_RISK_RE,
    _ACCESS_PROPERTY_RE,
    _SANCTION_OBLIGATION_RE,
    _PARTICIPATION_PROTECTION_RE,
    _NORMATIVE_REFERENCE_RE,
)

# "Puedo/puede/debo... practicar/realizar/vender/instalar..." — un modal de
# posibilidad/obligación combinado con un verbo de actividad (con o sin
# pronombre enclítico: "hacerlo", "retirarla"). Por sí solo NO es señal
# jurídica (ver _has_legal_signal): solo cuenta cuando además hay contexto
# costero, p. ej. "¿Puedo practicar surf en El Rodadero?" o, tras heredar
# contexto de un seguimiento, "¿Y puedo hacerlo mientras deciden?".
_MODAL_ACTIVITY_RE = re.compile(
    r"\b(?:puedo|puede|podemos|podr[ií]an?|debo|debe|deben|deber[ií]a)\b"
    r"(?:\s+\w+){0,2}\s+(?:practicar|realizar|hacer(?:lo|la|los|las)?|iniciar|"
    r"organizar|operar|ejercer|desarrollar|instalar|construir|vender|"
    r"retirar(?:lo|la|los|las)?)\b",
    re.IGNORECASE,
)


def _has_legal_intent(text: str) -> bool:
    """Familia #4 (componente léxico, sin el modal de actividad): cualquiera
    de las subfamilias de intención jurídica/regulatoria."""
    return any(pattern.search(text) for pattern in _LEGAL_INTENT_PATTERNS)


def _has_legal_signal(text: str, *, coastal: bool) -> bool:
    """Familia #4 completa: intención jurídica o regulatoria, incluyendo el
    modal de posibilidad/obligación + verbo de actividad, que solo cuenta
    cuando ya hay contexto costero."""
    if _has_legal_intent(text):
        return True
    return coastal and bool(_MODAL_ACTIVITY_RE.search(text))


# --- Familia #5: solicitud inequívocamente ajena ----------------------------
#
# Cada subfamilia combina una acción con su objeto (no palabras sueltas),
# para que nunca colisione con una consulta jurídica legítima que use un
# verbo parecido en otro sentido — p. ej. "cocinar" en "¿puedo cocinar y
# vender pescado en una playa sin permiso?" no debe activar esta familia
# porque no hay ninguna subfamilia de "receta"/"cocinar" aislada, solo el
# sustantivo "receta" y la combinación acción+objeto de las demás.
# Cualquier coincidencia aquí fuerza out_of_scope de forma incondicional en
# _fallback() y en _apply_domain_guard(); ambas llaman a la misma función
# _has_unambiguous_off_topic_intent(), ninguna mantiene su propia copia.

_CREATE_VISUAL_RE = re.compile(
    r"\b(?:cr[eé]a\w*|genera\w*|dib[uú]j\w*|il[uú]stra\w*|haz\w*|hac\w*)\s+(?:un[ao]?s?\s+)?"
    r"(?:imagen\w*|dibujo\w*|ilustraci[oó]n\w*|foto\w*)\b",
    re.IGNORECASE,
)
# Cada verbo admite tanto su forma base como la forma con pronombre
# enclítico ("dibújame", "compón", "escríbeme"), que en español desplaza el
# acento ortográfico — de lo contrario la familia no reconoce esas formas
# de imperativo tan comunes en una solicitud creativa.
_CREATIVE_WRITING_RE = re.compile(
    r"\b(?:escr[ií]b\w*|red[aá]ct\w*|comp[oó]n\w*|inv[eé]nt\w*|cr[eé]a\w*|haz\w*)\s+(?:un[ao]?s?\s+)?"
    r"(?:poemas?|canci[oó]n(?:es)?|cuentos?|chistes?)\b",
    re.IGNORECASE,
)
_PROGRAMMING_RE = re.compile(
    r"\bprogr[aá]ma\w*\s+(?:un[ao]?\s+)?(?:api|aplicaci[oó]n\w*|software|c[oó]digo|scripts?|programa\w*)\b"
    r"|\b(?:desarroll\w*|escr[ií]b\w*)\s+(?:un[ao]?\s+)?(?:software|c[oó]digo|scripts?)\b"
    r"|c[oó]digo\s+(?:python|javascript)\b",
    re.IGNORECASE,
)
_WEATHER_FORECAST_RE = re.compile(
    r"\bpron[oó]stico\w*\s+del?\s+(?:tiempo|clima)\b",
    re.IGNORECASE,
)
_SPORTS_RESULTS_RE = re.compile(
    r"\bresultados?\s+(?:de\s+)?f[uú]tbol\b|\btabla\s+de\s+posiciones\b",
    re.IGNORECASE,
)
_GENERAL_GEOGRAPHY_RE = re.compile(
    r"\bcu[aá]l\s+es\s+la\s+capital\s+de\b",
    re.IGNORECASE,
)
_HOTEL_RECOMMENDATION_RE = re.compile(
    r"\brecomi[eé]nd\w*\s+(?:un\s+)?hotel(?:es)?\b|\brecomendaci[oó]n\w*\s+de\s+hotel(?:es)?\b",
    re.IGNORECASE,
)
_REAL_ESTATE_PRICE_RE = re.compile(
    r"\bprecios?\s+de\s+(?:los\s+)?inmuebles?\b",
    re.IGNORECASE,
)
_RECIPE_REQUEST_RE = re.compile(
    r"\brecetas?\b",
    re.IGNORECASE,
)
# El lookahead negativo excluye "entrenar personal/trabajadores/empleados"
# (formación de personal, un asunto regulatorio legítimo) del sentido
# deportivo/recreativo de "entrenar".
_TRAINING_PRACTICE_RE = re.compile(
    r"\bentrenar(?!\s+(?:personal|trabajador\w*|empleado\w*))\w*\b"
    r"|\baprender\w*\s+a\s+(?:usar|manejar|montar|navegar)\w*\b",
    re.IGNORECASE,
)
_RECREATIONAL_SHOPPING_RE = re.compile(
    r"\bd[oó]nde\s+(?:puedo\s+)?comprar\w*\b",
    re.IGNORECASE,
)

_UNAMBIGUOUS_OFF_TOPIC_PATTERNS: tuple[re.Pattern[str], ...] = (
    _CREATE_VISUAL_RE,
    _CREATIVE_WRITING_RE,
    _PROGRAMMING_RE,
    _WEATHER_FORECAST_RE,
    _SPORTS_RESULTS_RE,
    _GENERAL_GEOGRAPHY_RE,
    _HOTEL_RECOMMENDATION_RE,
    _REAL_ESTATE_PRICE_RE,
    _RECIPE_REQUEST_RE,
    _TRAINING_PRACTICE_RE,
    _RECREATIONAL_SHOPPING_RE,
)


def _has_unambiguous_off_topic_intent(text: str) -> bool:
    """Familia #5: solicitud inequívocamente ajena (contenido creativo,
    programar software, clima, deportes, geografía general, recomendar
    hoteles, precios de inmuebles, recetas, entrenar/aprender por ocio,
    comprar por ocio). Nunca se convierte en in_scope, sin importar qué
    señales costeras o jurídicas también estén presentes."""
    return any(pattern.search(text) for pattern in _UNAMBIGUOUS_OFF_TOPIC_PATTERNS)


# --- Familia #7: seguimiento que hereda contexto del historial -------------
#
# Marcadores anafóricos "fuertes" (se refieren explícitamente al mismo tema
# ya discutido: "también", "aplica", "eso", "lo mismo", "mencionado") ceden
# tanto el contexto costero como la intención jurídica desde el historial
# combinado. Un marcador "débil" (una "y" inicial genérica, que también
# podría introducir un tema nuevo y no relacionado) solo hereda el contexto
# costero; la intención jurídica se vuelve a evaluar sobre la pregunta
# ACTUAL, ya con ese contexto disponible — así "¿Y puedo hacerlo mientras
# deciden?" cuenta el modal "puedo hacerlo" en cuanto hay contexto costero,
# sin heredar ciegamente la intención jurídica de un historial no
# relacionado (lo que evitaría, p. ej., que "¿Y qué hora es en Bogotá?"
# se cuele como in_scope solo por aparecer después de una consulta costera).
_STRONG_FOLLOW_UP_RE = re.compile(
    r"\b(ese|esa|eso|esos|esas|all[ií]|tambi[eé]n|lo\s+mismo|eso\s+mismo|"
    r"anterior|mencionad[oa]s?|dich[oa]s?|aplica(?:r[ií]a)?)\b",
    re.IGNORECASE,
)
_WEAK_FOLLOW_UP_RE = re.compile(r"^\s*[¿?¡!]*\s*y\b", re.IGNORECASE)


def _inherit_context_from_history(
    clean_question: str,
    history_context: str,
    *,
    coastal: bool,
    legal: bool,
) -> tuple[bool, bool]:
    """Familia #7: si la pregunta es un seguimiento y el historial reciente
    contiene una consulta costera válida, hereda el contexto costero y/o
    jurídico que falte. Devuelve el par ``(coastal, legal)`` actualizado.

    Una pregunta expresamente ajena nunca llega aquí: las familias #5 y #6
    ya se evalúan antes en _fallback() y retornan de inmediato.
    """
    if coastal and legal:
        return coastal, legal
    if not history_context:
        return coastal, legal

    strong_marker = bool(_STRONG_FOLLOW_UP_RE.search(clean_question))
    weak_marker = bool(_WEAK_FOLLOW_UP_RE.search(clean_question))
    if not (strong_marker or weak_marker or legal):
        return coastal, legal

    combined = f"{history_context}\n{clean_question}"
    if not coastal:
        coastal = _has_coastal_signal(combined)

    if not legal and coastal:
        if strong_marker:
            # Marcador fuerte: el historial completo puede aportar tanto el
            # contexto como la intención jurídica ("¿también aplica a los
            # pescadores?" hereda el "necesito autorización..." anterior).
            legal = _has_legal_signal(combined, coastal=True)
        else:
            # Marcador débil o señal jurídica propia: solo se reevalúa la
            # pregunta actual, ya con el contexto costero disponible.
            legal = _has_legal_signal(clean_question, coastal=True)

    return coastal, legal


def _fallback(question: str, history_context: str = "") -> EnrichedQuery:
    """Clasificación conservadora usada si el LLM falla o está deshabilitado.

    Política de precedencia, expresada sobre las siete familias descritas
    arriba:
    1. solicitud inequívocamente ajena (familia #5) -> ``out_of_scope``
       SIEMPRE, sin excepción por combinación costera+jurídica.
    2. saludo/meta-pregunta completa (familia #6) -> ``conversation``.
    3. seguimiento que hereda contexto del historial (familia #7).
    4. contexto costero (familias #1-#3) + intención jurídica/regulatoria
       (familia #4) -> ``in_scope``.
    5. una sola señal (costera o jurídica, sin la otra) ->
       ``needs_clarification``.
    6. ausencia de cualquier señal pertinente -> ``out_of_scope``.
    """
    clean_question = question.strip()

    if _has_unambiguous_off_topic_intent(clean_question):
        return EnrichedQuery(
            route="out_of_scope",
            standalone_question=clean_question,
            expanded_query=clean_question,
            doc_types=[],
        )

    if _is_meta_question(clean_question):
        return EnrichedQuery(
            route="conversation",
            standalone_question=clean_question,
            expanded_query=clean_question,
            doc_types=[],
        )

    coastal = _has_coastal_signal(clean_question)
    legal = _has_legal_signal(clean_question, coastal=coastal)
    coastal, legal = _inherit_context_from_history(
        clean_question, history_context, coastal=coastal, legal=legal
    )

    if coastal and legal:
        route: QueryRoute = "in_scope"
    elif coastal or legal:
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
    """Corrige errores evidentes del clasificador sin sustituir el análisis
    semántico del LLM salvo en los casos deterministas cubiertos por la
    heurística. Reutiliza exactamente las mismas funciones de familia que
    ``_fallback()``: ninguna regla de aquí abajo mantiene su propia copia de
    las señales.

    Precedencia:
    1. Conversación/meta-pregunta completa (familia #6) fuerza
       ``conversation``.
    2. Solicitud inequívocamente ajena (familia #5) fuerza ``out_of_scope``,
       incluso si el modelo dijo ``in_scope`` — y nunca al revés: esta regla
       ni siquiera examina ``result.route``, así que la mera aparición de
       términos jurídicos o costeros dentro de una solicitud creativa no
       puede anular un ``out_of_scope`` correcto del modelo.
    3. Una combinación de alta confianza entre contexto costero (familias
       #1-#3) y propósito jurídico (familia #4) corrige un falso negativo
       del modelo a ``in_scope``.
    4. Una actividad acuática ambigua con contexto interior (familias #2+#3)
       nunca produce ``in_scope`` en la heurística — por construcción de
       ``_has_coastal_signal()`` — así que la regla 3 nunca puede forzar
       ``in_scope`` en ese caso.
    5. Si la heurística no tiene suficiente certeza (``needs_clarification``
       o un ``out_of_scope`` que no proviene de una señal ajena
       inequívoca), se conserva el análisis semántico del LLM tal cual,
       incluyendo un ``in_scope`` del modelo para un caso ambiguo que la
       heurística no pudo resolver por sí sola.
    """
    heuristic = _fallback(question, history_context)
    clean_question = question.strip()

    if heuristic.route == "conversation":
        return heuristic

    if _has_unambiguous_off_topic_intent(clean_question):
        return heuristic

    if heuristic.route == "in_scope" and result.route != "in_scope":
        return EnrichedQuery(
            route="in_scope",
            standalone_question=result.standalone_question,
            expanded_query=result.expanded_query,
            doc_types=result.doc_types or heuristic.doc_types,
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
