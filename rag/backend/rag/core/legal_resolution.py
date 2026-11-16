"""Resolve explicit questions against verified documents from a BM25 snapshot."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from itertools import pairwise
from pathlib import Path

from langchain_core.documents import Document

from .domain_scope import _is_deterministic_terminal
from .tools import sanitize_replacement_chars

_DOCKET = re.compile(
    r"(?<![\w-])(?P<number>t-(?:\d(?:\.\d{3}){2}|\d{7})|"
    r"(?:\d{5}-\d{2}-\d{2}-\d{3}|\d{2}-\d{3}-\d{4}-\d{3}|\d{12})[ -]?\d{4}[ -]?\d{4,5}[ -]?\d{2}|\d{4})"
    r"(?:\s*\((?P<reference>[\d.]+)\))?(?![\w-])"
)
_QUESTION = re.compile(
    r"¿?que (?:ordeno|resolvio|decidio) en (primera instancia|segunda instancia|"
    r"unica instancia|sede de revision)(?: (?:a|al) (.+?))? (?:sobre|acerca de) (.+?)"
    rf",? en (?:el radicado )?(?P<docket>{_DOCKET.pattern})\?"
)
_PARTIAL_DOCKET = re.compile(
    r"\b(?:solo (?:tengo|conozco) (?:el )?(?:radicado|expediente|numero)|"
    r"(?:radicado|expediente|numero) (?:parcial|incompleto))"
    r"(?: *: *| )\d{5}(?![\w/-]|[.,]\d| \d)"
)
_UNKNOWN_INSTANCE = re.compile(
    r"\b(?:desconozco|no (?:se|conozco)) (?:la|en que|de que) instancia\b"
)
_OPERATIVE_REQUEST = re.compile(r"\b(?:plazo|termino|orden(?:es)?|ordeno|resolvio|decidio)\b")
_JUDICIAL_REFERENCE = re.compile(r"\b(?:fallo|sentencia|providencia|tribunal|juzgado)\b")
_RESPONSIBILITY_QUESTION = re.compile(
    r"¿?que (?:ordeno|resolvio|decidio) en (?:primera instancia|segunda instancia|"
    r"unica instancia|sede de revision) (?:a|al) .+? como "
    r"(?:unico responsable|responsable(?: unico)?) de .+?,? en (?:el radicado )?"
    rf"{_DOCKET.pattern}\?"
)
_ANSWER_DOCKET = re.compile(
    r"(?<![\w-])(?:\d(?:[ -]?\d){21,22}|t-(?:\d(?:\.\d{3}){2}|\d{7}))(?![\w-])"
)
_ANSWER_SHORT_DOCKET = re.compile(
    r"\b(?:radicado|radicacion|expediente)\b(?:\s+(?:numero|num\.?|nro\.?|n(?:\.?[oº°])\.?))?"
    r"\s*[:#]?\s*(\d{4})(?![\w/-]|\.\d|\s+\d)"
)
_INSTANCE_HEADING = re.compile(
    r"^(?:accion popular\s*-\s*)?sentencia (?:de )?(primera|segunda|unica) instancia(?:\s*-.*)?$"
    r"|^instancia\s*:?\s*(primera|segunda|unica)(?: instancia)?$"
)
_COURT = r"(?:la sala(?: de decision)?|esta corporacion|el tribunal|el despacho)"
_ANSWER_CLAUSE_BREAK = re.compile(r"[.!?;]\s+|\n\s*\n|\n(?=[ \t]*(?:[-*#>]|\d+[.)]))")
_ANSWER_DECISION_VERB = (
    r"(?:resolv(?:io|e)|decid(?:io|e)|(?:confirm|modific|orden|revoc|neg|declar)(?:o|a))"
)
_ANSWER_DECISION_ACTOR = rf"(?:el consejo de estado|la corte constitucional|{_COURT})"
_ANSWER_INSTANCE = re.compile(
    rf"^(?:\d+[.)] )?(?:en (?:la sentencia de |la )?|sentencia de |"
    rf"(?:se )?{_ANSWER_DECISION_VERB} en |"
    rf"{_ANSWER_DECISION_ACTOR}(?:,? en | {_ANSWER_DECISION_VERB} en ))"
    r"(primera instancia|segunda instancia|unica instancia|sede de revision)\b"
    r"(?!,? (?:(?:el juez|el tribunal|el juzgado) a quo|"
    r"(?:la sentencia|la providencia|el fallo) (?:apelad|impugnad|recurrid)[ao])\b)"
)
_APPEAL_OPENING = re.compile(
    rf"^(?:procede {_COURT} a (?:resolver|decidir)|{_COURT},? (?:resuelve|decide)|"
    r"decide la sala|se decide|asunto: resuelve) (?:el recurso|los recursos) de apelacion\b"
    r"|^(?:referencia|asunto):\s*apelacion (?:de )?sentencia$"
)
_TRIAL_OPENING = re.compile(
    rf"^{_COURT},? (?:resuelve|decide) en (primera|unica) instancia,? la demanda\b"
)
_SOLE_COMMISSION = re.compile(
    r"^por no haber aceptado la ponencia\b.*\bse procede a presentar nueva ponencia\b"
    r".*\bpara decidir en unica instancia la demanda\b"
)
_REVIEW_HEADING = re.compile(r"^(?:corte constitucional\s+)?sala (?:[a-z]+ )?de revision$")
_OPENING_END = re.compile(
    r"^(?:(?:[ivx]+|\d+)\s*[.\-]+\s*)*(?:antecedentes|resumen de la demanda|la demanda|"
    r"la sentencia (?:apelada|impugnada|recurrida)|sintesis del caso)\b"
    r"|^(?:salvamento|aclaracion) de voto\b"
)
_DOCKET_LABEL = r"(?:radicado|radicacion)(?: (?:numero|num\.?))?"
_PRINTED_DOCKET = re.compile(rf"^{_DOCKET_LABEL}(?:\s*:\s*|\s+|$)(.*)$")
_TABLE_DIVIDER = re.compile(r":?-{3,}:?")
_SERIALIZED_HEADER = re.compile(
    r"(?:^|\n)radicacion numero:\nactor:\nmedio de control:\ninstancia:\ntema:\n"
    r"(?P<number>[^\n ]+) [^\n]+\n[^\n]+\n[^\n]+\n(?P<instance>primera|segunda|unica)(?=\n|$)"
)
_ORDINAL = (
    r"(?:primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno|"
    r"d[eé]cimo(?:\s+(?:primero|segundo|tercero|cuarto|quinto|sexto|s[eé]ptimo|octavo|noveno))?|"
    r"und[eé]cimo|duod[eé]cimo|\d+[º°]\)?)\s*[:.]?"
)
_BOUNDARY = re.compile(
    rf"(?<!\w)(?P<ordinal>{_ORDINAL})(?=\s+(?:[-–]\s+)?(?:ordenar|modificar|modif[ií]case|"
    r"confirmar|conf[ií]rmase|revocar|rev[oó]case|negar|declarar|conformar|conf[oó]rmese|"
    r"amparar|exhortar|sin costas|como consecuencia|en firme|en cumplimiento)\b)"
    r"|(?m:^[ \t]*[-–]\s+(?=(?:ORDENAR|CONMINAR|Para verificar[^\n]{0,270}\bse ordena)\b))"
    r"|(?P<stop>\b(?:notif[ií]quese|c[oó]piese|comun[ií]quese|salvamento de voto|aclaraci[oó]n de voto)\b)",
    re.IGNORECASE,
)
_DECISION = re.compile(
    r"^(?:#+\s+(?:iii\.\s*)?(?:f\s*a\s*l\s*l\s*a|r\s*e\s*s\s*u\s*e\s*l\s*v\s*e)\s*[:.\-]*\s*)?"
    rf"(?:[-–]\s+)?(?:{_ORDINAL}\s+(?:[-–]\s+)?)?(?:orden(?:ar|ase|enase)|confirm(?:ar|ase)|revoc(?:ar|ase)|"
    r"modific(?:ar|ase)|declar(?:ar|ase)|neg(?:ar|anse|ase)|den(?:egar|ieganse|iegase)|"
    r"exhort(?:ar|ase)|ampar(?:ar|ase)|conced(?:er|ese)|conform(?:ar|ase|ese)|sin costas)\b"
)
_DATE = re.compile(
    r"\b(?:(\d{1,2}) de )?(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) de (\d{4})\b"
)
_NUMBERS = {
    "un": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "doce": 12,
    "dieciocho": 18,
}
_TERM_NUMBER = rf"\d+|{'|'.join(_NUMBERS)}"
_TERM_UNIT = r"anos?|mes(?:es)?|dias?"
_TERM = re.compile(rf"\b({_TERM_NUMBER})(?:\s*\((\d+)\))?\s+({_TERM_UNIT})\b")
_REQUEST_TERM = re.compile(
    r"\s+(en(?: (?:un|el) plazo de)?|dentro de|cada) "
    rf"(\S+(?:\s*\(\d+\))? (?:{_TERM_UNIT}))(?: desde (.+))?$"
)
_REQUEST_TRIGGER = re.compile(r"\s+(una vez|desde) (.+)$")
_IMMEDIATE_TRIGGER = re.compile(
    r"\s+(?:que debe (?:comenzar|iniciarse) )?inmediatamente despues de (.+)$"
)
_AFTER_TERM = re.compile(
    r"^\s+(?:siguientes? al?|posteriores? al?|desde|contados? a partir de)\s+([^.,:;]+)"
)
_TIMED_ACTION_BREAK = re.compile(
    r"(?:\b(?:y|e|o|ni|asi como)(?:,\s*|\s+)|;\s*)"
    r"(?=(?:dentro de|en (?:un|el) plazo(?: maximo)? de|al cabo de)\b|"
    rf"en (?:{_TERM_NUMBER})(?:\s*\(\d+\))?\s+(?:{_TERM_UNIT})\b|"
    r"(?:debera[n]?\s+)?[a-z]{2,}(?:ar|er|ir|[ae]n?)[, :]\s*\w)"
)
_CLAUSE_BREAK = re.compile(
    r"\n[ \t]*\n|\n(?=[ \t]*[-–] |\s*\d+\.\d+\s*\.)"
    r"|\s+(?=y\s+(?:presente[n]?|rinda[n]?|remita[n]?|elabore[n]?)\s+(?:los?\s+)?informes?\b)",
    re.IGNORECASE,
)
_ORDER_VERB = r"(?:ordenar|ordenase|se ordena|se dispone|conminar|exhortar)"
_ADDRESSEE = re.compile(rf"\b{_ORDER_VERB} a(?:l| la)? (.+?)\bque\b")
_LOCAL_ORDER = re.compile(rf"\b{_ORDER_VERB}\b")
_INQUIRY_COMPLEMENT = re.compile(
    r"\b(informen?|comuniquen?|indiquen?|verifiquen?|determinen?)\s+si\b"
)
_DUTY = re.compile(r"\b(?:debe(?:ra)?n?|(?:estara|quedara)n? a cargo de)\b")
_NAME_WORD = r"[A-Z][a-zA-Z0-9-]*"
_PROPER_NAME = rf"{_NAME_WORD}(?: (?:(?:de(?: la| los| las)?|del|y|e) )?{_NAME_WORD})*"
_CORPORATE_INITIALS = r"(?:[A-Z]\.\s*)+[A-Z]\.?"
_DUTY_ADVERB = (
    r"(?:luego|despues|entonces|tambien|ademas|asimismo|aun|todavia"
    r"|posteriormente|previamente|seguidamente|finalmente|igualmente)"
)
_NEXT_DUTY = re.compile(
    rf"(?:[.!?;]\s*|\b(?:y|e|o|ni|asi como),?\s+)"
    rf"(?:(?:el|la|los|las)\s+[^,.;:!?]+?|"
    rf"(?!{_DUTY_ADVERB}\b)(?-i:{_PROPER_NAME}))"
    # Dotted initials in a business name stay with the subject.
    rf"(?: {_CORPORATE_INITIALS}|,\s*{_CORPORATE_INITIALS},)?"
    rf"(?:,\s*(?:(?!{_DUTY.pattern})[^,.;:!?])+,)?\s+{_DUTY.pattern}",
    re.IGNORECASE,
)
_OWN_SUBORDER = re.compile(
    rf"^[-–]?\s*\d+\.\d+\s*\.\s*"
    rf"(?:(?:(?!{_DUTY.pattern})[^,.;:])+,\s*)*"
    rf"((?:el|la|los|las)\s+[^,.;:]+?)\s+{_DUTY.pattern}"
)
_AFTER = re.compile(
    r"^posteriormente,.*\bejecutar dichas actividades\b.*\bvencimiento del termino anterior\b"
)
_LIST_INTRO = re.compile(r"^las (?:anotadas |referidas )?actividades son las siguientes:$")
_LIST_ITEM = re.compile(r"^[-–] [a-z]\. ")
_SUBORDER = re.compile(r"^(?:[-–] )?(\d+)\.(\d+)\s*\.")
_INHERITED_SUBORDER = re.compile(
    r"^(?:adopte|disene|efectue|establezca|formule|implemente|realice)\b"
)
_ANALYSIS_LIST = re.compile(r"(?:realice|efectue) analisis(?: [a-z]+)? de (?P<items>[a-z ,]+)\.?")
_LOCAL_ANALYSIS_QUALIFIER = re.compile(
    r"\b(?:de|del|en|sobre|entre|desde|hasta|fuera|dentro|procedentes?|provenientes?|"
    r"originari[oa]s?|tomad[oa]s?|obtenid[oa]s?|unicamente|exclusivamente)\b"
)
_BUDGET = "para el cumplimiento de la anterior orden,"
_CADENCE = r"(?:semanal|mensual|bimestral|trimestral|semestral|anual)"
_PERIODIC_PLAN = re.compile(rf"^este instrumento\b.*\bevaluacion periodica \(minimo ({_CADENCE})\)")
_EVALUATION_TOPIC = re.compile(rf"^(?:la )?evaluacion ({_CADENCE})$")
_COMMITTEE = re.compile(r"\bcomit[eé]\s+de\s+verificaci[oó]n\b", re.IGNORECASE)
_COMMITTEE_REPORT_QUERY = re.compile(
    r"(?:la )?(?:integracion|conformacion) (?:del|de un) comite de verificacion y (?:sus|los) informes"
)
_COMPOSITION = re.compile(r"\bintegrado\s+por\s*:", re.IGNORECASE)
_ACTOR_APPOSITION = re.compile(
    r"\bel\s+actor(?P<apposition>\s+de\s+la\s+presente\s+acci[oó]n\s+popular,"
    r"(?:\s+[A-ZÁÉÍÓÚ][\w]+){2,7}\s+)(?=o\s+un\s+representante\s+del\s+mismo)",
)
_COMPOUND = re.compile(
    r",\s+(?=sus |la |el |las |los )|\s+y\s+(?=(?:la|el|las|los|del|sobre|como|quien)\s)"
)
_ISSUER_ASIDE = re.compile(
    r",\s+(?:expedida|proferida)\s+por\s+[^,.\n]+(?=,\s+y\s+\d|\.)", re.IGNORECASE
)
_SENTENCE_TOPIC = re.compile(r"^(?:la )?(?:sentencia|providencia)\b")
_SENTENCE = re.compile(
    r"(?:la )?(?:sentencia|providencia)(?: (?P<appealed>apelada|recurrida))?"
    r"(?: del? (?P<date>[\w ]+?))?"
    r"(?: (?:dictada|proferida|emitida) por (?:el|la) (?P<issuer>.+))?\Z"
)
_RULING = re.compile(
    rf"^(?:[-–]\s+)?(?:{_ORDINAL}\s+)?(?:confirmar|confirmase|revocar|revocase|"
    r"modificar|modificase) (?:la )?(?:sentencia|providencia)\b(?: (?P<appealed>apelada|recurrida))?"
)
_TARGET_DATE = re.compile(
    r"^(?:, esto es, la (?:sentencia|providencia))? del? "
    rf"(?P<date>{_DATE.pattern})"
)
_ISSUED_BY = re.compile(
    r"^,? (?:dictada|proferida|emitida) por (?:el|la) ([^,.]+?)(?= que\b|,|\.|$)"
)
_APPEAL_TARGET = re.compile(r"\bcontra la (?:sentencia|providencia)\b")
_NULLITY_TOPIC = re.compile(r"^(?:las )?pretensiones(?: de la demanda)? de nulidad$")
_NULLITY_COMMISSION = re.compile(
    r"\b(?:decidir|resolver|decide|resuelve)\s+en\s+[úu]nica\s+instancia,?\s+la\s+demanda\b[^.!?]*?"
    r"\ben\s+ejercicio\s+de\s+la\s+acci[oó]n(?:\s+p[úu]blica)?\s+de\s+nulidad\b",
    re.IGNORECASE,
)
_DENIED_CLAIMS = re.compile(
    rf"^(?:{_ORDINAL}\s+)?(?:negar|nieganse) las pretensiones de la demanda\b"
)
_REVIEW_PROTECTION_TOPIC = re.compile(r"^(?:el )?amparo (?:del derecho )?a(?:l| la) (?P<right>.+)$")
_GRANT = re.compile(
    r"\ben\s+su\s+lugar,\s+conceder\s+el\s+amparo\s+de\s+los\s+derechos\s+fundamentales\b",
    re.IGNORECASE,
)
_GRANT_HOLDERS = re.compile(r"\s+de\s+las\s+comunidades\b", re.IGNORECASE)
_PROJECT_DETAIL = re.compile(r",\s+correspondiente\s+a\s+la\s+unidad\b", re.IGNORECASE)
_WORDS = re.compile(r"[a-z0-9]+")
_GRAMMAR = frozenset(
    "a al acerca como con cual cuando cuanto de del desde dicha dicho el en entre esa ese esta este estos fue hasta inicio la las los lo medida o para plazo por que se sobre su sus tiempo un una y".split()
)


def _flat(text: str, *, lowercase: bool = True) -> str:
    normalized = unicodedata.normalize("NFD", text.lower() if lowercase else text)
    folded = "".join(c for c in normalized if not unicodedata.combining(c))
    return " ".join(folded.split())


def _docket(value: str) -> tuple[str, str | None] | None:
    match = _DOCKET.fullmatch(value)
    if match is None:
        return None
    number = match["number"]
    canonical = (
        "t-" + number[2:].replace(".", "") if number.startswith("t-") else re.sub(r"\D", "", number)
    )
    return canonical, match["reference"]


def _metadata_docket(value: str) -> tuple[str, str | None] | None:
    if not value.endswith("(ap)"):
        return _docket(value)
    identity = _docket(value.removesuffix("(ap)").rstrip())
    if identity is not None and len(identity[0]) == 23 and identity[1] is None:
        return identity
    return None


@dataclass(frozen=True, slots=True)
class FragmentProvenance:
    """One entry from the verified collection's provenance manifest."""

    path: str
    line: int
    content_sha256: str
    metadata_sha256: str


