"""Offline contracts for the standalone snapshot CLI; no real SDK or service.

Run only this file with unittest when the verification phase is authorized.
All captures, links and failures below use disposable directories and doubles.
"""

from __future__ import annotations

import builtins
import errno
import hashlib
import importlib
import importlib.util
import io
import json
import os
import socket
import sys
import tempfile
import types
import unittest
import urllib.request
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[3] / "data" / "export_chroma_snapshot.py"
TENANT = "snapshot-test-tenant"
DATABASE = "snapshot-test-database"
COLLECTION = "snapshot-test-collection"


def page(rows):
    return {
        "ids": [row["id"] for row in rows],
        "documents": [row["document"] for row in rows],
        "metadatas": [row["metadata"] for row in rows],
    }


def records(count):
    return [
        {"id": f"{index:04d}", "document": f"Texto {index}", "metadata": {"n": index}}
        for index in range(count)
    ]


class StrictDouble:
    def __getattr__(self, name):
        raise AssertionError(f"Unexpected SDK access: {name}")


class FakeCollection(StrictDouble):
    def __init__(self, rows=(), *, pages=None, counts=None, identity="snapshot-test-uuid"):
        self.rows = list(rows)
        self.pages = pages
        self.counts = iter(counts if counts is not None else [len(self.rows), len(self.rows)])
        self.name = COLLECTION
        self.tenant = TENANT
        self.database = DATABASE
        self.id = identity
        self.offsets = []

    def count(self):
        return next(self.counts)

    def get(self, *, include, limit, offset):
        if include != ["documents", "metadatas"]:
            raise AssertionError("Unexpected include or embedding request")
        self.offsets.append(offset)
        response = (
            self.pages[offset]
            if self.pages is not None
            else page(self.rows[offset : offset + limit])
        )
        if isinstance(response, BaseException):
            raise response
        return response


