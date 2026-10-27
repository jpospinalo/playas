"""Extracción PDF/MD y OCR español local, cacheados por contenido."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
import unicodedata
from collections import Counter
from pathlib import Path

EXTRACTOR_VERSION = "pymupdf-tesseract-spa-1"
NORMALIZER_VERSION = "nfc-mapped-1"
MIN_PAGE_CHARS = 80


def atomic_text(path, content):
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def cpu_time():
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
        return time.process_time() + usage.ru_utime + usage.ru_stime
    except ImportError:
        return time.process_time()


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ocr(page, cache, key):
    target = cache / "ocr" / (key + ".txt")
    if target.exists():
        return target.read_text(encoding="utf-8"), False
    import fitz

    image = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).tobytes("png")
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "-l", "spa", "--psm", "3"],
        input=image,
        capture_output=True,
        timeout=120,
        env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    if result.returncode:
        raise RuntimeError("Tesseract falló; revisar instalación e idioma spa")
    text = result.stdout.decode("utf-8", "replace")
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(target, text)
    return text, True


def read_document(path: Path, cache: Path):
    started = cpu_time()
    digest = sha256_file(path)
    cache_key = hashlib.sha256(
        (digest + EXTRACTOR_VERSION + NORMALIZER_VERSION).encode()
    ).hexdigest()
    target = cache / "extraction" / (cache_key + ".json")
    if target.exists():
        doc = json.loads(target.read_text(encoding="utf-8"))
        return {
            **doc,
            "extraction_cache_hit": True,
            "new_ocr_pages": 0,
            "cpu_seconds": cpu_time() - started,
        }
    originals = cache / "originals"
    originals.mkdir(parents=True, exist_ok=True)
    original_path = originals / (digest + path.suffix.lower())
    if not original_path.exists():
        shutil.copy2(path, original_path)
    pages = []
    ocr_pages = []
    failures = []
    new_ocr = 0
    if path.suffix.lower() == ".pdf":
        import fitz

        with fitz.open(path) as pdf:
            for index, page in enumerate(pdf):
                text = page.get_text("text", sort=True)
                if len(re.sub(r"\s", "", text)) < MIN_PAGE_CHARS:
                    try:
                        text, created = _ocr(page, cache, digest + f"-{index}-{EXTRACTOR_VERSION}")
                        new_ocr += int(created)
                        ocr_pages.append(index + 1)
                    except (RuntimeError, subprocess.TimeoutExpired, FileNotFoundError):
                        failures.append(index + 1)
                pages.append(unicodedata.normalize("NFC", text))
    else:
        pages = [
            unicodedata.normalize("NFC", text)
            for text in path.read_text(encoding="utf-8-sig").split("\f")
        ]
    doc = {
        "doc_id": digest,
        "sha256": digest,
        "original": "\n\f\n".join(pages),
        "raw_pages": pages,
        "ocr_pages": ocr_pages,
        "ocr_failed_pages": failures,
        "original_file": str(original_path),
        "extractor_version": EXTRACTOR_VERSION,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(target, json.dumps(doc, ensure_ascii=False))
    return {
        **doc,
        "extraction_cache_hit": False,
        "new_ocr_pages": new_ocr,
        "cpu_seconds": cpu_time() - started,
    }


def _line_key(line):
    return re.sub(r"\d+", "#", " ".join(line.strip().casefold().split()))


def _remove(pairs, pattern):
    text = "".join(c for c, _ in pairs)
    remove = {
        i for match in re.finditer(pattern, text, re.M) for i in range(match.start(), match.end())
    }
    return [pair for i, pair in enumerate(pairs) if i not in remove]


def clean_pages(raw_pages):
    """Offsets de código Unicode en original NFC, antes de limpieza; fin exclusivo."""
    counts = Counter()
    for page in raw_pages:
        lines = page.splitlines()
        corners = lines[:2] + lines[-2:]
        counts.update({_line_key(line) for line in corners if line.strip() and len(line) < 120})
    repeated = {
        key
        for key, count in counts.items()
        if len(raw_pages) >= 2
        and count >= max(2, math.ceil(0.6 * len(raw_pages)))
        and not re.search(r"art[íi]culo|consideraciones|resuelve|antecedentes|decisi[oó]n", key)
    }
    all_pairs, page_map = [], []
    original_offset = 0
    for number, page in enumerate(raw_pages, 1):
        pairs = []
        lines = page.splitlines(keepends=True)
        offset = original_offset
        for index, line in enumerate(lines):
            is_corner = index < 2 or index >= len(lines) - 2
            if not (is_corner and _line_key(line) in repeated):
                pairs.extend(
                    (" " if c == "\t" else c, offset + i)
                    for i, c in enumerate(line)
                    if unicodedata.category(c) not in {"Cc", "Cf"} or c in "\n\t"
                )
            offset += len(line)
        pairs = _remove(pairs, r"(?<=\w)-[ \t]*\n[ \t]*(?=\w)")
        pairs = _remove(pairs, r"(?<= )[ ]+")
        pairs = _remove(pairs, r"[ ]+$")
        pairs = _remove(pairs, r"(?<=\n\n)\n+")
        while pairs and pairs[0][0].isspace():
            pairs.pop(0)
        while pairs and pairs[-1][0].isspace():
            pairs.pop()
        if all_pairs and pairs:
            all_pairs.extend([("\n", original_offset), ("\n", original_offset)])
        start = len(all_pairs)
        all_pairs.extend(pairs)
        page_map.append(
            {
                "page": number,
                "clean_start": start,
                "clean_end": len(all_pairs),
                "source_start": original_offset,
                "source_end": original_offset + len(page),
            }
        )
        original_offset += len(page) + 3
    runs = []
    for index, (_, source) in enumerate(all_pairs):
        if runs and source == runs[-1]["source_end"]:
            runs[-1]["clean_end"] += 1
            runs[-1]["source_end"] += 1
        else:
            runs.append(
                {
                    "clean_start": index,
                    "clean_end": index + 1,
                    "source_start": source,
                    "source_end": source + 1,
                }
            )
    return {
        "text": "".join(c for c, _ in all_pairs),
        "pages": page_map,
        "offset_map": runs,
        "removed_furniture_keys": sorted(repeated),
        "normalizer_version": NORMALIZER_VERSION,
    }


def source_span(offset_map, start, end):
    selected = [r for r in offset_map if r["clean_start"] < end and r["clean_end"] > start]
    if not selected:
        return None, None
    first, last = selected[0], selected[-1]
    return first["source_start"] + max(0, start - first["clean_start"]), last["source_start"] + min(
        end, last["clean_end"]
    ) - last["clean_start"]
