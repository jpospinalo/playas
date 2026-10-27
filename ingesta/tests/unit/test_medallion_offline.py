"""Contratos medallion sin servicios; ejecutables también con unittest estándar."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
import math
import sqlite3
import sys
import tempfile
import unittest
import weakref
from contextlib import chdir, closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ingest.offline import layers, quality
from ingest.offline.__main__ import main
from ingest.offline.chunks import header
from ingest.offline.extract import _ocr
from ingest.offline.pipeline import Pipeline
from ingest.offline.publish import ChromaPublisher, chroma_lock_directory
from ingest.offline.quality import (
    COMPARISON_METRICS,
    THRESHOLDS,
    _comparison_changes,
    chunk_body,
    compare_v1,
    extraction_metrics,
    invalid_pct,
    metric,
    mojibake_pct,
    report_quality,
    text_metrics,
)
from ingest.offline.storage import atomic_bytes, guard_output, writer_lock
from ingest.offline_embeddings import FakeBatchEmbeddings

TEXT = (
    "CONSEJO DE ESTADO\nMagistrado ponente: JUAN PEREZ\n"
    "Radicado: 47001-23-33-000-2020-00123-01\nSanta Marta, 12 de marzo de 2024\n"
    "ANTECEDENTES\nEl acceso público a las playas.\nACTUACIÓN PROCESAL\n"
    "Texto de trámite.\nCONSIDERACIONES\n"
    + "Las playas son bienes de uso público. " * 30
    + "\nRESUELVE\nSe protege el acceso."
)


def controlled_chunks(doc_id, cleaned, metadata, source, doc_type, mode, budget):
    # El splitter real tiene pruebas propias; aquí se aísla la máquina de etapas.
    text = cleaned["text"]
    result = []
    for start in range(0, len(text), 600):
        raw = text[start : start + 600]
        prefix = header(metadata["campos"], "Texto íntegro")
        document = prefix + "\n\n" + raw
        identity = hashlib.sha256((doc_id + str(start) + document).encode()).hexdigest()
        result.append(
            {
                "id": identity,
                "document": document,
                "raw_text": raw,
                "metadata": {
                    "chunk_id": identity,
                    "doc_id": doc_id,
                    "source_path": source,
                    "source": Path(source).name,
                    "doc_type": doc_type,
                    "section_name": "Texto íntegro",
                    "clean_start": start,
                    "clean_end": start + len(raw),
                    "source_start": start,
                    "source_end": start + len(raw),
                    "header": prefix,
                },
            }
        )
    return result


class Publisher:
    collection_name = "bench_medallion"

    def __init__(self):
        self.docs = {}
        self.calls = 0

    def upsert_document(self, doc_id, records, vectors):
        self.calls += 1
        self.docs[doc_id] = records

    def delete_document(self, doc_id):
        self.docs.pop(doc_id, None)


class MedallionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.raw = self.base / "data/documents/raw"
        self.raw.mkdir(parents=True)
        self.source = self.raw / "fallo.txt"
        self.source.write_text(TEXT, encoding="utf-8")
        self.cache = self.base / "cache"
        self.embedder = FakeBatchEmbeddings(self.cache / "bench_embeddings.sqlite")
        self.addCleanup(self.embedder.close)
        self.publisher = Publisher()
        self.root = self.base / "data/documents-v2"
        self.pipeline = Pipeline(
            self.raw,
            self.base / "state",
            self.cache,
            self.embedder,
            self.publisher,
            layers_root=self.root,
        )
        self.addCleanup(self.pipeline.close)
        self.chunker_patch = patch.object(layers, "make_chunks", controlled_chunks)
        self.chunker_patch.start()
        self.addCleanup(self.chunker_patch.stop)

    def run_pipeline(self, **kwargs):
        result = self.pipeline.run(**kwargs)
        self.assertEqual(result["errors"], [])
        return result

    def snapshot(self, path):
        return {
            p.relative_to(path).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
            for p in path.rglob("*")
            if p.is_file()
        }

    def fresh_pipeline(self, name, **kwargs):
        pipeline = Pipeline(
            self.raw,
            self.base / name,
            self.cache,
            self.embedder,
            Publisher(),
            layers_root=self.root,
            **kwargs,
        )
        self.addCleanup(pipeline.close)
        return pipeline

    def test_idempotent_layers_and_quality_no_embedding_or_publish(self):
        self.run_pipeline()
        before = self.snapshot(self.root)
        raw = self.snapshot(self.raw)
        calls = self.publisher.calls
        result = self.run_pipeline()
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["new_embeddings"], 0)
        self.assertEqual(self.publisher.calls, calls)
        self.assertEqual(before, self.snapshot(self.root))
        self.assertEqual(raw, self.snapshot(self.raw))
        self.assertFalse((self.base / "data/documents/bronze").exists())

    @unittest.skipUnless(
        importlib.util.find_spec("langchain_text_splitters"), "Requiere splitter real"
    )
    def test_real_chunker_roundtrip(self):
        self.chunker_patch.stop()
        self.run_pipeline()
        before = self.snapshot(self.root / "gold")
        self.assertEqual(self.run_pipeline()["new_embeddings"], 0)
        self.assertEqual(self.run_pipeline(from_stage="silver")["new_embeddings"], 0)
        self.assertEqual(before, self.snapshot(self.root / "gold"))

    def test_from_silver_reads_bronze_and_keeps_gold_bytes_and_mtimes(self):
        self.run_pipeline()
        before = self.snapshot(self.root / "gold")
        with patch.object(layers, "read_document", side_effect=AssertionError("No reextraer")):
            result = self.run_pipeline(from_stage="silver")
        self.assertEqual(result["new_embeddings"], 0)
        self.assertEqual(before, self.snapshot(self.root / "gold"))

    def test_rename_keeps_all_layers_and_curated_metadata(self):
        (self.raw / "metadata.csv").write_text(
            "Archivo;Nº;Corporación;Tema principal\nfallo.txt;SM-01;CONSEJO DE ESTADO;Playas\n",
            encoding="utf-8",
        )
        self.run_pipeline()
        before = {stage: self.snapshot(self.root / stage) for stage in layers.STAGES}
        self.source.rename(self.raw / "nuevo_nombre.txt")
        result = self.run_pipeline()
        self.assertEqual(result["renamed"], 1)
        self.assertEqual(result["new_embeddings"], 0)
        self.assertEqual(
            before, {stage: self.snapshot(self.root / stage) for stage in layers.STAGES}
        )
        context = json.loads(
            next((self.root / "silver").glob("*.context.json")).read_text(encoding="utf-8")
        )
        self.assertEqual(context["metadata"]["metadata_curada"]["Nº"], "SM-01")
        self.assertTrue(context["metadata"]["cobertura_csv"]["Corporación"]["reproducido"])
        self.assertFalse(context["metadata"]["cobertura_csv"]["Tema principal"]["reproducido"])

    def test_modify_only_one_document_and_retire_original(self):
        other = self.raw / "otro.txt"
        other.write_text(TEXT + " Otro caso.", encoding="utf-8")
        self.run_pipeline()
        old_id = hashlib.sha256(self.source.read_bytes()).hexdigest()
        other_id = hashlib.sha256(other.read_bytes()).hexdigest()
        snapshots = {
            p: (p.read_bytes(), p.stat().st_mtime_ns) for p in self.root.rglob(other_id + "*")
        }
        self.source.write_text(TEXT + " Modificado.", encoding="utf-8")
        result = self.run_pipeline()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(snapshots, {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in snapshots})
        catalog = json.loads((self.root / "catalog.json").read_text(encoding="utf-8"))
        self.assertIn(old_id, catalog["retirados"])
        report = json.loads((self.root / "quality/quality_report.json").read_text(encoding="utf-8"))
        self.assertNotIn(old_id, [d["doc_id"] for d in report["documentos"]])

    def test_stage_versions_only_invalidate_downstream(self):
        self.run_pipeline()
        bronze = self.snapshot(self.root / "bronze")
        gold = self.snapshot(self.root / "gold")
        versions = {**layers.STAGE_VERSIONS, "silver": "silver-test"}
        with (
            patch.dict(layers.STAGE_VERSIONS, versions),
            patch.object(layers, "read_document", side_effect=AssertionError("No reextraer")),
        ):
            result = self.run_pipeline()
        self.assertEqual(result["processed"], 1)
        self.assertEqual(bronze, self.snapshot(self.root / "bronze"))
        current = self.snapshot(self.root / "gold")
        # La firma cambia con silver; los bytes y mtimes de los chunks se conservan.
        self.assertEqual(
            {name: value for name, value in gold.items() if name.endswith(".jsonl")},
            {name: value for name, value in current.items() if name.endswith(".jsonl")},
        )
        self.assertNotEqual(gold, current)
        rows = dict(self.pipeline.db.execute("SELECT stage,version FROM layers"))
        self.assertEqual(rows["silver"], "silver-test")

    def test_gold_and_embeddings_restarts_do_not_clean_or_extract(self):
        self.run_pipeline()
        for stage in ("gold", "embeddings"):
            with (
                self.subTest(stage=stage),
                patch.object(layers, "clean_pages", side_effect=AssertionError("No limpiar")),
                patch.object(layers, "read_document", side_effect=AssertionError("No reextraer")),
            ):
                self.assertEqual(self.run_pipeline(from_stage=stage)["new_embeddings"], 0)

    def test_missing_upstream_rejected_for_restart(self):
        report = self.pipeline.run(from_stage="silver")
        self.assertEqual(len(report["errors"]), 1)
        self.assertIn("Bronze", report["errors"][0]["reason"])

    def test_fresh_state_restores_layers_and_catalog_without_originals(self):
        self.run_pipeline()
        before = {stage: self.snapshot(self.root / stage) for stage in layers.STAGES}
        rows = self.pipeline.db.execute("SELECT * FROM layers ORDER BY stage").fetchall()
        for doc_id, stage, version, input_hash, artifacts in rows:
            manifest = self.pipeline.layers.read_json(stage, doc_id, ".manifest.json")
            self.assertEqual(
                manifest,
                {"version": version, "input_hash": input_hash, "artifacts": json.loads(artifacts)},
            )
        self.source.unlink()
        self.raw.rmdir()
        for stage in ("silver", "gold", "embeddings"):
            with self.subTest(stage=stage):
                pipeline = self.fresh_pipeline("fresh-" + stage)
                self.assertEqual(pipeline.db.execute("SELECT * FROM layers").fetchall(), [])
                with patch.object(layers, "read_document", side_effect=AssertionError("No raw")):
                    result = pipeline.run(from_stage=stage)
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["processed"], 1)
                self.assertEqual(result["new_embeddings"], 0)
                self.assertEqual(
                    pipeline.db.execute("SELECT * FROM layers ORDER BY stage").fetchall(), rows
                )
                self.assertEqual(
                    dict(pipeline.db.execute("SELECT path,doc_id FROM paths")),
                    {"fallo.txt": doc_id},
                )
                self.assertEqual(
                    before, {name: self.snapshot(self.root / name) for name in layers.STAGES}
                )

    def test_new_chunker_budget_and_model_reuse_extraction_in_fresh_state(self):
        self.run_pipeline()
        before = {stage: self.snapshot(self.root / stage) for stage in ("bronze", "silver")}
        for name, options, digest in (
            ("chunker", {"chunker": "structure"}, self.embedder.digest),
            ("budget", {"token_budget": 256}, self.embedder.digest),
            ("model", {}, "bench-sha256-768-2"),
        ):
            with self.subTest(change=name), patch.object(self.embedder, "digest", digest):
                pipeline = self.fresh_pipeline("fresh-" + name, **options)
                with (
                    patch.object(layers, "read_document", side_effect=AssertionError("No extraer")),
                    patch.object(layers, "clean_pages", side_effect=AssertionError("No limpiar")),
                    patch.object(layers, "make_chunks", wraps=controlled_chunks) as chunker,
                ):
                    result = pipeline.run()
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["processed"], 1)
                chunker.assert_called_once()
                self.assertEqual(
                    before, {stage: self.snapshot(self.root / stage) for stage in before}
                )
                self.assertEqual(
                    pipeline.db.execute("SELECT count(*) FROM layers").fetchone()[0], 4
                )

    def test_fresh_state_rejects_changed_upstream_hash_and_preserves_catalog_for_retry(self):
        self.run_pipeline()
        catalog = (self.root / "catalog.json").read_bytes()
        for stage, suffix, restart in (
            ("bronze", ".txt", "silver"),
            ("bronze", ".extraction.json", "silver"),
            ("bronze", ".quality.json", "silver"),
            ("silver", ".txt", "gold"),
            ("silver", ".jsonl", "gold"),
            ("silver", ".context.json", "gold"),
            ("gold", ".jsonl", "embeddings"),
        ):
            with self.subTest(stage=stage, suffix=suffix):
                target = next((self.root / stage).glob("*" + suffix))
                content = target.read_bytes()
                # Incluso un JSON válido con estructura ajena debe fallar por hash.
                target.write_bytes(b"[]" if suffix.endswith(".json") else content + b"\n")
                pipeline = self.fresh_pipeline("corrupt-" + stage + suffix)
                with patch.object(
                    layers, "read_document", side_effect=AssertionError("No extraer")
                ):
                    result = pipeline.run(from_stage=restart)
                self.assertEqual(result["processed"], 0)
                self.assertEqual(len(result["errors"]), 1)
                self.assertIn("--from-stage " + stage, result["errors"][0]["reason"])
                self.assertEqual((self.root / "catalog.json").read_bytes(), catalog)
                target.write_bytes(content)
                self.assertEqual(pipeline.run(from_stage=restart)["errors"], [])

    def test_fresh_state_checks_persisted_stage_version_and_input_signature(self):
        self.run_pipeline()
        target = next((self.root / "bronze").glob("*.manifest.json"))
        content = target.read_bytes()
        for field in ("version", "input_hash"):
            with self.subTest(field=field):
                manifest = json.loads(content)
                manifest[field] = "obsoleto"
                target.write_bytes(layers.canonical(manifest))
                pipeline = self.fresh_pipeline("invalid-" + field)
                result = pipeline.run(from_stage="silver")
                self.assertEqual(len(result["errors"]), 1)
                self.assertIn("--from-stage bronze", result["errors"][0]["reason"])
                target.write_bytes(content)

    def test_artifact_hashes_and_vectors_not_in_layers(self):
        self.run_pipeline()
        for _, _, artifacts in self.pipeline.db.execute(
            "SELECT stage,version,artifacts FROM layers"
        ):
            for relative, expected in json.loads(artifacts).items():
                self.assertEqual(
                    hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), expected
                )
        for path in (self.root / "gold").glob("*.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                self.assertEqual(set(row), {"page_content", "metadata"})
                self.assertIn("embedding_cache_key", row["metadata"])
                self.assertNotIn("embedding", row)
        self.assertEqual(
            set(self.run_pipeline()["stage_timings"]),
            {
                "extraction",
                "ocr",
                "cleaning",
                "metadata",
                "chunking",
                "duplicates",
                "embeddings",
                "chroma_publish",
                "quality_report",
            },
        )

    def test_corrupted_artifact_rebuilt(self):
        self.run_pipeline()
        target = next((self.root / "gold").glob("*.jsonl"))
        expected = target.read_bytes()
        target.write_bytes(b"json invalido")
        self.run_pipeline()
        self.assertEqual(target.read_bytes(), expected)

    def test_artifact_failure_rolls_back_document_marks_and_retries_curated_csv(self):
        curated = self.raw / "metadata.csv"
        curated.write_text("Archivo;Tema principal\nfallo.txt;Anterior\n", encoding="utf-8")
        self.run_pipeline()
        doc_id = hashlib.sha256(self.source.read_bytes()).hexdigest()
        artifact = self.pipeline.state / "documents" / (doc_id + ".json.gz")
        before = artifact.read_bytes()
        tables = ("documents", "paths", "layers")
        saved = {
            table: self.pipeline.db.execute(
                f"SELECT * FROM {table} WHERE doc_id=?", (doc_id,)
            ).fetchall()
            for table in tables
        }
        curated.write_text("Archivo;Tema principal\nfallo.txt;Actualizado\n", encoding="utf-8")
        (self.raw / "otro.txt").write_text(TEXT + " Otro documento.", encoding="utf-8")
        calls = self.publisher.calls

        def fail_artifact(path, content):
            if path == artifact:
                # El fallo sucede después de publicar y actualizar embeddings.
                self.assertGreater(self.publisher.calls, calls)
                self.assertNotEqual(
                    saved["layers"],
                    self.pipeline.db.execute(
                        "SELECT * FROM layers WHERE doc_id=?", (doc_id,)
                    ).fetchall(),
                )
                raise OSError("Fallo al persistir el artefacto")
            return atomic_bytes(path, content)

        with patch("ingest.offline.pipeline.atomic_bytes", side_effect=fail_artifact):
            failed = self.pipeline.run()
        self.assertEqual(len(failed["errors"]), 1)
        self.assertEqual(failed["processed"], 1)
        self.assertEqual(artifact.read_bytes(), before)
        # Consultar otra conexión verifica el estado confirmado por el commit final.
        with closing(sqlite3.connect(self.pipeline.state / "manifest.sqlite")) as db:
            for table in tables:
                self.assertEqual(
                    saved[table],
                    db.execute(f"SELECT * FROM {table} WHERE doc_id=?", (doc_id,)).fetchall(),
                )
        retried = self.run_pipeline()
        self.assertEqual((retried["processed"], retried["skipped"]), (1, 1))
        with gzip.open(artifact, "rt", encoding="utf-8") as stream:
            self.assertEqual(
                json.load(stream)["metadata"]["metadata_curada"]["Tema principal"], "Actualizado"
            )
        self.assertEqual(self.run_pipeline()["skipped"], 2)

    def test_manifest_failure_rolls_back_new_document_and_all_layer_marks(self):
        self.pipeline.db.execute(
            "CREATE TEMP TRIGGER fail_manifest BEFORE INSERT ON documents "
            "BEGIN SELECT RAISE(ABORT, 'Fallo de manifiesto'); END"
        )
        failed = self.pipeline.run()
        self.assertEqual(len(failed["errors"]), 1)
        self.assertEqual(failed["processed"], 0)
        for table in ("documents", "paths", "layers"):
            self.assertEqual(
                self.pipeline.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0], 0
            )
        self.pipeline.db.execute("DROP TRIGGER fail_manifest")
        self.assertEqual(self.run_pipeline()["processed"], 1)

    def test_chroma_lock_covers_the_entire_sync_and_add(self):
        publisher = ChromaPublisher.__new__(ChromaPublisher)
        publisher.lock_directory = self.base / "chroma-lock"
        publisher._publishing = False
        publisher.collection_name = "bench_lock"
        publisher._upsert_document = lambda *args: None
        self.pipeline.publisher = publisher
        original_build = self.pipeline.layers.build

        def build(*args, **kwargs):
            with self.assertRaisesRegex(RuntimeError, "Ya hay un escritor"):
                with writer_lock(publisher.lock_directory):
                    self.fail("Otro escritor entró durante extracción")
            return original_build(*args, **kwargs)

        with patch.object(self.pipeline.layers, "build", side_effect=build):
            self.run_pipeline()
            self.run_pipeline(add=self.source)
        self.assertFalse((publisher.lock_directory / ".writer.lock").exists())

    def test_restart_from_silver_without_originals(self):
        self.run_pipeline()
        before = self.snapshot(self.root / "gold")
        self.source.unlink()
        self.raw.rmdir()
        with patch.object(layers, "read_document", side_effect=AssertionError("No raw")):
            self.run_pipeline(from_stage="silver")
        self.assertEqual(before, self.snapshot(self.root / "gold"))

    def test_export_remains_compatible_atomic_and_deterministic(self):
        self.run_pipeline()
        target = self.base / "exports/chunks.jsonl.gz"
        count = self.pipeline.export(target)
        self.assertGreater(count, 0)
        with gzip.open(target, "rt", encoding="utf-8") as stream:
            records = [json.loads(line) for line in stream]
        self.assertIn("__manifest__", records[0])
        self.assertEqual(len(records) - 1, count)
        self.assertEqual(len(records[1]["embedding"]), 768)
        before = self.snapshot(target.parent)
        self.pipeline.export(target)
        self.assertEqual(before, self.snapshot(target.parent))
        with self.assertRaises(ValueError):
            self.pipeline.export(self.raw / "export.jsonl.gz")

    def test_layers_are_reproducible_in_another_state_and_cache(self):
        self.run_pipeline()
        other_cache = self.base / "other-cache"
        other_embedder = FakeBatchEmbeddings(other_cache / "bench_embeddings.sqlite")
        self.addCleanup(other_embedder.close)
        other = Pipeline(
            self.raw,
            self.base / "other-state",
            other_cache,
            other_embedder,
            Publisher(),
            layers_root=self.base / "other-layers",
        )
        self.addCleanup(other.close)
        self.assertEqual(other.run()["errors"], [])
        first = {name: value[0] for name, value in self.snapshot(self.root).items()}
        second = {name: value[0] for name, value in self.snapshot(other.layers_root).items()}
        self.assertEqual(first, second)

    def test_fake_pipeline_guard_even_with_real_publisher_argument(self):
        publisher = Publisher()
        publisher.collection_name = "produccion"
        with self.assertRaises(ValueError):
            Pipeline(
                self.raw,
                self.base / "new-state",
                self.cache,
                self.embedder,
                publisher,
                layers_root=self.root,
            )
        self.assertFalse((self.base / "new-state").exists())

    def test_quality_deterministic_and_only_writes_quality(self):
        self.run_pipeline()
        before = self.snapshot(self.base)
        report_quality(self.root, self.pipeline.state, self.cache / "bench_embeddings.sqlite")
        self.assertEqual(before, self.snapshot(self.base))
        result = report_quality(self.root)
        for doc in result["documentos"]:
            self.assertEqual(set(doc["metricas"]), set(THRESHOLDS))
            self.assertEqual(doc["metricas"]["chunks_without_vector"]["bandera"], "no medido")
        before = self.snapshot(self.root / "quality")
        report_quality(self.root)
        self.assertEqual(before, self.snapshot(self.root / "quality"))

    def test_quality_releases_document_texts_with_and_without_comparison(self):
        (self.raw / "otro.txt").write_text(TEXT + " Otro caso.", encoding="utf-8")
        self.run_pipeline()
        v1 = self.base / "baseline"
        (v1 / "bronze").mkdir(parents=True)
        (v1 / "bronze/fallo.md").write_text(TEXT, encoding="utf-8")
        (v1 / "bronze/otro.md").write_text(TEXT, encoding="utf-8")

        class Text(str):
            pass

        class Chunks(list):
            pass

        inspect = quality.inspect_document
        for compare in (None, v1):
            with self.subTest(compare=compare):
                references = []

                def inspect_tracked(*args, references=references):
                    self.assertTrue(all(reference() is None for reference in references))
                    doc, original, cleaned, chunks = inspect(*args)
                    original, cleaned, chunks = Text(original), Text(cleaned), Chunks(chunks)
                    references.extend(weakref.ref(value) for value in (original, cleaned, chunks))
                    return doc, original, cleaned, chunks

                with patch.object(quality, "inspect_document", side_effect=inspect_tracked):
                    result = report_quality(self.root, compare=compare)
                self.assertEqual(result["resumen"]["documentos"], 2)
                self.assertTrue(all(reference() is None for reference in references))

    def test_quality_missing_layers_are_reported(self):
        self.run_pipeline()
        for stage, suffix in (("bronze", ".txt"), ("silver", ".context.json"), ("gold", ".jsonl")):
            path = next((self.root / stage).glob("*" + suffix))
            path.unlink()
        result = report_quality(self.root)
        self.assertGreater(result["documentos"][0]["metricas"]["missing_layers"]["valor"], 0)

    def test_quality_validates_cache_dimension_finiteness_and_missing(self):
        self.run_pipeline()
        cache = self.cache / "bench_embeddings.sqlite"
        with closing(sqlite3.connect(cache)) as db, db:
            keys = [row[0] for row in db.execute("SELECT key FROM vectors ORDER BY key")]
            db.execute(
                "UPDATE vectors SET vector=? WHERE key=?",
                (json.dumps([float("inf")] * 767), keys[0]),
            )
            db.execute("DELETE FROM vectors WHERE key=?", (keys[1],))
        metrics = report_quality(self.root, cache=cache)["documentos"][0]["metricas"]
        self.assertEqual(metrics["invalid_vectors"]["valor"], 1)
        self.assertEqual(metrics["chunks_without_vector"]["valor"], 1)
        self.assertEqual(metrics["embedding_dimension"]["bandera"], "rojo")

    def test_quality_compare_v1_same_documents_and_excerpts(self):
        self.run_pipeline()
        v1 = self.base / "baseline"
        (v1 / "bronze").mkdir(parents=True)
        (v1 / "gold").mkdir()
        (v1 / "bronze/fallo.md").write_text(
            "## Encabezado\n![](imagen.png)\n" + TEXT * 2, encoding="utf-8"
        )
        (v1 / "bronze/no_coincide.md").write_text("Sin pareja", encoding="utf-8")
        (v1 / "gold/fallo.jsonl").write_text(
            json.dumps({"page_content": "x"}) + "\n", encoding="utf-8"
        )
        # Un quality.json v1 deliberadamente inválido nunca debe leerse.
        (v1 / "bronze/fallo.quality.json").write_bytes(b"invalido")
        before = self.snapshot(v1)
        result = report_quality(self.root, compare=v1)
        comparison = result["comparacion_v1"]
        self.assertEqual(len(comparison["documentos"]), 1)
        self.assertTrue(comparison["peores_10"])
        self.assertEqual(comparison["documentos_retencion_menor_80_pct"], 1)
        self.assertEqual(comparison["regresiones_por_metrica"]["extracted_chars"], 1)
        self.assertEqual(comparison["regresiones_por_metrica"]["chunk_median"], 0)
        self.assertEqual(len(comparison["sin_pareja_v1"]), 1)
        markdown = (self.root / "quality/quality_report.md").read_text(encoding="utf-8")
        self.assertIn("| Métrica | v1 | v2 | documentos con regresión |", markdown)
        self.assertIn("Documentos con regresiones objetivas: 1 (menos de 10)", markdown)
        self.assertIn("### Diez documentos con más regresiones objetivas", markdown)
        self.assertIn("| v1 | v2 |", markdown)
        doc_id = comparison["peores_10"][0]
        self.assertIn(f"### {doc_id} — fallo.txt", markdown)
        self.assertIn(f"#### {doc_id} — fallo.txt", markdown)
        self.assertEqual(before, self.snapshot(v1))
        quality_before = self.snapshot(self.root / "quality")
        report_quality(self.root, compare=v1)
        self.assertEqual(quality_before, self.snapshot(self.root / "quality"))
        self.assertIn(
            "v1_extracted_chars",
            (self.root / "quality/quality_por_documento.csv").read_text(encoding="utf-8"),
        )
        self.assertTrue(report_quality(self.root, compare=v1, enforce=True)["enforce_failed"])

    def test_quality_cli_does_not_construct_services(self):
        self.run_pipeline()
        with (
            patch(
                "ingest.offline.__main__.ChromaPublisher", side_effect=AssertionError("No Chroma")
            ),
            patch(
                "ingest.offline.__main__.OllamaBatchEmbeddings",
                side_effect=AssertionError("No Ollama"),
            ),
        ):
            self.assertEqual(main(["quality", "--layers-root", str(self.root)]), 0)

    def test_enforce_only_changes_exit_gate(self):
        self.run_pipeline()
        next((self.root / "gold").glob("*.jsonl")).unlink()
        self.assertFalse(report_quality(self.root)["enforce_failed"])
        self.assertTrue(report_quality(self.root, enforce=True)["enforce_failed"])

    def test_protected_destinations_resolved_before_writes(self):
        for destination in (
            self.raw,
            self.raw / "layers",
            self.raw / "a/../layers",
            self.base / "data/documents/bronze",
            self.base / "data/documents/silver",
            self.base / "data/documents/gold",
            self.base / "data/documents",
        ):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                guard_output(destination, self.raw)
        for parameter in ("layers_root", "state", "cache"):
            arguments = {
                "root": self.raw,
                "state": self.base / "safe-state",
                "cache": self.cache,
                "embedder": self.embedder,
                "publisher": self.publisher,
                "layers_root": self.root,
                parameter: self.raw / "prohibido",
            }
            with self.subTest(parameter=parameter), self.assertRaises(ValueError):
                Pipeline(**arguments)
        self.assertFalse((self.raw / "prohibido").exists())

    def test_symlink_escape_rejected(self):
        link = self.base / "link"
        try:
            link.symlink_to(self.raw, target_is_directory=True)
        except OSError:
            self.skipTest("El sistema no permite crear enlaces simbólicos")
        with self.assertRaises(ValueError):
            guard_output(link / "layers", self.raw)
        self.run_pipeline()
        quality = self.root / "quality"
        for p in quality.iterdir():
            p.unlink()
        quality.rmdir()
        quality.symlink_to(self.base / "outside", target_is_directory=True)
        with self.assertRaises(ValueError):
            report_quality(self.root)
        self.assertFalse((self.base / "outside").exists())

    def test_single_writer_lock(self):
        with writer_lock(self.base / "locked"), self.assertRaises(RuntimeError):
            with writer_lock(self.base / "locked"):
                self.fail("Dos escritores")
        self.assertFalse((self.base / "locked/.writer.lock").exists())


class QualityComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.v1 = self.base / "baseline"
        (self.v1 / "bronze").mkdir(parents=True)
        (self.v1 / "gold").mkdir()
        self.documents, self.texts = [], {}

    def add_pair(self, doc_id, before, after, old_chunks=None, new_chunks=None):
        (self.v1 / "bronze" / f"{doc_id}.md").write_text(before, encoding="utf-8")
        (self.v1 / "gold" / f"{doc_id}.jsonl").write_text(
            "".join(
                json.dumps({"page_content": text}) + "\n"
                for text in (old_chunks if old_chunks is not None else ["a" * 250])
            ),
            encoding="utf-8",
        )
        self.documents.append({"doc_id": doc_id, "paths": [f"{doc_id}.pdf", f"alias/{doc_id}.pdf"]})
        self.texts[doc_id] = after, "", (new_chunks if new_chunks is not None else ["a" * 250])

    def comparison_layers(self):
        self.add_pair("a", "Bogotá " * 100, "Bogotá " * 70, ["a" * 250], ["b" * 300])
        self.add_pair("b", "Texto estable " * 100, "Texto estable " * 100)
        root = self.base / "layers"
        root.mkdir()
        (root / "catalog.json").write_bytes(
            layers.canonical({"documentos": {d["doc_id"]: d["paths"] for d in self.documents}})
        )
        (root / "bronze").mkdir()
        (root / "gold").mkdir()
        prefix = "Cabecera de plantilla " * 40
        for doc_id, (original, _, chunks) in self.texts.items():
            (root / "bronze" / f"{doc_id}.txt").write_text(original, encoding="utf-8")
            (root / "gold" / f"{doc_id}.jsonl").write_bytes(
                layers.jsonl(
                    {"page_content": prefix + "\n\n" + text, "metadata": {"header": prefix}}
                    for text in chunks
                )
            )
        return root

    def test_quality_bytes_match_previous_reports_and_comparison_uses_chunk_body(self):
        root = self.comparison_layers()
        # Huellas de los tres informes anteriores al procesamiento documento a documento.
        expected = {
            False: {
                "quality_por_documento.csv": "915986d02f46344922988ac2ac49bc7430e1b0bc895bca7f53b2fc4d3ab1935a",
                "quality_report.json": "49ce781ad1208429f7ca7fa927340a3ff2bd9fc12d68fa49e4628e6a07203e0a",
                "quality_report.md": "df92fdf0d99e753fa471a4d4f115ecc3343b1474d9354424868a2521c39e0621",
            },
            True: {
                "quality_por_documento.csv": "3af2d5a1d853af4433f6e2127f69faef108a27eb36194ad08206469fb0592613",
                "quality_report.json": "c5a92aa7672f563a8a88db1d22e6218f4f70c2bcbdf9e7fd876009bc340004d7",
                "quality_report.md": "8cf143d5b47c8970c3352f492ee45f7fa6d81094d7c8e69fcec3463192760adf",
            },
        }
        for compare in (None, self.v1):
            with self.subTest(compare=compare):
                result = report_quality(root, compare=compare)
                if compare is not None:
                    comparison = result["comparacion_v1"]
                    self.assertEqual(
                        comparison, compare_v1(self.v1, result["documentos"], self.texts)
                    )
                    self.assertEqual(
                        comparison["documentos"][0]["v2"]["chunk_median"]["valor"], 300
                    )
                self.assertEqual(
                    {
                        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in (root / "quality").iterdir()
                    },
                    expected[compare is not None],
                )

    def enforced_report(self, exclude=None, baseline=None):
        root = self.base / "layers"
        root.mkdir(exist_ok=True)
        doc = {
            "doc_id": "correcto",
            "paths": [],
            "metricas": {},
            "capas_ausentes_o_invalidas": [],
        }
        # Aislar la cobertura v1 de las banderas operativas del documento v2.
        with (
            patch("ingest.offline.quality._read_manifest", return_value={"correcto": []}),
            patch("ingest.offline.quality.inspect_document", return_value=(doc, "", "", [])),
        ):
            return report_quality(
                root, compare=baseline or self.v1, enforce=True, compare_exclude=exclude
            )

    def test_missing_and_empty_baseline_are_reported_and_fail_enforce(self):
        for baseline in (self.base / "inexistente", self.v1):
            with self.subTest(baseline=baseline):
                result = self.enforced_report(baseline=baseline)
                self.assertTrue(result["enforce_failed"])
                self.assertTrue(result["comparacion_v1"]["errores"])
                markdown = (self.base / "layers/quality/quality_report.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("línea base v1", markdown)
        (self.v1 / "bronze/vacio.md").write_text(" \n\t", encoding="utf-8")
        self.assertTrue(self.enforced_report()["comparacion_v1"]["errores"])

    def test_unmatched_v1_fails_enforce_unless_explicitly_excluded(self):
        (self.v1 / "bronze/solo_v1.md").write_text("Texto omitido", encoding="utf-8")
        self.assertTrue(self.enforced_report()["enforce_failed"])
        exclude = self.base / "exclude.txt"
        exclude.write_text("bronze/solo_v1.md\n", encoding="utf-8")
        result = self.enforced_report(exclude)
        self.assertFalse(result["enforce_failed"])
        self.assertEqual(result["comparacion_v1"]["sin_pareja_v1"], ["bronze/solo_v1.md"])
        self.assertEqual(result["comparacion_v1"]["sin_pareja_v1_no_excluidos"], [])
        self.assertTrue(self.enforced_report(self.base / "missing_exclusions")["enforce_failed"])

    def test_alias_ambiguity_is_reported_without_failing_coverage(self):
        self.add_pair("caso", "Texto del caso", "Texto del caso")
        (self.v1 / "bronze/alias").mkdir()
        (self.v1 / "bronze/alias/caso.md").write_text("Texto del caso", encoding="utf-8")
        result = compare_v1(self.v1, self.documents, self.texts)
        self.assertFalse(result["enforce_failed"])
        self.assertEqual(result["sin_pareja_v1"], [])
        ambiguous = result["sin_pareja_v2"][0]
        self.assertEqual(ambiguous["razon"], "coincidencia_ambigua")
        self.assertTrue(ambiguous["aliases_mismo_doc_id"])
        self.assertEqual(len(ambiguous["candidatos_v1"]), 2)
        self.documents[0]["paths"] = ["otra/caso.pdf"]
        result = compare_v1(self.v1, self.documents, self.texts)
        self.assertTrue(result["enforce_failed"])
        self.assertFalse(result["sin_pareja_v2"][0]["aliases_mismo_doc_id"])

    def test_compare_exclude_cli_is_forwarded_and_requires_baseline(self):
        with patch(
            "ingest.offline.__main__.report_quality",
            return_value={"resumen": {}, "enforce_failed": True},
        ) as report:
            self.assertEqual(
                main(
                    [
                        "quality",
                        "--compare-v1",
                        str(self.v1),
                        "--compare-exclude",
                        str(self.base / "exclude.txt"),
                        "--enforce",
                    ]
                ),
                1,
            )
            self.assertEqual(report.call_args.kwargs["compare_exclude"], self.base / "exclude.txt")
        with self.assertRaises(SystemExit) as exc:
            main(["quality", "--compare-exclude", "exclude.txt"])
        self.assertEqual(exc.exception.code, 2)

    def test_larger_fewer_chunks_are_neutral_and_fill_the_list(self):
        self.add_pair(
            "neutral",
            "Bogotá " * 100,
            "Bogotá " * 100,
            [letter * 250 for letter in "abcd"],
            [letter * 500 for letter in "ab"],
        )
        self.add_pair("unchanged", "Bogotá " * 100, "Bogotá " * 100)
        result = compare_v1(self.v1, self.documents, self.texts)
        neutral, unchanged = result["documentos"]
        self.assertEqual(neutral["bandera"], "amarillo")
        self.assertEqual(neutral["numero_regresiones"], 0)
        self.assertEqual(
            set(neutral["cambios"]), {"chunk_count", "chunk_median", "chunk_p5", "chunk_p95"}
        )
        self.assertTrue(all("cambio, no regresión" in r for r in neutral["cambios_neutrales"]))
        self.assertEqual(unchanged["bandera"], "verde")
        self.assertEqual(result["peores_10"], ["neutral"])
        self.assertEqual(result["documentos_con_regresion"], 0)
        self.assertTrue(all(n == 0 for n in result["regresiones_por_metrica"].values()))

    def test_character_retention_is_strict_and_counted_once(self):
        for size in (79, 80, 81, 150):
            self.add_pair(str(size), "a" * 100, "a" * size)
        result = compare_v1(self.v1, self.documents, self.texts)
        self.assertEqual([d["bandera"] for d in result["documentos"]], ["rojo"] + ["verde"] * 3)
        self.assertEqual(result["documentos"][0]["numero_regresiones"], 1)
        self.assertEqual(result["documentos_retencion_menor_80_pct"], 1)

    def test_increase_requires_relative_and_absolute_floors(self):
        for name in ("invalid_pct", "mojibake_pct", "short_chunks_pct"):
            for before, after, adverse in (
                (0, 0.01, False),
                (0, 0.1, True),
                (0.1, 0.15, False),
                (1, 1.2, False),
                (1, 1.21, True),
                (1, 0, False),
            ):
                with self.subTest(metric=name, before=before, after=after):
                    old = {n: {"valor": 0} for n in COMPARISON_METRICS}
                    new = {n: {"valor": 0} for n in COMPARISON_METRICS}
                    old[name]["valor"], new[name]["valor"] = before, after
                    regressions, changes = _comparison_changes(old, new)
                    self.assertEqual(name in regressions, adverse)
                    self.assertFalse(changes)
        for name in ("exact_duplicates", "near_duplicates"):
            for before, after, adverse in (
                (0, 1, False),
                (0, 2, True),
                (1, 2, False),
                (10, 12, False),
                (10, 13, True),
                (3, 0, False),
            ):
                with self.subTest(metric=name, before=before, after=after):
                    old = {n: {"valor": 0} for n in COMPARISON_METRICS}
                    new = {n: {"valor": 0} for n in COMPARISON_METRICS}
                    old[name]["valor"], new[name]["valor"] = before, after
                    regressions, _ = _comparison_changes(old, new)
                    self.assertEqual(name in regressions, adverse)

    def test_one_new_exact_duplicate_does_not_make_comparison_red(self):
        self.add_pair("duplicate", "a" * 500, "a" * 500, ["a" * 250], ["a" * 250] * 2)
        doc = compare_v1(self.v1, self.documents, self.texts)["documentos"][0]
        self.assertEqual(doc["v2"]["exact_duplicates"]["valor"], 1)
        self.assertEqual(doc["bandera"], "amarillo")
        self.assertFalse(doc["regresiones"])

    def test_both_damage_rates_are_compared_and_ranked_before_neutral(self):
        self.add_pair("both", "Bogotá " * 100, ("BogotÆ \ufffd" * 70))
        self.add_pair("one", "a" * 1000, "a" * 100)
        self.add_pair("neutral", "a" * 500, "a" * 500, ["a" * 250], ["b" * 10000])
        result = compare_v1(self.v1, self.documents, self.texts)
        self.assertEqual(result["peores_10"], ["both", "one", "neutral"])
        self.assertEqual(result["documentos"][0]["numero_regresiones"], 2)
        self.assertEqual(result["regresiones_por_metrica"]["invalid_pct"], 1)
        self.assertEqual(result["regresiones_por_metrica"]["mojibake_pct"], 1)
        self.assertEqual(result["documentos"][2]["bandera"], "amarillo")
        # Al invertir los lados, la desaparición del daño no es regresión.
        self.add_pair("improved", "BogotÆ diecisØis " * 50, "Bogotá dieciséis " * 50)
        improved = compare_v1(self.v1, self.documents, self.texts)["documentos"][-1]
        self.assertEqual(improved["bandera"], "verde")

    def test_ranking_ties_magnitude_paths_top_five_and_determinism(self):
        self.add_pair("b", "a" * 100, "a" * 60)
        self.add_pair("a", "a" * 100, "a" * 60)
        self.add_pair("first", "a" * 100, "a" * 20)
        for index in range(10):
            self.add_pair(
                f"neutral{index}", "a" * 100, "a" * 100, ["a" * 250], ["b" * (500 + index)]
            )
        root = self.base / "layers"
        root.mkdir()
        (root / "catalog.json").write_text(
            json.dumps({"documentos": {d["doc_id"]: d["paths"] for d in self.documents}}),
            encoding="utf-8",
        )
        (root / "bronze").mkdir()
        for doc_id, (original, _, _) in self.texts.items():
            (root / "bronze" / f"{doc_id}.txt").write_text(original, encoding="utf-8")
        # El informe lee los chunks gold v2, además del texto bronze.
        (root / "gold").mkdir()
        for doc_id, (_, _, chunks) in self.texts.items():
            (root / "gold" / f"{doc_id}.jsonl").write_text(
                "".join(json.dumps({"page_content": c}) + "\n" for c in chunks), encoding="utf-8"
            )
        result = report_quality(root, compare=self.v1)["comparacion_v1"]
        self.assertEqual(result["peores_10"][:5], ["first", "a", "b", "neutral9", "neutral8"])
        self.assertEqual(len(result["peores_10"]), 10)
        markdown = (root / "quality/quality_report.md").read_text(encoding="utf-8")
        self.assertEqual(markdown.count("\n| v1 | v2 |\n"), 5)
        self.assertIn("#### first — alias/first.pdf, first.pdf", markdown)
        self.assertIn("cambio, no regresión", markdown)
        before = {p.name: p.read_bytes() for p in (root / "quality").iterdir()}
        report_quality(root, compare=self.v1)
        self.assertEqual(before, {p.name: p.read_bytes() for p in (root / "quality").iterdir()})


class ObjectiveMetricsTests(unittest.TestCase):
    def test_chroma_lock_is_shared_across_cwds_and_fails_fast(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            first, second = base / "first", base / "second"
            first.mkdir()
            second.mkdir()
            collection = SimpleNamespace(metadata={"atlas_offline_config": "config"})
            chroma = SimpleNamespace(
                HttpClient=lambda **kwargs: SimpleNamespace(get_collection=lambda name: collection)
            )
            with (
                patch.dict(sys.modules, {"chromadb": chroma}),
                patch.dict("os.environ", {"ATLAS_CHROMA_LOCK_DIR": ""}),
                patch(
                    "ingest.offline.publish.tempfile.gettempdir", return_value=str(base / "locks")
                ),
            ):
                with chdir(first):
                    publisher = ChromaPublisher("bench_lock", "config")
                with publisher.publish_phase(), chdir(second):
                    self.assertEqual(publisher.lock_directory, chroma_lock_directory("bench_lock"))
                    self.assertTrue(publisher.lock_directory.is_absolute())
                    with self.assertRaisesRegex(RuntimeError, "Ya hay un escritor"):
                        ChromaPublisher("bench_lock", "config")
                with chdir(second):
                    other = ChromaPublisher("bench_lock", "config")
                self.assertEqual(publisher.lock_directory, other.lock_directory)
                self.assertNotEqual(other.lock_directory, chroma_lock_directory("bench_other"))
                self.assertNotEqual(other.lock_directory, chroma_lock_directory("bench_lock", 8001))
            with (
                patch.dict("os.environ", {"ATLAS_CHROMA_LOCK_DIR": "relative"}),
                self.assertRaises(ValueError),
            ):
                chroma_lock_directory("bench_lock")

    def test_ocr_tsv_confidence_and_cache(self):
        output = (
            b"level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tconf\ttext\n"
            b"5\t1\t1\t1\t1\t1\t90\tLas\n"
            b"5\t1\t1\t1\t1\t2\t50\tplayas\n"
            b"5\t1\t1\t1\t2\t1\t-1\t\n"
        )
        page = SimpleNamespace(
            get_pixmap=lambda **kwargs: SimpleNamespace(tobytes=lambda kind: b"png")
        )
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(sys.modules, {"fitz": SimpleNamespace(Matrix=lambda *args: None)}),
            patch(
                "ingest.offline.extract.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=output),
            ) as run,
        ):
            text, created, confidence = _ocr(page, Path(temporary), "page")
            self.assertEqual((text, created, confidence), ("Las playas", True, 70.0))
            self.assertEqual(_ocr(page, Path(temporary), "page"), ("Las playas", False, 70.0))
            self.assertEqual(run.call_count, 1)

    def test_extraction_metrics_are_objective_and_thresholded(self):
        result = extraction_metrics(
            {
                "raw_pages": ["corto", "a" * 100],
                "original": "corto\n\f\n" + "a" * 100,
                "ocr_pages": [1],
                "ocr_confidence": {"1": 70.0},
                "ocr_failed_pages": [2],
            }
        )
        self.assertEqual(result["pages"]["valor"], 2)
        self.assertEqual(result["near_empty_pct"]["valor"], 50)
        self.assertEqual(result["ocr_pct"]["valor"], 50)
        self.assertEqual(result["ocr_confidence"]["valor"], 70)
        self.assertEqual(result["extraction_errors"]["bandera"], "rojo")

    def test_mojibake_controls_and_accents(self):
        correct = "Bogotá, Niño, acción, público\n\t\f"
        self.assertEqual(invalid_pct(correct), 0)
        self.assertEqual(mojibake_pct(correct), 0)
        self.assertEqual(invalid_pct("\ufffd\x00\x1f\x7f\x80\x9f\r\n\t\f"), 70)
        self.assertEqual(invalid_pct("BogotÆ diecisØis"), 0)
        self.assertAlmostEqual(mojibake_pct("BogotÆ diecisØis"), 200 / len("BogotÆ diecisØis"))
        for damaged in ("BogotÆ", "diecisØis", "pœblico", "aæ", "aø", "aŒ", "ał", "aˇ"):
            with self.subTest(text=damaged):
                self.assertGreater(mojibake_pct(damaged), 0)
        self.assertEqual(mojibake_pct("Æ æ Ø ø œ Œ ł ˇ 1Æ Æ1 ЖÆ"), 0)
        for damaged in ("Ã©", "Ã±", "Ã³", "Ãa", "ÃZ", "â€™", "Â ", "Â\x80", "ï¿½"):
            with self.subTest(text=damaged):
                self.assertEqual(mojibake_pct(damaged), 100)
        self.assertEqual(mojibake_pct("Ârbol"), 0)
        # El control de una secuencia puede aparecer en ambas tasas sin ocultarlas.
        self.assertEqual(invalid_pct("Ã\x80"), 50)
        self.assertEqual(mojibake_pct("Ã\x80"), 100)
        values = text_metrics("BogotÆ diecisØis", "BogotÆ diecisØis", [])
        self.assertEqual(values["invalid_pct"]["bandera"], "verde")
        self.assertEqual(values["mojibake_pct"]["bandera"], "rojo")
        self.assertEqual(metric("mojibake_pct", 0.2)["bandera"], "verde")
        self.assertEqual(metric("mojibake_pct", 1)["bandera"], "amarillo")

    def test_comparison_body_excludes_template_header(self):
        record = {"page_content": "Cabecera\n\nCuerpo", "metadata": {"header": "Cabecera"}}
        self.assertEqual("Cuerpo", chunk_body(record))
        # Sin cabecera registrada, o si no es prefijo, el texto queda intacto.
        self.assertEqual("Cuerpo", chunk_body({"page_content": "Cuerpo", "metadata": {}}))
        other = {"page_content": "Otro texto", "metadata": {"header": "Cabecera"}}
        self.assertEqual("Otro texto", chunk_body(other))

    def test_fake_embedder_is_deterministic_and_digest_separated(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "cache.sqlite"
            first = FakeBatchEmbeddings(path)
            vector = first.embed(["playas"])[0]
            self.assertEqual(len(vector), 768)
            self.assertTrue(all(math.isfinite(x) for x in vector))
            first.close()
            second = FakeBatchEmbeddings(path)
            self.assertEqual(second.embed(["playas"])[0], vector)
            self.assertEqual(second.new_embeddings, 0)
            second.close()

    def test_fake_publish_guard_before_connection(self):
        with self.assertRaises(ValueError):
            ChromaPublisher("produccion", "config", fake_embeddings=True)

    def test_atomic_writer_preserves_mtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact.txt"
            atomic_bytes(path, b"contenido")
            before = path.stat().st_mtime_ns
            atomic_bytes(path, b"contenido")
            self.assertEqual(before, path.stat().st_mtime_ns)


if __name__ == "__main__":
    unittest.main()