@dataclass(frozen=True, slots=True)
class Passage:
    document: Document
    start: int
    end: int

    @property
    def text(self) -> str:
        return self.document.page_content[self.start : self.end]


@dataclass(frozen=True, slots=True)
class Resolution:
    answer: str
    sources: tuple[Document, ...]
    passages: tuple[Passage, ...]
    excerpts: tuple[str, ...]

    def presentation_sources(self) -> list[Document]:
        return [
            doc.model_copy(update={"page_content": excerpt, "metadata": dict(doc.metadata)})
            for doc, excerpt in zip(self.sources, self.excerpts, strict=True)
        ]


def _cited_excerpts(excerpts: Sequence[str]) -> str:
    return "\n".join(f"- «{text}» [doc{i}]" for i, text in enumerate(excerpts, 1))


@dataclass(frozen=True, slots=True)
class DocketEvidence:
    docket: str
    reference: str | None
    instance: str
    fragments: Mapping[str, FragmentProvenance]
    decisions: tuple[tuple[tuple[str, Passage], ...], ...]

    def select(self, documents: Sequence[Document], limit: int) -> list[Document]:
        selected: list[Document] = []
        lines: set[int] = set()
        for doc in documents:
            ident = doc.metadata.get("chunk_id")
            if not isinstance(ident, str):
                continue
            proof = self.fragments.get(ident)
            if proof is None or proof.line in lines or not _verified(doc, ident, proof):
                continue
            selected.append(doc)
            lines.add(proof.line)
            if len(selected) == limit:
                break
        return selected

    def select_for_question(
        self, question: str, documents: Sequence[Document], limit: int
    ) -> tuple[list[Document], str | None]:
        """Return sources and the literal answer for a reconstructed order, if any."""
        intent = _resolution_intent(question)
        if (
            not self.decisions
            or intent is None
            or not intent[0].lstrip("¿").startswith("que ordeno ")
        ):
            return self.select(documents, limit), None

        ranked = self.select(documents, len(documents))
        by_line = {self.fragments[doc.metadata["chunk_id"]].line: doc for doc in ranked}
        anchored = []
        for unit in self.decisions:
            lines = [self.fragments[ident].line for ident, _ in unit]
            if len(lines) > 1 and lines[0] in by_line and lines[-1] in by_line:
                anchored.append((unit, lines))
        if not anchored:
            return ranked[:limit], None
        if len(anchored) != 1:
            return [], None
        unit, lines = anchored[0]
        if len(lines) > limit or any(b != a + 1 for a, b in pairwise(lines)):
            return [], None

        verified = []
        for (original_id, span), line in zip(unit, lines, strict=True):
            original = span.document
            doc = by_line.get(line, original)
            if not _verified(original, original_id, self.fragments[original_id]):
                return [], None
            if doc is not original and not _verified(
                doc, doc.metadata["chunk_id"], self.fragments[doc.metadata["chunk_id"]]
            ):
                return [], None
            verified.append(Passage(doc, span.start, span.end))
        excerpts = _visible_order_sources(verified, intent[3])
        if not excerpts:
            return [], None
        citations = _cited_excerpts([doc.page_content for doc in excerpts])
        return excerpts, f"{self.instance.capitalize()}. Radicado {self.docket}.\n\n{citations}"


