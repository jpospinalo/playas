"""Mediciones objetivas reproducibles; no consulta modelos ni valoraciones v1."""

from __future__ import annotations

import csv
import io
import json
import math
import re
import sqlite3
import statistics
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from ..legal_metadata import FIELDS
from ..offline_embeddings import DIMENSION, validate_vector
from .chunks import token_estimate
from .extract import _line_key
from .layers import ARTICLE_RE, SECTION_RE, canonical, key
from .storage import atomic_bytes, guard_output

# dirección, límite verde, límite amarillo; fuera de ambos: rojo.
THRESHOLDS = {
    "pages": ("min", 1, 1),
    "extracted_chars": ("min", 200, 80),
    "chars_per_page": ("min", 80, 40),
    "near_empty_pct": ("max", 5, 20),
    "ocr_pct": ("max", 25, 75),
    "ocr_confidence": ("min", 85, 60),
    "extraction_errors": ("max", 0, 0),
    "invalid_pct": ("max", 0.2, 1),
    "mojibake_pct": ("max", 0.2, 1),
    "alphabetic_pct": ("min", 50, 30),
    "eol_hyphenations": ("max", 0, 3),
    "repeated_corner_lines": ("max", 0, 2),
    "removed_chars": ("max", 10000, 100000),
    "removed_pct": ("max", 10, 30),
    "sections_detected": ("min", 1, 1),
    "sections_expected": ("min", 1, 1),
    "structure_coverage_pct": ("min", 100, 50),
    "metadata_present": ("min", len(FIELDS), 6),
    "metadata_absent": ("max", 0, 6),
    "metadata_conflicts": ("max", 0, 0),
    "metadata_without_evidence": ("max", 0, 0),
    "review_queue_entries": ("max", 0, 6),
    "chunk_count": ("min", 1, 1),
    "chunk_median": ("min", 200, 100),
    "chunk_p5": ("min", 200, 100),
    "chunk_p95": ("max", 4000, 8000),
    "short_chunks_pct": ("max", 5, 20),
    "over_budget_pct": ("max", 0, 5),
    "exact_duplicates": ("max", 0, 2),
    "near_duplicates": ("max", 0, 2),
    "embedding_dimension": ("equal", DIMENSION, DIMENSION),
    "invalid_vectors": ("max", 0, 0),
    "chunks_without_vector": ("max", 0, 0),
    "missing_layers": ("max", 0, 0),
}
NEUTRAL_METRICS = {"chunk_count", "chunk_median", "chunk_p5", "chunk_p95"}
REGRESSION_FLOORS = {
    "invalid_pct": 0.1,
    "mojibake_pct": 0.1,
    "short_chunks_pct": 0.1,
    "exact_duplicates": 2,
    "near_duplicates": 2,
}
COMPARISON_METRICS = (
    "extracted_chars",
    "invalid_pct",
    "mojibake_pct",
    "chunk_count",
    "chunk_median",
    "chunk_p5",
    "chunk_p95",
    "short_chunks_pct",
    "exact_duplicates",
    "near_duplicates",
)
REGRESSION_LIMIT = 0.2


def metric(name, value):
    direction, green, yellow = THRESHOLDS[name]
    if value is None:
        flag = "no medido"
    elif direction == "min":
        flag = "verde" if value >= green else "amarillo" if value >= yellow else "rojo"
    elif direction == "equal":
        flag = "verde" if value == green else "rojo"
    else:
        flag = "verde" if value <= green else "amarillo" if value <= yellow else "rojo"
    return {
        "valor": round(value, 6) if isinstance(value, float) else value,
        "bandera": flag,
        "umbral": {"direccion": direction, "verde": green, "amarillo": yellow},
    }


def percent(count, total):
    return 100 * count / max(1, total)


def invalid_pct(text):
    # Solo U+FFFD y controles C0/C1; el mojibake se mide por separado.
    return percent(
        sum(c == "\ufffd" or (unicodedata.category(c) == "Cc" and c not in "\n\t\f") for c in text),
        len(text),
    )


