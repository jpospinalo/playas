"""T2.3 — resolución de .env y alias de variables de entorno en config.py.

Antes de esta entrega, ``config.py`` cargaba ``load_dotenv(BASE_DIR / ".env")``
con ``BASE_DIR`` resuelto a ``rag/backend`` (dos niveles arriba de
``config.py``, cuando el ``.env`` real vive en ``rag/`` — un nivel más
arriba). Como ``load_dotenv()`` con ruta explícita no busca hacia arriba, esa
llamada era, en la práctica, un no-op: ningún ``.env`` real se cargaba salvo
que otro módulo con su propio ``load_dotenv()`` ya se hubiera importado antes
en el mismo proceso.

Estas pruebas verifican los tres bloques nuevos por separado (``_env`` —
alias + tratamiento de vacío/espacios como no-definido; ``_find_repo_root`` —
localización del marcador único ``pyproject.toml`` + ``backend/``;
``_resolve_env_file`` — orden RAG_ENV_FILE → cwd → raíz del repo) y, al
final, una comprobación de extremo a extremo contra el árbol real de este
repositorio (sin tocar ningún ``.env`` real: solo confirma que el marcador
resuelve al directorio correcto).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from rag import config as config_module
from rag.config import _env, _find_repo_root, _resolve_env_file

_BACKEND_DIR = Path(config_module.__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clean_relevant_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Aísla estas pruebas de cualquier variable ya presente en el proceso
    (RAG_ENV_FILE, CHROMA_*, OLLAMA_*) para que cada caso controle
    explícitamente lo que fija."""
    for name in [
        "RAG_ENV_FILE",
        "CHROMA_HOST",
        "CHROMA_PORT",
        "CHROMA_COLLECTION",
        "CHROMA_COLLECTION_NAME",
        "OLLAMA_BASE_URL",
        "OLLAMA_EMBED_BASE_URL",
        "OLLAMA_EMBEDDING_MODEL",
        "OLLAMA_EMBED_MODEL",
        "OLLAMA_RERANK_BASE_URL",
        "OLLAMA_RERANK_MODEL",
        "OLLAMA_RERANKER_MODEL",
    ]:
        monkeypatch.delenv(name, raising=False)
    yield


# ---------------------------------------------------------------------------
# _env() — precedencia de alias + vacío/espacios como no-definido
# ---------------------------------------------------------------------------


def test_env_returns_default_when_nothing_set() -> None:
    assert _env("FOO", "BAR", default="fallback") == "fallback"


def test_env_returns_none_default_when_no_default_given() -> None:
    assert _env("FOO") is None


def test_env_prefers_first_name_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "valor-foo")
    monkeypatch.setenv("BAR", "valor-bar")
    assert _env("FOO", "BAR", default="fallback") == "valor-foo"


def test_env_falls_back_to_second_name_when_first_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BAR", "valor-bar")
    assert _env("FOO", "BAR", default="fallback") == "valor-bar"


def test_env_treats_empty_string_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "")
    monkeypatch.setenv("BAR", "valor-bar")
    assert _env("FOO", "BAR", default="fallback") == "valor-bar"


def test_env_treats_whitespace_only_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "   ")
    assert _env("FOO", default="fallback") == "fallback"


def test_env_all_names_empty_returns_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOO", "")
    monkeypatch.setenv("BAR", "  ")
    assert _env("FOO", "BAR", default="fallback") == "fallback"


# ---------------------------------------------------------------------------
# _find_repo_root() — marcador único pyproject.toml + backend/
# ---------------------------------------------------------------------------


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def test_find_repo_root_locates_marker_directly(tmp_path: Path) -> None:
    root = tmp_path / "rag"
    _touch(root / "pyproject.toml")
    (root / "backend").mkdir(parents=True)

    assert _find_repo_root(root) == root


def test_find_repo_root_walks_up_from_nested_file(tmp_path: Path) -> None:
    root = tmp_path / "rag"
    _touch(root / "pyproject.toml")
    (root / "backend").mkdir(parents=True)
    nested = root / "backend" / "rag" / "core"
    nested.mkdir(parents=True)

    assert _find_repo_root(nested / "retriever.py") == root