class FakeClient(StrictDouble):
    def __init__(self, collection, *, final_collection=None, close_error=None):
        self.collection = collection
        self.final_collection = final_collection or collection
        self.tenant = TENANT
        self.database = DATABASE
        self.close_error = close_error
        self.calls = []
        self.closed = False

    def get_version(self):
        self.calls.append(("get_version", Path.cwd()))
        return "fake-server-version"

    def get_collection(self, *, name, embedding_function, data_loader):
        if name != COLLECTION or embedding_function is not None or data_loader is not None:
            raise AssertionError("Unexpected collection lookup or embedding/data loader")
        lookup_count = sum(call[0] == "get_collection" for call in self.calls)
        self.calls.append(("get_collection", Path.cwd()))
        if lookup_count > 1:
            raise AssertionError("Unexpected retry")
        return self.collection if lookup_count == 0 else self.final_collection

    def close(self):
        self.calls.append(("close", Path.cwd()))
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class SnapshotContracts(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.temp = Path(self.stack.enter_context(tempfile.TemporaryDirectory())).resolve()
        self.original_cwd = Path.cwd()
        self.allow_fake_sdk = False
        self.sdk_imports = []
        self.output_number = 0
        original_import = builtins.__import__
        original_import_module = importlib.import_module

        def allowed_import(name):
            if name == "chromadb" or name.startswith("chromadb."):
                if not self.allow_fake_sdk or name not in sys.modules:
                    raise AssertionError("Real Chroma imports are forbidden")
                if not getattr(sys.modules[name], "snapshot_test_double", False):
                    raise AssertionError("Only fake SDK modules are allowed")
                self.sdk_imports.append((name, Path.cwd()))
            if name == "rag" or name.startswith(("rag.", "ingesta.")):
                raise AssertionError("Product imports are forbidden")

        def guarded_import(name, *args, **kwargs):
            allowed_import(name)
            return original_import(name, *args, **kwargs)

        def guarded_import_module(name, *args, **kwargs):
            allowed_import(name)
            return original_import_module(name, *args, **kwargs)

        def guarded_open(original):
            def open_without_env(file, *args, **kwargs):
                if isinstance(file, (str, bytes, os.PathLike)):
                    if Path(os.fsdecode(file)).name.startswith(".env"):
                        raise AssertionError("Reading or writing .env is forbidden")
                return original(file, *args, **kwargs)

            return open_without_env

        self.stack.enter_context(mock.patch("builtins.__import__", side_effect=guarded_import))
        self.stack.enter_context(
            mock.patch("importlib.import_module", side_effect=guarded_import_module)
        )
        self.stack.enter_context(mock.patch("builtins.open", new=guarded_open(builtins.open)))
        self.stack.enter_context(mock.patch("io.open", new=guarded_open(io.open)))
        for name in (
            "socket",
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            self.stack.enter_context(
                mock.patch.object(socket, name, side_effect=AssertionError("Network/DNS forbidden"))
            )
        self.proxy = self.stack.enter_context(
            mock.patch.object(
                urllib.request,
                "getproxies",
                side_effect=AssertionError("Proxy discovery during import is forbidden"),
            )
        )
        module_name = f"snapshot_cli_under_test_{id(self)}"
        spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        self.sut = importlib.util.module_from_spec(spec)
        self.stack.enter_context(mock.patch.dict(sys.modules, {module_name: self.sut}))
        spec.loader.exec_module(self.sut)
        self.proxy.side_effect = None
        self.proxy.return_value = {}
        self.version = self.stack.enter_context(
            mock.patch.object(self.sut.importlib.metadata, "version", return_value="1.5.9")
        )
        self.sleep = self.stack.enter_context(mock.patch.object(self.sut.time, "sleep"))

    def output(self):
        self.output_number += 1
        return self.temp / f"capture-{self.output_number}"

    def argv(self, output):
        return [
            "--host",
            "snapshot.example.invalid",
            "--port",
            "8000",
            "--tenant",
            TENANT,
            "--database",
            DATABASE,
            "--collection",
            COLLECTION,
            "--output-dir",
            str(output),
            "--batch-size",
            "2",
            "--confirm-no-writes",
        ]

    def run_cli(self, client, output, *, argv=None, check_cwd=True):
        stdout, stderr = io.StringIO(), io.StringIO()
        with ExitStack() as stack:
            factory = None
            if client is not None:
                factory = stack.enter_context(
                    mock.patch.object(self.sut, "create_client", return_value=client)
                )
            stack.enter_context(redirect_stdout(stdout))
            stack.enter_context(redirect_stderr(stderr))
            code = self.sut.main(self.argv(output) if argv is None else argv)
        if check_cwd:
            self.assertEqual(Path.cwd(), self.original_cwd)
        return code, stdout.getvalue(), stderr.getvalue(), factory

    def assert_complete(self, output, expected_rows):
        payload = (output / "snapshot.jsonl").read_bytes()
        self.assertEqual([json.loads(line) for line in payload.splitlines()], expected_rows)
        manifest = json.loads((output / "manifest.json").read_bytes())
        self.assertEqual(manifest["capture_status"], "COMPLETE")
        self.assertEqual(manifest["count_before"], len(expected_rows))
        self.assertEqual(manifest["count_after"], len(expected_rows))
        self.assertEqual(manifest["rows_written"], len(expected_rows))
        self.assertEqual(manifest["unique_ids"], len(expected_rows))
        self.assertEqual(
            manifest["snapshot"],
            {
                "path": "snapshot.jsonl",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_bytes": len(payload),
            },
        )
        self.assertEqual(manifest["consistency_basis"], "operator_declared_no_writes")
        self.assertIs(manifest["atomic_snapshot"], False)
        self.assertIs(manifest["no_writes_verified_by_exporter"], False)
        for name in ("snapshot.jsonl", "manifest.json"):
            self.assertTrue(os.path.samefile(output / name, output / f"{name}.partial"))
        self.assertTrue(
            self.sut.publication_is_own(output, (output / "manifest.json.partial").read_bytes())
        )
        return manifest

    def assert_not_accepted(self, output):
        candidate = output / "manifest.json.partial"
        expected = candidate.read_bytes() if candidate.exists() else b"{}"
        self.assertFalse(self.sut.publication_is_own(output, expected))

    def test_import_help_and_invalid_cli_do_not_load_sdk_or_create_outputs(self):
        output = self.output()
        client = FakeClient(FakeCollection())
        code, _, _, factory = self.run_cli(client, output, argv=["--help"])
        self.assertEqual(code, 0)
        factory.assert_not_called()
        self.assertFalse(output.exists())
        self.proxy.assert_not_called()
        invalid = [
            ("--host", "http://user:PRIVATE_MARKER@example.invalid/path"),
            ("--host", "2001:db8::1"),
            ("--port", "PRIVATE_MARKER"),
            ("--port", "0"),
            ("--batch-size", "101"),
            ("--tenant", "   "),
            ("--confirm-no-writes", None),
        ]
        for name, value in invalid:
            with self.subTest(name=name, value=value):
                output = self.output()
                args = self.argv(output)
                index = args.index(name)
                if value is None:
                    args.pop(index)
                else:
                    args[index + 1] = value
                code, stdout, stderr, factory = self.run_cli(client, output, argv=args)
                self.assertEqual(code, 2)
                factory.assert_not_called()
                self.assertFalse(output.exists())
                self.assertNotIn("PRIVATE_MARKER", stdout + stderr)
        self.proxy.assert_not_called()

    def test_paths_environment_and_proxy_fail_before_client(self):
        client = FakeClient(FakeCollection())
        existing = self.temp / "existing"
        existing.mkdir()
        missing_parent = self.temp / "missing" / "capture"
        alias = self.temp / "repo-alias"
        alias.symlink_to(self.sut.REPO_ROOT, target_is_directory=True)
        for output in (existing, missing_parent, alias / "forbidden-capture", alias):
            with self.subTest(path=str(output)):
                code, _, _, factory = self.run_cli(client, output)
                self.assertEqual(code, 2)
                factory.assert_not_called()
        for proxies in (
            {"http": "http://user:PRIVATE_MARKER@proxy.invalid", "no": "*"},
            {"https": "x"},
            {"all": "x"},
        ):
            with self.subTest(proxies=tuple(proxies)):
                self.proxy.return_value = proxies
                output = self.output()
                code, stdout, stderr, factory = self.run_cli(client, output)
                self.assertEqual(code, 1)
                factory.assert_not_called()
                self.assertFalse(output.exists())
                self.assertNotIn("PRIVATE_MARKER", stdout + stderr)
        self.proxy.return_value = {}
        self.proxy.side_effect = OSError("PRIVATE_MARKER")
        output = self.output()
        code, stdout, stderr, factory = self.run_cli(client, output)
        self.assertEqual(code, 1)
        factory.assert_not_called()
        self.assertFalse(output.exists())
        self.assertNotIn("PRIVATE_MARKER", stdout + stderr)
        self.proxy.side_effect = None
        self.version.return_value = "unexpected-version"
        output = self.output()
        code, _, _, factory = self.run_cli(client, output)
        self.assertEqual(code, 1)
        factory.assert_not_called()
        self.assertFalse(output.exists())

    def test_late_mkdir_collision_preserves_foreign_contents_before_client(self):
        output = self.output()
        real_mkdir = Path.mkdir

        def directory_appears(path, *args, **kwargs):
            if path == output:
                real_mkdir(path, mode=0o700)
                (path / "foreign.txt").write_bytes(b"keep this file")
                raise FileExistsError("PRIVATE_MARKER")
            return real_mkdir(path, *args, **kwargs)

        with mock.patch.object(
            self.sut.Path, "mkdir", autospec=True, side_effect=directory_appears
        ):
            code, stdout, stderr, factory = self.run_cli(FakeClient(FakeCollection()), output)
        self.assertEqual(code, 2)
        factory.assert_not_called()
        self.assertEqual({path.name for path in output.iterdir()}, {"foreign.txt"})
        self.assertEqual((output / "foreign.txt").read_bytes(), b"keep this file")
        self.assertNotIn("PRIVATE_MARKER", stdout + stderr)

    def test_fake_sdk_factory_settings_namespace_and_private_cwd(self):
        client = FakeClient(FakeCollection())
        sdk, config = types.ModuleType("chromadb"), types.ModuleType("chromadb.config")
        sdk.__path__ = []
        sdk.snapshot_test_double = config.snapshot_test_double = True
        observed = {}

        def settings(**kwargs):
            observed["settings"] = kwargs
            return types.SimpleNamespace(**kwargs)

        def http_client(**kwargs):
            observed["client"] = kwargs
            observed["cwd"] = Path.cwd()
            self.assertEqual(list(Path.cwd().iterdir()), [])
            return client

        config.Settings, sdk.HttpClient, sdk.config = settings, http_client, config
        output = self.output()
        self.allow_fake_sdk = True
        try:
            with mock.patch.dict(sys.modules, {"chromadb": sdk, "chromadb.config": config}):
                code, _, _, _ = self.run_cli(None, output)
        finally:
            self.allow_fake_sdk = False
        self.assertEqual(code, 0)
        self.assertEqual(observed["cwd"], output)
        self.assertEqual(self.sdk_imports, [("chromadb", output), ("chromadb.config", output)])
        self.assertEqual(
            observed["settings"],
            {
                "_env_file": None,
                "is_persistent": False,
                "allow_reset": False,
                "anonymized_telemetry": False,
                "chroma_otel_granularity": "none",
                "chroma_otel_collection_endpoint": "",
                "chroma_otel_collection_headers": {},
                "chroma_client_auth_provider": None,
                "chroma_client_auth_credentials": None,
                "chroma_overwrite_singleton_tenant_database_access_from_auth": False,
                "chroma_product_telemetry_impl": "chromadb.telemetry.product.posthog.Posthog",
                "chroma_telemetry_impl": "chromadb.telemetry.product.posthog.Posthog",
            },
        )
        kwargs = observed["client"]
        self.assertEqual(
            {k: v for k, v in kwargs.items() if k != "settings"},
            {
                "host": "snapshot.example.invalid",
                "port": 8000,
                "ssl": False,
                "headers": None,
                "tenant": TENANT,
                "database": DATABASE,
            },
        )
        self.assertEqual(kwargs["settings"].__dict__, observed["settings"])
        self.assertTrue(client.closed)
        self.assertTrue(all(cwd == output for _, cwd in client.calls))
        self.assert_complete(output, [])

        def failing_constructor(**kwargs):
            self.assertEqual(list(Path.cwd().iterdir()), [])
            raise RuntimeError("PRIVATE_MARKER")

        sdk.HttpClient = failing_constructor
        output = self.output()
        self.allow_fake_sdk = True
        try:
            with mock.patch.dict(sys.modules, {"chromadb": sdk, "chromadb.config": config}):
                code, stdout, stderr, _ = self.run_cli(None, output)
        finally:
            self.allow_fake_sdk = False
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_MARKER", stdout + stderr)
        self.assertEqual(self.sdk_imports[2:], [("chromadb", output), ("chromadb.config", output)])
        self.assert_not_accepted(output)

    def test_empty_eof_and_short_intermediate_pages(self):
        for empty in (
            {"ids": [], "documents": [], "metadatas": []},
            {"ids": [], "documents": None, "metadatas": None},
        ):
            with self.subTest(empty_columns=empty["documents"]):
                collection = FakeCollection(pages={0: empty})
                output = self.output()
                code, _, _, _ = self.run_cli(FakeClient(collection), output)
                self.assertEqual(code, 0)
                self.assertEqual(collection.offsets, [0])
                self.assert_complete(output, [])
        rows = records(5)
        collection = FakeCollection(
            rows, pages={0: page(rows[:2]), 2: page(rows[2:3]), 3: page(rows[3:]), 5: page([])}
        )
        output = self.output()
        self.sleep.reset_mock()
        code, _, _, _ = self.run_cli(FakeClient(collection), output)
        self.assertEqual(code, 0)
        self.assertEqual(collection.offsets, [0, 2, 3, 5])
        self.assertEqual(self.sleep.call_args_list, [mock.call(0.1)] * 3)
        self.assert_complete(output, rows)

    def test_bad_pages_counts_and_collection_identity_are_incomplete(self):
        one = records(1)
        cases = [
            FakeCollection(one, pages={0: {"ids": (), "documents": [], "metadatas": []}}),
            FakeCollection(one, pages={0: {"ids": ["a"], "documents": None, "metadatas": [{}]}}),
            FakeCollection(one, pages={0: {"ids": ["a"], "documents": ["a"], "metadatas": []}}),
            FakeCollection(one, pages={0: page([])}),
            FakeCollection(pages={0: {"ids": [], "documents": ["extra"], "metadatas": None}}),
            FakeCollection(pages={0: {"ids": [], "documents": (), "metadatas": None}}),
            FakeCollection(one, pages={0: page(records(2))}),
            FakeCollection(one, pages={0: {"ids": [""], "documents": ["a"], "metadatas": [{}]}}),
            FakeCollection(records(2), pages={0: page(one), 1: page(one)}),
            FakeCollection(one, counts=[True]),
            FakeCollection(one, counts=[-1]),
            FakeCollection(one, counts=[1.0]),
            FakeCollection(one, counts=[1, 2]),
        ]
        for index, collection in enumerate(cases):
            with self.subTest(case=index):
                client, output = FakeClient(collection), self.output()
                code, _, _, _ = self.run_cli(client, output)
                self.assertEqual(code, 1)
                self.assertTrue(client.closed)
                self.assertEqual(sum(name == "close" for name, _ in client.calls), 1)
                self.assert_not_accepted(output)
        for attribute, value in (("id", "replacement"), ("tenant", "different-tenant")):
            with self.subTest(final_identity=attribute):
                final = FakeCollection()
                setattr(final, attribute, value)
                client, output = FakeClient(FakeCollection(), final_collection=final), self.output()
                self.assertEqual(self.run_cli(client, output)[0], 1)
                self.assert_not_accepted(output)
        client, output = FakeClient(FakeCollection()), self.output()
        client.database = "wrong-database"
        self.assertEqual(self.run_cli(client, output)[0], 1)
        self.assertEqual([name for name, _ in client.calls], ["close"])

    def test_observed_values_anomalies_and_real_ids_are_preserved(self):
        rows = [
            {
                "id": "0001",
                "document": "NO_LOG_DOCUMENT_MARKER ñ\nsegunda línea 1.25",
                "metadata": {
                    "chunk_id": "different",
                    "keywords_str": "observado, antiguo",
                    "nested": '["á", true, null]',
                    "bool": True,
                    "int": 1,
                    "float": 1.0,
                },
            },
            {"id": "0002", "document": None, "metadata": None},
            {"id": "0003", "document": "", "metadata": []},
            {"id": "0004", "document": 27, "metadata": {}},
        ]
        original = json.dumps(rows, ensure_ascii=False)
        output = self.output()
        code, stdout, stderr, _ = self.run_cli(FakeClient(FakeCollection(rows)), output)
        self.assertEqual(code, 0)
        self.assertNotIn("NO_LOG_DOCUMENT_MARKER", stdout + stderr)
        self.assertEqual(json.dumps(rows, ensure_ascii=False), original)
        manifest = self.assert_complete(output, rows)
        self.assertEqual(
            manifest["anomalies"],
            {
                "null_document": 1,
                "empty_document": 1,
                "unexpected_document_type": 1,
                "null_metadata": 1,
                "unexpected_metadata_type": 1,
                "metadata_chunk_id_mismatch": 1,
            },
        )
        observed = json.loads((output / "snapshot.jsonl").read_text().splitlines()[0])["metadata"]
        self.assertIs(type(observed["bool"]), bool)
        self.assertIs(type(observed["int"]), int)
        self.assertIs(type(observed["float"]), float)
        output = self.output()
        bad = [{"id": "finite-required", "document": "texto", "metadata": {"n": float("nan")}}]
        self.assertEqual(self.run_cli(FakeClient(FakeCollection(bad)), output)[0], 1)
        self.assert_not_accepted(output)
        self.assertNotIn(b"NaN", (output / "snapshot.jsonl.partial").read_bytes())

    def test_late_collisions_do_not_replace_or_adopt_foreign_files(self):
        real_link = os.link
        sentinel = b'{"capture_status":"COMPLETE","owner":"foreign"}\n'
        for collision in ("snapshot.jsonl", "manifest.json"):
            with self.subTest(collision=collision):
                output = self.output()

                def collide(source, target, *, filename=collision):
                    if Path(target).name == filename:
                        Path(target).write_bytes(sentinel)
                    return real_link(source, target)

                with mock.patch.object(self.sut.os, "link", side_effect=collide):
                    self.assertEqual(self.run_cli(FakeClient(FakeCollection()), output)[0], 1)
                self.assertEqual((output / collision).read_bytes(), sentinel)
                self.assert_not_accepted(output)

    def test_unsupported_links_have_no_rename_replace_or_copy_fallback(self):
        output = self.output()
        with (
            mock.patch.object(
                self.sut.os, "link", side_effect=OSError(errno.EOPNOTSUPP, "no links")
            ),
            mock.patch.object(
                self.sut.os, "rename", side_effect=AssertionError("No rename fallback")
            ),
            mock.patch.object(
                self.sut.os, "replace", side_effect=AssertionError("No replace fallback")
            ),
        ):
            self.assertEqual(self.run_cli(FakeClient(FakeCollection()), output)[0], 1)
        self.assertFalse((output / "snapshot.jsonl").exists())
        self.assertFalse((output / "manifest.json").exists())
        self.assertTrue((output / "manifest.json.partial").is_file())

    def test_publish_rejects_symlink_candidate_before_creating_final_names(self):
        output = self.output()
        output.mkdir()
        source = self.temp / "outside-candidate.jsonl"
        source.write_bytes(b"")
        (output / "snapshot.jsonl.partial").symlink_to(source)
        expected = self.sut.manifest_bytes(
            {"capture_status": "COMPLETE", "snapshot": self.sut.file_receipt(source)}
        )
        (output / "manifest.json.partial").write_bytes(expected)
        with mock.patch.object(self.sut.os, "link") as link:
            with self.assertRaises(self.sut.SnapshotError):
                self.sut.publish(output, expected)
        link.assert_not_called()
        self.assertEqual(source.read_bytes(), b"")
        self.assertFalse((output / "snapshot.jsonl").exists())
        self.assertFalse((output / "manifest.json").exists())

    def test_interrupt_before_commit_preserves_closed_complete_candidate(self):
        real_link, output, observed = os.link, self.output(), {}

        def interrupt_before_link(source, target):
            if Path(target).name == "manifest.json":
                observed["candidate"] = Path(source).read_bytes()
                raise KeyboardInterrupt
            return real_link(source, target)

        with mock.patch.object(self.sut.os, "link", side_effect=interrupt_before_link):
            self.assertEqual(self.run_cli(FakeClient(FakeCollection()), output)[0], 130)
        self.assertEqual((output / "manifest.json.partial").read_bytes(), observed["candidate"])
        self.assertEqual(json.loads(observed["candidate"])["capture_status"], "COMPLETE")
        self.assertFalse((output / "manifest.json").exists())
        self.assert_not_accepted(output)

    def test_signal_after_final_link_is_recognized_without_a_local_flag(self):
        real_link, output = os.link, self.output()
        client = FakeClient(FakeCollection(records(1)))

        def link_then_interrupt(source, target):
            self.assertTrue(client.closed)
            self.assertEqual(Path.cwd(), self.original_cwd)
            real_link(source, target)
            if Path(target).name == "manifest.json":
                raise KeyboardInterrupt

        with mock.patch.object(self.sut.os, "link", side_effect=link_then_interrupt):
            self.assertEqual(self.run_cli(client, output)[0], 130)
        self.assert_complete(output, records(1))

    def test_console_failure_after_commit_does_not_downgrade_publication(self):
        output = self.output()
        with mock.patch("builtins.print", side_effect=BrokenPipeError("PRIVATE_MARKER")):
            code, _, _, _ = self.run_cli(FakeClient(FakeCollection()), output)
        self.assertEqual(code, 1)
        self.assert_complete(output, [])

    def test_read_close_and_restore_failures_prevent_commit_without_secret_echo(self):
        collection = FakeCollection(counts=[1], pages={0: RuntimeError("PRIVATE_MARKER")})
        client = FakeClient(collection, close_error=OSError("SECONDARY_PRIVATE_MARKER"))
        output = self.output()
        code, stdout, stderr, _ = self.run_cli(client, output)
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_MARKER", stdout + stderr)
        manifest = json.loads((output / "manifest.json.partial").read_bytes())
        self.assertEqual(manifest["error"], {"stage": "capture", "category": "RuntimeError"})
        self.assertTrue(client.closed)
        self.assert_not_accepted(output)
        output = self.output()
        client = FakeClient(FakeCollection(), close_error=OSError("PRIVATE_MARKER"))
        self.assertEqual(self.run_cli(client, output)[0], 1)
        self.assertEqual(
            json.loads((output / "manifest.json.partial").read_bytes())["error"]["stage"], "close"
        )
        self.assert_not_accepted(output)
        real_chdir, output = os.chdir, self.output()

        def fail_restore(path):
            if Path(path) == self.original_cwd:
                raise OSError("PRIVATE_MARKER")
            return real_chdir(path)

        try:
            with mock.patch.object(self.sut.os, "chdir", side_effect=fail_restore):
                code, stdout, stderr, _ = self.run_cli(
                    FakeClient(FakeCollection()), output, check_cwd=False
                )
        finally:
            real_chdir(self.original_cwd)
        self.assertEqual(code, 1)
        self.assertNotIn("PRIVATE_MARKER", stdout + stderr)
        self.assertEqual(
            json.loads((output / "manifest.json.partial").read_bytes())["error"]["stage"],
            "restore_cwd",
        )
        self.assert_not_accepted(output)


if __name__ == "__main__":
    unittest.main()
