"""Capas medallion versionadas por contenido, sin vectores ni evaluación subjetiva."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path

from ..legal_metadata import SCHEMA_VERSION, apply_overrides, extract_legal_metadata
from ..offline_embeddings import DIGEST
from .chunks import CHUNKER_VERSION, make_chunks
from .extract import EXTRACTOR_VERSION, NORMALIZER_VERSION, clean_pages, read_document
from .storage import atomic_bytes, guard_output

STAGES = ("bronze", "silver", "gold", "embeddings")
STAGE_VERSIONS = {
    "bronze": "bronze-1",
    "silver": "silver-1",
    "gold": "gold-1",
    "embeddings": "embeddings-1",
}
SECTION_NAMES = {
    1: "Contexto del caso",
    2: "Desarrollo procesal",
    3: "Análisis del tribunal",
    4: "Decisión",
}
SECTION_RE = re.compile(
    r"(?mi)^[ \t]*(?:#{1,6}\s*)?(?:[IVXLCDM\d]+[.):\-]?\s+)?"
    r"(?P<label>ANTECEDENTES|SÍNTESIS DEL CASO|CONTESTACI[ÓO]N DE LA DEMANDA|"
    r"ACTUACI[ÓO]N PROCESAL|TR[ÁA]MITE[^\n]*|RECURSO DE APELACI[ÓO]N|"
    r"CONSIDERACIONES[^\n]*|FUNDAMENTOS[^\n]*|RESUELVE|FALLA|DECISI[ÓO]N)[^\n]*$"
)
ARTICLE_RE = re.compile(r"(?mi)^[ \t]*(?:#{1,6}\s*)?ART[ÍI]CULO\s+(\d+(?:\s*\.\s*\d+)*)[^\n]*")
# Correspondencia semántica; no implica igualdad de valores ni extracción del CSV.
CSV_REGEX_FIELDS = {
    "corporacion": "corporacion",
    "radicado": "radicado",
    "magistrado ponente": "magistrado_ponente",
    "tipo de documento": "tipo_documento",
    "tipo documento": "tipo_documento",
    "fecha": "fecha_iso",
    "numero": "numero",
    "ano": "anio",
    "sala": "sala",
    "municipio": "municipio",
}


def canonical(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode()


def signature(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def jsonl(records):
    return "".join(
        json.dumps(r, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n" for r in records
    ).encode()


def key(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn"
    )


def curated_metadata(root, aliases):
    candidates = []
    for path in sorted(root.rglob("*.csv")):
        if not path.resolve().is_relative_to(root):
            raise ValueError("CSV fuera de input-dir")
        content = path.read_text(encoding="utf-8-sig")
        try:
            dialect = csv.Sniffer().sniff(content[:4096], delimiters=";,\t")
        except csv.Error:
            continue
        for row in csv.DictReader(io.StringIO(content), dialect=dialect):
            row = {
                unicodedata.normalize("NFC", k).strip(): unicodedata.normalize(
                    "NFC", v or ""
                ).strip()
                for k, v in row.items()
                if k
            }
            filename = next(
                (v for k, v in row.items() if key(k) in {"archivo", "file", "source", "ruta"}), ""
            )
            filename = filename.replace("\\", "/")
            if filename and any(key(Path(filename).stem) == key(Path(a).stem) for a in aliases):
                candidates.append((path.relative_to(root).as_posix(), row))
    if len(candidates) > 1:
        return {}, {"conflicto_csv": [p for p, _ in candidates]}
    return (candidates[0][1], {"csv": candidates[0][0]}) if candidates else ({}, {})


def csv_coverage(curated, metadata):
    result = {}
    for field, value in sorted(curated.items()):
        regex_field = CSV_REGEX_FIELDS.get(key(field))
        extracted = metadata["campos"][regex_field]["valor"] if regex_field else None
        same = extracted is not None and re.sub(r"\W", "", key(str(extracted))) == re.sub(
            r"\W", "", key(value)
        )
        result[field] = {
            "campo_regex": regex_field,
            "reproducido": same,
            "estado": "coincide"
            if same
            else "sin_regla"
            if not regex_field
            else "sin_evidencia"
            if extracted is None
            else "difiere",
        }
    return result


def sections(text, doc_type):
    matches = list((ARTICLE_RE if doc_type == "normativa" else SECTION_RE).finditer(text))
    starts = sorted({0, len(text)} | {m.start() for m in matches})
    headings = {m.start(): m.group().strip() for m in matches}
    active = 1 if doc_type != "normativa" else 0
    label = SECTION_NAMES[1] if doc_type != "normativa" else "Preámbulo"
    result = []
    for start, end in zip(starts, starts[1:], strict=False):
        if start in headings:
            heading = headings[start]
            if doc_type == "normativa":
                active += 1
                label = heading
            else:
                normalized = key(heading)
                active = (
                    4
                    if re.search(r"resuelve|falla|decision", normalized)
                    else 3
                    if re.search(r"consideraciones|fundamentos", normalized)
                    else 1
                    if re.search(r"antecedentes|sintesis", normalized)
                    else 2
                )
                label = SECTION_NAMES[active]
        result.append(
            {
                "page_content": text[start:end],
                "metadata": {
                    "section_index": active,
                    "section_name": label,
                    "section_heading": headings.get(start),
                    "clean_start": start,
                    "clean_end": end,
                },
            }
        )
    return result


class Layers:
    def __init__(self, root, db, input_root):
        self.root = guard_output(root, input_root)
        self.db = db
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS layers (doc_id TEXT, stage TEXT, version TEXT, input_hash TEXT, artifacts TEXT, PRIMARY KEY(doc_id,stage))"
        )

    def path(self, stage, doc_id, suffix):
        path = self.root / stage / (doc_id + suffix)
        target = guard_output(path)
        if not target.is_relative_to(self.root / stage):
            raise ValueError("Enlace de capa fuera de layers-root")
        return target

    def valid(self, doc_id, stage, inputs):
        row = self.db.execute(
            "SELECT version,input_hash,artifacts FROM layers WHERE doc_id=? AND stage=?",
            (doc_id, stage),
        ).fetchone()
        if not row or row[:2] != (STAGE_VERSIONS[stage], signature(inputs)):
            return False
        for relative, digest in json.loads(row[2]).items():
            path = self.root / relative
            if not path.is_file() or signature_bytes(path.read_bytes()) != digest:
                return False
        return True

    def save(self, doc_id, stage, inputs, artifacts):
        hashes = {}
        for suffix, content in artifacts.items():
            path = self.path(stage, doc_id, suffix)
            hashes[path.relative_to(self.root).as_posix()] = atomic_bytes(path, content)
        self.db.execute(
            "INSERT OR REPLACE INTO layers VALUES (?,?,?,?,?)",
            (
                doc_id,
                stage,
                STAGE_VERSIONS[stage],
                signature(inputs),
                json.dumps(hashes, sort_keys=True),
            ),
        )

    def read_json(self, stage, doc_id, suffix):
        return json.loads(self.path(stage, doc_id, suffix).read_text(encoding="utf-8"))

    def persist(self):
        # Publicar las marcas confirmadas junto a las capas permite cambiar de estado.
        for doc_id, stage, version, input_hash, artifacts in self.db.execute(
            "SELECT doc_id,stage,version,input_hash,artifacts FROM layers"
        ):
            atomic_bytes(
                self.path(stage, doc_id, ".manifest.json"),
                canonical(
                    {
                        "version": version,
                        "input_hash": input_hash,
                        "artifacts": json.loads(artifacts),
                    }
                ),
            )

    def restore(self, doc_id, from_stage=None):
        for stage in STAGES:
            if self.artifacts(doc_id, stage) is not None:
                continue
            try:
                manifest = self.read_json(stage, doc_id, ".manifest.json")
                version, input_hash, artifacts = (
                    manifest["version"],
                    manifest["input_hash"],
                    manifest["artifacts"],
                )
                if (
                    not isinstance(version, str)
                    or not isinstance(input_hash, str)
                    or not isinstance(artifacts, dict)
                    or not artifacts
                ):
                    continue
                # No confiar en las marcas si falta un archivo o cambiaron sus bytes.
                for relative, digest in artifacts.items():
                    path = (self.root / relative).resolve()
                    if (
                        path.parent != self.root / stage
                        or not path.name.startswith(doc_id + ".")
                        or not path.is_file()
                        or signature_bytes(path.read_bytes()) != digest
                    ):
                        break
                else:
                    self.db.execute(
                        "INSERT INTO layers VALUES (?,?,?,?,?)",
                        (doc_id, stage, version, input_hash, json.dumps(artifacts, sort_keys=True)),
                    )
            except (OSError, ValueError, KeyError, TypeError):
                # Sin un manifiesto verificable, la etapa debe reconstruirse.
                continue
        if from_stage:
            for stage in STAGES[: STAGES.index(from_stage)]:
                if self.artifacts(doc_id, stage) is None:
                    raise ValueError(
                        f"{stage.capitalize()} ausente o inválido; ejecutar --from-stage {stage}"
                    )

    def build(
        self,
        doc_id,
        aliases,
        root,
        cache,
        config,
        overrides,
        digest=DIGEST,
        from_stage=None,
        measure=None,
    ):
        def timed(name, operation):
            return measure(name, operation) if measure else operation()

        force = STAGES.index(from_stage) if from_stage else len(STAGES)
        bronze_inputs = [doc_id, EXTRACTOR_VERSION]
        bronze_changed = not self.valid(doc_id, "bronze", bronze_inputs)
        if force > 0 and from_stage and bronze_changed:
            raise ValueError("Bronze ausente o inválido; ejecutar --from-stage bronze")
        if force == 0 or bronze_changed:
            document = timed("extraction", lambda: read_document(root / aliases[0], cache))
            extraction = {
                k: v
                for k, v in document.items()
                if k
                not in {
                    "raw_pages",
                    "original",
                    "new_ocr_pages",
                    "cpu_seconds",
                    "ocr_seconds",
                    "extraction_cache_hit",
                }
            }
            extraction.update(
                {
                    "extractor": document.get("extractor", "PyMuPDF/Tesseract spa"),
                    "original_file": Path(document["original_file"]).name,
                    "chars_per_page": [len(re.sub(r"\s", "", p)) for p in document["raw_pages"]],
                    "errors": [
                        {"page": p, "reason": "ocr_failed"} for p in document["ocr_failed_pages"]
                    ],
                }
            )
            from .quality import extraction_metrics

            self.save(
                doc_id,
                "bronze",
                bronze_inputs,
                {
                    ".txt": document["original"].encode(),
                    ".extraction.json": canonical(extraction),
                    ".quality.json": canonical(extraction_metrics(document)),
                },
            )
        else:
            extraction = self.read_json("bronze", doc_id, ".extraction.json")
            original = self.path("bronze", doc_id, ".txt").read_bytes().decode("utf-8")
            document = {
                **extraction,
                "original_file": str(cache / "originals" / extraction["original_file"]),
                "original": original,
                "raw_pages": original.split("\n\f\n"),
                "new_ocr_pages": 0,
                "cpu_seconds": 0,
                "ocr_seconds": 0,
            }
        stable_aliases = list(aliases)
        old_context = self.path("silver", doc_id, ".context.json")
        previous_context = {}
        if old_context.exists():
            try:
                previous_context = json.loads(old_context.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
            origin = previous_context.get("source_path")
            if origin:
                stable_aliases.append(origin)
        curated, csv_source = curated_metadata(root, stable_aliases)
        if not root.exists() and previous_context:
            old_metadata = previous_context["metadata"]
            curated, csv_source = (
                old_metadata.get("metadata_curada", {}),
                old_metadata.get("origen_csv", {}),
            )
        origin_source = previous_context.get("source_path") or aliases[0]
        doc_type = "normativa" if "normativa" in Path(origin_source).parts else "jurisprudencia"
        silver_inputs = [
            self.artifacts(doc_id, "bronze"),
            NORMALIZER_VERSION,
            SCHEMA_VERSION,
            overrides,
            curated,
            csv_source,
            doc_type,
        ]
        silver_changed = bronze_changed or not self.valid(doc_id, "silver", silver_inputs)
        if from_stage in {"gold", "embeddings"} and silver_changed:
            raise ValueError("Silver ausente o inválido; ejecutar --from-stage silver")
        if force <= 1 or silver_changed:
            metadata = timed(
                "metadata",
                lambda: apply_overrides(
                    extract_legal_metadata(document["original"]),
                    overrides,
                    doc_id,
                    document["original"],
                ),
            )
            cleaned = timed("cleaning", lambda: clean_pages(document["raw_pages"]))
            metadata["metadata_curada"] = curated
            metadata["cobertura_csv"] = csv_coverage(curated, metadata)
            metadata["origen_csv"] = csv_source
            records = sections(cleaned["text"], doc_type)
            for record in records:
                record["metadata"].update({"doc_id": doc_id, "doc_type": doc_type, **metadata})
            self.save(
                doc_id,
                "silver",
                silver_inputs,
                {
                    ".txt": cleaned["text"].encode(),
                    ".jsonl": jsonl(records),
                    ".context.json": canonical(
                        {
                            "cleaned": cleaned,
                            "metadata": metadata,
                            "doc_type": doc_type,
                            "source_path": origin_source,
                        }
                    ),
                },
            )
        else:
            context = self.read_json("silver", doc_id, ".context.json")
            cleaned, metadata = context["cleaned"], context["metadata"]
        # Los alias actuales se publican; las capas conservan el origen del primer build.
        # Renombrar no cambia identidad, bytes ni claves de embedding.
        gold_inputs = [
            self.artifacts(doc_id, "silver"),
            CHUNKER_VERSION,
            config["chunker"],
            config["token_budget"],
            digest,
        ]
        gold_changed = silver_changed or not self.valid(doc_id, "gold", gold_inputs)
        if from_stage == "embeddings" and gold_changed:
            raise ValueError("Gold ausente o inválido; ejecutar --from-stage gold")
        if force <= 2 or gold_changed:
            source = origin_source
            chunks = timed(
                "chunking",
                lambda: make_chunks(
                    doc_id,
                    cleaned,
                    metadata,
                    source,
                    doc_type,
                    config["chunker"],
                    config["token_budget"],
                ),
            )
            section_records = sections(cleaned["text"], doc_type)
            for chunk in chunks:
                meta = chunk["metadata"]
                meta["section_index"] = next(
                    (
                        r["metadata"]["section_index"]
                        for r in section_records
                        if r["metadata"]["clean_start"]
                        <= meta["clean_start"]
                        < r["metadata"]["clean_end"]
                    ),
                    0,
                )
                meta["embedding_cache_key"] = hashlib.sha256(
                    (digest + "\0" + chunk["document"]).encode()
                ).hexdigest()
                meta["embedding_model_digest"] = digest
                meta["token_budget"] = config["token_budget"]
                meta["chunker"] = config["chunker"]
                meta["metadata_curada"] = json.dumps(curated, ensure_ascii=False, sort_keys=True)
            self.save(
                doc_id,
                "gold",
                gold_inputs,
                {
                    ".jsonl": jsonl(
                        {"page_content": c["document"], "metadata": c["metadata"]} for c in chunks
                    )
                },
            )
        else:
            chunks = []
            for line in (
                self.path("gold", doc_id, ".jsonl").read_text(encoding="utf-8").splitlines()
            ):
                row = json.loads(line)
                meta = row["metadata"]
                chunks.append(
                    {
                        "id": meta["chunk_id"],
                        "document": row["page_content"],
                        "metadata": meta,
                        "raw_text": cleaned["text"][meta["clean_start"] : meta["clean_end"]],
                    }
                )
        return (
            document,
            metadata,
            cleaned,
            chunks,
            bronze_changed or silver_changed or gold_changed or force < len(STAGES),
        )

    def artifacts(self, doc_id, stage):
        row = self.db.execute(
            "SELECT version,input_hash,artifacts FROM layers WHERE doc_id=? AND stage=?",
            (doc_id, stage),
        ).fetchone()
        return list(row) if row else None


def signature_bytes(content):
    return hashlib.sha256(content).hexdigest()