def mojibake_pct(text):
    # Heurística de codificación y glifos PDF; cuenta posiciones únicas sospechosas.
    positions = {
        i
        for i, c in enumerate(text)
        if c in "ÆæØøœŒłˇ"
        and any(
            0 <= neighbor < len(text)
            and text[neighbor].isalpha()
            and "LATIN" in unicodedata.name(text[neighbor], "")
            for neighbor in (i - 1, i + 1)
        )
    }
    for match in re.finditer(r"Ã[\x80-\xBFa-zA-Z©±³º¡]|â€[\s\S]?|Â[^\w]|ï¿½", text):
        positions.update(range(match.start(), match.end()))
    return percent(len(positions), len(text))


def extraction_metrics(document):
    pages = document.get("raw_pages", [])
    counts = [len(re.sub(r"\s", "", p)) for p in pages]
    confidence = [
        c
        for c in document.get("ocr_confidence", {}).values()
        if isinstance(c, (int, float)) and math.isfinite(c)
    ]
    values = {
        "pages": len(pages),
        "extracted_chars": len(document.get("original", "")),
        "chars_per_page": statistics.mean(counts) if counts else None,
        "near_empty_pct": percent(sum(c < 80 for c in counts), len(counts)) if counts else None,
        "ocr_pct": percent(len(document.get("ocr_pages", [])), len(pages)) if pages else None,
        "ocr_confidence": statistics.mean(confidence) if confidence else None,
        "extraction_errors": len(document.get("errors", document.get("ocr_failed_pages", []))),
    }
    return {name: metric(name, value) for name, value in values.items()}


def percentile(values, fraction):
    if not values:
        return None
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = int(index)
    return values[lower] + (values[min(lower + 1, len(values) - 1)] - values[lower]) * (
        index - lower
    )


def duplicate_counts(texts):
    from .pipeline import simhash

    counts = Counter(texts)
    exact = sum(count - 1 for count in counts.values())
    buckets = defaultdict(list)
    pairs = set()
    fingerprints = [simhash(t) for t in texts]
    for index, fingerprint in enumerate(fingerprints):
        for band in range(4):
            bucket = (band, (fingerprint >> (16 * band)) & 65535)
            for other in buckets[bucket]:
                if (
                    texts[index] != texts[other]
                    and (fingerprint ^ fingerprints[other]).bit_count() <= 3
                ):
                    pairs.add((other, index))
            buckets[bucket].append(index)
    return exact, len(pairs)


def text_metrics(original, cleaned, chunks, budget=512, page_texts=None, measure=None):
    sizes = [len(c) for c in chunks]
    exact, near = (
        measure("duplicates", lambda: duplicate_counts(chunks))
        if measure
        else duplicate_counts(chunks)
    )
    corners = Counter()
    for page in page_texts or [cleaned]:
        lines = page.splitlines()
        corners.update(
            {
                _line_key(line)
                for line in lines[:2] + lines[-2:]
                if 3 <= len(line.strip()) < 120
                and not SECTION_RE.search(line)
                and not ARTICLE_RE.search(line)
            }
        )
    repeated = sum(
        count >= max(2, math.ceil(0.6 * len(page_texts or [cleaned]))) for count in corners.values()
    )
    removed = max(0, len(original) - len(cleaned))
    values = {
        "invalid_pct": invalid_pct(cleaned),
        "mojibake_pct": mojibake_pct(cleaned),
        "alphabetic_pct": percent(sum(c.isalpha() for c in cleaned), len(cleaned)),
        "eol_hyphenations": len(re.findall(r"\w-[ \t]*\n[ \t]*\w", cleaned)),
        "repeated_corner_lines": repeated,
        "removed_chars": removed,
        "removed_pct": percent(removed, len(original)),
        "chunk_count": len(chunks),
        "chunk_median": statistics.median(sizes) if sizes else None,
        "chunk_p5": percentile(sizes, 0.05),
        "chunk_p95": percentile(sizes, 0.95),
        "short_chunks_pct": percent(sum(s < 200 for s in sizes), len(sizes)) if sizes else None,
        "over_budget_pct": percent(sum(token_estimate(c) > budget for c in chunks), len(chunks))
        if chunks
        else None,
        "exact_duplicates": exact,
        "near_duplicates": near,
    }
    return {name: metric(name, value) for name, value in values.items()}


def load_json(path, missing):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Se esperaba objeto JSON")
        return value
    except (OSError, ValueError):
        missing.append(path.name)
        return {}