def test_find_repo_root_requires_both_pyproject_and_backend_dir(tmp_path: Path) -> None:
    # pyproject.toml sin backend/ al lado (como ingesta/pyproject.toml real).
    only_pyproject = tmp_path / "ingesta"
    _touch(only_pyproject / "pyproject.toml")

    assert _find_repo_root(only_pyproject) is None


def test_find_repo_root_does_not_match_pyproject_inside_backend(tmp_path: Path) -> None:
    # rag/backend/pyproject.toml no cuenta: backend/ no tiene su propio
    # subdirectorio backend/ al lado.
    backend_dir = tmp_path / "rag" / "backend"
    _touch(backend_dir / "pyproject.toml")

    assert _find_repo_root(backend_dir) is None


def test_find_repo_root_returns_none_when_absent(tmp_path: Path) -> None:
    lonely = tmp_path / "sin_marcador" / "sub"
    lonely.mkdir(parents=True)
    assert _find_repo_root(lonely) is None


def test_find_repo_root_resolves_the_real_repository_root() -> None:
    """Sanity check de extremo a extremo contra el árbol real del repo (sin
    tocar ningún .env): confirma que, partiendo de config.py de verdad, el
    marcador resuelve exactamente a rag/ — no a rag/backend/ (el BASE_DIR
    histórico, roto) ni a la raíz del monorepo."""
    real_config_path = Path(config_module.__file__).resolve()
    root = _find_repo_root(real_config_path)

    assert root is not None
    assert root.name == "rag"
    assert (root / "pyproject.toml").is_file()
    assert (root / "backend").is_dir()
    assert (root / ".env.example").is_file()


# ---------------------------------------------------------------------------
# _resolve_env_file() — RAG_ENV_FILE → cwd → raíz del repo
# ---------------------------------------------------------------------------


def test_resolve_env_file_raises_when_rag_env_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "no-existe.env"
    monkeypatch.setenv("RAG_ENV_FILE", str(missing))

    with pytest.raises(FileNotFoundError, match="RAG_ENV_FILE"):
        _resolve_env_file()


def test_resolve_env_file_uses_rag_env_file_when_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "custom.env"
    explicit.write_text("FOO=1\n")
    monkeypatch.setenv("RAG_ENV_FILE", str(explicit))

    assert _resolve_env_file() == explicit


def test_resolve_env_file_prefers_rag_env_file_over_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "custom.env"
    explicit.write_text("FOO=1\n")
    monkeypatch.setenv("RAG_ENV_FILE", str(explicit))

    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    (cwd_dir / ".env").write_text("FOO=2\n")
    monkeypatch.chdir(cwd_dir)

    assert _resolve_env_file() == explicit


def test_resolve_env_file_uses_cwd_env_when_no_rag_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir()
    (cwd_dir / ".env").write_text("FOO=1\n")
    monkeypatch.chdir(cwd_dir)

    assert _resolve_env_file() == cwd_dir / ".env"


def test_resolve_env_file_falls_back_to_repo_root_when_no_cwd_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "rag"
    _touch(root / "pyproject.toml")
    backend_dir = root / "backend"
    (backend_dir / "rag").mkdir(parents=True)
    (root / ".env").write_text("FOO=1\n")

    cwd_dir = tmp_path / "cwd_sin_env"
    cwd_dir.mkdir()
    monkeypatch.chdir(cwd_dir)
    monkeypatch.setattr(config_module, "__file__", str(backend_dir / "rag" / "config.py"))

    assert _resolve_env_file() == root / ".env"


def test_resolve_env_file_returns_none_when_nothing_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd_dir = tmp_path / "cwd_vacio"
    cwd_dir.mkdir()
    monkeypatch.chdir(cwd_dir)
    monkeypatch.setattr(config_module, "__file__", str(tmp_path / "huerfano" / "config.py"))

    assert _resolve_env_file() is None


# ---------------------------------------------------------------------------
# Constantes de módulo — se fijan una sola vez al importar, así que los
# alias solo se pueden verificar en un proceso nuevo (subprocess), con la
# variable de entorno ya puesta ANTES del import.
# ---------------------------------------------------------------------------


def _import_and_print(env: dict[str, str], attrs: list[str]) -> list[str]:
    code = "from rag import config\n" + "\n".join(f"print(config.{a})" for a in attrs)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip().splitlines()


