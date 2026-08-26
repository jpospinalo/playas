"""T1.3 — salvaguardas de los scripts operativos de Chroma.

Prohibido tocar Chroma real en estas pruebas: todo se ejercita con clientes
falsos (``FakeChromaClient``) y, para los dos casos de resolución de
``CHROMA_HOST``, con una copia del script en un directorio temporal ejecutada
en un subproceso — nunca contra un servidor real.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# ``utils/`` no es un paquete (sin __init__.py); se añade su directorio al
# path para poder importar los scripts por nombre, como hará quien los
# invoque con ``python utils/chroma_count.py``.
_UTILS_DIR = Path(__file__).resolve().parents[2] / "utils"
if str(_UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(_UTILS_DIR))

import chroma_clear  # noqa: E402
import chroma_count  # noqa: E402


class FakeCollection:
    def __init__(self, count: int) -> None:
        self._count = count

    def count(self) -> int:
        return self._count


class FakeChromaClient:
    """Cliente falso que solo implementa lo que cada script necesita.

    ``get_or_create_collection`` deliberadamente NO existe: si algún cambio
    futuro reintroduce esa llamada, la prueba falla con ``AttributeError`` en
    vez de crear una colección en silencio.
    """

    def __init__(self, collections: dict[str, int] | None = None) -> None:
        self._collections = dict(collections or {})
        self.deleted: list[str] = []
        self.created: list[str] = []

    def get_collection(self, name: str) -> FakeCollection:
        if name not in self._collections:
            raise ValueError(f"Collection {name} does not exist.")
        return FakeCollection(self._collections[name])

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)
        self._collections.pop(name, None)

    def create_collection(self, name: str) -> FakeCollection:
        self.created.append(name)
        self._collections[name] = 0
        return FakeCollection(0)


# ---------------------------------------------------------------------------
# chroma_count.py
# ---------------------------------------------------------------------------


def test_count_collection_reads_existing_collection() -> None:
    client = FakeChromaClient({"rag_playas": 42})
    assert chroma_count.count_collection(client, "rag_playas") == 42


def test_count_collection_never_creates_missing_collection() -> None:
    client = FakeChromaClient({})
    with pytest.raises(ValueError, match="does not exist"):
        chroma_count.count_collection(client, "rag_playas")
    assert client.created == []


def test_chroma_count_main_reports_count_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeChromaClient({chroma_count.CHROMA_COLLECTION: 7})
    monkeypatch.setattr(chroma_count.chromadb, "HttpClient", lambda **kwargs: client)

    exit_code = chroma_count.main()

    assert exit_code == 0
    assert "7" in capsys.readouterr().out


def test_chroma_count_main_fails_clearly_when_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = FakeChromaClient({})
    monkeypatch.setattr(chroma_count.chromadb, "HttpClient", lambda **kwargs: client)

    exit_code = chroma_count.main()

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "No fue posible leer la colección" in out
    assert client.created == []


# ---------------------------------------------------------------------------
# chroma_clear.py — describe_collection / confirm / run
# ---------------------------------------------------------------------------


def test_describe_collection_never_creates() -> None:
    client = FakeChromaClient({"rag_playas": 5})
    assert chroma_clear.describe_collection(client, "rag_playas") == 5
    assert client.created == []


def test_confirm_cancels_when_not_interactive() -> None:
    calls: list[str] = []
    ok = chroma_clear.confirm(
        "rag_playas",
        interactive=False,
        read_input=lambda prompt: calls.append(prompt) or "rag_playas",
    )
    assert ok is False
    assert calls == []  # ni siquiera se pregunta


def test_confirm_cancels_on_mismatched_input() -> None:
    ok = chroma_clear.confirm("rag_playas", interactive=True, read_input=lambda _: "otra_cosa")
    assert ok is False


def test_confirm_accepts_exact_match() -> None:
    ok = chroma_clear.confirm("rag_playas", interactive=True, read_input=lambda _: "rag_playas")
    assert ok is True


def test_confirm_rejects_case_or_whitespace_variants() -> None:
    assert (
        chroma_clear.confirm("rag_playas", interactive=True, read_input=lambda _: "RAG_PLAYAS")
        is False
    )
    assert (
        chroma_clear.confirm("rag_playas", interactive=True, read_input=lambda _: "  rag_playas")
        is True
    )
    # strip() del lado de la respuesta es tolerable (espacios accidentales al
    # teclear); un nombre distinto o con mayúsculas distintas no lo es.


def test_run_dry_run_by_default_never_deletes() -> None:
    client = FakeChromaClient({"rag_playas": 10})
    exit_code = chroma_clear.run(client, "rag_playas", execute=False, interactive=True)

    assert exit_code == 0
    assert client.deleted == []
    assert client.created == []


def test_run_empty_collection_never_deletes_even_with_execute() -> None:
    client = FakeChromaClient({"rag_playas": 0})
    exit_code = chroma_clear.run(client, "rag_playas", execute=True, interactive=True)

    assert exit_code == 0
    assert client.deleted == []


def test_run_execute_without_interactive_cancels_without_prompting() -> None:
    client = FakeChromaClient({"rag_playas": 3})
    prompted = []
    exit_code = chroma_clear.run(
        client,
        "rag_playas",
        execute=True,
        interactive=False,
        read_input=lambda p: prompted.append(p) or "rag_playas",
    )

    assert exit_code == 1
    assert prompted == []
    assert client.deleted == []


def test_run_execute_with_wrong_confirmation_cancels() -> None:
    client = FakeChromaClient({"rag_playas": 3})
    exit_code = chroma_clear.run(
        client, "rag_playas", execute=True, interactive=True, read_input=lambda _: "no"
    )

    assert exit_code == 1
    assert client.deleted == []


def test_run_execute_with_exact_confirmation_deletes_and_recreates() -> None:
    client = FakeChromaClient({"rag_playas": 3})
    exit_code = chroma_clear.run(
        client,
        "rag_playas",
        execute=True,
        interactive=True,
        read_input=lambda _: "rag_playas",
    )

    assert exit_code == 0
    assert client.deleted == ["rag_playas"]
    assert client.created == ["rag_playas"]


def test_run_shows_host_name_and_count(capsys: pytest.CaptureFixture[str]) -> None:
    client = FakeChromaClient({"rag_playas": 99})
    chroma_clear.run(client, "rag_playas", execute=False, interactive=True)

    out = capsys.readouterr().out
    assert chroma_clear.CHROMA_HOST in out
    assert "rag_playas" in out
    assert "99" in out


def test_run_missing_collection_fails_clearly_without_touching_client() -> None:
    client = FakeChromaClient({})
    exit_code = chroma_clear.run(client, "no_existe", execute=True, interactive=True)

    assert exit_code == 1
    assert client.deleted == []
    assert client.created == []


def test_main_requires_explicit_collection_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["chroma_clear.py"])
    with pytest.raises(SystemExit):
        chroma_clear.main()


# ---------------------------------------------------------------------------
# Resolución de host: no cae silenciosamente a localhost si rag/.env define
# otro host. Se ejecuta en subproceso sobre una copia del script en un
# directorio temporal — nunca importando el módulo real ya cacheado, y sin
# tocar ningún servidor.
# ---------------------------------------------------------------------------


def _run_import_and_print_host(tmp_path: Path, script_name: str) -> str:
    rag_dir = tmp_path / "rag"
    utils_dir = rag_dir / "utils"
    utils_dir.mkdir(parents=True)
    (rag_dir / ".env").write_text("CHROMA_HOST=chroma.interno.example\nCHROMA_PORT=9000\n")
    source = (_UTILS_DIR / script_name).read_text()
    (utils_dir / script_name).write_text(source)

    module_name = script_name.removesuffix(".py")
    result = subprocess.run(
        [sys.executable, "-c", f"import {module_name}; print({module_name}.CHROMA_HOST)"],
        cwd=str(utils_dir),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_chroma_count_reads_host_from_env_file(tmp_path: Path) -> None:
    assert _run_import_and_print_host(tmp_path, "chroma_count.py") == "chroma.interno.example"


def test_chroma_clear_reads_host_from_env_file(tmp_path: Path) -> None:
    assert _run_import_and_print_host(tmp_path, "chroma_clear.py") == "chroma.interno.example"