def load_jsonl(path, missing):
    try:
        records = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if any(
            not isinstance(row, dict) or not isinstance(row.get("page_content"), str)
            for row in records
        ):
            raise ValueError("Se esperaban registros page_content/metadata")
        return records
    except (OSError, ValueError):
        missing.append(path.name)
        return []


def load_text(path, missing):
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeError):
        missing.append(path.name)
        return ""


def _vector_metrics(records, cache):
    values = {"embedding_dimension": None, "invalid_vectors": None, "chunks_without_vector": None}
    if cache is None or not Path(cache).is_file():
        return {k: metric(k, v) for k, v in values.items()}
    try:
        with closing(sqlite3.connect(Path(cache).resolve().as_uri() + "?mode=ro", uri=True)) as db:
            dimensions, invalid, absent = [], 0, 0
            for record in records:
                cache_key = record.get("metadata", {}).get("embedding_cache_key")
                row = db.execute("SELECT vector FROM vectors WHERE key=?", (cache_key,)).fetchone()
                if not row:
                    absent += 1
                    continue
                try:
                    vector = json.loads(row[0])
                    dimensions.append(len(vector) if isinstance(vector, list) else 0)
                    validate_vector(vector)
                except (ValueError, TypeError):
                    invalid += 1
            values = {
                "embedding_dimension": min(dimensions)
                if dimensions and len(set(dimensions)) == 1
                else 0
                if dimensions
                else None,
                "invalid_vectors": invalid,
                "chunks_without_vector": absent,
            }
    except sqlite3.DatabaseError:
        pass
    return {k: metric(k, v) for k, v in values.items()}


def inspect_document(root, doc_id, paths, cache, review, measure=None):
    missing = []
    quality_path = root / "bronze" / (doc_id + ".quality.json")
    if not quality_path.is_file():
        missing.append(quality_path.name)
    original = load_text(root / "bronze" / (doc_id + ".txt"), missing)
    extraction = load_json(root / "bronze" / (doc_id + ".extraction.json"), missing)
    context = load_json(root / "silver" / (doc_id + ".context.json"), missing)
    cleaned = load_text(root / "silver" / (doc_id + ".txt"), missing)
    records = load_jsonl(root / "silver" / (doc_id + ".jsonl"), missing)
    gold = load_jsonl(root / "gold" / (doc_id + ".jsonl"), missing)
    pages = original.split("\n\f\n") if original else []
    metrics = extraction_metrics({**extraction, "original": original, "raw_pages": pages})
    chunks = [r.get("page_content", "") for r in gold]
    page_texts = [
        cleaned[p["clean_start"] : p["clean_end"]]
        for p in context.get("cleaned", {}).get("pages", [])
    ]
    budget = gold[0].get("metadata", {}).get("token_budget", 512) if gold else 512
    metrics.update(text_metrics(original, cleaned, chunks, budget, page_texts, measure))
    # Sobre ausencia de silver no se atribuyen al limpiador pérdidas del 100%.
    if not context or not (root / "silver" / (doc_id + ".txt")).exists():
        for name in (
            "invalid_pct",
            "mojibake_pct",
            "alphabetic_pct",
            "eol_hyphenations",
            "repeated_corner_lines",
            "removed_chars",
            "removed_pct",
        ):
            metrics[name] = metric(name, None)
    doc_type = context.get("doc_type", "jurisprudencia")
    if doc_type == "normativa":
        expected = max(1, len({key(m.group(1)) for m in ARTICLE_RE.finditer(original)}))
        detected = len(
            {
                r.get("metadata", {}).get("section_name")
                for r in records
                if r.get("metadata", {}).get("section_index", 0) > 0
            }
        )
    else:
        expected = 4
        detected = len(
            {
                r.get("metadata", {}).get("section_index")
                for r in records
                if r.get("metadata", {}).get("section_heading")
            }
        )
    metadata = context.get("metadata", {})
    fields = metadata.get("campos", {})
    present = [name for name in FIELDS if fields.get(name, {}).get("valor") is not None]
    absent = sorted(set(FIELDS) - set(present))

    def supported(field):
        evidence = field.get("evidencia")
        quotes = evidence if isinstance(evidence, list) else [evidence]
        return bool(quotes) and all(
            isinstance(q, str) and bool(q) and q in original for q in quotes
        )

    no_evidence = [name for name in present if not supported(fields[name])]
    values = {
        "sections_detected": detected,
        "sections_expected": expected,
        "structure_coverage_pct": percent(detected, expected),
        "metadata_present": len(present),
        "metadata_absent": len(absent),
        "metadata_conflicts": len(metadata.get("conflictos", []))
        + bool(metadata.get("origen_csv", {}).get("conflicto_csv"))
        + sum(v.get("estado") == "difiere" for v in metadata.get("cobertura_csv", {}).values()),
        "metadata_without_evidence": len(no_evidence),
        "review_queue_entries": review[doc_id] if review is not None else None,
        "missing_layers": len(missing),
    }
    metrics.update({name: metric(name, value) for name, value in values.items()})
    metrics.update(_vector_metrics(gold, cache))
    return (
        {
            "doc_id": doc_id,
            "paths": paths,
            "source_path": context.get("source_path"),
            "doc_type": doc_type,
            "metricas": metrics,
            "capas_ausentes_o_invalidas": sorted(missing),
            "metadatos": {
                "presentes": present,
                "ausentes": absent,
                "sin_evidencia": no_evidence,
                "conflictos": metadata.get("conflictos", []),
                "cobertura_csv": metadata.get("cobertura_csv", {}),
            },
        },
        original,
        cleaned,
        [chunk_body(r) for r in gold],
    )


