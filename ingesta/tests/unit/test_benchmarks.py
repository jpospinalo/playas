"""Contratos rápidos del harness; no requieren servicios, OCR ni acceso a red."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import math
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from benchmarks.common import inside, output_dir, parse_time_verbose
from benchmarks.cost import cost_per_1000
from benchmarks.report import extrapolate, extrapolate_embeddings, render_report
from benchmarks.run_pipeline import embedding_counts, latest_run
from benchmarks.run_pipeline import main as pipeline_main
from benchmarks.simhash_scaling import fit_exponent, near_duplicates
from benchmarks.synth_corpus import build_corpus
from ingest.offline.extract import clean_pages, read_document


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "PyMuPDF no está instalado")
    def test_synthetic_hashes_salt_every_page_and_metadata(self):
        import fitz

        src = self.base / "source"
        src.mkdir()
        for filename in ("b.pdf", "a.pdf"):
            with fitz.open() as pdf:
                for _ in range(3):
                    pdf.new_page()
                pdf.save(src / filename)
        (src / "metadata.csv").write_text("archivo;fecha\na.pdf;2024\n", encoding="utf-8")
        originals = {p.name: p.read_bytes() for p in src.iterdir()}
        out = self.base / "synth"
        with redirect_stdout(io.StringIO()):
            manifest = build_corpus(src, 5, out, seed=17)
            repeated = build_corpus(src, 5, self.base / "repeated", seed=17)
        copies = manifest["copies"]
        self.assertEqual(
            [c["source"] for c in copies], ["a.pdf", "b.pdf", "a.pdf", "b.pdf", "a.pdf"]
        )
        self.assertEqual(len({c["sha256"] for c in copies}), 5)
        self.assertEqual([c["salt"] for c in copies], [c["salt"] for c in repeated["copies"]])
        for copy in copies:
            path = out / copy["file"]
            self.assertEqual(copy["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
            with fitz.open(path) as pdf:
                self.assertEqual(len(pdf), 3)
                for page in pdf:
                    text = page.get_text()
                    self.assertIn(copy["salt"], text)
                    self.assertLess(len("".join(text.split())), 80)
        self.assertEqual((out / "raw/metadata.csv").read_bytes(), originals["metadata.csv"])
        self.assertEqual(originals, {p.name: p.read_bytes() for p in src.iterdir()})
        self.assertTrue((out / "synth_corpus.json").exists())

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "PyMuPDF no está instalado")
    def test_synthetic_body_salt_survives_real_extraction_and_cleaning(self):
        import fitz

        src = self.base / "source"
        src.mkdir()
        with fitz.open() as pdf:
            for _ in range(4):
                page = pdf.new_page()
                page.insert_text((50, 40), "Cabecera repetida\nEncabezado repetido")
                page.insert_text(
                    (50, 150), "ANTECEDENTES\n" + "Las playas son de uso publico.\n" * 8
                )
                page.insert_text((50, 750), "Pie repetido\nReferencia repetida")
            pdf.save(src / "caso.pdf")
        out = self.base / "synth"
        with redirect_stdout(io.StringIO()):
            manifest = build_corpus(src, 2, out, seed=17)
        cleaned_copies = []
        for copy in manifest["copies"]:
            document = read_document(out / copy["file"], self.base / "cache")
            self.assertEqual(document["ocr_pages"], [])
            cleaned = clean_pages(document["raw_pages"])
            self.assertTrue(cleaned["removed_furniture_keys"])
            self.assertNotIn("Cabecera repetida", cleaned["text"])
            self.assertEqual(len(set(copy["page_salts"])), 4)
            for raw, span, salt in zip(
                document["raw_pages"], cleaned["pages"], copy["page_salts"], strict=True
            ):
                lines = raw.splitlines()
                self.assertTrue(any(salt in line for line in lines[2:-2]))
                self.assertIn(salt, cleaned["text"][span["clean_start"] : span["clean_end"]])
            cleaned_copies.append(cleaned["text"])
        self.assertNotEqual(*cleaned_copies)

    def test_extrapolate_linear_fit_and_status(self):
        rows = [{"documents": n, "wall_seconds": 5 + 2 * n} for n in (10, 20, 40)]
        prediction = extrapolate(rows, 100)
        self.assertAlmostEqual(prediction["wall_seconds"], 205)
        self.assertAlmostEqual(prediction["slope_seconds_per_doc"], 2)
        self.assertTrue(prediction["extrapolated"])
        self.assertEqual(prediction["status"], "EXTRAPOLADA")
        embedding = extrapolate_embeddings(300, 1.25)
        self.assertEqual(embedding["embedding_seconds"], 240)
        self.assertEqual(embedding["status"], "EXTRAPOLADA")

    def test_extrapolate_rejects_underdetermined_or_decreasing_fit(self):
        for rows in (
            [{"documents": 10, "wall_seconds": 5}],
            [{"documents": 10, "wall_seconds": 5}] * 2,
            [{"documents": 10, "wall_seconds": 20}, {"documents": 20, "wall_seconds": 10}],
        ):
            with self.assertRaises(ValueError):
                extrapolate(rows, 100)

    def test_cost_math_and_invalid_values(self):
        self.assertEqual(cost_per_1000(200, 0.1), 0.5)
        self.assertEqual(cost_per_1000(200, 0), 0)
        for docs, price in ((0, 1), (-1, 1), (math.inf, 1), (100, -1), (100, math.nan)):
            with self.assertRaises(ValueError):
                cost_per_1000(docs, price)

    def test_exponent_quadratic_linear(self):
        counts = [10, 100, 1000, 10000]
        self.assertAlmostEqual(fit_exponent(counts, [n * n * 0.001 for n in counts]), 2)
        self.assertAlmostEqual(fit_exponent(counts, [n * 0.001 for n in counts]), 1)
        with self.assertRaises(ValueError):
            fit_exponent([1, 1], [1, 2])
        with self.assertRaises(ValueError):
            fit_exponent([1, 2], [0, 1])

    def test_near_duplicate_loop_ignores_exact_text_and_deduplicates_bands(self):
        docs = [
            {"doc_id": "a", "text_hash": "x", "fingerprint": 0},
            {"doc_id": "b", "text_hash": "y", "fingerprint": 1},
            {"doc_id": "c", "text_hash": "x", "fingerprint": 0},
        ]
        self.assertEqual(
            near_duplicates(docs),
            [
                {"documents": ("a", "b"), "hamming_distance": 1},
                {"documents": ("b", "c"), "hamming_distance": 1},
            ],
        )

    def test_output_rejects_escape_overlap_and_protected_paths(self):
        out = output_dir(self.base / "out")
        with self.assertRaises(ValueError):
            inside(out, "../escape")
        with self.assertRaises(ValueError):
            output_dir(out / "nested", [out])
        with self.assertRaises(ValueError):
            output_dir(self.base / "data/documents/new")
        self.assertFalse((self.base / "data").exists())

    def test_gnu_time_units_and_cpu(self):
        result = parse_time_verbose(
            "\tUser time (seconds): 1.25\n\tSystem time (seconds): 0.25\n"
            "\tPercent of CPU this job got: 150%\n"
            "\tMaximum resident set size (kbytes): 1024\n"
        )
        self.assertEqual(result["cpu_seconds"], 1.5)
        self.assertEqual(result["cpu_percent"], 150)
        self.assertEqual(result["max_rss_bytes"], 1024 * 1024)

    def test_cache_hits_separate_pending_duplicates_and_skipped_documents(self):
        gold = self.base / "gold"
        gold.mkdir()
        for name, keys in (("a", ["cached", "new", "new"]), ("b", ["new", "next"])):
            (gold / f"{name}.jsonl").write_text(
                "".join(json.dumps({"metadata": {"embedding_cache_key": k}}) + "\n" for k in keys),
                encoding="utf-8",
            )
        report = {
            "documents_detail": [{"doc_id": "a"}, {"doc_id": "b"}],
            "new_embeddings": 2,
            "skipped": 99,
        }
        counts = embedding_counts(report, self.base, {"cached"})
        self.assertEqual(counts["chunks_embedded_or_reused"], 5)
        self.assertEqual(counts["embedding_cache_hits"], 2)
        self.assertEqual(counts["embedding_pending_duplicates"], 1)
        self.assertTrue(counts["cache_count_consistent"])
        self.assertEqual(counts["embedding_cache_hit_rate"], 0.5)

    def test_latest_run_does_not_return_stale_report(self):
        import sqlite3

        with closing(sqlite3.connect(self.base / "manifest.sqlite")) as db:
            db.execute("CREATE TABLE runs (id INTEGER PRIMARY KEY, report TEXT)")
            db.execute("INSERT INTO runs VALUES (1, ?)", ('{"documents": 3}',))
            db.commit()
        self.assertEqual(latest_run(self.base)["documents"], 3)
        self.assertIsNone(latest_run(self.base, after=1))

    def test_pipeline_rejects_non_benchmark_collection_before_subprocess(self):
        source = self.base / "source"
        source.mkdir()
        with patch("benchmarks.run_pipeline.measured_process") as measured:
            with self.assertRaises(ValueError):
                pipeline_main(
                    [
                        "--input",
                        str(source),
                        "--out",
                        str(self.base / "out"),
                        "--collection",
                        "real",
                    ]
                )
            measured.assert_not_called()

    def test_pipeline_repeat_and_add_use_isolated_copy_and_one_call_per_file(self):
        import sqlite3

        source, extra, out = (self.base / name for name in ("source", "extra", "out"))
        source.mkdir()
        extra.mkdir()
        (source / "base.txt").write_text("original", encoding="utf-8")
        for index in range(2):
            (extra / f"extra_{index}.txt").write_text(f"nuevo {index}", encoding="utf-8")
        commands = []

        def measured(command, destination, label, env):
            self.assertEqual(destination, out)
            self.assertEqual(env["PYTHONDONTWRITEBYTECODE"], "1")
            self.assertTrue(Path(env["TMPDIR"]).is_relative_to(out))
            commands.append(command)
            state = Path(command[command.index("--state") + 1])
            state.mkdir(exist_ok=True)
            report = {
                "documents": 1 + max(0, len(commands) - 2),
                "processed": 0 if label == "repeat_sync" else 1,
                "new_embeddings": 0,
                "documents_detail": [],
                "stage_timings": {"extraction": {"seconds": 0.1, "calls": 1}},
            }
            with closing(sqlite3.connect(state / "manifest.sqlite")) as db:
                db.execute("CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, report TEXT)")
                db.execute("INSERT INTO runs(report) VALUES (?)", (json.dumps(report),))
                db.commit()
            return {"wall_seconds": 1.0, "returncode": 0, "cpu_seconds": 0.1}

        with (
            patch("benchmarks.run_pipeline.measured_process", side_effect=measured),
            redirect_stdout(io.StringIO()),
        ):
            status = pipeline_main(
                [
                    "--input",
                    str(source),
                    "--extra-dir",
                    str(extra),
                    "--out",
                    str(out),
                    "--collection",
                    "bench_test",
                    "--fake-embeddings",
                    "--from-stage",
                    "bronze",
                    "--repeat-sync",
                    "--add-new",
                    "2",
                ]
            )
        self.assertEqual(status, 0)
        self.assertEqual(len(commands), 4)
        self.assertEqual([c[-1] for c in commands[:2]], ["sync", "sync"])
        self.assertIn("--from-stage", commands[0])
        self.assertNotIn("--from-stage", commands[1])
        for command in commands:
            self.assertEqual(Path(command[command.index("--input-dir") + 1]), out / "input")
        for command in commands[2:]:
            self.assertEqual(command[-2], "add")
            self.assertTrue(Path(command[-1]).is_relative_to(out / "input"))
        self.assertEqual([p.name for p in source.iterdir()], ["base.txt"])
        self.assertEqual(len(list((out / "input/bench_added").iterdir())), 2)
        result = json.loads((out / "run_pipeline.json").read_text(encoding="utf-8"))
        self.assertEqual(
            [r["label"] for r in result["runs"]], ["sync", "repeat_sync", "add_1", "add_2"]
        )
        self.assertTrue(all(r["embeddings_per_second"] is None for r in result["runs"]))

    def test_add_requires_new_bytes(self):
        source, extra = self.base / "source", self.base / "extra"
        source.mkdir()
        extra.mkdir()
        (source / "a.txt").write_text("mismos bytes", encoding="utf-8")
        (extra / "b.txt").write_text("mismos bytes", encoding="utf-8")
        with patch("benchmarks.run_pipeline.measured_process") as measured:
            with self.assertRaisesRegex(ValueError, "bytes nuevos"):
                pipeline_main(
                    [
                        "--input",
                        str(source),
                        "--extra-dir",
                        str(extra),
                        "--out",
                        str(self.base / "out"),
                        "--collection",
                        "bench_test",
                        "--add-new",
                        "1",
                    ]
                )
            measured.assert_not_called()

    def test_report_marks_projections_and_keeps_fake_separate(self):
        results = []
        for fake in (False, True):
            for size in (10, 20):
                results.append(
                    (
                        f"{fake}_{size}.json",
                        {
                            "benchmark": "run_pipeline",
                            "fake_embeddings": fake,
                            "runs": [
                                {
                                    "label": "sync",
                                    "success": True,
                                    "resources": {"wall_seconds": size * (1 if fake else 10)},
                                    "pipeline": {"documents": size, "processed": size},
                                    "embedding_cache_hit_rate": 0,
                                    "stage_timings": {
                                        "extraction": {"seconds": 1, "calls": size},
                                        "embeddings": {"seconds": size, "calls": size},
                                    },
                                }
                            ],
                        },
                    )
                )
        results.append(
            (
                "embed.json",
                {
                    "benchmark": "embed_throughput",
                    "embeddings": 300,
                    "batch": 16,
                    "num_thread": 2,
                    "wall_seconds": 240,
                    "embeddings_per_second": 1.25,
                    "chars_per_second": 1250,
                },
            )
        )
        markdown = render_report(results, [100], chunks_per_doc=3)
        self.assertEqual(markdown.count("**EXTRAPOLADA**"), 3)
        self.assertIn("900.0000", markdown)
        self.assertIn("100.0000", markdown)
        self.assertIn("240.0000", markdown)
        self.assertIn("extraction", markdown)
        self.assertIn("NO medidos", markdown)

    def test_report_excludes_cache_hits_and_projects_only_unique_throughput(self):
        results = []
        for size, hit_rate in ((10, 0), (20, 0.05), (30, 0.051), (40, 0.8)):
            results.append(
                (
                    f"run_{size}.json",
                    {
                        "benchmark": "run_pipeline",
                        "fake_embeddings": False,
                        "preexisting_state": False,
                        "preexisting_cache": False,
                        "preexisting_layers": False,
                        "runs": [
                            {
                                "label": "sync",
                                "success": True,
                                "resources": {"wall_seconds": size * 100},
                                "pipeline": {"documents": size, "processed": size},
                                "stage_timings": {
                                    "embeddings": {"seconds": size * 90, "calls": size}
                                },
                                "embedding_cache_hit_rate": hit_rate,
                                "embeddings_per_second": 99999,
                            }
                        ],
                    },
                )
            )
        markdown = render_report(results, [100], chunks_per_doc=3)
        projection = markdown.split("## Proyecciones lineales")[1].split("## Interpretación")[0]
        self.assertIn("run_10.json, run_20.json", projection)
        self.assertNotIn("run_30.json", projection)
        self.assertNotIn("run_40.json", projection)
        self.assertIn("1000.0000", projection)
        self.assertNotIn("Proyecciones de embeddings nuevos", markdown)
        self.assertIn("0.0510 | excluido: hits >5%", markdown)
        self.assertIn("0.8000 | excluido: hits >5%", markdown)
        results.append(
            (
                "unique.json",
                {
                    "benchmark": "embed_throughput",
                    "embeddings": 100,
                    "batch": 10,
                    "num_thread": 1,
                    "wall_seconds": 50,
                    "embeddings_per_second": 2,
                    "chars_per_second": 1000,
                },
            )
        )
        projected = render_report(results, [100], chunks_per_doc=3).split(
            "## Proyecciones de embeddings nuevos"
        )[1]
        self.assertIn("**EXTRAPOLADA** | 100 | 300 | 150.0000 | 2 | unique.json", projected)

    def test_report_fake_embedding_times_and_rate_are_not_measured(self):
        results = [
            (
                "fake.json",
                {
                    "benchmark": "run_pipeline",
                    "fake_embeddings": True,
                    "runs": [
                        {
                            "label": "sync",
                            "success": True,
                            "resources": {"wall_seconds": 1},
                            "pipeline": {"documents": 1, "processed": 1},
                            "embeddings_per_second": 98765,
                            "stage_timings": {"embeddings": {"seconds": 12345, "calls": 1}},
                        }
                    ],
                },
            )
        ]
        markdown = render_report(results)
        self.assertIn("ficticios: NO medido", markdown)
        self.assertIn("embeddings | NO medido |", markdown)
        self.assertNotIn("98765", markdown)
        self.assertNotIn("12345", markdown)


if __name__ == "__main__":
    unittest.main()
