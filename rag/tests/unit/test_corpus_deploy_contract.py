"""Offline deployment selection/wiring contracts; never run a cloud entrypoint.

Only the shared Bash helper is executed, with controlled Git/Python doubles and
cloud commands denied on PATH. Runtime configuration lives in disposable paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPER = ROOT / "scripts/corpus_release.sh"
PACKAGE = "gold-a-cc7bf44b54a9"
COLLECTION = "rag_playas_gold_a_cc7bf44b54a9"
MODEL = "embeddinggemma:latest"
HEAD = "a" * 40


class CorpusDeploymentContracts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="corpus-deploy-contract-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.repo, self.bin = self.work / "fixture repo", self.work / "bin"
        self.repo.mkdir()
        self.bin.mkdir()
        self.log, self.forbidden = self.work / "calls.jsonl", self.work / "forbidden.log"
        self.env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL") if key in os.environ}
        self.env.update(
            PATH=str(self.bin) + os.pathsep + self.env.get("PATH", os.defpath),
            CORPUS_CONTRACT_LOG=str(self.log),
            CORPUS_FORBIDDEN_LOG=str(self.forbidden),
            CORPUS_TEST_HEAD=HEAD,
            CORPUS_TEST_REMOTE_HEAD=HEAD,
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONNOUSERSITE="1",
        )
        deny = '#!/bin/sh\nprintf "%s\\n" "$0" >> "$CORPUS_FORBIDDEN_LOG"\nexit 97\n'
        for name in ("aws", "ssh", "scp", "terraform", "curl", "docker", "uv", "sudo", "ollama"):
            self.executable(self.bin / name, deny)
        self.executable(
            self.bin / "git",
            f"#!{sys.executable}\n"
            + """import json, os, sys
args = sys.argv[1:]
with open(os.environ['CORPUS_CONTRACT_LOG'], 'a') as f:
    f.write(json.dumps({'program': 'git', 'args': args}) + '\\n')
command = args[2:] if args[:1] == ['-C'] else args
if command[:1] == ['ls-files']:
    raise SystemExit(int(os.environ.get('CORPUS_TEST_UNTRACKED', '0')))
if command[:2] == ['branch', '--show-current']:
    print(os.environ.get('CORPUS_TEST_BRANCH', 'corpus'))
elif command[:1] == ['diff']:
    key = 'CORPUS_TEST_STAGED' if '--cached' in command else 'CORPUS_TEST_DIRTY'
    raise SystemExit(int(os.environ.get(key, '0')))
elif command[:2] == ['rev-parse', 'HEAD']:
    print(os.environ['CORPUS_TEST_HEAD'])
elif command[:2] == ['ls-remote', '--exit-code']:
    if os.environ.get('CORPUS_TEST_REMOTE_ERROR'): raise SystemExit(128)
    print(os.environ['CORPUS_TEST_REMOTE_HEAD'] + '\\trefs/heads/corpus')
else:
    raise SystemExit('unexpected git arguments: ' + repr(command))
""",
        )

    def tearDown(self):
        self.assertFalse(self.forbidden.exists(), "A cloud/SSH command was attempted")

    def executable(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        path.chmod(0o700)

    def fake_restore_python(self, returncode=0):
        self.env["CORPUS_TEST_PYTHON_RC"] = str(returncode)
        self.executable(
            self.repo / "rag/.venv/bin/python",
            f"#!{sys.executable}\n"
            + """import json, os, sys
with open(os.environ['CORPUS_CONTRACT_LOG'], 'a') as f:
    f.write(json.dumps({'program': 'python', 'args': sys.argv[1:]}) + '\\n')