def chunk_body(record):
    """Texto del chunk sin la cabecera de plantilla, comparable con el gold v1."""
    text = record.get("page_content", "")
    header = record.get("metadata", {}).get("header") or ""
    if header and text.startswith(header):
        return text[len(header) :].lstrip("\n")
    return text


def _stem(path):
    return key(Path(path.replace("\\", "/")).with_suffix("").as_posix())


def strip_markdown(text):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"(?m)^\s*\|?[ :\-]+\|[| :\-]*$", "", text)
    return text.replace("**", "").replace("__", "").replace("`", "")


def _comparison_changes(old, new):
    regressions, changes = {}, {}
    for name in COMPARISON_METRICS:
        before, after = old[name]["valor"], new[name]["valor"]
        if before is None or after is None:
            continue
        if name == "extracted_chars":
            if after < 0.8 * before:
                regressions[name] = (before - after) / before
        elif name in NEUTRAL_METRICS:
            change = abs(after - before) / before if before else (1 if after else 0)
            if change > REGRESSION_LIMIT + 1e-9:
                changes[name] = change
        else:
            floor = REGRESSION_FLOORS[name]
            increase = after - before
            # Con base cero se divide por el mínimo absoluto para mantener magnitudes finitas.
            change = increase / before if before else increase / floor
            if change > REGRESSION_LIMIT + 1e-9 and increase >= floor - 1e-9:
                regressions[name] = change
    return regressions, changes