def _resolution_intent(question: str) -> re.Match[str] | None:
    if _is_deterministic_terminal(question):
        return None
    return _QUESTION.fullmatch(_flat(question))


def has_docket_intent(question: str) -> bool:
    return _resolution_intent(question) is not None


def needs_providencia_clarification(question: str) -> bool:
    """Detecta una orden o un plazo pedido con referencia explícitamente incompleta."""
    text = _flat(question)
    return bool(
        _PARTIAL_DOCKET.search(text)
        and _JUDICIAL_REFERENCE.search(text)
        and _UNKNOWN_INSTANCE.search(text)
        and _OPERATIVE_REQUEST.search(text)
        and not any(len(match["number"]) > 4 for match in _DOCKET.finditer(text))
    )


def requires_operative_proof(question: str) -> bool:
    """A claimed addressee, deadline or trigger needs direct operative support."""
    intent = _resolution_intent(question)
    if intent is not None:
        actor, subject = intent.group(2, 3)
        return bool(actor) or any(
            _REQUEST_TERM.search(part)
            or _REQUEST_TRIGGER.search(part)
            or _IMMEDIATE_TRIGGER.search(part)
            or part.startswith("sobre ")
            for part in _COMPOUND.split(subject)
        )
    return bool(
        not _is_deterministic_terminal(question)
        and _RESPONSIBILITY_QUESTION.fullmatch(_flat(question))
    )


def matches_answer_attribution(answer: str, docket: str, instance: str) -> bool:
    """Reject explicit contradictory attribution within a one-docket answer."""
    normalized = _flat(answer).lstrip("#*- ")
    if len(docket) == 4:
        plain = re.sub(r"[*_`]", "", normalized)
        if any(match[1] != docket for match in _ANSWER_SHORT_DOCKET.finditer(plain)):
            return False
    for clause in _ANSWER_CLAUSE_BREAK.split(answer):
        # Presentation markup does not alter the assertion's instance.
        plain = _flat(clause.replace("*", "").replace("_", "")).lstrip("#>- ")
        if (declared := _ANSWER_INSTANCE.match(plain)) and declared[1] != instance:
            return False
    return all(
        (match[0].replace(".", "") if match[0].startswith("t-") else re.sub(r"\D", "", match[0]))
        == docket
        for match in _ANSWER_DOCKET.finditer(normalized)
    )


def load_provenance(path: Path, expected_sha256: str | None) -> dict[str, FragmentProvenance]:
    """Load a pinned sidecar, checking the fields that authorize documentary use."""
    if not expected_sha256:
        raise ValueError("Falta la huella esperada de la procedencia documental.")
    data = path.read_bytes()
    if sha256(data).hexdigest() != expected_sha256:
        raise ValueError("La huella de la procedencia documental difiere de la configurada.")
    try:
        records = json.loads(data)["vector_records"]
        provenance: dict[str, FragmentProvenance] = {}
        for row in records:
            ident = row["id"]
            source = row["document_source"]
            file_path, line = source["path"], source["line"]
            content_sha, metadata_sha = row["page_content_sha256"], row["metadata_payload_sha256"]
            if (
                not isinstance(ident, str)
                or not ident
                or ident in provenance
                or not isinstance(file_path, str)
                or not file_path
                or type(line) is not int
                or line < 1
                or not all(
                    isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
                    for value in (content_sha, metadata_sha)
                )
            ):
                raise ValueError("Fila de procedencia documental inválida.")
            provenance[ident] = FragmentProvenance(file_path, line, content_sha, metadata_sha)
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError("Estructura de procedencia documental inválida.") from exc
    return provenance


@dataclass(frozen=True, slots=True)
class _Case:
    instance: str
    reference: str | None
    decisions: tuple[tuple[Passage, ...], ...]
    opening: tuple[Passage, ...]
    verified_documents: Mapping[str, tuple[Document, FragmentProvenance]]


def _verified(doc: Document, ident: str, proof: FragmentProvenance) -> bool:
    metadata = dict(doc.metadata)
    if metadata.get("chunk_id") != ident or doc.id not in {None, ident}:
        return False
    if metadata.get("id") == ident:
        del metadata["id"]  # The verified Gold A payload omits the loader's id.
    try:
        payload = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError):
        return False
    return (
        sha256(doc.page_content.encode()).hexdigest() == proof.content_sha256
        and sha256(payload.encode()).hexdigest() == proof.metadata_sha256
    )


def _opening_passages(
    rows: Sequence[tuple[FragmentProvenance, Document]], jurisdiction: str, docket: str
) -> list[Passage]:
    context: list[tuple[str, Passage]] = []
    for _, document in rows:
        if document.metadata.get("section_name") != "Contexto del caso":
            continue
        offset = 0
        for raw in document.page_content.splitlines(keepends=True):
            line = _flat(raw)
            if line:
                span = Passage(
                    document, offset + len(raw) - len(raw.lstrip()), offset + len(raw.rstrip())
                )
                context.append((line, span))
            offset += len(raw)
    start = 0
    if context and _OPENING_END.match(context[0][0].lstrip("# ")):
        # A leading OCR excerpt can precede the court's own cover. Restart only
        # at its identified heading and check the recorded docket in that opening.
        starts = [
            i
            for i, (line, _) in enumerate(context)
            if line.startswith("#") and line.lstrip("# ").startswith(jurisdiction)
        ]
        if len(starts) != 1:
            return []
        start = starts[0]
    passages = []
    for raw, span in context[start:]:
        if _OPENING_END.match(raw.lstrip("# ")):
            break
        passages.append(span)
    if start and not any(
        (identity := _metadata_docket(_flat(span.text).lstrip("# "))) and identity[0] == docket
        for span in passages
    ):
        return []
    return passages


