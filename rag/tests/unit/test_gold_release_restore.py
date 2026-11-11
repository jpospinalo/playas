"""Standalone offline contracts: stdlib, tiny records, no SDK/product/service.

Run this file directly with unittest after the implementation is reviewed.
The historical generic importer's separate contract is intentionally preserved.
"""

from __future__ import annotations

import base64
import copy
import http.client
import importlib.util
import io
import json
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from email.message import Message
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
SCRIPT = Path(__file__).resolve().parents[3] / "data/restore_gold_release.py"
NEW_ID = "11111111-1111-4111-8111-111111111111"
OLD_ID = "22222222-2222-4222-8222-222222222222"
DIGEST = "85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1"


def load_script():
    before = set(sys.modules)
    with (
        mock.patch.object(socket, "create_connection", side_effect=AssertionError("network")),
        mock.patch.object(
            http.client.HTTPConnection, "connect", side_effect=AssertionError("HTTP")
        ),
        mock.patch.object(subprocess, "Popen", side_effect=AssertionError("process")),
    ):
        spec = importlib.util.spec_from_file_location("_gold_restore_contract", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    forbidden = ("rag", "chromadb", "langchain", "langchain_core", "langchain_openai")
    added = set(sys.modules) - before
    if any(
        name == prefix or name.startswith(prefix + ".") for name in added for prefix in forbidden
    ):
        raise AssertionError("Restorer imported a product/SDK dependency")
    return module


def records():
    return [
        {
            "id": f"synthetic-{i}",
            "document": f"Cuerpo sintético {i} — á",
            "metadata": {
                "chunk_id": f"synthetic-{i}",
                "doc_type": "normativa" if i % 2 else "jurisprudencia",
                "typed_number": 1,
                "flag": True,
                "fraction": 1.0,
            },
            "embedding": [0.25 + i / 100, -0.125] + [0.0] * 766,
        }
        for i in range(5)
    ]


class FakeChroma:
    """Only documented REST calls exist; add has server-side state and failures."""

    def __init__(self, module, rows, *, existing=False, alter=None, fail_add=None, auth=False):
        self.m, self.original = module, copy.deepcopy(rows)
        self.rows = {r["id"]: self.wire_row(r) for r in rows} if existing else {}
        self.exists, self.alter, self.fail_add, self.auth = existing, alter, fail_add, auth
        self.calls, self.mutations, self.adds = [], [], []
        self.before_mutation = None

    def wire_row(self, row):
        result = copy.deepcopy(row)
        result["embedding"] = list(struct.unpack("<768f", self.m.f32_bytes(row["embedding"])))
        return result

    def descriptor(self):
        hnsw = copy.deepcopy(self.m.HNSW)
        if self.alter == "config":
            hnsw["space"] = "l2"
        return {
            "id": NEW_ID,
            "name": self.m.COLLECTION_NAME,
            "tenant": "default_tenant",
            "database": "default_database",
            "dimension": 768 if self.rows else None,
            "configuration_json": {"hnsw": hnsw, "embedding_function": None},
            "metadata": {"hnsw:space": "cosine"},
        }

    def request(self, method, path, payload=None, missing=False):
        self.calls.append((method, path, copy.deepcopy(payload), missing))
        route = urlsplit(path).path
        if self.auth:
            raise self.m.Stop("synthetic authentication failure")
        if method == "GET" and route == "/api/v2/heartbeat":
            return {"heartbeat": 1}
        if method == "GET" and route == "/api/v2/version":
            return "1.0.0"
        if method == "GET" and route == "/api/v2/pre-flight-checks":
            return {"max_batch_size": 2, "supports_base64_encoding": True}
        if method == "GET" and route == self.m.COLS:
            return [{"id": OLD_ID, "name": "rag_playas"}] + (
                [self.descriptor()] if self.exists else []
            )
        if method == "GET" and route == self.m.COLS + "/" + self.m.COLLECTION_NAME:
            if self.exists:
                return self.descriptor()
            if missing:
                return None
            raise self.m.Stop("synthetic not found")
        if method == "GET" and route == self.m.COLS + "/" + NEW_ID + "/count":
            return len(self.rows) + (1 if self.alter == "count" else 0)
        if method == "GET" and route == self.m.COLS + "/" + OLD_ID + "/count":
            return 7
        if method == "POST" and route == self.m.COLS:
            if self.before_mutation:
                self.before_mutation("CREATE_INTENT", payload)
            assert not self.exists and payload["name"] == self.m.COLLECTION_NAME
            assert payload.get("get_or_create") is False
            self.mutations.append((method, path, copy.deepcopy(payload)))
            self.exists = True
            return self.descriptor()
        if method == "POST" and route == self.m.COLS + "/" + NEW_ID + "/add":
            if self.before_mutation:
                self.before_mutation("ADD_INTENT", payload)
            self.mutations.append((method, path, copy.deepcopy(payload)))
            self.adds.append(copy.deepcopy(payload))
            assert set(payload) == {"ids", "documents", "metadatas", "embeddings"}
            assert len(payload["ids"]) <= 2
            for ident, body, meta, embedding in zip(
                payload["ids"],
                payload["documents"],
                payload["metadatas"],
                payload["embeddings"],
                strict=True,
            ):
                assert ident not in self.rows and isinstance(embedding, str)
                vector = list(struct.unpack("<768f", base64.b64decode(embedding, validate=True)))
                self.rows[ident] = {
                    "id": ident,
                    "document": body,
                    "metadata": copy.deepcopy(meta),
                    "embedding": vector,
                }
            if len(self.adds) == self.fail_add:
                raise self.m.Stop("synthetic accepted batch, lost response; no retry")
            return {}
        if method == "POST" and route == self.m.COLS + "/" + NEW_ID + "/get":
            chosen = [copy.deepcopy(self.rows[i]) for i in reversed(payload["ids"])]
            for row in chosen:
                row["embedding"] = self.m.read_representation(row["embedding"])
                if self.alter == "body":
                    row["document"] += " altered"
                if self.alter == "metadata":
                    row["metadata"]["typed_number"] = True
                if self.alter == "vector":
                    row["embedding"][0] += 0.125
                if self.alter == "dimension":
                    row["embedding"].pop()
            if self.alter == "id" and chosen:
                chosen[0]["id"] = "unexpected"
            return {
                "ids": [r["id"] for r in chosen],
                "documents": [r["document"] for r in chosen],
                "metadatas": [r["metadata"] for r in chosen],
                "embeddings": [r["embedding"] for r in chosen],
            }
        raise AssertionError(f"Unexpected operation: {method} {path}")


class FakeOllama:
    def __init__(self, *, version="0.40.13", digest=DIGEST, dimension=768, context=2048):
        self.version, self.digest, self.dimension, self.context = (
            version,
            digest,
            dimension,
            context,
        )
        self.calls = []

    def request(self, method, path, payload=None, missing=False):
        self.calls.append((method, path, copy.deepcopy(payload)))
        if (method, path) == ("GET", "/api/version"):
            return {"version": self.version}
        if (method, path) == ("GET", "/api/tags"):
            return {
                "models": [
                    {
                        "name": "embeddinggemma:latest",
                        "model": "embeddinggemma:latest",
                        "digest": self.digest,
                    }
                ]
            }
        if (method, path) == ("POST", "/api/show"):
            return {
                "model_info": {
                    "gemma3.embedding_length": self.dimension,
                    "gemma3.context_length": self.context,
                }
            }
        raise AssertionError(f"Model inference or unexpected endpoint: {method} {path}")


class GoldReleaseContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = load_script()
        cls.production_batch_size = cls.m.BATCH_SIZE

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="gold-restore-contract-")
        self.addCleanup(self.tmp.cleanup)
        self.root, self.source = Path(self.tmp.name), records()
        patcher = mock.patch.object(self.m, "BATCH_SIZE", 2)
        patcher.start()
        self.addCleanup(patcher.stop)

    def journal(self, name="receipt.jsonl"):
        journal = self.m.Journal(self.root / name)
        self.addCleanup(journal.close)
        return journal

    def invoke(self, args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            try:
                return self.m.main(args)
            except SystemExit as exc:
                return exc.code

    def test_default_release_is_current_and_check_is_offline(self):
        self.assertEqual(self.m.DEFAULT_PACKAGE.name, "gold-a-cc7bf44b54a9")
        self.assertEqual(self.m.COLLECTION_NAME, "rag_playas_gold_a_cc7bf44b54a9")
        self.assertEqual(self.production_batch_size, 25)
        with (
            mock.patch.object(self.m, "load_package", return_value=({}, self.source)),
            mock.patch.object(self.m, "HTTP", side_effect=AssertionError("offline HTTP")),
        ):
            self.assertEqual(self.invoke(["--check"]), 0)

    def test_untrusted_package_fails_without_any_http_client(self):
        invalid = self.root / "incomplete"
        invalid.mkdir()
        (invalid / "manifest.json").write_text("{}", encoding="utf-8")
        with mock.patch.object(
            self.m, "HTTP", side_effect=AssertionError("HTTP before validation")
        ):
            with self.assertRaises((self.m.Stop, OSError, KeyError)):
                self.m.load_package(invalid)

    def test_new_collection_exact_batches_and_durable_intents(self):
        original = copy.deepcopy(self.source)
        fake, journal, events = FakeChroma(self.m, self.source), self.journal(), []
        real_note = journal.note

        def note(kind, data):
            real_note(kind, data)
            events.append(kind)

        def before_mutation(kind, payload):
            self.assertTrue(events)
            self.assertEqual(events[-1], kind)

        fake.before_mutation = before_mutation
        with mock.patch.object(journal, "note", side_effect=note):
            result = self.m.restore(fake, self.source, journal)
        self.assertEqual(result["status"], "NEW_VERIFIED")
        self.assertEqual(result["records"], 5)
        self.assertEqual([len(p["ids"]) for p in fake.adds], [2, 2, 1])
        sent = [
            item
            for batch in fake.adds
            for item in zip(
                batch["ids"],
                batch["documents"],
                batch["metadatas"],
                batch["embeddings"],
                strict=True,
            )
        ]
        for row, (ident, body, meta, wire) in zip(self.source, sent, strict=True):
            self.assertEqual((ident, body), (row["id"], row["document"]))
            self.assertEqual(
                json.dumps(meta, sort_keys=True), json.dumps(row["metadata"], sort_keys=True)
            )
            self.assertEqual(
                base64.b64decode(wire, validate=True), self.m.f32_bytes(row["embedding"])
            )
        self.assertEqual(self.source, original)
        self.assertEqual(events.count("CREATE_INTENT"), 1)
        self.assertEqual(events.count("ADD_INTENT"), 3)
        self.assertFalse(any(OLD_ID in path or "/upsert" in path for _, path, _ in fake.mutations))

    def test_existing_exact_target_is_only_verified(self):
        for verify_only in (False, True):
            with self.subTest(verify_only=verify_only):
                fake = FakeChroma(self.m, self.source, existing=True)
                result = self.m.restore(
                    fake,
                    self.source,
                    self.journal(str(verify_only) + ".jsonl"),
                    verify_only=verify_only,
                )
                self.assertEqual(result["status"], "REUSED_VERIFIED")
                self.assertEqual(fake.mutations, [])

    def test_missing_verify_only_and_auth_failure_never_create(self):
        for name, fake, verify_only in [
            ("missing", FakeChroma(self.m, self.source), True),
            ("auth", FakeChroma(self.m, self.source, auth=True), False),
        ]:
            with self.subTest(name=name):
                with self.assertRaises(self.m.Stop):
                    self.m.restore(fake, self.source, self.journal(name), verify_only=verify_only)
                self.assertEqual(fake.mutations, [])

    def test_existing_mismatch_never_repairs_or_overwrites(self):
        for alter in ("body", "metadata", "vector", "dimension", "id", "count", "config"):
            with self.subTest(alter=alter):
                fake = FakeChroma(self.m, self.source, existing=True, alter=alter)
                with self.assertRaises(self.m.Stop):
                    self.m.restore(fake, self.source, self.journal(alter))
                self.assertEqual(fake.mutations, [])

    def test_new_uuid_cannot_alias_a_preexisting_collection(self):
        fake = FakeChroma(self.m, self.source)
        request = fake.request

        def alias(method, path, payload=None, missing=False):
            response = request(method, path, payload, missing)
            if method == "POST" and path == self.m.COLS:
                response["id"] = OLD_ID
            return response

        fake.request = alias
        with self.assertRaises(self.m.Stop):
            self.m.restore(fake, self.source, self.journal())
        self.assertEqual(fake.adds, [])

    def test_invalid_last_vector_is_rejected_before_any_http(self):
        self.source[-1]["embedding"][0] = True
        fake = FakeChroma(self.m, self.source)
        with self.assertRaises(self.m.Stop):
            self.m.restore(fake, self.source, self.journal())
        self.assertEqual(fake.calls, [])

    def test_accepted_batch_with_lost_response_stops_without_retry(self):
        fake = FakeChroma(self.m, self.source, fail_add=2)
        journal = self.journal()
        with self.assertRaises(self.m.Stop):
            self.m.restore(fake, self.source, journal)
        self.assertEqual([len(p["ids"]) for p in fake.adds], [2, 2])
        self.assertEqual(len(fake.rows), 4)  # Timeout is not proof that nothing was accepted.
        self.assertTrue(journal.pending)
        self.assertEqual(sum(path == self.m.COLS for method, path, _ in fake.mutations), 1)
        mutations = len(fake.mutations)
        with self.assertRaises(self.m.Stop):
            self.m.restore(fake, self.source, self.journal("later.jsonl"))
        self.assertEqual(
            len(fake.mutations), mutations
        )  # Existing partial target cannot auto-resume.

    def test_intent_fsync_failure_prevents_remote_mutation(self):
        fake, journal = FakeChroma(self.m, self.source), self.journal()
        with mock.patch.object(
            self.m.os, "fsync", side_effect=OSError("synthetic durable write failure")
        ):
            with self.assertRaises((OSError, self.m.Stop)):
                self.m.restore(fake, self.source, journal)
        self.assertEqual(fake.mutations, [])

    def test_journal_is_exclusive_and_private(self):
        self.journal()
        self.assertEqual(stat.S_IMODE((self.root / "receipt.jsonl").stat().st_mode), 0o600)
        with self.assertRaises((FileExistsError, self.m.Stop)):
            self.journal()

    def test_journal_rejects_repository_path_before_open(self):
        forbidden = SCRIPT.parent.parent / "receipt-that-must-never-be-created.jsonl"
        with mock.patch.object(
            self.m.os, "open", side_effect=AssertionError("repository write")
        ) as opened:
            with self.assertRaisesRegex(self.m.Stop, "receipt_in_repository"):
                self.m.Journal(forbidden)
            opened.assert_not_called()

    def test_vectors_reject_nonfinite_boolean_zero_and_float32_overflow(self):
        for vector in (
            [0.0] * 768,
            [True] + [0.1] * 767,
            [float("nan")] * 768,
            [float("inf")] * 768,
            [1e39] * 768,
            [1e-100] * 768,
            [0.1] * 767,
        ):
            with self.subTest(first=repr(vector[0]), length=len(vector)):
                with self.assertRaises((self.m.Stop, OverflowError, struct.error)):
                    self.m.f32_bytes(vector)

    def test_T_golden_float32_readback_is_neither_identity_nor_unit_normalization(self):
        # SIMD4 reduction of [1,1,0,...]: the observed float32 round-trip is
        # [nextafter_f32(1,0), nextafter_f32(1,0), 0,...], not [1,1] or unit norm.
        row = self.source[0]
        row["embedding"] = [1.0, 1.0] + [0.0] * 766
        golden = struct.pack("<II", 0x3F7FFFFF, 0x3F7FFFFF) + bytes(766 * 4)
        self.assertEqual(self.m.f32_bytes(self.m.read_representation(row["embedding"])), golden)
        response = {
            "ids": [row["id"]],
            "documents": [row["document"]],
            "metadatas": [row["metadata"]],
            "embeddings": [row["embedding"]],
        }
        with self.assertRaises(self.m.Stop):
            self.m.compare_rows([row], response)
        response["embeddings"] = [list(struct.unpack("<768f", golden))]
        self.m.compare_rows([row], response)

    def test_model_preflight_accepts_only_pinned_profile_without_inference(self):
        self.m.check_model(FakeOllama())
        for kw in (
            {"version": "wrong"},
            {"digest": "0" * 64},
            {"dimension": 1536},
            {"context": 4096},
        ):
            with self.subTest(kw=kw):
                fake = FakeOllama(**kw)
                with self.assertRaises(self.m.Stop):
                    self.m.check_model(fake)
                self.assertTrue(
                    all(
                        path in ("/api/version", "/api/tags", "/api/show")
                        for _, path, _ in fake.calls
                    )
                )

    def test_execute_model_mismatch_stops_before_chroma_access(self):
        chroma, ollama = FakeChroma(self.m, self.source), FakeOllama(digest="0" * 64)

        def factory(host, *args, **kwargs):
            return ollama if host == "ollama.invalid" else chroma

        with (
            mock.patch.object(self.m, "load_package", return_value=({}, self.source)),
            mock.patch.object(self.m, "HTTP", side_effect=factory),
        ):
            code = self.invoke(
                [
                    "--execute",
                    "--host",
                    "chroma.invalid",
                    "--port",
                    "8000",
                    "--ollama-base-url",
                    "http://ollama.invalid:11434",
                    "--receipt",
                    str(self.root / "model-mismatch.jsonl"),
                ]
            )
        self.assertEqual(code, 1)
        self.assertEqual(chroma.calls, [])

    def test_http_accepts_only_typed_missing_and_rejects_incomplete_body_without_retry(self):
        cases = [
            (404, {"error": "NotFoundError"}, 0, True),
            (404, {"detail": "missing"}, 0, False),
            (200, None, 0, False),
            (204, None, 0, False),
            (200, {"ok": True}, 1, False),
        ]
        for status, value, extra_length, accepted in cases:
            with self.subTest(status=status, value=value, extra_length=extra_length):
                raw = b"" if status == 204 else json.dumps(value).encode()
                headers = Message()
                headers["Content-Length"] = str(len(raw) + extra_length)
                stream = io.BytesIO(raw)
                response = mock.Mock(status=status, headers=headers, read1=stream.read)
                connection = mock.Mock()
                connection.getresponse.return_value = response
                with (
                    mock.patch.object(
                        self.m.http.client, "HTTPConnection", return_value=connection
                    ),
                    mock.patch.object(self.m.signal, "setitimer"),
                    mock.patch.object(self.m.signal, "signal"),
                ):
                    http = self.m.HTTP("synthetic.invalid", 8000)
                    if accepted:
                        self.assertIsNone(
                            http.request(
                                "GET", self.m.COLS + "/" + self.m.COLLECTION_NAME, missing=True
                            )
                        )
                    else:
                        with self.assertRaises(self.m.Stop):
                            http.request(
                                "GET", self.m.COLS + "/" + self.m.COLLECTION_NAME, missing=True
                            )
                self.assertEqual(connection.request.call_count, 1)
                connection.close.assert_called_once_with()

    def test_http_denies_destructive_or_model_inference_routes_before_connection(self):
        with mock.patch.object(
            self.m.http.client, "HTTPConnection", side_effect=AssertionError("connection")
        ) as factory:
            http = self.m.HTTP("synthetic.invalid", 8000)
            for method, path in (
                ("DELETE", self.m.COLS + "/old"),
                ("POST", self.m.COLS + "/old/upsert"),
                ("POST", "/api/embeddings"),
                ("POST", "/api/generate"),
            ):
                with self.subTest(method=method, path=path):
                    with self.assertRaises(self.m.Stop):
                        http.request(method, path, {})
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
