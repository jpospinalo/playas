"""Pruebas de la utilidad offline de cobertura sintáctica de citas
(``evaluation/citation_coverage.py``).

Esta utilidad no es un guard online — no se importa desde ``core/agent.py``
ni desde ninguna ruta de ``api/`` — así que estas pruebas verifican
únicamente que la utilidad misma sea correcta y determinista, ya que su
salida se usa como evidencia de evaluación offline.

También confirma que reutiliza exactamente el mismo patrón de cita que
``_validate_citations()`` usa en la ruta online (``_CITATION_RE`` de
``core/agent.py``), para que no pueda divergir en silencio de lo que
producción realmente reconoce como cita.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from evaluation.citation_coverage import (
    SYNTHETIC_ANSWER_DATASET,
    analyze_citation_coverage,
    analyze_dataset,
    summarize,
)


def test_uses_the_exact_same_citation_pattern_as_the_online_gate() -> None:
    """No es una reimplementación paralela: usa el mismo objeto regex que
    ``core/agent.py::_validate_citations`` importa internamente."""
    from evaluation import citation_coverage

    from rag.core.agent import _CITATION_RE
    from rag.core.tools import CITATION_RE

    assert citation_coverage._CITATION_RE is _CITATION_RE is CITATION_RE


def test_answer_with_no_citations_is_flagged_correctly() -> None:
    result = analyze_citation_coverage("Texto sin ninguna referencia a documentos.", doc_count=3)
    assert result.has_any_citation is False
    assert result.citation_indices == []
    assert result.valid_indices == []
    assert result.invalid_indices == []
    assert result.paragraph_count == 1
    assert result.uncited_paragraph_count == 1


def test_answer_with_a_valid_citation_is_flagged_correctly() -> None:
    result = analyze_citation_coverage("El decreto aplica al caso [doc1].", doc_count=2)
    assert result.has_any_citation is True
    assert result.citation_indices == [1]
    assert result.valid_indices == [1]
    assert result.invalid_indices == []
    assert result.uncited_paragraph_count == 0


def test_citation_referencing_a_document_beyond_doc_count_is_invalid() -> None:
    """'Cita inexistente': referencia un índice que nunca fue entregado
    como contexto (doc_count=2, pero cita [doc5])."""
    from rag.core.agent import _validate_citations

    result = analyze_citation_coverage("Según el análisis [doc5].", doc_count=2)
    assert result.citation_indices == [5]
    assert result.valid_indices == []
    assert result.invalid_indices == [5]
    # La validación online (_validate_citations) rechazaría esta misma
    # respuesta por la misma razón — confirma que ambas piezas están de
    # acuerdo sobre qué cuenta como cita inexistente.
    assert _validate_citations("Según el análisis [doc5].", 2) is False


def test_citation_index_zero_or_negative_is_invalid() -> None:
    result = analyze_citation_coverage("Ver referencia [doc0].", doc_count=3)
    assert result.citation_indices == [0]
    assert result.invalid_indices == [0]
    assert result.valid_indices == []


def test_paragraphs_are_split_on_blank_lines_and_checked_independently() -> None:
    answer = "Primer párrafo con cita [doc1].\n\nSegundo párrafo sin ninguna cita."
    result = analyze_citation_coverage(answer, doc_count=2)
    assert result.paragraph_count == 2
    assert result.uncited_paragraph_count == 1
    assert result.uncited_paragraphs == ["Segundo párrafo sin ninguna cita."]


def test_a_paragraph_with_only_an_invalid_citation_still_counts_as_cited() -> None:
    """'Párrafo sin cita' es una señal puramente sintáctica (¿hay algún
    token [docN]?), independiente de si ese índice es válido — la validez
    se reporta por separado en invalid_indices."""
    answer = "Párrafo con una cita fuera de rango [doc9]."
    result = analyze_citation_coverage(answer, doc_count=1)
    assert result.uncited_paragraph_count == 0
    assert result.invalid_indices == [9]


def test_repeated_valid_citations_to_the_same_document_are_all_counted() -> None:
    answer = "Primero [doc1]. Después se reitera [doc1] y se añade [doc2]."
    result = analyze_citation_coverage(answer, doc_count=2)
    assert result.citation_indices == [1, 1, 2]
    assert result.valid_indices == [1, 1, 2]
    assert result.invalid_indices == []


def test_empty_paragraphs_from_extra_blank_lines_are_not_counted() -> None:
    answer = "Único párrafo con contenido [doc1].\n\n\n\n   \n\n"
    result = analyze_citation_coverage(answer, doc_count=1)
    assert result.paragraph_count == 1


def test_synthetic_dataset_summary_matches_a_hand_count() -> None:
    """El dataset sintético fue diseñado para cubrir las cuatro señales por
    separado — este conteo a mano documenta exactamente qué se espera de
    cada caso, y protege el resumen agregado de una regresión silenciosa."""
    rows = analyze_dataset()
    summary = summarize(rows)

    assert summary["n_respuestas"] == len(SYNTHETIC_ANSWER_DATASET) == 6
    assert summary["respuestas_sin_ninguna_cita"] == 1  # "sin_ninguna_cita"
    assert summary["respuestas_con_al_menos_una_cita"] == 5
    # Párrafos sin cita: "dos_parrafos_uno_sin_cita" (1) + "sin_ninguna_cita" (1)
    # + "tres_parrafos_cobertura_mixta" (1, el tercer párrafo) = 3.
    assert summary["parrafos_sin_cita"] == 3
    # Citas inexistentes: "cita_fuera_de_rango" ([doc5]) +
    # "tres_parrafos_cobertura_mixta" ([doc9]) = 2.
    assert summary["citas_inexistentes_totales"] == 2
    assert summary["respuestas_con_alguna_cita_inexistente"] == 2
    # Citas válidas: doc1 (parrafo_unico) + doc1 (dos_parrafos) +
    # doc1,doc1,doc2 (citas_repetidas) + doc1 (tres_parrafos) = 6.
    assert summary["citas_validas_totales"] == 6


def test_analyze_dataset_is_deterministic_across_runs() -> None:
    assert analyze_dataset() == analyze_dataset()


def test_citation_pattern_grammar_is_preserved() -> None:
    """La utilidad conserva la gramática y los flags del gate existente."""
    from evaluation import citation_coverage

    from rag.core.agent import _CITATION_RE
    from rag.core.tools import CITATION_RE

    assert citation_coverage._CITATION_RE is _CITATION_RE is CITATION_RE
    assert _CITATION_RE.pattern == r"\[doc(\d+)\]"
    assert _CITATION_RE.flags == re.IGNORECASE | re.UNICODE
    for text, expected in (
        ("", []),
        ("[doc1] [DOC2] [doc0]", ["1", "2", "0"]),
        ("[doc1] [doc1]", ["1", "1"]),
        ("[doc-1] [doc 1] [doc1.2]", []),
    ):
        assert _CITATION_RE.findall(text) == expected


# El proceso fresco es autocontenido: CI no depende de archivos externos del
# equipo. Las guardas se instalan en el hijo antes de importar la utilidad.
_CITATION_IMPORT_PROBE = r'''"""Self-contained citation import probe; P1 preparation does not execute it."""

import errno
import hashlib
import importlib.abc
import json
import os
from pathlib import Path
import socket
import sys


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


require(len(sys.argv) == 3 and sys.dont_write_bytecode, "fixed_argv_and_B_required")
RAG = Path(sys.argv[1])
OUTPUT = Path(sys.argv[2])
require(RAG.is_absolute() and RAG.resolve() == RAG, "invalid_rag_root")
require((RAG / "evaluation/citation_coverage.py").is_file(), "missing_metric_source")
require(OUTPUT.is_absolute() and OUTPUT.resolve() == OUTPUT, "invalid_probe_output")
require(OUTPUT.is_dir() and Path.cwd().resolve() == OUTPUT, "unexpected_probe_cwd")
require(not OUTPUT.is_relative_to(RAG.parent), "probe_must_be_external")
require(not (OUTPUT / "PROBE_CONTROL.json").exists(), "existing_probe_receipt")
require(not (OUTPUT / ".env").exists(), "unexpected_cwd_dotenv")
os.umask(0o077)
for name in ("home", "tmp", "cache", "config"):
    (OUTPUT / name).mkdir(mode=0o700, exist_ok=False)
os.environ.clear()
os.environ.update({
    "PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C",
    "HOME": str(OUTPUT / "home"), "TMPDIR": str(OUTPUT / "tmp"),
    "XDG_CACHE_HOME": str(OUTPUT / "cache"),
    "XDG_CONFIG_HOME": str(OUTPUT / "config"),
    "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
    "RAG_ENV_FILE": str(OUTPUT / "empty.env"),
    "LEGAL_RESOLUTION_PROVENANCE_PATH": "", "LEGAL_RESOLUTION_PROVENANCE_SHA256": "",
    "AWS_EC2_METADATA_DISABLED": "true", "ANONYMIZED_TELEMETRY": "false",
    "HF_HUB_OFFLINE": "1", "HF_DATASETS_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
})
sys.path[:0] = [str(RAG / "backend"), str(RAG)]
with (OUTPUT / "empty.env").open("x") as stream:
    stream.write("# Synthetic import-only fixture.\n")

FORBIDDEN = (
    "rag.api", "rag.config", "rag.core.agent", "rag.core.generator",
    "rag.core.retriever", "rag.core.embeddings", "rag.core.llm_factory",
    "rag.core.vectorstore", "rag.core.chroma_query", "chromadb", "langchain_chroma",
    "langgraph", "langchain_openai", "langchain_google_genai", "openai",
    "google.genai", "google.generativeai",
)
events = {"network": [], "outside_writes": [], "blocked_processes": [],
          "sensitive_reads": [], "denied_known_probes": [], "forbidden_imports": []}


class RuntimeDependencyDetected(ImportError):
    pass


class ImportGuard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == root or fullname.startswith(root + ".") for root in FORBIDDEN):
            events["forbidden_imports"].append(fullname)
            raise RuntimeDependencyDetected("runtime_dependency_detected")
        return None


def audit(event, args):
    if event == "socket.bind":
        frame = sys._getframe(1)
        source = Path(frame.f_code.co_filename)
        if (frame.f_code.co_name == "_has_ipv6"
                and source.parts[-3:] == ("urllib3", "util", "connection.py")
                and hashlib.sha256(source.read_bytes()).hexdigest()
                == "2633bbdb69731e5ccb5cf4e4afd65605d86c7979cc5633126f50c92d5ad74a74"
                and args[0].family == socket.AF_INET6 and args[1] == ("::1", 0)):
            events["denied_known_probes"].append("urllib3-ipv6-denied-before-bind")
            raise OSError(errno.EPERM, "offline_capability_unavailable")
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.bind",
                 "socket.listen", "socket.sendto", "socket.gethostbyname", "socket.gethostbyaddr"}:
        events["network"].append(event)
        raise RuntimeError("network_denied")
    if event in {"subprocess.Popen", "os.posix_spawn", "os.system", "os.exec", "os.fork", "os.forkpty"}:
        events["blocked_processes"].append(event)
        raise RuntimeError("probe_children_denied")
    if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
        path = Path(os.fsdecode(args[0])).resolve()
        writing = (isinstance(args[1], str) and any(char in args[1] for char in "wax+"))
        writing = writing or (isinstance(args[2], int) and bool(args[2] & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)))
        if writing and path != Path(os.devnull) and not path.is_relative_to(OUTPUT):
            events["outside_writes"].append("open")
            raise RuntimeError("outside_write_denied")
        if not writing and (path.name == ".env" or path.suffix == ".pem"
                            or ".aws" in path.parts or path.is_relative_to(RAG.parent / "data")):
            events["sensitive_reads"].append("unrelated_input")
            raise RuntimeError("sensitive_read_denied")
    mutations = {"os.mkdir": [0], "os.remove": [0], "os.rmdir": [0], "os.chmod": [0],
                 "os.utime": [0], "os.truncate": [0], "os.rename": [0, 1],
                 "os.link": [0, 1], "os.symlink": [1]}
    for offset in mutations.get(event, []):
        if isinstance(args[offset], (str, bytes, os.PathLike)):
            target = Path(os.fsdecode(args[offset])).resolve()
            if not target.is_relative_to(OUTPUT):
                events["outside_writes"].append(event)
                raise RuntimeError("outside_mutation_denied")


sys.addaudithook(audit)
sys.meta_path.insert(0, ImportGuard())
failure = None
result = None
status = "blocked"
preloaded = [name for name in sys.modules
             if any(name == root or name.startswith(root + ".") for root in FORBIDDEN)]
try:
    require(not preloaded, "forbidden_module_preloaded")
    from evaluation.citation_coverage import analyze_citation_coverage

    coverage = analyze_citation_coverage("Primero [DOC1].\n\nSegundo [doc0].", 1)
    result = coverage.as_dict()
    require(result == {
        "has_any_citation": True, "citation_indices": [1, 0],
        "valid_indices": [1], "invalid_indices": [0], "paragraph_count": 2,
        "uncited_paragraphs": [],
    }, "unexpected_metric_result")
    status = "runtime_dependency_detected" if events["forbidden_imports"] else "complete"
except RuntimeDependencyDetected:
    status = "runtime_dependency_detected"
except BaseException as exc:
    failure = type(exc).__name__
loaded = [name for name in sys.modules
          if any(name == root or name.startswith(root + ".") for root in FORBIDDEN)]
guard_clean = not any(events[key] for key in (
    "network", "outside_writes", "blocked_processes", "sensitive_reads"))
if failure is not None or not guard_clean or preloaded or loaded:
    status = "blocked"
native = {"complete": 0, "runtime_dependency_detected": 1, "blocked": 2}[status]
receipt = {"status": status, "native_returncode": native, "control_clean": guard_clean,
           "failure_class": failure, "metric_result": result, "preloaded_forbidden": preloaded,
           "loaded_forbidden": loaded, "guards_installed_before_metric_import": True,
           "not_an_os_jail": True, **events}
with (OUTPUT / "PROBE_CONTROL.json").open("x") as stream:
    json.dump(receipt, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(receipt, ensure_ascii=False))
raise SystemExit(native)
'''


def test_citation_coverage_import_does_not_load_runtime_modules(tmp_path: Path) -> None:
    """Importar y usar métricas sintácticas no debe arrancar el runtime RAG."""
    rag_root = Path(__file__).resolve().parents[2]
    child_output = tmp_path / "citation-import"
    child_output.mkdir()
    environment = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
    }
    completed = subprocess.run(
        [sys.executable, "-B", "-c", _CITATION_IMPORT_PROBE, str(rag_root), str(child_output)],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=child_output,
        env=environment,
    )
    receipt = json.loads((child_output / "PROBE_CONTROL.json").read_text())
    assert json.loads(completed.stdout) == receipt
    assert completed.stderr == ""
    assert receipt["guards_installed_before_metric_import"] is True
    assert receipt["control_clean"] is True
    assert receipt["preloaded_forbidden"] == receipt["loaded_forbidden"] == []
    assert completed.returncode == 0, receipt
    assert receipt["native_returncode"] == 0
    assert receipt["status"] == "complete"
    assert receipt["failure_class"] is None
    assert receipt["forbidden_imports"] == []
    assert receipt["metric_result"] == {
        "has_any_citation": True,
        "citation_indices": [1, 0],
        "valid_indices": [1],
        "invalid_indices": [0],
        "paragraph_count": 2,
        "uncited_paragraphs": [],
    }