def _header_lines(lines: Sequence[str]) -> list[str]:
    """Expose labeled Markdown cells with the same syntax as plain headings."""
    result: list[str] = []
    previous: list[str] = []
    labels: list[str] = []
    for line in lines:
        if not line.startswith("|"):
            result.append(line)
            previous = labels = []
            continue
        cells = [cell.strip() for cell in line.removeprefix("|").removesuffix("|").split("|")]
        if len(previous) == len(cells) and all(_TABLE_DIVIDER.fullmatch(cell) for cell in cells):
            labels = previous
            previous = []
            continue
        result.append(cells[0])
        if labels and len(labels) == len(cells):
            fields = zip(labels, cells, strict=True)
        else:
            labels = []
            fields = zip(cells[:-1], cells[1:], strict=True)
        for label, value in fields:
            label = label.rstrip(":").strip()
            if not value:
                continue
            if re.fullmatch(_DOCKET_LABEL, label):
                result.append(f"radicacion numero: {value.removeprefix('expediente samai ')}")
            elif label == "instancia":
                result.append(f"instancia: {value}")
        previous = cells
    return result


def _printed_dockets(lines: Sequence[str]) -> set[tuple[str, str | None]]:
    identities: set[tuple[str, str | None]] = set()
    for index, line in enumerate(lines):
        if marker := _PRINTED_DOCKET.fullmatch(line):
            printed = marker[1] or (lines[index + 1] if index + 1 < len(lines) else "")
            if match := _DOCKET.match(re.sub(r"\s*-\s*", "-", printed)):
                if identity := _docket(match.group()):
                    identities.add(identity)
    return identities


def _instance(
    lines: Sequence[str], jurisdiction: str, docket: str, reference: str | None
) -> str | None:
    lines = _header_lines(lines)
    if any(
        printed != docket
        or (auxiliary is not None and reference is not None and auxiliary != reference)
        for printed, auxiliary in _printed_dockets(lines)
    ):
        return None
    if docket.startswith("t-"):
        has_reference = any(
            _docket(line.removeprefix("expediente ")) == (docket, None)
            for line in lines
            if line.startswith("expediente ")
        )
        if (
            has_reference
            and "corte constitucional" in jurisdiction
            and any(_REVIEW_HEADING.fullmatch(line) for line in lines)
        ):
            return "sede de revision"
        return None

    found = set()
    for line in lines:
        if match := _INSTANCE_HEADING.fullmatch(line):
            found.add(match[1] or match[2])
        if match := _TRIAL_OPENING.match(line):
            found.add(match[1])
        if _SOLE_COMMISSION.match(line):
            found.add("unica")
        if _APPEAL_OPENING.match(line):
            found.add("segunda")
        # Some cover pages keep the case number and the type of review in one line.
        if " apelacion de sentencia - " in line and any(
            (identity := _docket(match.group())) is not None and identity[0] == docket
            for match in _DOCKET.finditer(line)
        ):
            found.add("segunda")
    for header in _SERIALIZED_HEADER.finditer("\n".join(lines)):
        if _docket(header["number"]) == (docket, None):
            found.add(header["instance"])
    return f"{found.pop()} instancia" if len(found) == 1 else None


def _decision_units(
    rows: Sequence[tuple[FragmentProvenance, Document]],
) -> tuple[tuple[Passage, ...], ...]:
    units: list[list[Passage]] = []
    current: list[Passage] | None = None
    previous = 0
    for proof, doc in rows:
        if doc.metadata.get("section_name") != "Decisión" or proof.line != previous + 1:
            current = None
        previous = proof.line
        if doc.metadata.get("section_name") != "Decisión":
            continue
        body = doc.page_content
        start = 0
        for boundary in [*_BOUNDARY.finditer(body), None]:
            end = boundary.start() if boundary else len(body)
            part = body[start:end]
            if part.strip():
                if current is None and _DECISION.match(_flat(part)):
                    current = []
                    units.append(current)
                if current is not None:
                    current.append(
                        Passage(
                            doc,
                            start + len(part) - len(part.lstrip()),
                            end - len(part) + len(part.rstrip()),
                        )
                    )
            if boundary is None:
                break
            if boundary["stop"]:
                return tuple(tuple(unit) for unit in units if unit)
            start = end
            current = []
            units.append(current)
    return tuple(tuple(unit) for unit in units if unit)


def _source_identity(
    rows: Sequence[tuple[FragmentProvenance, Document]],
) -> tuple[str, str | None, str] | None:
    first = rows[0][1].metadata
    source_fields = ("source", "Corporación", "Radicado", "doc_type")
    if any(doc.metadata.get(key) != first.get(key) for _, doc in rows for key in source_fields):
        return None
    if first.get("doc_type") != "jurisprudencia" or not first.get("source"):
        return None
    corporation, radicado = first.get("Corporación"), first.get("Radicado")
    if not isinstance(corporation, str) or not corporation.strip() or not isinstance(radicado, str):
        return None
    jurisdiction, raw_docket = _flat(corporation), _flat(radicado)
    identity = _metadata_docket(raw_docket)
    if identity is None:
        return None
    docket, reference = identity
    if len(docket) in {4, 22} and not docket.startswith("t-"):
        opening = [
            _flat(p.text).lstrip("# ") for p in _opening_passages(rows, jurisdiction, docket)
        ]
        if identity not in _printed_dockets(_header_lines(opening)):
            return None
    return docket, reference, jurisdiction


def _terms(text: str) -> set[tuple[int, str]]:
    terms = set()
    for number, repeated, unit in _TERM.findall(text):
        value = int(number) if number.isdecimal() else _NUMBERS[number]
        if repeated and value != int(repeated):
            return set()
        terms.add((value, unit[:3]))
    return terms


def _topic_words(text: str) -> tuple[str, ...]:
    return tuple(
        word.removesuffix("s") if len(word) > 3 else word
        for word in _WORDS.findall(text)
        if word not in _GRAMMAR
    )


def _ordered_words(subject: str, candidate: str) -> bool:
    wanted = _topic_words(subject)
    available = iter(_topic_words(candidate))
    return bool(wanted) and all(word in available for word in wanted)


def _operative_topic_matches(topic: str, text: str) -> bool:
    # The affirmative purpose can be stated with an infinitive or a subordinate clause.
    return _ordered_words(topic, text) or (
        re.search(r"\bpara recuperar\b", topic) is not None
        and not re.search(r"\b(?:no|ni|nunca)\b", text)
        and _ordered_words(topic, re.sub(r"\bpara que se recupere\b", "para recuperar", text))
    )


def _visible_order_sources(spans: Sequence[Passage], subject: str) -> list[Document]:
    """Use the same bounded, literal excerpts for generation and public citations."""
    inner_limit = 490  # Leave space for omission marks within the API's 500 characters.
    bodies = [" ".join(sanitize_replacement_chars(span.text).split()) for span in spans]
    seen = set(_topic_words(_flat(" ".join(body[:inner_limit] for body in bodies))))
    requested = set(_topic_words(subject))
    missing = requested - seen
    docs = []
    for span, body in zip(spans, bodies, strict=True):
        if len(body) > inner_limit:
            boundaries = [0, *(m.end() for m in _ANSWER_CLAUSE_BREAK.finditer(body)), len(body)]
            windows = [
                (start, body[start:end].strip())
                for index, start in enumerate(boundaries)
                for end in boundaries[index + 1 :]
                if 0 < end - start <= inner_limit
            ]
            if not windows:
                return []
            start, best = max(
                windows,
                key=lambda w: (len(set(_topic_words(_flat(w[1]))) & missing), w[0] == 0, len(w[1])),
            )
            if start and not set(_topic_words(_flat(best))) & missing:
                return []
            body = ("[…] " if start or span.start else "") + best + " […]"
        else:
            if span.document.page_content[: span.start].strip():
                body = "[…] " + body
            if span.document.page_content[span.end :].strip():
                body += " […]"
        docs.append(
            span.document.model_copy(
                update={"page_content": body, "metadata": dict(span.document.metadata)}
            )
        )
    visible = set(_topic_words(_flat(" ".join(doc.page_content for doc in docs))))
    return docs if requested <= visible else []


def _subspan(passage: Passage, start: int, end: int) -> Passage:
    return Passage(passage.document, passage.start + start, passage.start + end)


def _clauses(unit: tuple[Passage, ...]) -> list[Passage]:
    clauses: list[Passage] = []
    for passage in unit:
        start = 0
        for boundary in [*_CLAUSE_BREAK.finditer(passage.text), None]:
            end = boundary.start() if boundary else len(passage.text)
            text = passage.text[start:end]
            if text.strip():
                clause = _subspan(
                    passage,
                    start + len(text) - len(text.lstrip()),
                    start + len(text.rstrip()),
                )
                if clauses and _flat(clauses[-1].text) == _flat(text):
                    if _AFTER.match(_flat(text)):
                        clauses[-1] = clause
                else:
                    clauses.append(clause)
            if boundary is not None:
                start = boundary.end()
    return clauses


def _bounded_studies(heading: Passage) -> tuple[Passage, ...]:
    # Preserve the responsible parties, the act and the separate upper bound.
    studies = re.search(
        r"\b(?:realicen|realizar)\s+los\s+estudios\s+t[eé]cnicos\b",
        heading.text,
        re.IGNORECASE,
    )
    limit = re.search(r"\bsin\s+que\s+excedan\b[^.!?]*[.!?]?", heading.text, re.IGNORECASE)
    if studies and limit and studies.end() < limit.start():
        return _subspan(heading, 0, studies.end()), _subspan(heading, limit.start(), limit.end())
    return (heading,)


