"""Dataset determinista desde textos FUENTE; sin proveedores ni claves LLM."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

VERSION = "templates-1"


def nfc(text):
    return unicodedata.normalize("NFC", text)


def document_key(path):
    return nfc(Path(path).stem).casefold()


def topic(text):
    for pattern, label in [
        (r"concesi[oó]n", "las concesiones en zonas costeras"),
        (r"uso p[uú]blico", "los bienes de uso público"),
        (r"permiso", "los permisos para actividades en playas"),
        (r"DIMAR|Mar[ií]tima", "las competencias de la autoridad marítima"),
        (r"playa", "el uso de las playas"),
        (r"ambienta", "la protección ambiental en zonas costeras"),
    ]:
        if re.search(pattern, text, re.I):
            return label
    return "las reglas aplicables a zonas costeras"


def candidates(text):
    found = []
    for match in re.finditer(r"[^\n\f]{60,260}", text):
        quote = match.group().strip()
        if not re.search(r"playa|mar[ií]tim|DIMAR|concesi|uso p[uú]blico|bajamar", quote, re.I):
            continue
        if len(re.findall(r"[a-záéíóúñ]{3,}", quote, re.I)) < 8:
            continue
        score = len(
            re.findall(r"playa|DIMAR|deber|derecho|permiso|concesi|p[uú]blico", quote, re.I)
        )
        found.append((score, match.start(), quote))
    return sorted(found, key=lambda item: (-item[0], item[1]))


def build(sources_dir, snapshot, output):
    manifest = json.loads((sources_dir / "manifest.json").read_text(encoding="utf-8"))
    with gzip.open(snapshot, "rt", encoding="utf-8") as stream:
        indexed = {
            document_key(row["metadata"].get("source", ""))
            for line in stream
            if "__manifest__" not in (row := json.loads(line))
        }
    eligible = []
    for source in manifest:
        text = nfc((sources_dir / (source["source_id"] + ".txt")).read_text(encoding="utf-8"))
        key = document_key(source["path"])
        passages = candidates(text)
        if len(text) >= 200 and passages and key in indexed:
            eligible.append({**source, "text": text, "key": key, "passages": passages})
    eligible.sort(key=lambda row: (row["type"], row["source_id"]))
    groups = {
        kind: [s for s in eligible if s["type"] == kind] for kind in ["jurisprudencia", "normativa"]
    }
    # Alternancia de tipos y documentos, sin muestreo sobre chunks.
    ordered = []
    for index in range(max(map(len, groups.values()))):
        for rows in groups.values():
            if index < len(rows):
                ordered.append(rows[index])
    if len(ordered) < 12:
        raise ValueError("Fuentes elegibles insuficientes; revisar extracción y mapeo exacto")
    cases = []

    def evidence(source, quote, start):
        assert quote in source["text"]
        context = source["text"][
            max(0, start - 160) : min(len(source["text"]), start + len(quote) + 160)
        ]
        return {
            "quote": quote,
            "reference_context": context,
            "source_id": source["source_id"],
            "source_path": source["path"],
            "document_key": source["key"],
            "pages": [source["text"][:start].count("\f") + 1] if source["pages"] else None,
        }

    def label(source):
        return nfc(Path(source["path"]).stem).replace("_", " ")

    def add(question, category, entries):
        cases.append(
            {
                "id": f"atlas-{len(cases) + 1:03}",
                "pregunta": question,
                "reference_contexts": [e["reference_context"] for e in entries],
                "evidence": entries,
                "documentos_fuente": [e["source_path"] for e in entries],
                "categoria": category,
                "validado_por_abogado": False,
                "estado_validacion": "no validado por abogados",
            }
        )

    for index in range(24):
        source = ordered[index % len(ordered)]
        _, start, quote = source["passages"][index // len(ordered) % len(source["passages"])]
        add(
            f"Según el documento «{label(source)}», ¿qué se señala sobre {topic(quote)}?",
            "contenido",
            [evidence(source, quote, start)],
        )
    identity_patterns = [
        (
            r"(?im)(?:magistrad[oa]|consejer[oa])\s+ponente\s*[:\-]?\s*[^\n\f]{5,100}",
            "¿Quién figura como ponente",
        ),
        (
            r"(?im)(?:radicaci[oó]n|radicado|expediente)\s*(?:n[úu]mero|no\.?|n[º°])?\s*[:\-]?\s*[0-9][0-9 .\-()]{8,60}",
            "¿Qué radicado o expediente identifica",
        ),
        (
            r"(?im)(?:CONSEJO DE ESTADO|CORTE CONSTITUCIONAL|TRIBUNAL ADMINISTRATIVO[^\n\f]{0,70})",
            "¿Qué corporación judicial se identifica en",
        ),
    ]
    used = set()
    for pattern, question in identity_patterns:
        for source in ordered:
            match = re.search(pattern, source["text"][:12000], re.I)
            if not match or (source["key"], match.group()) in used:
                continue
            used.add((source["key"], match.group()))
            add(
                f"{question} el documento «{label(source)}»?",
                "identidad",
                [evidence(source, match.group(), match.start())],
            )
            if len(cases) == 34:
                break
        if len(cases) == 34:
            break
    if len(cases) != 34:
        raise ValueError("No hay diez preguntas de identidad con evidencia verificable")
    norms = groups["normativa"]
    for index in range(6):
        first = norms[index % len(norms)]
        second = ordered[(index + 7) % len(ordered)]
        if second["key"] == first["key"]:
            second = ordered[(index + 8) % len(ordered)]
        entries = []
        for source in [first, second]:
            _, start, quote = source["passages"][0]
            entries.append(evidence(source, quote, start))
        add(
            f"¿Qué indican «{label(first)}» y «{label(second)}» acerca del uso de playas y zonas costeras? Distingue lo que dice cada documento.",
            "multi_documento",
            entries,
        )
    assert len(cases) == 40
    for case in cases:
        for entry in case["evidence"]:
            source = next(s for s in eligible if s["source_id"] == entry["source_id"])
            if nfc(entry["quote"]) not in source["text"]:
                raise ValueError("Cita no encontrada en la fuente NFC")
    output.mkdir(parents=True, exist_ok=True)
    path = output / "dataset_v1.jsonl"
    if path.exists():
        raise FileExistsError("Dataset congelado; no sobrescribir")
    path.write_bytes("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in cases).encode())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / "dataset_v1.sha256").write_bytes((digest + "  dataset_v1.jsonl\n").encode())
    metadata = {
        "version": VERSION,
        "dataset_sha256": digest,
        "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "fuentes_totales": len(manifest),
        "fuentes_elegibles": len(eligible),
        "fuentes_muestreadas": len({e["source_id"] for c in cases for e in c["evidence"]}),
        "categorias": dict(Counter(c["categoria"] for c in cases)),
        "api_calls": 0,
        "validado_por_abogado": False,
        "limitacion": "Plantillas y extracción digital; no se usan los 19 documentos con texto insuficiente para generar este dataset. Cobertura parcial del corpus.",
    }
    (output / "dataset_manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    selected = cases[:6] + cases[24:26] + cases[34:36]
    review = [
        "# Muestra para revisión",
        "",
        "**No validado por abogados.** Dataset por plantillas; mide mejora relativa, no corrección jurídica.",
        "",
    ]
    for case in selected:
        review.extend([f"## {case['id']} — {case['categoria']}", "", case["pregunta"], ""])
        for entry in case["evidence"]:
            review.extend(
                [
                    f"Fuente: `{entry['source_path']}`; páginas: {entry['pages']}",
                    "",
                    "> " + entry["quote"].replace("\n", "\n> "),
                    "",
                ]
            )
    (output / "muestra_revision.md").write_text("\n".join(review), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.sources, args.snapshot, args.output)
