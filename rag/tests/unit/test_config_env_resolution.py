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
from rag.config import _env, _find_repo_root, _parse_mode, _resolve_env_file

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


@pytest.fixture
def minimal_env(tmp_path: Path):
    """Fábrica de entornos mínimos para subprocesos de prueba.

    Por defecto, ``RAG_ENV_FILE`` apunta a un ``.env`` vacío propio de esta
    llamada — nunca al ``.env`` real de este repo — así que un subproceso
    que use este entorno sin más parte genuinamente de "nada configurado".
    Una prueba que sí quiera validar carga real de un ``.env`` pasa su
    propio ``RAG_ENV_FILE`` explícito en ``overrides`` (como ya hacen
    ``test_rag_env_file_is_actually_loaded_into_constants`` y
    ``test_rag_env_file_missing_fails_loudly_at_import``), que gana sobre
    este valor por defecto.

    C2: sin ``RAG_ENV_FILE`` fijado explícitamente, ``_resolve_env_file()``
    sigue buscando hacia arriba (cwd, luego la raíz del repo) y termina
    cargando el ``.env`` real de un desarrollador si existe, contaminando
    cualquier prueba que asuma "sin configuración" o "solo mi alias" —
    reproducido localmente: con un ``rag/.env`` real presente, 4 de estas
    pruebas fallaban sin este valor por defecto.

    H3: cada llamada crea su propio ``.env`` vacío dentro de ``tmp_path`` —
    el directorio temporal que pytest crea y limpia por prueba — en vez de
    ``tempfile.mkstemp()`` directamente en la raíz del directorio temporal
    del sistema, que no se borraba nunca (21 archivos sueltos tras una
    corrida completa de esta suite, ver
    ``test_minimal_env_does_not_leak_env_files_into_the_system_tmp_root``).
    """
    counter = {"n": 0}

    def _make(**overrides: str) -> dict[str, str]:
        counter["n"] += 1
        empty_env_file = tmp_path / f"minimal-{counter['n']}.env"
        empty_env_file.write_text("", encoding="utf-8")

        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("CHROMA_", "OLLAMA_", "RAG_ENV_FILE"))
        }
        env["RAG_ENV_FILE"] = str(empty_env_file)
        env.update(overrides)
        return env

    return _make


def test_minimal_env_does_not_leak_env_files_into_the_system_tmp_root(minimal_env) -> None:
    """H3: ``_empty_env_file()`` usaba ``tempfile.mkstemp()``, que crea el
    archivo directamente en la raíz del directorio temporal del sistema
    (``tempfile.gettempdir()``) y nunca lo borraba — 21 archivos ``.env``
    quedaron ahí tras una corrida completa de esta suite durante la
    verificación independiente. El reemplazo (fixture ``minimal_env``, ver
    arriba) delega el ciclo de vida a ``tmp_path`` — que pytest administra
    en un subdirectorio propio, nunca en la raíz del directorio temporal del
    sistema — así que la raíz del sistema no debe recibir ningún ``.env``
    nuevo al construir un entorno mínimo."""
    system_tmp_root = Path(tempfile.gettempdir())
    before = set(system_tmp_root.glob("*.env"))

    minimal_env()

    after = set(system_tmp_root.glob("*.env"))
    new_files = after - before
    assert not new_files, f"archivos .env nuevos en la raíz del tmp del sistema: {new_files}"


def test_chroma_collection_name_alias_used_when_primary_absent(minimal_env) -> None:
    out = _import_and_print(
        minimal_env(CHROMA_COLLECTION_NAME="legacy_name"), ["CHROMA_COLLECTION"]
    )
    assert out == ["legacy_name"]


def test_chroma_collection_primary_wins_over_alias(minimal_env) -> None:
    out = _import_and_print(
        minimal_env(CHROMA_COLLECTION="nueva", CHROMA_COLLECTION_NAME="legacy_name"),
        ["CHROMA_COLLECTION"],
    )
    assert out == ["nueva"]


def test_ollama_rerank_model_accepts_legacy_rerankermodel_alias(minimal_env) -> None:
    out = _import_and_print(
        minimal_env(OLLAMA_RERANKER_MODEL="mistral-legacy"), ["OLLAMA_RERANK_MODEL"]
    )
    assert out == ["mistral-legacy"]


def test_ollama_rerank_model_none_when_nothing_set(minimal_env) -> None:
    out = _import_and_print(minimal_env(), ["OLLAMA_RERANK_MODEL"])
    assert out == ["None"]


def test_ollama_embedding_aliases_resolve(minimal_env) -> None:
    out = _import_and_print(
        minimal_env(OLLAMA_EMBED_BASE_URL="http://legacy:11434", OLLAMA_EMBED_MODEL="legacy-model"),
        ["OLLAMA_BASE_URL", "OLLAMA_EMBEDDING_MODEL"],
    )
    assert out == ["http://legacy:11434", "legacy-model"]