def _committee_passages(clause: Passage, composition: bool) -> tuple[Passage, ...]:
    label = _COMMITTEE.search(clause.text)
    if label is None:
        return ()
    if not composition:
        return (_subspan(clause, 0, label.end()),)
    roster = _COMPOSITION.search(clause.text, label.end())
    if roster is None:
        return ()
    title = _subspan(clause, label.start(), label.end())
    name = _ACTOR_APPOSITION.search(clause.text, roster.end())
    if name:
        return (
            title,
            _subspan(clause, roster.start(), name.start("apposition")),
            _subspan(clause, name.end("apposition"), len(clause.text)),
        )
    return title, _subspan(clause, roster.start(), len(clause.text))


def _actor_matches(actor: str | None, governing: Passage) -> bool:
    if actor is None:
        return True
    literal_text = _flat(governing.text, lowercase=False)
    text = _operative_scope(literal_text.lower())
    suborder = _SUBORDER.match(text)
    if suborder:
        opening = text[suborder.end() :].lstrip()
        declaration = _OWN_SUBORDER.match(text) or _ADDRESSEE.match(text, len(text) - len(opening))
        if declaration and (
            _LOCAL_ORDER.search(text, declaration.end())
            or _NEXT_DUTY.search(literal_text, declaration.end(), len(text))
        ):
            return False
    else:
        declaration = _ADDRESSEE.search(text)
    if declaration is None:
        return False
    named = declaration[1].strip(" ,")
    if _topic_words(actor) == _topic_words(named) or (
        len(actor) >= 3 and _topic_words(named) == (actor, "e", "s", "p")
    ):
        return True
    if re.search(r"\b(?:y|o|ni)\b|[;,]", named):
        return False
    if actor in {"departamento", "municipio", "distrito"} and named.startswith(
        (actor + " de ", actor + " del ")
    ):
        return True
    literal = re.search(_ADDRESSEE.pattern, " ".join(governing.text.split()), re.IGNORECASE)
    if literal is None or _flat(literal[1]).strip(" ,") != named:
        return False
    acronym = re.search(r"([A-Z][A-Z0-9]{2,})\s*,?\s*$", literal[1])
    return bool(
        acronym
        and actor == _flat(acronym[1])
        and re.search(r"[a-záéíóúñ]", literal[1][: acronym.start()])
    )


def _operative_scope(text: str) -> str:
    # A question embedded in an order to report does not bind the reporter to
    # perform the action being investigated.
    if complement := _INQUIRY_COMPLEMENT.search(text):
        return text[: complement.end(1)]
    return text


def _exception_evidence(clause: Passage, topic: str) -> tuple[Passage, ...]:
    if not re.match(rf"^{_ORDINAL}\s+declarar (?:no )?probada la excepcion\b", _flat(clause.text)):
        return (clause,)
    spans = []
    start = 0
    for aside in _ISSUER_ASIDE.finditer(clause.text):
        spans.append(_subspan(clause, start, aside.start()))
        start = aside.end()
    spans.append(_subspan(clause, start, len(clause.text)))
    return (
        tuple(spans) if _ordered_words(topic, _flat(" ".join(p.text for p in spans))) else (clause,)
    )


_COMMITTEE_REPORT = re.compile(
    r",\s*(?P<report>quienes\s+deber[aá]n\s+informar\s+cada\s+(?P<interval>[^,.;]+))",
    re.IGNORECASE,
)
_ROSTER_PAGE_HEADER = re.compile(
    r"(?i:radicaci[oó]n\s+n[uú]m[.:]+)\s*(?P<docket>[\d-]+)\s+"
    r"[Dd]emandante:\s+(?:[A-ZÁÉÍÓÚÑ][\w.-]*\s+){2,}(?:y\s+otr[oa]s?\s+)?"
    r"(?=legal\s+de\b)",
)


_ROSTER_CLAUSE = re.compile(
    r"[.!?:]|\b\w+(?:ar|er|ir)án?\b|\b(?:deben?|deban?|pueden?|puedan?)\b"
    r"|\b(?:han? de|se (?:ordena|dispone|autoriza))\b"
    r"|\b(?:design|deleg|nombr)(?:a|an|ó|aron)\b"
    r"|\b(?:qued|est)(?:[aá]n?|ar[aá]n?)\s+\w+(?:ad|id)[oa]s?\s+(?:a|para)\s+\w+(?:ar|er|ir)\b"
    r"|\b(?=\w*[áéíóú])\w+se\b",
    re.IGNORECASE,
)
_ROSTER_DETERMINER = r"(?:el|la|los|las|un|una|unos|unas)"
_ROSTER_CONJUNCTION = r"(?:y|e|o|u)"
_ROSTER_COORDINATION = re.compile(
    rf"\b{_ROSTER_CONJUNCTION} (?={_ROSTER_DETERMINER}\b)", re.IGNORECASE
)
_ROSTER_MEMBER_PREFIX = rf"(?:{_ROSTER_DETERMINER}|{'|'.join(_NUMBERS)}|\d+)"
# Keep a compound proper name together when it contains a conjunction.
_ROSTER_NOUN = rf"(?>(?-i:{_PROPER_NAME})|[\w-]+)"
_ROSTER_NOMINAL = (
    rf"(?:{_ROSTER_MEMBER_PREFIX} )?{_ROSTER_NOUN}"
    rf"(?: (?:de|del)(?: {_ROSTER_DETERMINER})? {_ROSTER_NOUN})*"
)
_ROSTER_MEMBER = re.compile(_ROSTER_NOMINAL, re.IGNORECASE)
_ROSTER_APPOINTER = rf"(?:{_ROSTER_DETERMINER} )?(?:(?-i:{_PROPER_NAME})|[\w-]+)"
_ROSTER_DESIGNATION = r"(?:designe|delegue|nombre)n?"
_ROSTER_DELEGATE = (
    rf"(?: que (?:(?:este|esta|se) \w+|"
    rf"{_ROSTER_APPOINTER} {_ROSTER_DESIGNATION}|"
    rf"{_ROSTER_DESIGNATION} {_ROSTER_APPOINTER}))?"
)
_ROSTER_ANTECEDENT = re.compile(
    rf"(?:y )?(?:por )?{_ROSTER_NOMINAL}{_ROSTER_DELEGATE}"
    rf"(?: {_ROSTER_CONJUNCTION} (?:por )?{_ROSTER_NOMINAL}{_ROSTER_DELEGATE})*",
    re.IGNORECASE,
)
_ROSTER_COMPOUND_AUXILIARY = r"(?:ha|habia|habra)"
_ROSTER_COMPOUND_PARTICIPLE = r"(?:design|deleg|nombr)ado"
_ROSTER_COMPOUND = rf"{_ROSTER_COMPOUND_AUXILIARY}n? {_ROSTER_COMPOUND_PARTICIPLE}"
_ROSTER_COMPOUND_MENTION = re.compile(rf"\b{_ROSTER_COMPOUND}\b", re.IGNORECASE)
_ROSTER_RELATIVE_LINK = re.compile(r" que ", re.IGNORECASE)
_ROSTER_COMPOUND_APPOINTER = (
    rf"(?!(?:un|una|unos|unas|{'|'.join(_NUMBERS)}|\d+)\b){_ROSTER_APPOINTER}"
)
_ROSTER_COMPOUND_RELATIVE = re.compile(
    rf"(?:{_ROSTER_COMPOUND_APPOINTER} {_ROSTER_COMPOUND}|"
    # A subject after the verb must be definite and agree with the auxiliary.
    rf"{_ROSTER_COMPOUND_AUXILIARY} {_ROSTER_COMPOUND_PARTICIPLE} "
    rf"(?=(?:el|la) ){_ROSTER_COMPOUND_APPOINTER}|"
    rf"{_ROSTER_COMPOUND_AUXILIARY}n {_ROSTER_COMPOUND_PARTICIPLE} "
    rf"(?=(?:los|las) ){_ROSTER_COMPOUND_APPOINTER})",
    re.IGNORECASE,
)


def _roster_entry_for_validation(member: str) -> str:
    label = _flat(member, lowercase=False)
    compounds = _ROSTER_COMPOUND_MENTION.findall(label)
    if not compounds:
        return label
    parts = _ROSTER_RELATIVE_LINK.split(label, maxsplit=1)
    if len(compounds) == 1 and len(parts) == 2:
        nominal, relative = parts
        if _ROSTER_ANTECEDENT.fullmatch(nominal) and _ROSTER_COMPOUND_RELATIVE.fullmatch(relative):
            return nominal
    return ""


