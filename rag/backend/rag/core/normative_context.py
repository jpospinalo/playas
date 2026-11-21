"""Select small body-backed normative context from a verified snapshot.

No clients or caches: callers own snapshot verification and preserve the fallback.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Sequence

from langchain_core.documents import Document

_ACT = re.compile(r"\b(?:ley|decreto(?:[ -]+ley)?|resolucion)\s+\d+\s+de\s+\d{4}\b")
_ARTICLE = re.compile(r"\barticulo\s+(\d+(?:\.\d+)*)(?![\w.\-])")
_UNSUPPORTED = re.compile(
    r"\b(?:articulos|bis|ter|quater|literal(?:es)?|numeral(?:es)?|paragrafo(?:s)?|inciso(?:s)?)\b"
)
_HEADINGS = (r"^[IVXLCDM]+\.\s+\S", r"^\d+\.\s+\S", r"^[a-z]\)\s+\S")


def _canon(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(
        "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
        .lower()
        .split()
    )


def select_verified_article_context(
    question: str,
    original_doc_types: list[str] | None,
    documents: Sequence[Document],
    k: int = 4,
) -> list[Document] | None:
    """Return original objects, or None to keep the existing retriever unchanged."""
    if not isinstance(question, str) or type(k) is not int or not 1 <= k <= 4:
        return None
    if original_doc_types is not None:
        if not isinstance(original_doc_types, list):
            return None
        if "normativa" not in original_doc_types or any(
            t not in ("normativa", "jurisprudencia") for t in original_doc_types
        ):
            return None
    text = _canon(question)
    if not re.search(r"clasific|categoria|pertenec", text) or _UNSUPPORTED.search(text):
        return None
    acts, articles = list(_ACT.finditer(text)), list(_ARTICLE.finditer(text))
    if len(acts) != 1 or len(articles) != 1:
        return None
    if any(
        re.match(r"\s*(?:y|e|o|,|a|-|al)\s*(?:de\s+)?\d", text[m.end() :])
        for m in (acts[0], articles[0])
    ):
        return None
    act, article = acts[0].group(0), articles[0].group(1)
    rows = [
        d
        for d in documents
        if isinstance(d, Document)
        and isinstance(d.metadata, dict)
        and d.metadata.get("doc_type") == "normativa"
        and _canon(d.metadata.get("norma")) == act
        and d.metadata.get("articulo") == article
    ]
    if any(not isinstance(d.page_content, str) or not d.page_content.strip() for d in rows):
        return None
    if any(not isinstance(d.metadata.get("source"), str) for d in rows):
        return None
    signatures = {(d.metadata.get("source"), d.metadata.get("norma")) for d in rows}
    if len(signatures) != 1:
        return None
    source, _ = next(iter(signatures))
    if not isinstance(source, str) or not source.strip():
        return None
    n = len(rows)
    if any(
        type(d.metadata.get("chunk_index")) is not int
        or type(d.metadata.get("total_chunks_in_section")) is not int
        or d.metadata.get("total_chunks_in_section") != n
        for d in rows
    ):
        return None
    if {d.metadata["chunk_index"] for d in rows} != set(range(n)):
        return None
    identifiers = [d.metadata.get("id") or d.id or d.metadata.get("chunk_id") for d in rows]
    if (
        any(not isinstance(i, str) or not i.strip() for i in identifiers)
        or len(set(identifiers)) != n
    ):
        return None
    if any(
        type(d.metadata.get("section_index")) is not int or d.metadata["section_index"] < 0
        for d in rows
    ):
        return None
    if len({d.metadata["section_index"] for d in rows}) != 1:
        return None
    rows.sort(key=lambda d: d.metadata["chunk_index"])
    if n == 1:
        return rows
    query = _ARTICLE.sub("", _ACT.sub("", text))
    terms = {
        t
        for t in re.findall(r"[a-z]+", query)
        if len(t) >= 4
        and t not in {"segun", "como", "dentro", "entre", "para", "cuales"}
        and not t.startswith(("clasific", "categor", "pertenec"))
    }
    tokens = [set(re.findall(r"[a-z]+", _canon(d.page_content))) for d in rows]
    frequency = Counter(t for values in tokens for t in values)
    if any(frequency[t] == 0 for t in terms):
        return None
    terms = {t for t in terms if frequency[t] <= max(1, n // 2)}
    if not terms:
        return None
    stack: dict[int, tuple[int, str]]
    evidence: dict[int, dict[str, list[tuple[int, str]]]]
    parents: dict[tuple[int, str], tuple[str, ...]]
    stack, evidence, parents = {}, {}, {}
    for i, doc in enumerate(rows):
        for line in doc.page_content.splitlines():
            line = line.strip()
            level = next(
                (j for j, pattern in enumerate(_HEADINGS) if re.match(pattern, line)), None
            )
            if level is not None:
                parent = tuple(_canon(stack[j][1]) for j in sorted(stack) if j < level)
                if parents.setdefault((level, _canon(line)), parent) != parent:
                    return None
                current = stack.get(level)
                if (
                    level == 1
                    and current
                    and int(line.split(".")[0]) < int(current[1].split(".")[0])
                ):
                    return None
                if current is None or _canon(current[1]) != _canon(line):
                    stack = {j: value for j, value in stack.items() if j < level}
                    stack[level] = (i, line)
            hits = terms & set(re.findall(r"[a-z]+", _canon(line)))
            if hits:
                if 0 not in stack:
                    return None
                for term in hits:
                    evidence.setdefault(i, {}).setdefault(term, list(stack.values()))
    selected: set[int]
    covered: set[str]
    selected, covered = set(), set()
    while covered != terms:
        options = []
        for seed, term_evidence in evidence.items():
            new = set(term_evidence) - covered
            package = selected | {seed} | {i for term in new for i, _ in term_evidence[term]}
            if new and len(package) <= k:
                score = sum(1 / frequency[t] for t in new) / max(1, len(package - selected))
                options.append((score, -seed, new, package))
        if not options:
            return None
        _, _, new, selected = max(options, key=lambda x: x[:2])
        covered |= new
    return [rows[i] for i in sorted(selected)]


_PLAN_ADOPTION_QUESTION = re.compile(
    r"¿?(?:que (?:autoridad|organo) debe|a que (?:autoridad|organo) corresponde) "
    r"adoptar (?:ese|dicho|el) (?P<plan>plan [^?\n]{20,240})\?"
)

_PLAN_ADOPTION_ATTRIBUTION = re.compile(
    r"\b(?:su|la) adopcion(?: de(?:l| la)? [^.!?;]{1,120}?)? "
    r"(?:estara en cabeza de(?:l| la)?|"
    r"corresponde(?:ra)? a(?:l| la)?) \S"
)


def select_verified_plan_adoption_context(
    question: str, original_doc_types: list[str] | None, documents: Sequence[Document], k: int = 4
) -> list[Document] | None:
    """Select original identity/adoption bodies under a narrow literal grammar.

    Callers own snapshot verification; missing or ambiguous proof keeps fallback.
    """
    if type(k) is not int or k < 2 or k > 4:
        return None
    if original_doc_types is not None and (
        not isinstance(original_doc_types, list)
        or "normativa" not in original_doc_types
        or any(
            not isinstance(t, str) or t not in {"normativa", "jurisprudencia"}
            for t in original_doc_types
        )
    ):
        return None
    query = _canon(question)
    match = _PLAN_ADOPTION_QUESTION.fullmatch(query)
    if match is None or len(re.findall(r"\bplan\b", query)) != 1:
        return None
    name = match["plan"]
    identity: list[tuple[Document, str]] = []
    for doc in documents:
        if not isinstance(doc, Document) or not isinstance(doc.metadata, dict):
            return None
        meta = doc.metadata
        if meta.get("doc_type") != "normativa" or not _canon(meta.get("norma")):
            continue
        if not isinstance(meta.get("source"), str) or not meta["source"].strip():
            continue
        aliases = re.findall(
            re.escape(name) + r"\s*[-—]\s*([a-z][a-z0-9 ]{2,60}?)\s*[-—]", _canon(doc.page_content)
        )
        if len(aliases) > 1:
            return None
        if aliases:
            identity.append((doc, aliases[0]))
    if len(identity) != 1:
        return None
    original, alias = identity[0]
    candidates: list[Document] = []
    alias_occurrences: int = 0
    alias_pattern = re.compile(r"[-—]\s*" + re.escape(alias) + r"\s*[-—]")
    for doc in documents:
        meta = doc.metadata
        if (meta.get("source"), meta.get("norma"), meta.get("doc_type")) != (
            original.metadata["source"],
            original.metadata["norma"],
            "normativa",
        ):
            continue
        alias_occurrences += len(alias_pattern.findall(_canon(doc.page_content)))
        title = _canon(meta.get("articulo_titulo"))
        if not re.fullmatch(r"(?:formulacion y )?adopcion de(?:l| la)? " + re.escape(alias), title):
            continue
        body = _canon(doc.page_content)
        if (
            title not in body
            or len(_PLAN_ADOPTION_ATTRIBUTION.findall(body)) != 1
            or len(re.findall(r"\b(?:su|la) adopcion\b", body)) != 1
        ):
            continue
        linked = re.search(
            r"\bla formulacion de(?:l| la)? "
            + re.escape(alias)
            + r",? estara a cargo de(?P<actor>[^.!?;]{1,600}?) y su adopcion "
            + r"estara en cabeza de(?:l| la)? \S",
            body,
        )
        direct = re.search(
            r"\bla adopcion de(?:l| la)? "
            + re.escape(alias)
            + r" (?:estara en cabeza de(?:l| la)?|corresponde(?:ra)? a(?:l| la)?) \S",
            body,
        )
        if not direct and (not linked or re.search(r"\bplan\b", linked["actor"])):
            continue
        if (
            type(meta.get("chunk_index")) is not int
            or meta["chunk_index"] != 0
            or type(meta.get("total_chunks_in_section")) is not int
            or meta["total_chunks_in_section"] != 1
            or type(meta.get("section_index")) is not int
            or meta["section_index"] < 1
            or not isinstance(meta.get("articulo"), str)
            or not re.fullmatch(r"\d+(?:\.\d+)*", meta["articulo"])
        ):
            return None
        candidates.append(doc)
    if alias_occurrences != 1 or len(candidates) != 1 or candidates[0] is original:
        return None
    return [original, candidates[0]]