def test_rag_env_file_is_actually_loaded_into_constants(tmp_path: Path, minimal_env) -> None:
    """Extremo a extremo: RAG_ENV_FILE apuntando a un .env real cambia el
    valor de una constante de config.py — antes de esta entrega, esto no
    funcionaba salvo que otro módulo ya hubiera cargado el .env primero."""
    env_file = tmp_path / "custom.env"
    env_file.write_text("CHROMA_COLLECTION=desde_rag_env_file\n")

    out = _import_and_print(
        minimal_env(RAG_ENV_FILE=str(env_file)),
        ["CHROMA_COLLECTION"],
    )
    assert out == ["desde_rag_env_file"]


def test_rag_env_file_missing_fails_loudly_at_import(minimal_env) -> None:
    env = minimal_env(RAG_ENV_FILE="/no/existe/en/absoluto.env")
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


# ---------------------------------------------------------------------------
# _parse_mode() — A1.3: off/observe/enforce estricto, sin default silencioso
# ---------------------------------------------------------------------------
#
# RAG_RATE_LIMIT_MODE, TITLE_RATE_LIMIT_MODE, AUTH_RATE_LIMIT_MODE y
# RAG_BACKPRESSURE_MODE comparten esta validación. Antes, un valor no
# reconocido (typo, valor de otra versión, etc.) se degradaba en silencio a
# "off" — desactivando una protección sin ningún aviso. Ahora falla de forma
# explícita, nombrando la variable, al importar rag.config.


@pytest.mark.parametrize("value", ["off", "observe", "enforce"])
def test_parse_mode_accepts_the_three_valid_values(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOME_MODE_VAR", value)
    assert _parse_mode("SOME_MODE_VAR") == value


def test_parse_mode_is_case_insensitive_and_strips_whitespace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOME_MODE_VAR", "  ENFORCE  ")
    assert _parse_mode("SOME_MODE_VAR") == "enforce"


def test_parse_mode_uses_default_when_var_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SOME_MODE_VAR", raising=False)
    assert _parse_mode("SOME_MODE_VAR") == "off"
    assert _parse_mode("SOME_MODE_VAR", default="observe") == "observe"


def test_parse_mode_raises_and_names_the_variable_on_invalid_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SOME_MODE_VAR", "enable")
    with pytest.raises(ValueError, match="SOME_MODE_VAR") as error:
        _parse_mode("SOME_MODE_VAR")
    assert "enable" in str(error.value)


def test_parse_mode_treats_empty_string_as_invalid_not_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A diferencia de _env(), aquí una variable *definida* pero vacía es un
    # valor inválido explícito, no "no definida" — evita que un despliegue
    # con RAG_RATE_LIMIT_MODE="" (en vez de ausente) se interprete como off.
    monkeypatch.setenv("SOME_MODE_VAR", "")
    with pytest.raises(ValueError, match="SOME_MODE_VAR"):
        _parse_mode("SOME_MODE_VAR")


@pytest.mark.parametrize(
    "env_var",
    [
        "RAG_RATE_LIMIT_MODE",
        "TITLE_RATE_LIMIT_MODE",
        "AUTH_RATE_LIMIT_MODE",
        "RAG_BACKPRESSURE_MODE",
    ],
)
def test_invalid_mode_env_var_fails_loudly_at_import(env_var: str, minimal_env) -> None:
    env = minimal_env(**{env_var: "not-a-valid-mode"})
    result = subprocess.run(
        [sys.executable, "-c", "from rag import config"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0, result.stdout
    assert env_var in result.stderr
    assert "ValueError" in result.stderr


def test_all_four_mode_constants_default_to_off_when_unset(minimal_env) -> None:
    out = _import_and_print(
        minimal_env(),
        [
            "RATE_LIMIT_MODE",
            "TITLE_RATE_LIMIT_MODE",
            "AUTH_RATE_LIMIT_MODE",
            "BACKPRESSURE_MODE",
        ],
    )
    assert out == ["off", "off", "off", "off"]


# ---------------------------------------------------------------------------
# PASSWORD_HASH_MAX_CONCURRENT — C1/3.1: >= 1 exigido explícitamente al
# importar, sin degradarse en silencio a un valor por defecto.
# ---------------------------------------------------------------------------


def test_password_hash_max_concurrent_defaults_to_two(minimal_env) -> None:
    out = _import_and_print(minimal_env(), ["PASSWORD_HASH_MAX_CONCURRENT"])
    assert out == ["2"]


def test_password_hash_max_concurrent_reads_the_env_var(minimal_env) -> None:
    out = _import_and_print(
        minimal_env(PASSWORD_HASH_MAX_CONCURRENT="5"), ["PASSWORD_HASH_MAX_CONCURRENT"]
    )
    assert out == ["5"]


@pytest.mark.parametrize("invalid_value", ["0", "-1", "-100"])
def test_password_hash_max_concurrent_rejects_values_below_one(
    invalid_value: str, minimal_env
) -> None:
    env = minimal_env(PASSWORD_HASH_MAX_CONCURRENT=invalid_value)
    result = subprocess.run(
        [sys.executable, "-c", "from rag import config"],
        cwd=str(_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0, result.stdout
    assert "PASSWORD_HASH_MAX_CONCURRENT" in result.stderr
    assert "ValueError" in result.stderr
