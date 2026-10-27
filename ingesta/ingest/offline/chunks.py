"""Chunks con cabeceras por plantilla, páginas y offsets estables."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .extract import source_span

CHUNKER_VERSION = "legal-spans-1"
HEADING = re.compile(
    r"(?mi)^[ \t]*(?:#{1,6}[ \t]+)?(?:[IVXLCDM\d]+[.):\-]?[ \t]+)?(?P<label>(?:ANTECEDENTES|CONSIDERACIONES(?:[ \t]+DE[ \t]+LA[ \t]+SALA)?|FUNDAMENTOS|RESUELVE|FALLA|DECISI[ÓO]N|ART[ÍI]CULO[ \t]+[\d\w.\-]+)[^\n]{0,160})$"
)


def token_estimate(text):
    """Aproximación documentada: ceil(bytes UTF-8 / 3), no tokenizer BPE."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def header(fields, section):
    def value(name):
        result = fields[name]["valor"]
        return str(result) if result is not None else "sin identificar"

    return f"{value('tipo_documento')} {value('numero')}/{value('anio')} — {value('corporacion')} — M.P. {value('magistrado_ponente')} — {section[:90]}"


def make_chunks(doc_id, cleaned, metadata, source, doc_type, mode="legacy", token_budget=512):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    text = cleaned["text"]
    if mode not in {"legacy", "structure"} or token_budget < 128:
        raise ValueError("Chunker inválido o presupuesto menor de128tokens")
    matches = list(HEADING.finditer(text)) if mode == "structure" else []
    boundaries = sorted({0, len(text)} | {m.start() for m in matches})
    result = []
    active = "Texto íntegro" if mode == "legacy" else "Preámbulo"
    labels = {m.start(): m.group("label").strip() for m in matches}
    for start, end in zip(boundaries, boundaries[1:], strict=False):
        active = labels.get(start, active)
        prefix = header(metadata["campos"], active)
        if mode == "legacy":
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=1000,
                chunk_overlap=200,
                separators=["\n\n", "\n", ".", " ", ""],
                add_start_index=True,
            )
        else:
            available = token_budget - token_estimate(prefix + "\n\n") - 2
            if available < 32:
                raise ValueError("Cabecera excede el presupuesto de tokens")
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=available,
                chunk_overlap=min(64, available // 5),
                length_function=token_estimate,
                separators=["\n\n", "\n", ". ", " ", ""],
                add_start_index=False,
            )
        cursor = 0
        previous_start = -1
        segment = text[start:end]
        for part in splitter.split_text(segment):
            # Solapamiento puede retroceder; find desde última posición menos el
            # máximo tamaño del chunk mantiene offsets reales y verificables.
            overlap_bound = 200 if mode == "legacy" else 192
            local = segment.find(part, max(previous_start + 1, cursor - overlap_bound, 0))
            if local < 0:
                raise ValueError("No se pudo mapear chunk al texto normalizado")
            absolute = start + local
            previous_start = local
            cursor = local + len(part)
            source_start, source_end = source_span(
                cleaned["offset_map"], absolute, absolute + len(part)
            )
            pages = [
                p["page"]
                for p in cleaned["pages"]
                if p["clean_start"] < absolute + len(part) and p["clean_end"] > absolute
            ]
            document = prefix + "\n\n" + part
            if mode == "structure" and token_estimate(document) > token_budget:
                raise ValueError("Chunk excede presupuesto estimado de tokens")
            identity = (
                doc_id
                + "\0"
                + CHUNKER_VERSION
                + mode
                + str(token_budget)
                + f"\0{absolute}:{len(part)}\0"
                + document
            )
            chunk_id = hashlib.sha256(identity.encode()).hexdigest()
            meta = {
                "doc_id": doc_id,
                "chunk_id": chunk_id,
                "source": Path(source).name,
                "source_path": source,
                "title": Path(source).stem.replace("_", " "),
                "doc_type": doc_type,
                "section_name": active,
                "clean_start": absolute,
                "clean_end": absolute + len(part),
                "source_start": source_start if source_start is not None else -1,
                "source_end": source_end if source_end is not None else -1,
                "pages": json.dumps(pages),
                "legal_metadata": json.dumps(metadata, ensure_ascii=False),
                "header": prefix,
            }
            for name, field in metadata["campos"].items():
                if field["valor"] is not None:
                    meta[name] = (
                        json.dumps(field["valor"], ensure_ascii=False)
                        if isinstance(field["valor"], list)
                        else field["valor"]
                    )
            result.append(
                {"id": chunk_id, "document": document, "raw_text": part, "metadata": meta}
            )
    return result