def _committee_reporting(
    clauses: Sequence[Passage], requested: set[tuple[int, str]]
) -> tuple[Passage, ...]:
    if not clauses or not requested:
        return ()
    head = clauses[0]
    if re.match(rf"^{_ORDINAL}\s+conformese el comite de verificacion\b", _flat(head.text)) is None:
        return ()
    roster = re.search(r"\bestar[aá]\s+integrado\s+por\b", head.text, re.IGNORECASE)
    if roster is None:
        return ()

    tail = head
    tail_start = roster.end()
    if not _COMMITTEE_REPORT.search(head.text, roster.end()):
        # The printed docket can interrupt a role name at a page boundary.
        # A free-standing block, a suborder, or a different document cannot
        # supply the antecedent of "quienes".
        if len(clauses) < 2 or not _flat(head.text).endswith(" representante"):
            return ()
        tail = clauses[1]
        raw_docket = head.document.metadata.get("Radicado")
        header = _ROSTER_PAGE_HEADER.match(tail.text)
        if (
            tail.document is not head.document
            or head.end >= tail.start
            or head.document.page_content[head.end : tail.start].strip()
            or not header
            or not isinstance(raw_docket, str)
            or _docket(header["docket"]) != _metadata_docket(_flat(raw_docket))
        ):
            return ()
        tail_start = header.end()

    reports = list(_COMMITTEE_REPORT.finditer(tail.text, tail_start))
    if len(reports) != 1:
        return ()
    report = reports[0]
    if _terms(_flat(report["interval"])) != requested:
        return ()
    membership = tail.text[tail_start : report.start()]
    if tail is not head:
        membership = head.text[roster.end() :] + " " + membership
    members = re.split(r"[,;]", membership)
    # Classify compound designation as part of a roster entry only when
    # the entire relative is attached to a validated nominal. Keep the citation literal.
    checked_members = [_roster_entry_for_validation(member) for member in members]
    if (
        not all(checked_members)
        or _ROSTER_CLAUSE.search(membership)
        or any(not re.match(r"(?:y )?por ", member, re.I) for member in checked_members[1:])
        # Without a new "por", a coordinated determiner must introduce a
        # simple nominal member, not a sentence with its own subject.
        or any(
            not _ROSTER_MEMBER.fullmatch(coordinated.strip())
            for member in checked_members
            for coordinated in _ROSTER_COORDINATION.split(member)[1:]
        )
        # The immediate antecedent of "quienes" must be a full roster entry.
        or not _ROSTER_ANTECEDENT.fullmatch(checked_members[-1])
    ):
        return ()

    full_report = tail.text[report.start("report") :]
    if re.fullmatch(r"[^.!?]+\.?", full_report.strip()) is None:
        return ()
    if tail is head and len(head.text) <= 492:
        return (head,)
    if tail is not head and len(head.text) + len(tail.text) - tail_start <= 487:
        return head, _subspan(tail, tail_start, len(tail.text))

    # Preserve the constitution and report with the first and last intact
    # roster entries. The intervening entries are omitted visibly.
    first_end = roster.end() + len(members[0].rstrip())
    last_member = re.search(
        r"(?:^|[,;])\s*(?:y\s+)?por\s+([^,;]+)$", tail.text[tail_start : report.start()], re.I
    )
    if last_member is None:
        return ()
    last_start = tail_start + last_member.start(1)
    if tail is head and first_end >= last_start:
        return ()
    return (
        _subspan(head, 0, first_end),
        _subspan(tail, last_start, len(tail.text)),
    )


_MONITORING_SCOPE = re.compile(
    r"(?:establezca|implemente|adopte) (?:un|el) programa de monitoreo (?P<scope>[^.!?;]+)\.?"
)
_SITE_EXCLUSION = re.compile(
    r"\b(?:no|ni|salvo|excepto|exclu\w*|exceptu\w*|descart\w*)\b"
    r"|\b(?:fuera del?|sin (?:incluir|comprender|abarcar)|eventual(?:mente)?|posible(?:mente)?)\b"
)
_SITE_MODIFIER = re.compile(r"\b(?:antes|despues|cuando|mientras|para|previa|segun|si)\b")
_SITE_COORDINATION = re.compile(r"\s*(?:,\s*(?:(?:y|e)\s+)?|\s+(?:y|e)\s+)")
_SITE_MATERIAL = r"(?P<material>\w+) (?:ubicad[oa]s? )?"
_SITE_LINK = r"(?:del?|en) "
_SITE_ARTICLE = r"(?:(?:el|la|los|las) )?"
_REQUEST_SITE = re.compile(rf"{_SITE_MATERIAL}{_SITE_LINK}(?P<place>.+)")
_MONITORED_SITE = re.compile(
    rf"(?:continuo )?{_SITE_LINK}(?:la calidad {_SITE_LINK}{_SITE_ARTICLE}\w+ (?:y|e) )?"
    rf"{_SITE_ARTICLE}{_SITE_MATERIAL}(?P<area>en el area de influencia )?"
    rf"{_SITE_LINK}(?P<places>.+)"
)
_NAMED_WATER_BODY = re.compile(
    rf"{_SITE_ARTICLE}(?:bahia|cienaga|ensenada|estuario|golfo|laguna|mar|quebrada|rio) de "
    r"(?!(?:el|la|los|las)\b)(?P<name>.+)"
)


def _monitored_site_matches(site: str, scope: str) -> bool:
    requested = _REQUEST_SITE.fullmatch(site)
    declared = _MONITORED_SITE.fullmatch(scope)
    if not requested or not declared or requested["material"] != declared["material"]:
        return False
    wanted = _topic_words(requested["place"])
    locations = _SITE_COORDINATION.split(declared["places"])
    for location in locations:
        # Repeated material in a coordinated site has the same locative link.
        repeated = re.fullmatch(rf"{_SITE_ARTICLE}{_REQUEST_SITE.pattern}", location)
        if repeated and repeated["material"] == requested["material"]:
            location = repeated["place"]
        if _topic_words(location) == wanted:
            return True
        # A named body of water may be identified by its name alone. A site's
        # name inside an infrastructure description does not establish scope.
        feature = _NAMED_WATER_BODY.fullmatch(location) if declared["area"] else None
        if feature and _topic_words(feature["name"]) == wanted:
            return True
    return False


def _analysis_context(topic: str, current: Passage, previous: Passage) -> bool:
    analysis, separator, site = topic.partition(" en los ")
    if not analysis.startswith("los analisis de ") or not separator:
        return False
    previous_text = _flat(previous.text)
    earlier = _SUBORDER.match(previous_text)
    program = (
        _MONITORING_SCOPE.fullmatch(previous_text[earlier.end() :].strip()) if earlier else None
    )
    current_text = _flat(current.text)
    later = _SUBORDER.match(current_text)
    analysis_list = (
        _ANALYSIS_LIST.fullmatch(current_text[later.end() :].lstrip()) if later else None
    )
    return bool(
        earlier
        and later
        and earlier[1] == later[1]
        and int(earlier[2]) + 1 == int(later[2])
        and program
        # Only one affirmative monitoring order can establish a site.
        and not _TIMED_ACTION_BREAK.search(program["scope"])
        and not _SITE_EXCLUSION.search(program["scope"])
        and not _SITE_MODIFIER.search(program["scope"])
        and analysis_list
        and not _LOCAL_ANALYSIS_QUALIFIER.search(analysis_list["items"])
        and _monitored_site_matches(site, program["scope"])
        and _ordered_words(analysis, current_text)
    )


_PLAIN_DENIAL = re.compile(
    rf"^(?:{_ORDINAL}\s+(?:[-–]\s+)?)?negar las pretensiones de la demanda "
    r"dentro del medio de control de proteccion de los derechos (?:e )?intereses colectivos"
)
_PARTY_TOKEN = r"(?:[A-ZÁÉÍÓÚÑ][\w.-]*|(?:la|las|el|los|señora?|e|y|de|del)\b|[-–])"
_IDENTIFIED_PARTIES = re.compile(
    rf"incoad[ao]\s+por\s+(?:{_PARTY_TOKEN}\s+)+en\s+contra\s+de\s+"
    rf"(?:{_PARTY_TOKEN}\s+)*{_PARTY_TOKEN},\s+por\s+los\s+argumentos\s+expuestos"
    r"\s+en\s+esta\s+providencia\.?"
)
_SCOPE_CONDITION = re.compile(
    r"\b(?:excepto|salvo|parcial\w*|unicamente|solamente|solo|exclusivamente|limitad\w*)\b"
    r"|\b(?:sin perjuicio|en cuanto|respecto de|en lo que|en lo relativo|"
    r"en la (?:parte|medida)|siempre que|se reconoce)\b"
)


def _operative_excerpt(clause: Passage, topic: str) -> Passage:
    body = clause.text
    # A list of ancillary requirements is included only if the requested
    # scope needs it.
    auxiliary = re.search(r",\s+el\s+cual\s+deber[aá]\s*:\s*\(i\)", body, re.IGNORECASE)
    if auxiliary and _ordered_words(topic, _flat(body[: auxiliary.start()])):
        return _subspan(clause, 0, auxiliary.start())
    if topic == "las pretensiones de la demanda":
        # In an unqualified denial, preserve the exact kind of proceeding.
        # Shorten only a recognized identification of the parties and a
        # referral to the reasons already stated in the decision.
        literal_scope = re.search(r"\s+incoad[ao]\s+por\s+", body, re.IGNORECASE)
        if (
            literal_scope
            and _PLAIN_DENIAL.fullmatch(_flat(body[: literal_scope.start()]))
            and _IDENTIFIED_PARTIES.fullmatch(body[literal_scope.start() :].strip())
            and not _SCOPE_CONDITION.search(_flat(body[literal_scope.start() :]))
        ):
            return _subspan(clause, 0, literal_scope.start())
    return clause


def _matches_immediate_act(topic: str, event: str, text: str, actor: str | None) -> bool:
    predicate = re.escape(topic)
    if re.match(r"(?:la|el|las|los)\s", topic):
        predicate = (
            r"(?:comenzar|iniciar|ejecutar|realizar|efectuar|"
            r"comience|inicie|ejecute|realice|efectue) " + predicate
        )
    mandate = re.compile(
        rf"(?i:(?:{_ORDINAL} )?(?:ordenar|ordenase|se ordena))"
        rf"(?: (?i:al|a la|a los|a las|a) (?P<recipient>.+?) (?i:que))? "
    )
    for sentence in _ANSWER_CLAUSE_BREAK.split(_flat(text, lowercase=False)):
        condition = _IMMEDIATE_TRIGGER.search(sentence.lower().rstrip(".;,: "))
        if condition is None or condition[1] != event:
            continue
        found = mandate.match(sentence)
        if not found:
            continue
        # Match the action after the first explicit delimiter. A mandate to
        # consider another act does not impose the act itself.
        recipient = found["recipient"]
        if recipient and not re.fullmatch(_PROPER_NAME, recipient):
            continue
        if re.fullmatch(predicate, sentence[found.end() : condition.start()], re.IGNORECASE) and (
            actor is None or (recipient and _flat(recipient) == actor)
        ):
            return True
    return False