def _empty_env_file() -> str:
    """Ruta a un .env vacío recién creado — NUNCA el ``rag/.env`` real de
    este repo, aunque exista en disco. C2: antes, ``_minimal_env()`` se
    limitaba a *eliminar* ``RAG_ENV_FILE`` del entorno copiado, sin fijarlo a
    ningún valor — eso deja que ``_resolve_env_file()`` siga buscando hacia
    arriba (cwd, luego la raíz del repo) y termine cargando el ``.env`` real
    de un desarrollador si existe, contaminando cualquier prueba que asuma
    "sin configuración" o "solo mi alias". Reproducido localmente: con un
    ``rag/.env`` real presente, 4 de estas pruebas fallaban antes de este
    cambio."""
    fd, path = tempfile.mkstemp(suffix=".env")
    os.close(fd)
    return path


def _minimal_env(**overrides: str) -> dict[str, str]:
    """Entorno mínimo para subprocesos de prueba.

    Por defecto, ``RAG_ENV_FILE`` apunta a un ``.env`` vacío propio de esta
    llamada — nunca al ``.env`` real de este repo — así que un subproceso
    que use este entorno sin más parte genuinamente de "nada configurado".
    Una prueba que sí quiera validar carga real de un ``.env`` pasa su
    propio ``RAG_ENV_FILE`` explícito en ``overrides`` (como ya hacen
    ``test_rag_env_file_is_actually_loaded_into_constants`` y
    ``test_rag_env_file_missing_fails_loudly_at_import``), que gana sobre
    este valor por defecto.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CHROMA_", "OLLAMA_", "RAG_ENV_FILE"))
    }
    env["RAG_ENV_FILE"] = _empty_env_file()
    env.update(overrides)
    return env


def test_chroma_collection_name_alias_used_when_primary_absent() -> None:
    out = _import_and_print(
        _minimal_env(CHROMA_COLLECTION_NAME="legacy_name"), ["CHROMA_COLLECTION"]
    )
    assert out == ["legacy_name"]


def test_chroma_collection_primary_wins_over_alias() -> None:
    out = _import_and_print(
        _minimal_env(CHROMA_COLLECTION="nueva", CHROMA_COLLECTION_NAME="legacy_name"),
        ["CHROMA_COLLECTION"],
    )
    assert out == ["nueva"]


def test_ollama_rerank_model_accepts_legacy_rerankermodel_alias() -> None:
    out = _import_and_print(
        _minimal_env(OLLAMA_RERANKER_MODEL="mistral-legacy"), ["OLLAMA_RERANK_MODEL"]
    )
    assert out == ["mistral-legacy"]


def test_ollama_rerank_model_none_when_nothing_set() -> None:
    out = _import_and_print(_minimal_env(), ["OLLAMA_RERANK_MODEL"])
    assert out == ["None"]


def test_ollama_embedding_aliases_resolve() -> None:
    out = _import_and_print(
        _minimal_env(
            OLLAMA_EMBED_BASE_URL="http://legacy:11434", OLLAMA_EMBED_MODEL="legacy-model"
        ),
        ["OLLAMA_BASE_URL", "OLLAMA_EMBEDDING_MODEL"],
    )
    assert out == ["http://legacy:11434", "legacy-model"]


def test_rag_env_file_is_actually_loaded_into_constants(tmp_path: Path) -> None:
    """Extremo a extremo: RAG_ENV_FILE apuntando a un .env real cambia el
    valor de una constante de config.py — antes de esta entrega, esto no
    funcionaba salvo que otro módulo ya hubiera cargado el .env primero."""
    env_file = tmp_path / "custom.env"
    env_file.write_text("CHROMA_COLLECTION=desde_rag_env_file\n")

    out = _import_and_print(
        _minimal_env(RAG_ENV_FILE=str(env_file)),
        ["CHROMA_COLLECTION"],
    )
    assert out == ["desde_rag_env_file"]


def test_rag_env_file_missing_fails_loudly_at_import() -> None:
    env = _minimal_env(RAG_ENV_FILE="/no/existe/en/absoluto.env")
    result = subprocess.run(
        [sys.executable, "-c", "from rag import config"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "RAG_ENV_FILE" in result.stderr
    assert "FileNotFoundError" in result.stderr
