"""Promote explicit plan-attribution evidence already present in a candidate pool.

This module owns no clients, models, caches or retrieval. The caller binds a
verified snapshot and preserves the existing four-document fallback.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Sequence

from langchain_core.documents import Document


def _canon(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(
        "".join(
            char
            for char in unicodedata.normalize("NFD", value)
            if unicodedata.category(char) != "Mn"
        )
        .lower()
        .split()
    )


def _plan_name(text: str) -> str | None:
    if len(re.findall(r"\bplan\b", text)) != 1:
        return None
    found = re.search(r"\bplan [^?!.;\n]{8,220}", text)
    return found.group(0).strip() if found else None


def requested_act(question: object) -> str | None:
    """Recognize only the bounded attribution grammar, without inferring actors."""
    text = _canon(question)
    if not re.search(r"\bquien\b", text) or re.search(r"\b(?:no|nunca|excepto|salvo)\b", text):
        return None
    actions = []
    for pattern, action in (
        (r"\bformular(?:lo|la)?\b", "formulate"),
        (r"\badoptar(?:lo|la)?\b", "adopt"),
        (r"\bejecutar(?:lo|la)?\b", "execute"),
        (r"\bcoordina(?:r)?\s+(?:la\s+)?ejecucion\b", "coordinate_execution"),
    ):
        if re.search(pattern, text):
            actions.append(action)
    return actions[0] if len(actions) == 1 else None


def _explicit_attribution(text: str, alias: str, act: str) -> bool:
    if re.search(r"\b(?:no|nunca|excepto|salvo)\b", text):
        return False
    escaped = re.escape(alias)
    if act == "formulate":
        pattern = (
            r"\bla formulacion de(?:l| la)?\s+"
            + escaped
            + r"\s*,?\s*(?:esta|estara) a cargo de(?:l| la)?\s+\S"
        )
    elif act == "adopt":
        attribution = (
            r"\s*,?\s*(?:esta(?:ra)? en cabeza de(?:l| la)?|"
            r"corresponde(?:ra)? a(?:l| la)?)\s+\S"
        )
        direct = r"\bla adopcion de(?:l| la)?\s+" + escaped + attribution
        linked = (
            r"\bla formulacion de(?:l| la)?\s+"
            + escaped
            + r"(?P<link>[^.!?;]{1,400}?)\s+y su adopcion"
            + attribution
        )
        direct_count = len(re.findall(direct, text))
        linked_count = sum(
            not re.search(r"\b(?:plan|adopcion|formulacion)\b", match["link"])
            for match in re.finditer(linked, text)
        )
        return direct_count + linked_count == 1
    elif act == "execute":
        pattern = (
            r"\bla ejecucion de(?:l| la)?\s+"
            + escaped
            + r"\s*,?\s*(?:esta(?:ra)? a cargo de(?:l| la)?|"
            r"corresponde(?:ra)? a(?:l| la)?)\s+\S"
        )
    else:
        pattern = (
            r"\bcorresponde a [^.!?;]{2,160}?\s+coordinar la ejecucion de(?:l| la)?\s+"
            + escaped
            + r"\b"
        )
    return len(re.findall(pattern, text)) == 1


def _identifier(document: Document) -> str | None:
    ident = document.metadata.get("chunk_id")
    if not isinstance(ident, str) or not ident.strip():
        return None
    if document.id not in (None, ident):
        return None
    if "id" in document.metadata and document.metadata["id"] != ident:
        return None
    return ident


def _canonical_metadata(document: Document, ident: str) -> str | None:
    if _identifier(document) != ident:
        return None
    metadata = dict(document.metadata)
    if metadata.get("id") == ident:
        del metadata["id"]  # Only the matching loader-added identifier is normalized.
    try:
        return json.dumps(
            metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError):
        return None


def _matches_snapshot(decisive: Sequence[Document], verified_documents: Sequence[Document]) -> bool:
    wanted = {doc.metadata["chunk_id"] for doc in decisive}
    references: dict[str, list[Document]] = {ident: [] for ident in wanted}
    for reference in verified_documents:
        if isinstance(reference, Document):
            ident = reference.metadata.get("chunk_id")
            if isinstance(ident, str) and ident in references:
                references[ident].append(reference)
    for document in decisive:
        ident = document.metadata["chunk_id"]
        matches = references[ident]
        if len(matches) != 1:
            return False
        reference = matches[0]
        canonical = _canonical_metadata(document, ident)
        if (
            canonical is None
            or document.page_content != reference.page_content
            or canonical != _canonical_metadata(reference, ident)
        ):
            return False
    return True


def select_plan_attribution_context(
    *,
    question: str,
    history: list[dict[str, str]],
    standalone_question: str,
    original_doc_types: list[str] | None,
    current_selected: list[Document],
    candidate_pool: Sequence[Document],
    verified_documents: Sequence[Document],
    k: int = 4,
) -> list[Document]:
    """Return original objects, or the exact fallback list when proof is insufficient.

    The verified snapshot only authenticates decisive candidates. It never
    supplies a document absent from the already retrieved candidate pool.
    """
    if (
        type(k) is not int
        or k != 4
        or not isinstance(current_selected, list)
        or not 1 <= len(current_selected) <= k
        or not isinstance(candidate_pool, (list, tuple))
        or not isinstance(verified_documents, (list, tuple))
    ):
        return current_selected
    if original_doc_types is not None and (
        not isinstance(original_doc_types, list)
        or "normativa" not in original_doc_types
        or any(value not in ("normativa", "jurisprudencia") for value in original_doc_types)
    ):
        return current_selected
    act = requested_act(question)
    if act is None or requested_act(standalone_question) != act:
        return current_selected
    name = _plan_name(_canon(standalone_question))
    if not name:
        return current_selected
    original_name = _plan_name(_canon(question))
    if original_name and original_name != name:
        return current_selected
    if not isinstance(history, list) or any(
        not isinstance(message, dict)
        or message.get("role") not in ("user", "assistant")
        or not isinstance(message.get("content"), str)
        for message in history
    ):
        return current_selected
    history_names = [
        _plan_name(_canon(message["content"])) for message in history if message["role"] == "user"
    ]
    if original_name is None and (
        not history_names or any(previous != name for previous in history_names)
    ):
        return current_selected
    if original_name is not None and any(
        previous is not None and previous != name for previous in history_names
    ):
        return current_selected
    if any(not isinstance(document, Document) for document in candidate_pool):
        return current_selected
    identifiers = [_identifier(document) for document in candidate_pool]
    if any(ident is None for ident in identifiers) or len(set(identifiers)) != len(identifiers):
        return current_selected
    if any(
        not any(document is selected for document in candidate_pool)
        for selected in current_selected
    ):
        return current_selected
    eligible = [
        document
        for document in candidate_pool
        if document.metadata.get("doc_type") == "normativa"
        and _canon(document.metadata.get("source"))
        and _canon(document.metadata.get("norma"))
        and document.page_content.strip()
    ]
    declarations = []
    name_pattern = re.escape(name) + r"\s*[-—]\s*([a-z][a-z0-9 ]{2,60}?)\s*[-—]"
    for document in eligible:
        for alias in re.findall(name_pattern, _canon(document.page_content)):
            declarations.append(
                (document, document.metadata["source"], document.metadata["norma"], alias)
            )
    identities = {(source, norma, alias) for _, source, norma, alias in declarations}
    if len(identities) != 1:
        return current_selected
    source, norma, alias = next(iter(identities))
    alias_definition = r"\b(?P<name>plan [^.!?;]{8,220}?)\s*[-—]\s*" + re.escape(alias) + r"\s*[-—]"
    for document in eligible:
        if any(
            match["name"].strip() != name
            for match in re.finditer(alias_definition, _canon(document.page_content))
        ):
            return current_selected
    alias_pattern = r"\b" + re.escape(alias) + r"\b"
    if any(
        re.search(alias_pattern, _canon(document.page_content))
        and (document.metadata["source"], document.metadata["norma"]) != (source, norma)
        for document in eligible
    ):
        return current_selected
    proofs = [
        document
        for document in eligible
        if (document.metadata["source"], document.metadata["norma"]) == (source, norma)
        and re.search(alias_pattern, _canon(document.page_content))
        and _explicit_attribution(_canon(document.page_content), alias, act)
    ]
    if len(proofs) != 1:
        return current_selected
    proof = proofs[0]
    if any(proof is document for document in current_selected):
        return current_selected
    decisive = [document for document, _, _, _ in declarations] + [proof]
    if not _matches_snapshot(decisive, verified_documents):
        return current_selected
    return [proof, *[document for document in current_selected if document is not proof]][:k]
