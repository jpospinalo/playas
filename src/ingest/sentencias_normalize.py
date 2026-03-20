from __future__ import annotations

import re
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from .sentencias_schema import Section


# ---------------------------------------------------------------------------
# Canonical section titles defined by the contract
# ---------------------------------------------------------------------------

_CANONICAL_TITLES: List[str] = [
    "Caratula",
    "Vistos",
    "Resultandos",
    "Considerandos",
    "Fundamentos de derecho",
    "Resuelve",
    "Fallo",
    "Parte dispositiva",
    "Costas",
    "Honorarios",
    "Disidencia",
    "Aclaratoria",
    "Anexo",
]

# Simple keywords to aid matching when the heading doesn't match verbatim
_CANONICAL_KEYWORDS: dict[str, List[str]] = {
    "Caratula": ["caratula", "carátula", "autos", "expte"],
    "Vistos": ["vistos", "visto"],
    "Resultandos": ["resultando", "resultandos"],
    "Considerandos": ["considerando", "considerandos"],
    "Fundamentos de derecho": ["fundamentos de derecho", "fundamento de derecho"],
    "Resuelve": ["resuelve", "resolviendo"],
    "Fallo": ["fallo", "por ello se falla", "se falla"],
    "Parte dispositiva": ["parte dispositiva", "dispositiva"],
    "Costas": ["costas"],
    "Honorarios": ["honorarios"],
    "Disidencia": ["disidencia", "voto en disidencia"],
    "Aclaratoria": ["aclaratoria"],
    "Anexo": ["anexo"],
}


def _canonical_title(raw: str) -> str:
    """Map an arbitrary heading to the nearest canonical contract title.

    Matching is case-insensitive substring. Falls back to "Otro".
    """
    normalized = raw.strip().casefold()
    for canonical, keywords in _CANONICAL_KEYWORDS.items():
        for kw in keywords:
            if kw in normalized:
                return canonical
    return "Otro"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def sections_from_doc_chunks(docs: List[Document]) -> List[Section]:
    """Build sections from DOC_CHUNKS Docling output.

    Each Document in DOC_CHUNKS may carry a 'headings' list in its metadata.
    Consecutive chunks that share the same top-level heading are merged into
    one section.
    """
    if not docs:
        return []

    sections: List[Section] = []
    current_title: str | None = None
    current_parts: List[str] = []

    def _flush() -> None:
        if current_title is not None and current_parts:
            text = " ".join(current_parts).strip()
            if text:
                sections.append(Section(title=current_title, text=text))

    for doc in docs:
        headings: List[str] = doc.metadata.get("headings", [])
        raw_heading = headings[0].strip() if headings else ""
        title = _canonical_title(raw_heading) if raw_heading else "Otro"

        if title != current_title:
            _flush()
            current_title = title
            current_parts = []

        content = doc.page_content.strip()
        if content:
            current_parts.append(content)

    _flush()
    return sections


def sections_from_markdown(doc: Document) -> List[Section]:
    """Build sections by splitting a single Markdown document on headings.

    Handles ATX headings (# / ## / ###). Text before the first heading
    is grouped as "Otro".
    """
    text = doc.page_content

    # Split on ATX headings (levels 1–3), keeping the heading delimiter
    pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    parts = pattern.split(text)

    # parts layout after split with 2 capturing groups:
    #   [pre_heading_text, level, heading, body, level, heading, body, ...]
    sections: List[Section] = []

    # Text before the first heading
    preamble = parts[0].strip()
    if preamble:
        sections.append(Section(title="Otro", text=preamble))

    # Iterate over (level, heading, body) triplets
    i = 1
    while i + 2 <= len(parts):
        _level = parts[i]       # e.g. "##"
        heading = parts[i + 1].strip()
        body = parts[i + 2].strip()
        title = _canonical_title(heading)
        if body:
            sections.append(Section(title=title, text=body))
        elif not body and heading:
            # Heading with no body – keep it with heading text as content
            sections.append(Section(title=title, text=heading))
        i += 3

    return sections


# ---------------------------------------------------------------------------
# Header field extraction
# ---------------------------------------------------------------------------

# Spanish month name → ISO month number
_MONTHS_ES: dict[str, str] = {
    "enero": "01", "febrero": "02", "marzo": "03", "abril": "04",
    "mayo": "05", "junio": "06", "julio": "07", "agosto": "08",
    "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12",
}

_DATE_LONG_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+("
    + "|".join(_MONTHS_ES) +
    r")\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)
_DATE_NUMERIC_RE = re.compile(r"\b(\d{2})[/\-](\d{2})[/\-](\d{4})\b")

_CASE_PATTERNS: List[re.Pattern[str]] = [
    # Matches "Exp. No. 1234/2021", "Expediente 1234-2021", etc. — must start with a digit
    re.compile(r"(?:Exp(?:ediente)?\.?\s*(?:No\.?)?\s*)(\d[\w/\-]*)", re.IGNORECASE),
    # Matches "No. 1234/2021"
    re.compile(r"(?:\bNo\.\s*)(\d[\w/\-]*)", re.IGNORECASE),
    # Matches "Causa No. 1234"
    re.compile(r"(?:Causa\s+No\.?\s*)(\d[\w/\-]*)", re.IGNORECASE),
]


def _extract_case_number(text: str) -> str:
    for pattern in _CASE_PATTERNS:
        m = pattern.search(text[:3000])  # look in first 3 000 chars
        if m:
            candidate = m.group(1).strip()
            if candidate:
                return candidate
    return "DESCONOCIDO"


def _extract_judgement_date(text: str) -> str:
    # Try long Spanish date first
    m = _DATE_LONG_RE.search(text)
    if m:
        day = m.group(1).zfill(2)
        month = _MONTHS_ES[m.group(2).lower()]
        year = m.group(3)
        return f"{year}-{month}-{day}"

    # Fallback: numeric date DD/MM/YYYY or DD-MM-YYYY
    m = _DATE_NUMERIC_RE.search(text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        return f"{year}-{month}-{day}"

    return "1900-01-01"


def extract_header_fields(source_path: Path, text: str) -> dict:
    """Extract document-level metadata from raw text and source path."""
    return {
        "source_file": source_path.name,
        "case_number": _extract_case_number(text),
        "judgement_date": _extract_judgement_date(text),
    }