raise SystemExit(int(os.environ.get('CORPUS_TEST_PYTHON_RC', '0')))
""",
        )

    def calls(self, program=None):
        rows = (
            [json.loads(line) for line in self.log.read_text().splitlines()]
            if self.log.exists()
            else []
        )
        return [row for row in rows if program is None or row["program"] == program]

    def bash(self, body, *args):
        script = 'set -euo pipefail; source "$1"; shift; ' + body
        return subprocess.run(
            [
                "/bin/bash",
                "--noprofile",
                "--norc",
                "-c",
                script,
                "corpus-contract",
                str(HELPER),
                *(str(arg) for arg in args),
            ],
            env=self.env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_sourcing_is_inert_and_defaults_are_one_release(self):
        result = self.bash(
            'printf "%s|%s|%s|%s" "$CORPUS_RELEASE_BRANCH" "$CORPUS_RELEASE_PACKAGE" "$CORPUS_RELEASE_COLLECTION" "$CORPUS_RELEASE_MODEL"'
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "|".join(("corpus", PACKAGE, COLLECTION, MODEL)))
        self.assertEqual(self.calls(), [])

    def test_check_uses_fixed_package_and_cannot_fall_back_to_newest_legacy(self):
        self.fake_restore_python()
        legacy = self.repo / "data/newest-july.jsonl.gz"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(b"synthetic legacy, not an import candidate")
        os.utime(legacy, (2_000_000_000, 2_000_000_000))
        missing = self.bash('corpus_release_check_local "$@"', self.repo)
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(self.calls("python"), [])
        (self.repo / "data/chroma-releases" / PACKAGE).mkdir(parents=True)
        checked = self.bash('corpus_release_check_local "$@"', self.repo)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(
            self.calls("python")[-1]["args"],
            ["-I", "-S", "-B", str(self.repo / "data/restore_gold_release.py"), "--check"],
        )

    def test_restore_and_verify_forward_exact_argv_and_propagate_failure(self):
        self.fake_restore_python()
        receipt = self.work / "receipt directory/receipt.json"
        arguments = [self.repo, "198.51.100.7", "8123", "http://198.51.100.8:11434", receipt]
        for mode in ([], ["--verify-only"]):
            result = self.bash('corpus_release_restore "$@"', *arguments, *mode)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                self.calls("python")[-1]["args"],
                [
                    "-I",
                    "-S",
                    "-B",
                    str(self.repo / "data/restore_gold_release.py"),
                    "--execute",
                    "--host",
                    "198.51.100.7",
                    "--port",
                    "8123",
                    "--ollama-base-url",
                    "http://198.51.100.8:11434",
                    "--receipt",
                    str(receipt),
                    *mode,
                ],
            )
        count = len(self.calls("python"))
        invalid = self.bash('corpus_release_restore "$@"', *arguments, "--recreate")
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(len(self.calls("python")), count)
        self.env["CORPUS_TEST_PYTHON_RC"] = "17"
        failed = self.bash('corpus_release_restore "$@"', *arguments)
        self.assertEqual(failed.returncode, 17)

    def test_published_corpus_head_and_selected_inputs_are_explicit(self):
        result = self.bash(
            'corpus_release_published_head "$@"', self.repo, "https://example.invalid/source.git"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), HEAD)
        calls = [row["args"] for row in self.calls("git")]
        selected_call = next(args for args in calls if "ls-files" in args)
        paths = selected_call[selected_call.index("--") + 1 :]
        self.assertEqual(len(paths), 14)
        self.assertIn("data/restore_gold_release.py", paths)
        self.assertEqual(
            sum(path.startswith("data/chroma-releases/" + PACKAGE + "/") for path in paths), 5
        )
        self.assertFalse(any("validation/" in path or "769a847" in path for path in paths))
        self.assertEqual(
            calls[-1],
            ["ls-remote", "--exit-code", "https://example.invalid/source.git", "refs/heads/corpus"],
        )

    def test_unpublished_dirty_untracked_or_wrong_branch_stops(self):
        for key, value in (
            ("CORPUS_TEST_BRANCH", "main"),
            ("CORPUS_TEST_DIRTY", "1"),
            ("CORPUS_TEST_STAGED", "1"),
            ("CORPUS_TEST_UNTRACKED", "1"),
            ("CORPUS_TEST_REMOTE_HEAD", "b" * 40),
            ("CORPUS_TEST_REMOTE_ERROR", "1"),
        ):
            with self.subTest(key=key):
                old = dict(self.env)
                self.env[key] = value
                try:
                    result = self.bash(
                        'corpus_release_published_head "$@"',
                        self.repo,
                        "https://example.invalid/source.git",
                    )
                    self.assertNotEqual(result.returncode, 0)
                finally:
                    self.env = old

    def test_tfvars_reads_only_unambiguous_literals(self):
        path = self.work / "synthetic.tfvars"
        path.write_text(
            'chroma_host = "198.51.100.7" # comment\nchroma_port=8123\n', encoding="utf-8"
        )
        for key, default, expected in (
            ("chroma_host", "", "198.51.100.7"),
            ("chroma_port", "8000", "8123"),
            ("missing_port", "8000", "8000"),
        ):
            result = self.bash('corpus_release_tfvar "$@"', path, key, default)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), expected)
        invalid = [
            "chroma_host = var.host\n",
            'chroma_host = "${var.host}"\n',
            'chroma_host = "%{if true}x%{endif}"\n',
            'chroma_host = "one"\nchroma_host = "two"\n',
            'chroma_host = ""\n',
            'chroma_host = ["one"]\n',
        ]
        for value in invalid:
            with self.subTest(value=value):
                path.write_text(value, encoding="utf-8")
                self.assertNotEqual(
                    self.bash('corpus_release_tfvar "$@"', path, "chroma_host").returncode, 0
                )

    def test_wait_uses_only_fixed_model_probe_and_no_real_http(self):
        self.fake_restore_python()
        result = self.bash(
            'corpus_release_wait_ollama "$@"', self.repo, "http://198.51.100.8:11434"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls("python")[-1]["args"][-2:], ["http://198.51.100.8:11434", MODEL]
        )
        source = HELPER.read_text()
        self.assertIn('connection.request("GET", "/api/tags"', source)
        self.assertNotIn("/api/embeddings", source)
        self.assertNotIn("/api/generate", source)

    def test_openai_key_reader_accepts_literal_dotenv_formats(self):
        path = self.work / "synthetic.env"
        token = "sk-proj-synthetic_A9-z"
        for assignment in (
            f"OPENAI_API_KEY={token}\n",
            f"  OPENAI_API_KEY = '{token}'  \n",
            f'\tOPENAI_API_KEY = "{token}"\t\n',
        ):
            with self.subTest(assignment=assignment):
                path.write_text("# synthetic configuration\nOTHER=value\n" + assignment)
                result = self.bash('corpus_release_read_openai_key "$@"', path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, token + "\n")
                self.assertEqual(result.stderr, "")
        self.assertEqual(self.calls(), [])

    def test_openai_key_reader_rejects_ambiguous_or_unsafe_values_without_disclosure(self):
        path = self.work / "synthetic.env"
        token = "sk-proj-synthetic_A9-z"
        invalid = (
            "OTHER=value\n",
            "OPENAI_API_KEY=\n",
            "OPENAI_API_KEY = ''\n",
            'OPENAI_API_KEY = ""\n',
            f"OPENAI_API_KEY={token}\nOPENAI_API_KEY={token}\n",
            f"OPENAI_API_KEY='{token}\n",
            f'OPENAI_API_KEY="{token}" trailing\n',
            f"OPENAI_API_KEY={token} unsafe\n",
            f"OPENAI_API_KEY={token};echo\n",
            f"OPENAI_API_KEY='{token}$(printf injected)'\n",
            f"OPENAI_API_KEY={token}\x00\n",
        )
        for assignment in invalid:
            with self.subTest(assignment=assignment):
                path.write_text(assignment)
                result = self.bash('corpus_release_read_openai_key "$@"', path)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertNotIn(token, result.stderr)
                self.assertNotIn("injected", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_fresh_checkout_guard_preserves_existing_files_directories_and_symlinks(self):
        source = (ROOT / "scripts/deploy_bastion_ec2.sh").read_text()
        guard = source.split("<<'FRESH_BASTION_CHECK'\n", 1)[1].split("\nFRESH_BASTION_CHECK", 1)[0]
        self.assertIn('[[ -e "${HOME}/playas" || -L "${HOME}/playas" ]]', guard)
        self.assertNotIn("apt-get", guard)
        self.assertNotIn("rm -rf", guard)
        homes = {
            kind: self.work / (kind + " home")
            for kind in ("absent", "directory", "file", "symlink", "broken")
        }
        for home in homes.values():
            home.mkdir()
        directory = homes["directory"] / "playas"
        directory.mkdir()
        (directory / "state.bin").write_bytes(b"synthetic state\x00\xff")
        (homes["file"] / "playas").write_bytes(b"synthetic configuration\n")
        (homes["symlink"] / "playas").symlink_to(directory, target_is_directory=True)
        (homes["broken"] / "playas").symlink_to(
            self.work / "missing target", target_is_directory=True
        )

        def snapshot():
            return {
                str(path.relative_to(self.work)): (
                    ("symlink", os.readlink(path))
                    if path.is_symlink()
                    else ("directory", path.stat().st_mode)
                    if path.is_dir()
                    else ("file", path.read_bytes(), path.stat().st_mode)
                )
                for path in self.work.rglob("*")
            }

        before = snapshot()
        for kind, home in homes.items():
            with self.subTest(kind=kind):
                self.env["HOME"] = str(home)
                result = self.bash(guard)
                self.assertEqual(result.returncode == 0, kind == "absent", result.stderr)
                self.assertEqual(snapshot(), before)
        self.assertFalse((homes["absent"] / "playas").exists())
        self.assertEqual(self.calls(), [])

    def test_bastion_checks_before_aws_and_clones_the_published_commit(self):
        source = (ROOT / "scripts/deploy_bastion_ec2.sh").read_text()
        first_aws = source.index("aws ec2 describe-vpcs")
        self.assertLess(source.index('corpus_release_published_head "${REPO_DIR}"'), first_aws)
        self.assertLess(source.index('corpus_release_check_local "${REPO_DIR}"'), first_aws)
        self.assertLess(source.index('corpus_release_read_openai_key "${RAG_ENV}"'), first_aws)
        fresh_end = source.index("\nFRESH_BASTION_CHECK", source.index("<<'FRESH_BASTION_CHECK'"))
        self.assertLess(fresh_end, source.index("printf '%s' \"${OPENAI_API_KEY}\""))
        self.assertLess(fresh_end, source.index("'mkdir -p ~/seed_data'"))
        remote = source.split("<<'REMOTE_SCRIPT'\n", 1)[1].split("\nREMOTE_SCRIPT", 1)[0]
        self.assertLess(
            remote.index('if [[ -e "${HOME}/playas" || -L "${HOME}/playas" ]]'),
            remote.index("apt-get update"),
        )
        self.assertNotIn("rm -rf ~/playas", source)
        self.assertNotIn("grep -E '^OPENAI_API_KEY='", source)
        self.assertIn('git clone --branch corpus --single-branch "${REPO_URL}"', source)
        self.assertIn('git checkout --detach "${DEPLOY_COMMIT}"', source)
        self.assertIn("git rev-parse HEAD", source)
        self.assertRegex(source, r"DEPLOY_COMMIT=.*DEPLOY_COMMIT")
        self.assertNotIn("ls -t", source)
        self.assertNotIn("LATEST_EXPORT", source)
        self.assertNotIn("import_to_chromadb.py", source)

    def test_vector_publishes_collection_and_model_only_after_restore(self):
        source = (ROOT / "vector-infraestructura/scripts/deploy.sh").read_text()
        restore = source.index('corpus_release_restore "${REPO_DIR}"')
        for text in (
            'update_env "${RAG_ENV}" "CHROMA_COLLECTION" "${CORPUS_RELEASE_COLLECTION}"',
            'update_env "${RAG_ENV}" "OLLAMA_EMBEDDING_MODEL" "${CORPUS_RELEASE_MODEL}"',
            'update_tfvars "${ECS_TFVARS}" "chroma_collection" "${CORPUS_RELEASE_COLLECTION}"',
            'update_tfvars "${ECS_TFVARS}" "ollama_embedding_model" "${CORPUS_RELEASE_MODEL}"',
        ):
            self.assertGreater(source.index(text), restore)
        self.assertLess(
            source.index('corpus_release_check_local "${REPO_DIR}"'),
            source.index('terraform -chdir="${VECTOR_INFRA_DIR}" init'),
        )
        self.assertNotIn("ls -t", source)
        self.assertNotIn("import_to_chromadb.py", source)

    def test_direct_ecs_verifies_and_forces_the_same_configuration(self):
        source = (ROOT / "rag/infrastructure/scripts/deploy.sh").read_text()
        verify = source.index('corpus_release_restore "${REPO_DIR}"')
        init = source.index('terraform -chdir="${INFRA_DIR}" init')
        self.assertLess(verify, init)
        self.assertIn('"${RECEIPT_DIR}/receipt.json" --verify-only', source)
        for value in (
            "chroma_collection=${CORPUS_RELEASE_COLLECTION}",
            "ollama_embedding_model=${CORPUS_RELEASE_MODEL}",
            "chroma_host=${CHROMA_HOST_VAL}",
            "chroma_port=${CHROMA_PORT_VAL}",
            "ollama_base_url=${OLLAMA_URL_VAL}",
        ):
            self.assertIn(value, source)
        self.assertNotIn(
            "corpus_release_published_head", source
        )  # Detached approved checkout is valid remotely.
        self.assertIn(
            "value = var.chroma_collection", (ROOT / "rag/infrastructure/ecs.tf").read_text()
        )
        self.assertIn(
            "value = var.ollama_embedding_model", (ROOT / "rag/infrastructure/ecs.tf").read_text()
        )

    def test_templates_and_user_data_preserve_the_pinned_profile(self):
        env = (ROOT / "rag/.env.example").read_text()
        self.assertIn("CHROMA_COLLECTION=" + COLLECTION, env)
        self.assertIn("OLLAMA_EMBEDDING_MODEL=" + MODEL, env)
        variables = (ROOT / "rag/infrastructure/variables.tf").read_text()
        block = re.search(r'variable "chroma_collection"\s*\{(.*?)\n\}', variables, re.S)
        self.assertIsNotNone(block)
        self.assertRegex(block.group(1), 'default\\s*=\\s*"' + COLLECTION + '"')
        chroma = (ROOT / "vector-infraestructura/scripts/ec2_chroma_db.sh").read_text()
        self.assertIn("-v /opt/chroma-data:/data", chroma)
        self.assertIn(
            "sha256:111a6bd768be19721f5b4e88567d0e1d1f5c2ab5161129e711c0a431e667b128", chroma
        )
        self.assertLess(chroma.index("docker image inspect"), chroma.index("docker run"))
        ollama = (ROOT / "vector-infraestructura/scripts/ec2_ollama_embeddings.sh").read_text()
        self.assertIn("OLLAMA_NUM_PARALLEL=1", ollama)
        self.assertIn("OLLAMA_CONTEXT_LENGTH=2048", ollama)
        self.assertNotIn("OLLAMA_NUM_PARALLEL=4", ollama)
        self.assertNotIn(
            "ollama/ollama:0.40.13", ollama
        )  # Announced runtime version is not a verified registry tag.

    def test_historical_manifest_remains_archived(self):
        historical = ROOT / "data/chroma-releases/gold-a-769a847f096b/manifest.json"
        self.assertEqual(
            hashlib.sha256(historical.read_bytes()).hexdigest(),
            "7d319bc64ba2702d1bd11dd7bb10ae4525b5e3bd392b58d09a860af73e9f3a9c",
        )
        self.assertTrue((ROOT / "data/chroma-releases" / PACKAGE / "manifest.json").is_file())


if __name__ == "__main__":
    unittest.main()
