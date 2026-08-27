"""C1 — la configuración de base de datos y JWT no debe depender del orden
accidental de imports.

`rag.api.rate_limit` importa `rag.api.auth` (que a su vez importa
`rag.api.database`) antes de importar `rag.config`. Antes de esta entrega,
`database.py` y `auth.py` leían `DATABASE_URL`/`JWT_ALGORITHM`/
`JWT_EXPIRE_MINUTES` con `os.getenv()` directo, a nivel de módulo — si esos
módulos se importaban (vía `rate_limit.py`, como ocurre en
`rag.api.main`) antes de que algo más ya hubiera importado `rag.config`
(que es quien carga el `.env` resuelto por `RAG_ENV_FILE`), esos valores se
fijaban permanentemente a partir del `os.environ` de ese momento — sin el
`.env`. Lo mismo le pasaba a `REGISTER_ENABLED` en `routes/auth.py`.

Esta prueba reproduce el proceso real: importa `rag.api.main` (el punto de
entrada real, que dispara exactamente esa cadena de imports) en un
subproceso limpio con `RAG_ENV_FILE` apuntando a un `.env` temporal con
valores no-default, y confirma que los valores efectivos SÍ reflejan ese
`.env` — sin importar el orden interno de imports.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"


def _minimal_env(**overrides: str) -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(
            ("CHROMA_", "OLLAMA_", "RAG_ENV_FILE", "DATABASE_URL", "JWT_", "REGISTER_ENABLED")
        )
    }
    env.update(overrides)
    return env


def _import_main_and_print(env: dict[str, str], statements: list[str]) -> list[str]:
    code = (
        "import rag.api.main  # dispara rate_limit -> auth -> database, antes de rag.config\n"
        "import rag.api.database as database\n"
        "import rag.api.auth as auth\n"
        "import rag.api.routes.auth as routes_auth\n" + "\n".join(statements)
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()


def test_database_url_from_env_file_applies_despite_import_order(tmp_path: Path) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "DATABASE_URL=sqlite+aiosqlite:///./marcador_c1_database.db\n"
        "JWT_SECRET_KEY=un-secreto-de-prueba-suficientemente-largo\n"
    )

    out = _import_main_and_print(
        _minimal_env(RAG_ENV_FILE=str(env_file)),
        ["print(database.engine.url)"],
    )
    assert "marcador_c1_database" in out[0]


def test_jwt_algorithm_and_expiry_from_env_file_apply_despite_import_order(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "JWT_ALGORITHM=HS512\n"
        "JWT_EXPIRE_MINUTES=42\n"
        "JWT_SECRET_KEY=un-secreto-de-prueba-suficientemente-largo\n"
    )

    out = _import_main_and_print(
        _minimal_env(RAG_ENV_FILE=str(env_file)),
        ["print(auth._ALGORITHM)", "print(auth._EXPIRE_MINUTES)"],
    )
    assert out == ["HS512", "42"]


def test_register_enabled_from_env_file_applies_despite_import_order(tmp_path: Path) -> None:
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "REGISTER_ENABLED=true\nJWT_SECRET_KEY=un-secreto-de-prueba-suficientemente-largo\n"
    )

    out = _import_main_and_print(
        _minimal_env(RAG_ENV_FILE=str(env_file)),
        ["print(routes_auth._REGISTER_ENABLED)"],
    )
    assert out == ["True"]


def test_process_env_vars_still_take_precedence_over_env_file(tmp_path: Path) -> None:
    """Las variables ya presentes en el proceso real (Docker/ECS/CI) deben
    seguir ganando sobre el .env — python-dotenv no sobreescribe por
    defecto."""
    env_file = tmp_path / "custom.env"
    env_file.write_text(
        "DATABASE_URL=sqlite+aiosqlite:///./no_deberia_usarse.db\n"
        "JWT_SECRET_KEY=un-secreto-de-prueba-suficientemente-largo\n"
    )

    out = _import_main_and_print(
        _minimal_env(
            RAG_ENV_FILE=str(env_file),
            DATABASE_URL="sqlite+aiosqlite:///./desde_proceso_real.db",
        ),
        ["print(database.engine.url)"],
    )
    assert "desde_proceso_real" in out[0]
    assert "no_deberia_usarse" not in out[0]


def test_missing_rag_env_file_still_fails_loudly_before_app_import() -> None:
    env = _minimal_env(RAG_ENV_FILE="/no/existe/en/absoluto.env")
    result = subprocess.run(
        [sys.executable, "-c", "import rag.api.main"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "RAG_ENV_FILE" in result.stderr
    assert "FileNotFoundError" in result.stderr