def _act_evidence(
    subject: str, actor: str | None, unit: tuple[Passage, ...], linked: bool
) -> tuple[Passage, ...]:
    clauses = _clauses(unit)
    if not clauses:
        return ()
    heading = clauses[0]
    timing = _REQUEST_TERM.search(subject)
    requested = _terms(timing[2]) if timing and _TERM.fullmatch(timing[2]) else set()
    if timing and not requested:
        return ()
    trigger_only = _REQUEST_TRIGGER.search(subject) if timing is None else None
    immediate = _IMMEDIATE_TRIGGER.search(subject) if not (timing or trigger_only) else None
    constraint = timing or trigger_only or immediate
    topic = subject[: constraint.start()].rstrip() if constraint else subject
    topic = re.sub(r"^sobre |^del |^quien vigila\s+|^como se integra\s+", "", topic)
    topic = re.sub(r"^(?:la )?formulacion (?:del|de un) (?=plan\b)", "formule el ", topic)
    if subject.startswith("quien vigila "):
        topic = "vigilancia " + topic.replace("lugares restituidos", "sectores restituidos")
    linked_budget = topic == "el presupuesto para esas actividades"
    committee = topic in (
        "comite que vigila el cumplimiento",
        "el comite de seguimiento",
    )
    composition = subject.startswith("como se integra ")
    evaluation = _EVALUATION_TOPIC.fullmatch(topic) if immediate is None else None
    costs = topic in ("las costas del proceso", "costas del proceso")
    exhortation = topic.startswith("el exhorto sobre ")
    if exhortation:
        topic = topic.removeprefix("el exhorto sobre ")
    relief_request = topic.startswith("la solicitud de amparo ")
    if relief_request:
        topic = topic.removeprefix("la solicitud de ")
    if (
        _COMMITTEE_REPORT_QUERY.fullmatch(topic)
        and timing
        and timing[1] == "cada"
        and not timing[3]
        and actor is None
    ):
        return _committee_reporting(clauses, requested)
    if linked_budget and not linked:
        return ()
    matches: list[tuple[Passage, ...]] = []
    for index, clause in enumerate(clauses):
        text = _flat(clause.text)
        inherited: tuple[Passage, ...] = ()
        rule = clause
        addressee = clause
        if _LIST_ITEM.match(text) and index >= 2:
            # Exactly one explicit list introduction and phase must precede this item.
            prior = next(
                (
                    i
                    for i in range(index - 1, 0, -1)
                    if not _LIST_ITEM.match(_flat(clauses[i].text))
                ),
                0,
            )
            if (
                prior < 2
                or not _LIST_INTRO.fullmatch(_flat(clauses[prior].text))
                or not _AFTER.match(_flat(clauses[prior - 1].text))
            ):
                continue
            rule, addressee = clauses[prior - 1], heading
            inherited = (*_bounded_studies(heading), rule, clauses[prior])
        elif clause is not heading and _ADDRESSEE.search(_flat(heading.text)):
            scope = _operative_scope(text)
            suborder = _SUBORDER.match(scope)
            continuation = (
                _INHERITED_SUBORDER.match(scope[suborder.end() :].lstrip()) is not None
                if suborder
                else scope.startswith(("- ", "obras "))
            )
            # A numbered paragraph only inherits the recipient when its opening
            # continues the parent order and the clause has no own mandate.
            if continuation and not (_LOCAL_ORDER.search(scope) or _DUTY.search(scope)):
                addressee = heading
                if not _TERM.search(scope):
                    rule = heading
                inherited = (heading,)
        if timing:
            timing_text = _operative_scope(_flat(rule.text))
            if rule is clause:
                # A term stated for a coordinated operation only supports that
                # operation. A separate inherited term is checked at its source.
                scopes = [
                    scope
                    for scope in _TIMED_ACTION_BREAK.split(timing_text)
                    if _operative_topic_matches(topic, scope)
                ]
                if len(scopes) != 1:
                    continue
                timing_text = scopes[0]
            if requested != _terms(timing_text):
                continue
            recurring = {
                bool(re.search(r"\bcada $", timing_text[: term.start()]))
                for term in _TERM.finditer(timing_text)
            }
            if recurring != {timing[1] == "cada"}:
                continue
            trigger = timing[3]
            if trigger and not any(
                (start := _AFTER_TERM.match(timing_text[term.end() :]))
                and _topic_words(trigger)
                == _topic_words(start[1].removeprefix("la "))[: len(_topic_words(trigger))]
                for term in _TERM.finditer(timing_text)
            ):
                continue
        if trigger_only:
            # A superseded term can be visible without a number in the judgment.
            # Accept only an explicit leading condition attached to this act.
            opening = re.match(r"^[-–]? ?[a-z]?(vencido el termino anterior),", text)
            if trigger_only[1] != "una vez" or not opening or opening[1] != trigger_only[2]:
                continue
        if immediate and not _matches_immediate_act(topic, immediate[1], clause.text, actor):
            continue
        if not _actor_matches(actor, addressee):
            continue
        if linked_budget:
            if text.startswith(_BUDGET) and "presupuesto" in text:
                matches.append((clause,))
            continue
        if committee:
            if "se ordena la integracion" in text and "seguimiento" in text:
                if evidence := _committee_passages(clause, composition):
                    matches.append(evidence)
            continue
        if evaluation:
            if (
                index
                and (cadence := _PERIODIC_PLAN.match(text))
                and cadence[1] == evaluation[1]
                and _flat(clauses[index - 1].text).startswith("el referido plan ")
            ):
                matches.append((clauses[index - 1], clause))
            continue
        if costs:
            if re.match(
                rf"^(?:{_ORDINAL}\s+(?:[-–]\s+)?)?(?:no se condena en costas|sin (?:condena en )?costas)\b",
                text,
            ):
                matches.append((clause,))
            continue
        if exhortation and not re.match(rf"^(?:{_ORDINAL}\s+(?:[-–]\s+)?)?exhortar\b", text):
            continue
        if relief_request and not re.match(
            rf"^(?:{_ORDINAL}\s+(?:[-–]\s+)?)?(?:negar|conceder) el amparo\b", text
        ):
            continue
        if index and not constraint and _analysis_context(topic, clause, clauses[index - 1]):
            matches.append((*inherited, clauses[index - 1], clause))
            continue
        if _operative_topic_matches(topic, _operative_scope(text)):
            if trigger_only:
                examples = re.search(
                    r",\s+entre\s+las\s+que\s+se\s+encuentran\b",
                    clause.text,
                    re.IGNORECASE,
                )
                if examples and _ordered_words(topic, _flat(clause.text[: examples.start()])):
                    clause = _subspan(clause, 0, examples.start())
            matches.append(
                (
                    *inherited,
                    *_exception_evidence(_operative_excerpt(clause, topic), topic),
                )
            )
    return matches[0] if len(matches) == 1 else ()


def _unique_decision(spans: Sequence[Passage], case: _Case) -> Passage | None:
    if not spans:
        return None
    first = previous = spans[0]
    original = " ".join(first.text.split())
    for span in spans[1:]:
        previous_line = case.verified_documents[previous.document.metadata["chunk_id"]][1].line
        line = case.verified_documents[span.document.metadata["chunk_id"]][1].line
        if line != previous_line + 1 or " ".join(span.text.split()) != original:
            return None
        previous = span
    return first


def _appeal_anchors(case: _Case, date: str, issuer: str) -> list[Passage]:
    anchors = []
    for span in case.opening:
        text = _flat(span.text).lstrip("# ")
        if not _APPEAL_OPENING.match(text) or not (target := _APPEAL_TARGET.search(text)):
            continue
        described = text[target.end() :]
        subject_date = _TARGET_DATE.match(described)
        subject_issuer = _ISSUED_BY.match(described[subject_date.end() :]) if subject_date else None
        if not (subject_date and subject_issuer) or (subject_date["date"], subject_issuer[1]) != (
            date,
            issuer,
        ):
            return []
        anchors.append(span)
    return anchors


def _sentence_evidence(case: _Case, topic: str) -> tuple[Passage, ...]:
    request = _SENTENCE.fullmatch(topic)
    if request is None or not (request["date"] or request["appealed"]):
        return ()
    wanted = _DATE.fullmatch(request["date"]) if request["date"] else None
    if request["date"] and wanted is None:
        return ()

    matches = []
    for unit in case.decisions:
        for span in _clauses(unit):
            text = _flat(span.text)
            if not (ruling := _RULING.match(text)):
                continue
            decision = text[ruling.end() :]
            target = _TARGET_DATE.match(decision)
            date = _DATE.fullmatch(target["date"]) if target else None
            issuer = _ISSUED_BY.match(decision[target.end() :] if target else decision)
            if wanted and (
                date is None
                or any(
                    expect is not None and expect != seen
                    for expect, seen in zip(wanted.groups(), date.groups(), strict=True)
                )
            ):
                continue
            if request["issuer"] and (issuer is None or request["issuer"] != issuer[1]):
                continue
            requires_opening = request["appealed"] and not ruling["appealed"]
            opening = []
            if requires_opening:
                if case.instance != "segunda instancia" or date is None or issuer is None:
                    continue
                opening = _appeal_anchors(case, date[0], issuer[1])
                if len({_flat(p.text) for p in opening}) != 1:
                    continue
            matches.append((span, opening))
    selected = _unique_decision([span for span, _ in matches], case)
    if selected is None:
        return ()
    return (*matches[0][1][:1], selected)


