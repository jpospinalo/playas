"""Las entradas históricas deben delegar solo al CLI offline y vaciar claves."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("bash") is None, reason="Requiere Bash")
@pytest.mark.parametrize("script", ["run_pipeline.sh", "run_data_pipeline.sh"])
def test_offline_entrypoint(tmp_path, script):
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "invocation.json"
    python = tmp_path / "python"
    python.write_text(
        "#!/usr/bin/env python3\n"
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "Path(os.environ['CAPTURE']).write_text(json.dumps({"
        "'argv':sys.argv[1:],'cwd':os.getcwd(),"
        "'keys':{k:os.environ.get(k) for k in "
        "['GOOGLE_API_KEY','GEMINI_API_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY']}}))\n"
    )
    python.chmod(0o700)
    env = dict(os.environ, OFFLINE_PYTHON=str(python), CAPTURE=str(output))
    for key in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"]:
        env[key] = "dummy-must-not-propagate"
    subprocess.run(
        ["bash", str(root / "ingesta/scripts" / script), "--collection", "test_offline", "sync"],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
    )
    result = json.loads(output.read_text())
    assert result["argv"] == ["-m", "ingest.offline", "--collection", "test_offline", "sync"]
    assert Path(result["cwd"]) == root
    assert set(result["keys"].values()) == {""}