def compare_v1(v1, documents, texts):
    index = defaultdict(list)
    all_paths = sorted((v1 / "bronze").rglob("*.md"))
    for path in all_paths:
        relative = path.relative_to(v1 / "bronze")
        index[_stem(relative.as_posix())].append(path)
        index["stem:" + key(path.stem)].append(path)
    matched, used, unmatched = [], set(), []
    for doc in documents:
        candidates = set()
        aliases = doc["paths"] + ([doc["source_path"]] if doc.get("source_path") else [])
        for alias in aliases:
            candidates.update(index.get(_stem(alias), []))
        if not candidates:
            for alias in aliases:
                candidates.update(index.get("stem:" + key(Path(alias).stem), []))
        if len(candidates) != 1:
            unmatched.append(
                {
                    "doc_id": doc["doc_id"],
                    "paths": doc["paths"],
                    "razon": "sin_coincidencia" if not candidates else "coincidencia_ambigua",
                }
            )
            continue
        path = candidates.pop()
        used.add(path)
        missing = []
        text = strip_markdown(load_text(path, missing))
        gold = v1 / "gold" / path.relative_to(v1 / "bronze").with_suffix(".jsonl")
        records = load_jsonl(gold, missing)
        old_chunks = [r.get("page_content", "") for r in records]
        original, cleaned, chunks = texts[doc["doc_id"]]
        old = text_metrics(text, text, old_chunks)
        old["extracted_chars"] = metric("extracted_chars", len(text))
        # Las tasas comparan texto extraído en ambos lados, sin limpieza silver.
        # Los chunks v2 se miden sin la cabecera de plantilla, que v1 no tiene:
        # incluida, inflaría tamaños y acercaría los SimHash del mismo documento.
        new = text_metrics(original, original, chunks)
        new["extracted_chars"] = metric("extracted_chars", len(original))
        regressions, changes = _comparison_changes(old, new)
        reasons = [
            f"{name}: regresión objetiva ({old[name]['valor']} → {new[name]['valor']})"
            + ("; v2 extrae menos del 80% de caracteres de v1" if name == "extracted_chars" else "")
            for name in regressions
        ]
        neutral_reasons = [
            f"{name}: cambio, no regresión ({old[name]['valor']} → {new[name]['valor']})"
            for name in changes
        ]
        matched.append(
            {
                "doc_id": doc["doc_id"],
                "paths": doc["paths"],
                "source_path": doc.get("source_path"),
                "v1_path": path.relative_to(v1).as_posix(),
                "v1": {n: old[n] for n in COMPARISON_METRICS},
                "v2": {n: new[n] for n in COMPARISON_METRICS},
                "razones": reasons,
                "cambios_neutrales": neutral_reasons,
                "regresiones": regressions,
                "cambios": changes,
                "numero_regresiones": len(regressions),
                "severidad": max(regressions.values(), default=0),
                "severidad_cambio": max(changes.values(), default=0),
                "bandera": "rojo" if regressions else "amarillo" if changes else "verde",
                "faltantes_v1": missing,
                "extracto_v1": text[:600],
                "extracto_v2": original[:600],
            }
        )
    aggregate = {}
    for side in ("v1", "v2"):
        aggregate[side] = {
            name: round(statistics.mean(values), 6)
            if (
                values := [
                    d[side][name]["valor"] for d in matched if d[side][name]["valor"] is not None
                ]
            )
            else None
            for name in COMPARISON_METRICS
        }
        aggregate[side]["documentos"] = len(matched)
    regressions = sorted(
        (d for d in matched if d["regresiones"]),
        key=lambda d: (-d["numero_regresiones"], -d["severidad"], d["doc_id"]),
    )
    neutral = sorted(
        (d for d in matched if not d["regresiones"] and d["cambios"]),
        key=lambda d: (-d["severidad_cambio"], d["doc_id"]),
    )
    worst = (regressions + neutral)[:10]
    regression_counts = {
        name: sum(name in d["regresiones"] for d in matched) for name in COMPARISON_METRICS
    }
    return {
        "documentos": matched,
        "documentos_con_regresion": len(regressions),
        "regresiones_por_metrica": regression_counts,
        "documentos_retencion_menor_80_pct": regression_counts["extracted_chars"],
        "agregado_medias_por_documento": aggregate,
        "agregado_banderas": {
            side: {name: metric(name, aggregate[side][name]) for name in COMPARISON_METRICS}
            for side in ("v1", "v2")
        },
        "umbrales_comparacion": {
            "retencion_caracteres_min": 0.8,
            "variacion_relativa_max": REGRESSION_LIMIT,
            "incrementos_absolutos_min": REGRESSION_FLOORS,
            "metricas_neutrales": sorted(NEUTRAL_METRICS),
        },
        "sin_pareja_v2": unmatched,
        "sin_pareja_v1": [p.relative_to(v1).as_posix() for p in all_paths if p not in used],
        "peores_10": [d["doc_id"] for d in worst],
    }


def _document_label(doc):
    paths = doc["paths"] or ([doc["source_path"]] if doc.get("source_path") else [])
    return doc["doc_id"] + " — " + (", ".join(paths) if paths else "ruta raw no disponible")