def _nullity_evidence(case: _Case) -> tuple[Passage, ...]:
    if case.instance != "unica instancia":
        return ()
    context = []
    for span in case.opening:
        text = _flat(span.text).lstrip("# ")
        if (_SOLE_COMMISSION.match(text) or _TRIAL_OPENING.match(text)) and (
            found := _NULLITY_COMMISSION.search(span.text)
        ):
            context.append(_subspan(span, found.start(), found.end()))
    if len({_flat(p.text) for p in context}) != 1:
        return ()
    matches = [
        span
        for unit in case.decisions
        for span in _clauses(unit)
        if _DENIED_CLAIMS.match(_flat(span.text))
    ]
    ruling = _unique_decision(matches, case)
    return (context[0], ruling) if ruling else ()


def _review_grant_evidence(case: _Case, right: str) -> tuple[Passage, ...]:
    matches = []
    for unit in case.decisions:
        for span in _clauses(unit):
            body = span.text
            if not _RULING.match(_flat(body)) or not (grant := _GRANT.search(body)):
                continue
            holders = _GRANT_HOLDERS.search(body, grant.end())
            if holders is None or not re.search(
                rf"\ba(?:l| la) {re.escape(right)}$", _flat(body[grant.end() : holders.start()])
            ):
                continue
            detail = _PROJECT_DETAIL.search(body, holders.end())
            end = detail.start() if detail else len(body)
            matches.append(_subspan(span, grant.start(), end))
    selected = _unique_decision(matches, case)
    return (selected,) if selected else ()


class ResolutionIndex:
    """A pure index built from the same Document sequence supplied to BM25."""

    def __init__(
        self,
        documents: Sequence[Document],
        provenance: Mapping[str, FragmentProvenance],
    ):
        sources: dict[str, list[tuple[FragmentProvenance, Document]]] = defaultdict(list)
        expected: dict[str, set[str]] = defaultdict(set)
        for expected_id, expected_proof in provenance.items():
            expected[expected_proof.path].add(expected_id)

        seen: set[str] = set()
        unsuccessful: set[str] = set()
        for document in documents:
            ident = document.metadata.get("id", document.id or document.metadata.get("chunk_id"))
            if not isinstance(ident, str):
                continue
            proof = provenance.get(ident)
            if proof is None:
                continue
            if ident in seen or not _verified(document, ident, proof):
                unsuccessful.add(proof.path)
                continue
            seen.add(ident)
            sources[proof.path].append((proof, document))

        self.snapshot_verified = bool(seen) and len(seen) == len(documents) == len(provenance)

        candidates: dict[
            str, list[tuple[str | None, str, list[tuple[FragmentProvenance, Document]]]]
        ] = defaultdict(list)
        for path, rows in sources.items():
            if not path:
                continue
            positions = {proof.line for proof, _ in rows}
            if min(positions) < 1 or len(positions) != len(rows):
                continue
            ordered = sorted(rows, key=lambda row: row[0].line)
            if identity := _source_identity(ordered):
                docket, reference, jurisdiction = identity
                candidates[docket].append((reference, jurisdiction, ordered))

        self._cases: dict[str, _Case] = {}
        self._dockets: dict[str, DocketEvidence] = {}
        for docket, matches in candidates.items():
            signature = None
            fragments: dict[str, FragmentProvenance] = {}
            decisions: tuple[tuple[Passage, ...], ...] = ()
            for reference, jurisdiction, ordered in matches:
                path = ordered[0][0].path
                # A partial source can establish a collision. Only a complete
                # source can support an answer or prove an equivalent copy.
                if path in unsuccessful or len(ordered) != len(expected[path]):
                    break
                opening = _opening_passages(ordered, jurisdiction, docket)
                instance = _instance(
                    [_flat(p.text).lstrip("# ") for p in opening], jurisdiction, docket, reference
                )
                if instance is None:
                    break
                source_signature = (
                    reference,
                    jurisdiction,
                    instance,
                    tuple(
                        (proof.line, proof.content_sha256, doc.metadata.get("section_name"))
                        for proof, doc in ordered
                    ),
                )
                if signature is not None and source_signature != signature:
                    break
                if signature is None:
                    decisions = _decision_units(ordered)
                signature = source_signature
                fragments.update({doc.metadata["chunk_id"]: proof for proof, doc in ordered})
                if len(matches) == 1:
                    self._cases[docket] = _Case(
                        instance,
                        reference,
                        decisions,
                        tuple(opening),
                        {doc.metadata["chunk_id"]: (doc, proof) for proof, doc in ordered},
                    )
            else:
                assert signature is not None
                # Only equivalent copies need this bridge. A unique source is
                # already handled by the documentary resolver.
                anchored = (
                    tuple(
                        tuple((p.document.metadata["chunk_id"], p) for p in unit)
                        for unit in decisions
                    )
                    if len(matches) > 1
                    else ()
                )
                self._dockets[docket] = DocketEvidence(
                    docket, signature[0], signature[2], fragments, anchored
                )

    def docket_evidence(self, question: str) -> DocketEvidence | None:
        intent = _resolution_intent(question)
        if intent is None or _DOCKET.search(re.sub(r"\b\d{4}\b", "", intent[3])):
            return None
        identity = _docket(intent["docket"])
        if identity is None:
            return None
        docket, reference = identity
        evidence = self._dockets.get(docket)
        if (
            evidence is None
            or intent[1] != evidence.instance
            or (reference is not None and reference != evidence.reference)
        ):
            return None
        return evidence

    def resolve(self, question: str, *, max_sources: int = 4) -> Resolution | None:
        """Return quoted operative text only for an unambiguous verified match."""
        intent = _resolution_intent(question)
        if intent is None:
            return None
        instance, actor, subject = intent.group(1, 2, 3)
        identity = _docket(intent["docket"])
        if identity is None or _DOCKET.search(re.sub(r"\b\d{4}\b", "", subject)):
            return None
        docket, reference = identity
        case = self._cases.get(docket)
        if (
            case is None
            or instance != case.instance
            or (reference is not None and reference != case.reference)
        ):
            return None
        # Document instances are shared with the retriever. Verify the matched
        # source again before using its stored identity or any passage offsets.
        if any(
            not _verified(doc, ident, proof)
            for ident, (doc, proof) in case.verified_documents.items()
        ):
            return None
        # Independent clauses can require distinct orders. Shared nouns alone
        # cannot support an added action.
        subjects = _COMPOUND.split(subject)
        selected: dict[int, list[Passage]] = defaultdict(list)
        for part in subjects:
            dedicated = None
            if _SENTENCE_TOPIC.match(part):
                dedicated = _sentence_evidence(case, part) if actor is None else ()
            elif _NULLITY_TOPIC.fullmatch(part):
                dedicated = _nullity_evidence(case) if actor is None else ()
            elif case.instance == "sede de revision" and (
                right := _REVIEW_PROTECTION_TOPIC.fullmatch(part)
            ):
                dedicated = _review_grant_evidence(case, right["right"]) if actor is None else ()
            if dedicated is not None:
                if not dedicated:
                    return None
                selected[-1].extend(dedicated)
                continue
            supported = []
            for index, unit in enumerate(case.decisions):
                linked = any(_LIST_ITEM.match(_flat(p.text)) for p in selected.get(index, ()))
                evidence = _act_evidence(part, actor, unit, linked)
                if evidence:
                    supported.append((index, evidence))
            if len(supported) != 1:
                return None
            index, evidence = supported[0]
            selected[index].extend(evidence)
        by_document: dict[str, list[Passage]] = defaultdict(list)
        for index in sorted(selected):
            for passage in selected[index]:
                by_document[passage.document.metadata["chunk_id"]].append(passage)
        if len(by_document) > min(max_sources, 4):
            return None
        sources: list[Document] = []
        passages: list[Passage] = []
        excerpts: list[str] = []
        for ident in sorted(by_document, key=lambda ident: case.verified_documents[ident][1].line):
            merged: list[Passage] = []
            for span in sorted(by_document[ident], key=lambda p: (p.start, p.end)):
                if merged and not span.document.page_content[merged[-1].end : span.start].strip():
                    preceding = merged[-1]
                    merged[-1] = Passage(
                        span.document, preceding.start, max(preceding.end, span.end)
                    )
                else:
                    merged.append(span)
            document = merged[0].document
            excerpt = " […] ".join(p.text for p in merged)
            if merged[0].start and document.page_content[: merged[0].start].strip():
                excerpt = "[…] " + excerpt
            if document.page_content[merged[-1].end :].strip():
                excerpt += " […]"
            if len(excerpt) > 500 or not _verified(
                document, ident, case.verified_documents[ident][1]
            ):
                return None
            sources.append(document)
            passages.extend(merged)
            excerpts.append(excerpt)
        return Resolution(
            _cited_excerpts(excerpts), tuple(sources), tuple(passages), tuple(excerpts)
        )
