"""El wrapper se prueba con un uv falso: nunca procesa datos ni llama a servicios."""

import os
import subprocess
from pathlib import Path

import pytest

_PROJECT = Path(__file__).resolve().parents[2]
_SCRIPT = _PROJECT / "scripts" / "run_data_pipeline.sh"
_MODULES = ["ingest.pdf_to_md", "ingest.loaders", "ingest.splitter_and_enrich"]


def _run_with_fake_uv(tmp_path: Path, cwd: Path, fail_module: str = ""):
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        '#!/bin/sh\nprintf "%s|%s\\n" "$PWD" "$*" >> "$PIPELINE_TRACE"\n'
        '[ "$4" != "$PIPELINE_FAIL_MODULE" ] || exit 17\n',
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    trace = tmp_path / "trace.txt"
    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=cwd,
        env={
            **os.environ,
            "PATH": f"{tmp_path}{os.pathsep}{os.defpath}",
            "PIPELINE_TRACE": str(trace),
            "PIPELINE_FAIL_MODULE": fail_module,
        },
        capture_output=True,
        text=True,
        timeout=10,
    )
    calls = [line.split("|", 1) for line in trace.read_text().splitlines()]
    return result, calls


@pytest.mark.parametrize("from_project", [False, True])
def test_runs_only_data_stages_from_the_ingesta_workspace(tmp_path, from_project):
    result, calls = _run_with_fake_uv(tmp_path, _PROJECT if from_project else tmp_path)
    assert result.returncode == 0, result.stderr
    assert [arguments for _, arguments in calls] == [f"run python -m {m}" for m in _MODULES]
    assert all(Path(cwd).resolve() == _PROJECT.resolve() for cwd, _ in calls)
    assert "1/3" in result.stdout and "3/3" in result.stdout
    assert "1/5" not in result.stdout


@pytest.mark.parametrize("failed_stage", [0, 1, 2])
def test_preserves_failure_and_does_not_run_following_stages(tmp_path, failed_stage):
    result, calls = _run_with_fake_uv(tmp_path, tmp_path, _MODULES[failed_stage])
    assert result.returncode == 17
    assert [arguments for _, arguments in calls] == [
        f"run python -m {m}" for m in _MODULES[: failed_stage + 1]
    ]