def _read_manifest(state):
    mapping = defaultdict(list)
    if state is None or not (Path(state) / "manifest.sqlite").is_file():
        return mapping
    with closing(
        sqlite3.connect((Path(state) / "manifest.sqlite").resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        for path, doc_id in db.execute("SELECT path,doc_id FROM paths ORDER BY path"):
            mapping[doc_id].append(path)
    return mapping


def report_quality(
    layers_root, state=None, cache=None, compare=None, enforce=False, measure=None, input_root=None
):
    root = guard_output(layers_root, input_root)
    if not root.exists():
        raise FileNotFoundError("layers-root no existe; ejecutar sync primero")
    mapping = _read_manifest(state)
    retired = set()
    catalog_path = root / "catalog.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        retired = set(catalog.get("retirados", []))
        for doc_id, aliases in catalog.get("documentos", {}).items():
            mapping.setdefault(doc_id, aliases)
    # Permite analizar una copia de capas sin manifiesto, incluso si falta bronze.
    for stage in ("bronze", "silver", "gold"):
        for path in sorted((root / stage).glob("*.*")):
            doc_id = path.name.split(".")[0]
            if re.fullmatch(r"[a-f0-9]{64}", doc_id) and doc_id not in retired:
                mapping.setdefault(doc_id, [])
    review = None
    if state is not None and (Path(state) / "review_queue.csv").exists():
        with (Path(state) / "review_queue.csv").open(encoding="utf-8", newline="") as stream:
            review = Counter(row["doc_id"] for row in csv.DictReader(stream))
    documents, texts = [], {}
    for doc_id, paths in sorted(mapping.items()):
        if doc_id in retired:
            continue
        doc, original, cleaned, chunks = inspect_document(
            root, doc_id, sorted(paths), cache, review, measure
        )
        documents.append(doc)
        texts[doc_id] = original, cleaned, chunks
    flags = Counter(m["bandera"] for d in documents for m in d["metricas"].values())
    result = {
        "schema": "objective-quality-1",
        "umbrales": THRESHOLDS,
        "documentos": documents,
        "resumen": {"documentos": len(documents), "banderas": dict(sorted(flags.items()))},
        "enforce_failed": bool(enforce and (flags["rojo"] or not documents)),
    }
    if compare is not None:
        result["comparacion_v1"] = compare_v1(Path(compare), documents, texts)
        if enforce and any(d["bandera"] == "rojo" for d in result["comparacion_v1"]["documentos"]):
            result["enforce_failed"] = True
    markdown = [
        "# Informe objetivo de calidad",
        "",
        "Mediciones de texto y artefactos; los umbrales son reglas operativas, no validación jurídica. No se calcula puntuación compuesta.",
        "",
        f"Documentos: {len(documents)}. Banderas: {dict(sorted(flags.items()))}.",
        "",
        "## Umbrales",
        "",
        "| Métrica | Dirección | Verde | Amarillo |",
        "|---|---|---:|---:|",
    ]
    markdown.extend(f"| {n} | {d} | {g} | {y} |" for n, (d, g, y) in THRESHOLDS.items())
    markdown.extend(
        [
            "",
            "Fuera del límite amarillo: rojo. Datos ausentes: no medido. Porcentajes en escala 0–100.",
            "",
            "## Por documento",
            "",
        ]
    )
    output = io.StringIO(newline="")
    names = ["doc_id", "paths", "capas_ausentes_o_invalidas"] + [
        part for name in THRESHOLDS for part in (name, name + "_bandera")
    ]
    comparison_rows = {
        d["doc_id"]: d for d in result.get("comparacion_v1", {}).get("documentos", [])
    }
    if compare is not None:
        names += [f"{side}_{name}" for side in ("v1", "v2") for name in COMPARISON_METRICS]
        names += ["comparacion_bandera", "comparacion_razones"]
    writer = csv.DictWriter(output, fieldnames=names, lineterminator="\n")
    writer.writeheader()
    for doc in documents:
        row = {
            "doc_id": doc["doc_id"],
            "paths": "|".join(doc["paths"]),
            "capas_ausentes_o_invalidas": "|".join(doc["capas_ausentes_o_invalidas"]),
        }
        markdown.extend(
            [
                f"### {_document_label(doc)}",
                "",
                "| Métrica | Valor | Bandera |",
                "|---|---:|---|",
            ]
        )
        for name, item in doc["metricas"].items():
            row[name], row[name + "_bandera"] = item["valor"], item["bandera"]
            markdown.append(
                f"| {name} | {item['valor'] if item['valor'] is not None else 'no medido'} | {item['bandera']} |"
            )
        markdown.extend(
            ["", "Capas ausentes/ilegibles: " + ", ".join(doc["capas_ausentes_o_invalidas"]), ""]
        )
        if doc["doc_id"] in comparison_rows:
            compared = comparison_rows[doc["doc_id"]]
            row.update(
                {
                    f"{side}_{name}": compared[side][name]["valor"]
                    for side in ("v1", "v2")
                    for name in COMPARISON_METRICS
                }
            )
            row["comparacion_bandera"] = compared["bandera"]
            row["comparacion_razones"] = "; ".join(
                compared["razones"] + compared["cambios_neutrales"]
            )
            markdown.extend(
                [
                    f"Comparación v1/v2: {compared['bandera']}. "
                    + (row["comparacion_razones"] or "Sin regresiones ni cambios neutrales >20%."),
                    "",
                ]
            )
        writer.writerow(row)
    if "comparacion_v1" in result:
        comparison = result["comparacion_v1"]
        markdown.extend(
            [
                "## Comparación v1/v2",
                "",
                "Se eliminan referencias de imagen, prefijos de encabezado, enlaces (se conserva etiqueta), separadores de tablas y marcas **, __, ` del Markdown v1. Coincidencia por ruta sin extensión en NFC y sin acentos/mayúsculas; fallback a stem único. Ambigüedades se informan sin emparejar.",
                "",
                "Regresiones: caracteres v2 <80% de v1; invalid_pct, mojibake_pct y short_chunks_pct aumentan >20% y al menos 0,1 puntos porcentuales; duplicados aumentan >20% y al menos 2. Con base cero, la magnitud relativa usa como denominador ese mínimo absoluto. Conteo/mediana/p5/p95 de chunks: variación >20% es cambio neutral, nunca regresión. Comparación roja si hay regresiones, amarilla si solo hay cambios neutrales, verde en otro caso. Extractos iniciales, no selección semántica.",
                "",
                "Agregados: medias por documento sobre exactamente los pares coincidentes.",
                "",
                "| Métrica | v1 | v2 | documentos con regresión |",
                "|---|---:|---:|---:|",
            ]
        )
        for name in COMPARISON_METRICS:
            markdown.append(
                f"| {name} | {comparison['agregado_medias_por_documento']['v1'][name]} | {comparison['agregado_medias_por_documento']['v2'][name]} | {comparison['regresiones_por_metrica'][name]} |"
            )
        markdown.extend(
            [
                "",
                f"Documentos donde v2 extrae <80% de caracteres de v1: {comparison['documentos_retencion_menor_80_pct']}.",
                "",
                "Sin pareja v2: " + json.dumps(comparison["sin_pareja_v2"], ensure_ascii=False),
                "",
                "Sin pareja v1: " + json.dumps(comparison["sin_pareja_v1"], ensure_ascii=False),
                "",
                "### Diez documentos con más regresiones objetivas",
                "",
                "Orden: número de métricas adversas y después máxima magnitud relativa adversa.",
                "",
            ]
        )
        if comparison["documentos_con_regresion"] < 10:
            markdown.extend(
                [
                    f"Documentos con regresiones objetivas: {comparison['documentos_con_regresion']} (menos de 10). Se completa la lista con los mayores cambios neutrales disponibles: cambio, no regresión.",
                    "",
                ]
            )
        by_id = {d["doc_id"]: d for d in comparison["documentos"]}
        for index, doc_id in enumerate(comparison["peores_10"]):
            doc = by_id[doc_id]
            markdown.extend(
                [
                    f"#### {_document_label(doc)}",
                    "",
                    f"Regresiones objetivas: {doc['numero_regresiones']}. "
                    + "; ".join(doc["razones"] + doc["cambios_neutrales"]),
                    "",
                ]
            )
            if index < 5:

                def escaped(text):
                    return (
                        text.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace("|", "&#124;")
                        .replace("\n", "<br>")
                    )

                markdown.extend(
                    [
                        "| v1 | v2 |",
                        "|---|---|",
                        f"| {escaped(doc['extracto_v1'])} | {escaped(doc['extracto_v2'])} |",
                        "",
                    ]
                )
    destination = root / "quality"
    # La resolución de cada destino impide escapar mediante un enlace en quality/.
    for name, content in {
        "quality_report.json": canonical(result),
        "quality_por_documento.csv": output.getvalue().encode(),
        "quality_report.md": ("\n".join(markdown) + "\n").encode(),
    }.items():
        target = guard_output(destination / name, input_root)
        if not target.is_relative_to(root / "quality"):
            raise ValueError("Destino de quality fuera de layers-root/quality")
        atomic_bytes(target, content)
    return result
