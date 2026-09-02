"""Pruebas offline de ``evaluation/ragas_common.py`` — la infraestructura
compartida por ``ragas_eval_gemma.py`` y ``ragas_eval_ollama.py``.

Ninguna prueba de este archivo llama a un LLM real, a Ollama, a ChromaDB
ni a RAGAS real: ``generate_answer`` se sustituye por un doble en cada
prueba que lo necesita, y las pruebas que ejercitan ``run_metrics()``
inyectan un módulo ``ragas`` falso en ``sys.modules``. El paquete real
``ragas`` sí es importable en este entorno (con el pin de
``langchain-community==0.3.31`` del grupo ``dev``, ver el comentario junto
a ese pin en ``pyproject.toml``) pero, aun así, ninguna prueba de este
archivo lo importa de verdad: no hace falta red ni credenciales para
probar esta lógica, y un doble es más rápido y determinista.

La garantía de que nada aquí dispara un import real de ``ragas`` (u otra
regresión equivalente) no se repite prueba por prueba: vive en
``tests/unit/test_ragas_import_isolation.py``, en tres pruebas aisladas
en subproceso que sí observan un intérprete limpio de verdad.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from evaluation.ragas_common import (
    AMBIGUOUS_DOCUMENT_CASE_IDS,
    RagasMetricsError,
    build_ragas_dataset,
    case_ids_evaluated,
    dataset_sha256,
    generate_case_rows,
    git_state,
    normalize_required_env,
    run_metrics,
    summarize,
    validate_only,
    wants_validate_only,
    write_report,
)


def _fake_case(
    case_id: str, pregunta: str = "¿Pregunta?", respuesta: str = "Respuesta."
) -> dict[str, str]:
    return {
        "id": case_id,
        "doc_principal": "N-01",
        "doc_secundario": "No aplica",
        "pregunta": pregunta,
        "respuesta": respuesta,
        "ubicacion_evidencia": "p. 1",
    }


# ============================================================
#  AMBIGUOUS_DOCUMENT_CASE_IDS
# ============================================================


def test_ambiguous_document_case_ids_are_exactly_registros_17_to_22() -> None:
    assert AMBIGUOUS_DOCUMENT_CASE_IDS == frozenset({f"registro-0{n}" for n in range(17, 23)})


# ============================================================
#  dataset_sha256 / git_state
# ============================================================


def test_dataset_sha256_matches_hash_of_the_file_on_disk(tmp_path: Path) -> None:
    dataset_file = tmp_path / "dataset.json"
    dataset_file.write_bytes(b"contenido de prueba")
    import hashlib

    expected = hashlib.sha256(b"contenido de prueba").hexdigest()
    assert dataset_sha256(dataset_file) == expected


def test_dataset_sha256_default_path_matches_real_versioned_dataset() -> None:
    # Sin argumento usa default_dataset_path(): el mismo dataset que valida
    # evaluation/ground_truth.py y tests/unit/test_ground_truth_dataset.py.
    value = dataset_sha256()
    assert isinstance(value, str)
    assert len(value) == 64


def test_git_state_returns_the_real_head_and_a_bool_dirty_flag_when_git_succeeds() -> None:
    # Sin mocks: ejercita el subprocess real contra este repositorio. No se
    # asume un valor concreto de commit/dirty (dependen del estado local
    # cuando corre la prueba) -- solo la forma del resultado.
    state = git_state()
    assert state["commit"] != "desconocido"
    assert len(state["commit"]) == 40
    assert all(c in "0123456789abcdef" for c in state["commit"])
    assert isinstance(state["dirty"], bool)


def test_git_state_runs_git_with_cwd_fixed_to_this_modules_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # cwd del proceso deliberadamente distinto del directorio de
    # evaluation/: git_state() no debe depender de desde dónde se invocó el
    # proceso, solo del cwd que fija explícitamente a partir de __file__.
    captured_cwds: list[Any] = []

    def fake_run(args: list[str], **kwargs: Any) -> Any:
        captured_cwds.append(kwargs.get("cwd"))
        if args[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(stdout="a" * 40)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.chdir(Path(__file__).resolve().parent)

    import evaluation.ragas_common as ragas_common_module

    expected_dir = Path(ragas_common_module.__file__).resolve().parent
    git_state()

    assert captured_cwds == [expected_dir, expected_dir]


def test_git_state_falls_back_to_desconocido_and_dirty_none_when_git_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise FileNotFoundError("git no disponible")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert git_state() == {"commit": "desconocido", "dirty": None}


def test_git_state_reports_dirty_true_when_status_porcelain_has_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args: list[str], **kwargs: Any) -> Any:
        if args[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(stdout="b" * 40)
        return SimpleNamespace(stdout=" M algun_archivo.py\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_state() == {"commit": "b" * 40, "dirty": True}


def test_git_state_reports_dirty_false_when_tree_is_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args: list[str], **kwargs: Any) -> Any:
        if args[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(stdout="c" * 40)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_state() == {"commit": "c" * 40, "dirty": False}


def test_git_state_dirty_is_none_when_status_command_fails_but_commit_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(args: list[str], **kwargs: Any) -> Any:
        if args[:2] == ["git", "rev-parse"]:
            return SimpleNamespace(stdout="d" * 40)
        raise TimeoutError("git status tardo demasiado")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert git_state() == {"commit": "d" * 40, "dirty": None}


# ============================================================
#  normalize_required_env
# ============================================================


def test_normalize_required_env_treats_missing_empty_and_whitespace_as_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAGAS_TEST_AUSENTE", raising=False)
    monkeypatch.setenv("RAGAS_TEST_VACIA", "")
    monkeypatch.setenv("RAGAS_TEST_ESPACIOS", "   ")

    values, missing = normalize_required_env(
        ["RAGAS_TEST_AUSENTE", "RAGAS_TEST_VACIA", "RAGAS_TEST_ESPACIOS"]
    )

    assert values == {}
    assert missing == ["RAGAS_TEST_AUSENTE", "RAGAS_TEST_VACIA", "RAGAS_TEST_ESPACIOS"]


def test_normalize_required_env_returns_stripped_values_for_present_vars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAGAS_TEST_CON_ESPACIOS_ALREDEDOR", "  valor-real  ")
    monkeypatch.setenv("RAGAS_TEST_LIMPIA", "otro-valor")

    values, missing = normalize_required_env(
        ["RAGAS_TEST_CON_ESPACIOS_ALREDEDOR", "RAGAS_TEST_LIMPIA"]
    )

    assert values == {
        "RAGAS_TEST_CON_ESPACIOS_ALREDEDOR": "valor-real",
        "RAGAS_TEST_LIMPIA": "otro-valor",
    }
    assert missing == []


# ============================================================
#  generate_case_rows / _run_one_case (generate_answer con doble)
# ============================================================


def test_generate_case_rows_builds_one_row_per_case_without_truncating_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [_fake_case("registro-002"), _fake_case("registro-003")]

    docs = [SimpleNamespace(page_content=f"doc {i} [contenido]") for i in range(5)]

    def fake_generate_answer(question: str) -> tuple[str, list[Any]]:
        return f"Respuesta con cita [doc1] a: {question}", docs

    monkeypatch.setattr("evaluation.ragas_common.generate_answer", fake_generate_answer)

    rows = generate_case_rows(cases)

    assert [row["case_id"] for row in rows] == ["registro-002", "registro-003"]
    for row in rows:
        assert row["error"] is None
        assert row["doc_count"] == 5
        assert len(row["contexts"]) == 5  # ninguna trunca la lista de documentos
        assert row["citation_coverage"] is not None
        assert row["citation_coverage"]["has_any_citation"] is True


def test_generate_case_rows_labels_expected_document_metric_by_case_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [_fake_case("registro-017"), _fake_case("registro-002")]
    monkeypatch.setattr(
        "evaluation.ragas_common.generate_answer",
        lambda question: ("respuesta", []),
    )

    rows = generate_case_rows(cases)
    by_id = {row["case_id"]: row for row in rows}

    assert by_id["registro-017"]["expected_document_metric"] == "omitted:ambiguous_reference"
    assert (
        by_id["registro-002"]["expected_document_metric"]
        == "omitted:no_deterministic_mapping_available"
    )


def test_generate_case_rows_isolates_a_failing_case_without_stopping_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cases = [_fake_case("registro-002"), _fake_case("registro-003"), _fake_case("registro-004")]

    calls: list[str] = []

    def flaky_generate_answer(question: str) -> tuple[str, list[Any]]:
        calls.append(question)
        if len(calls) == 2:  # el segundo caso (registro-003) falla
            raise RuntimeError("fallo simulado del grafo")
        return "respuesta ok", []

    monkeypatch.setattr("evaluation.ragas_common.generate_answer", flaky_generate_answer)

    rows = generate_case_rows(cases)

    assert len(rows) == 3  # el fallo de uno no interrumpe a los demás
    assert rows[0]["error"] is None
    assert rows[1]["error"] is not None
    assert "RuntimeError" in rows[1]["error"]
    assert rows[1]["answer"] == ""
    assert rows[1]["citation_coverage"] is None
    assert rows[2]["error"] is None


# ============================================================
#  build_ragas_dataset
# ============================================================


def test_build_ragas_dataset_excludes_rows_with_error_and_defaults_empty_contexts() -> None:
    rows: list[dict[str, Any]] = [
        {
            "pregunta": "¿P1?",
            "answer": "R1",
            "contexts": ["ctx1"],
            "respuesta_esperada": "GT1",
            "error": None,
        },
        {
            "pregunta": "¿P2?",
            "answer": "",
            "contexts": [],
            "respuesta_esperada": "GT2",
            "error": "RuntimeError: fallo",
        },
        {
            "pregunta": "¿P3?",
            "answer": "R3",
            "contexts": [],
            "respuesta_esperada": "GT3",
            "error": None,
        },
    ]
    dataset = build_ragas_dataset(rows)

    assert len(dataset) == 2  # la fila con error queda fuera
    assert dataset["question"] == ["¿P1?", "¿P3?"]
    assert dataset["contexts"][0] == ["ctx1"]
    assert dataset["contexts"][1] == [""]  # contexts vacío -> [""], nunca []


# ============================================================
#  run_metrics — con un módulo `ragas` doble inyectado en sys.modules
# ============================================================


class _FakeEvaluationResult:
    def __init__(self, df: Any) -> None:
        self._df = df

    def to_pandas(self) -> Any:
        return self._df


def _install_fake_ragas(monkeypatch: pytest.MonkeyPatch, evaluate_impl: Any) -> None:
    """Instala un paquete `ragas` falso en sys.modules para que los imports
    diferidos de `run_metrics()` (`from ragas import evaluate`,
    `from ragas.dataset_schema import EvaluationResult`,
    `from ragas.run_config import RunConfig`) resuelvan sin tocar el
    paquete real (que en este entorno ni siquiera es importable)."""
    fake_ragas = SimpleNamespace(evaluate=evaluate_impl)
    fake_dataset_schema = SimpleNamespace(EvaluationResult=_FakeEvaluationResult)
    fake_run_config = SimpleNamespace(RunConfig=lambda **kwargs: SimpleNamespace(**kwargs))

    monkeypatch.setitem(sys.modules, "ragas", fake_ragas)
    monkeypatch.setitem(sys.modules, "ragas.dataset_schema", fake_dataset_schema)
    monkeypatch.setitem(sys.modules, "ragas.run_config", fake_run_config)


def test_case_ids_evaluated_matches_build_ragas_dataset_filter_and_order() -> None:
    rows: list[dict[str, Any]] = [
        {"case_id": "c1", "error": None},
        {"case_id": "c2", "error": "boom"},
        {"case_id": "c3", "error": None},
    ]
    assert case_ids_evaluated(rows) == ["c1", "c3"]


def test_run_metrics_associates_each_score_with_its_case_id_including_gaps_and_mean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    captured: dict[str, Any] = {}

    def fake_evaluate(**kwargs: Any) -> _FakeEvaluationResult:
        captured.update(kwargs)
        # "c2" (NaN), "c3" (+inf) y "c4" (-inf) no obtienen puntaje -- los
        # tres deben conservarse como None, nunca descartarse ni desplazar a
        # los casos siguientes ("c4"/"c5").
        df = pd.DataFrame({"faithfulness": [1.0, float("nan"), float("inf"), float("-inf"), 0.5]})
        return _FakeEvaluationResult(df)

    _install_fake_ragas(monkeypatch, fake_evaluate)

    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    judge = SimpleNamespace(name="fake-judge")
    embeddings = SimpleNamespace(name="fake-embeddings")
    dataset = ["row-c1", "row-c2", "row-c3", "row-c4", "row-c5"]  # solo importa su len()
    case_ids = ["c1", "c2", "c3", "c4", "c5"]

    result = run_metrics(
        dataset=dataset,
        metrics=[metric],
        judge=judge,
        embeddings=embeddings,
        evaluated_case_ids=case_ids,
    )

    # El judge/embeddings se propagan a cada métrica antes de evaluar, y se
    # pasan también a evaluate() junto con el dataset recibido.
    assert metric.llm is judge
    assert metric.embeddings is embeddings
    assert captured["dataset"] is dataset
    assert captured["llm"] is judge
    assert captured["embeddings"] is embeddings
    assert captured["raise_exceptions"] is False

    # Asociación exacta case_id -> puntaje, en el mismo orden recibido, con
    # NaN/+inf/-inf conservados como None (no descartados, no desplazan a
    # los casos siguientes).
    assert result["faithfulness"]["scores_by_case"] == {
        "c1": 1.0,
        "c2": None,
        "c3": None,
        "c4": None,
        "c5": 0.5,
    }
    # El promedio usa solo los puntajes finitos.
    assert result["faithfulness"]["mean"] == pytest.approx(0.75)
    assert result["faithfulness"]["scored_count"] == 2
    assert result["faithfulness"]["missing_count"] == 3


def test_run_metrics_raises_a_clear_error_when_a_score_is_not_numeric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    _install_fake_ragas(
        monkeypatch,
        evaluate_impl=lambda **kwargs: _FakeEvaluationResult(
            pd.DataFrame({"faithfulness": ["no-es-un-numero", 0.5]})
        ),
    )
    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    with pytest.raises(RagasMetricsError, match="faithfulness.*c1"):
        run_metrics(
            dataset=["r1", "r2"],
            metrics=[metric],
            judge=None,
            embeddings=None,
            evaluated_case_ids=["c1", "c2"],
        )


def test_run_metrics_raises_on_dataset_evaluated_case_ids_length_mismatch() -> None:
    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    with pytest.raises(RagasMetricsError, match="evaluated_case_ids"):
        run_metrics(
            dataset=["r1", "r2", "r3"],
            metrics=[metric],
            judge=None,
            embeddings=None,
            evaluated_case_ids=["c1", "c2"],
        )
    # El error se lanza antes de intentar importar/usar ragas.


def test_run_metrics_raises_on_metric_column_length_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    _install_fake_ragas(
        monkeypatch,
        evaluate_impl=lambda **kwargs: _FakeEvaluationResult(pd.DataFrame({"faithfulness": [1.0]})),
    )
    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    with pytest.raises(RagasMetricsError, match="faithfulness"):
        run_metrics(
            dataset=["r1", "r2"],
            metrics=[metric],
            judge=None,
            embeddings=None,
            evaluated_case_ids=["c1", "c2"],
        )


def test_run_metrics_raises_when_a_requested_metric_column_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pandas as pd

    _install_fake_ragas(
        monkeypatch,
        evaluate_impl=lambda **kwargs: _FakeEvaluationResult(
            pd.DataFrame({"other_metric": [1.0, 0.5]})
        ),
    )
    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    with pytest.raises(RagasMetricsError, match="faithfulness"):
        run_metrics(
            dataset=["r1", "r2"],
            metrics=[metric],
            judge=None,
            embeddings=None,
            evaluated_case_ids=["c1", "c2"],
        )


def test_run_metrics_raises_a_clear_error_if_evaluate_returns_something_unexpected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Guarda de tipo agregada tras el hallazgo de mypy: evaluate() declara
    # devolver `EvaluationResult | Executor`; si algún día se pasa
    # return_executor=True (o cambia el default), esto debe fallar aquí con
    # un mensaje claro, no con un AttributeError confuso más adelante. Es
    # una comprobación explícita (`if`/`raise`), no un `assert`, que Python
    # puede desactivar con optimización.
    _install_fake_ragas(monkeypatch, evaluate_impl=lambda **kwargs: object())

    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    with pytest.raises(RagasMetricsError, match="EvaluationResult"):
        run_metrics(
            dataset=["r1"],
            metrics=[metric],
            judge=None,
            embeddings=None,
            evaluated_case_ids=["c1"],
        )


def test_run_metrics_returns_empty_result_without_calling_evaluate_when_no_cases_evaluated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(**kwargs: Any) -> Any:
        raise AssertionError("evaluate() no debía invocarse con un dataset vacío")

    _install_fake_ragas(monkeypatch, evaluate_impl=_boom)

    metric_a = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    metric_b = SimpleNamespace(name="answer_relevancy", llm=None, embeddings=None)

    result = run_metrics(
        dataset=[], metrics=[metric_a, metric_b], judge=None, embeddings=None, evaluated_case_ids=[]
    )

    assert result == {
        "faithfulness": {
            "mean": None,
            "scores_by_case": {},
            "scored_count": 0,
            "missing_count": 0,
        },
        "answer_relevancy": {
            "mean": None,
            "scores_by_case": {},
            "scored_count": 0,
            "missing_count": 0,
        },
    }


def test_generation_error_case_never_appears_in_scores_by_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extremo a extremo con dobles: un caso cuya generación falló nunca
    llega a build_ragas_dataset()/case_ids_evaluated(), así que run_metrics()
    no puede ni debe producirle un puntaje -- se identifica solo por
    `error` en `rows`, no por un `None` en `scores_by_case`."""
    import pandas as pd

    cases = [
        _fake_case("registro-002", pregunta="¿Pregunta 2?"),
        _fake_case("registro-003", pregunta="¿Pregunta 3?"),
    ]

    def generate_answer_double(question: str) -> tuple[str, list[Any]]:
        if question == cases[1]["pregunta"]:
            raise RuntimeError("fallo simulado del grafo")
        return "respuesta ok", []

    monkeypatch.setattr("evaluation.ragas_common.generate_answer", generate_answer_double)

    rows = generate_case_rows(cases)
    case_ids = case_ids_evaluated(rows)
    assert case_ids == ["registro-002"]  # registro-003 falló y queda fuera

    _install_fake_ragas(
        monkeypatch,
        evaluate_impl=lambda **kwargs: _FakeEvaluationResult(pd.DataFrame({"faithfulness": [1.0]})),
    )
    metric = SimpleNamespace(name="faithfulness", llm=None, embeddings=None)
    dataset = build_ragas_dataset(rows)
    result = run_metrics(
        dataset=list(dataset),
        metrics=[metric],
        judge=None,
        embeddings=None,
        evaluated_case_ids=case_ids,
    )
    assert result["faithfulness"]["scores_by_case"] == {"registro-002": 1.0}
    assert "registro-003" not in result["faithfulness"]["scores_by_case"]
    assert rows[1]["error"] is not None  # el caso fallido sigue visible, pero por su `error`


# ============================================================
#  summarize
# ============================================================


def test_summarize_counts_errors_citations_and_ambiguous_omissions() -> None:
    rows: list[dict[str, Any]] = [
        {
            "error": None,
            "answer": "Respuesta con cita [doc1].",
            "citation_coverage": {"has_any_citation": True},
            "expected_document_metric": "omitted:ambiguous_reference",
        },
        {
            "error": None,
            "answer": "Respuesta sin cita.",
            "citation_coverage": {"has_any_citation": False},
            "expected_document_metric": "omitted:no_deterministic_mapping_available",
        },
        {
            "error": "RuntimeError: fallo",
            "answer": "",
            "citation_coverage": None,
            "expected_document_metric": "omitted:no_deterministic_mapping_available",
        },
    ]
    summary = summarize(
        rows,
        metric_results={
            "faithfulness": {
                "mean": 0.75,
                "scores_by_case": {"registro-001": 0.75},
                "scored_count": 1,
                "missing_count": 0,
            }
        },
    )

    assert summary["total_cases"] == 3
    assert summary["generation_errors"] == 1
    assert summary["answers_non_empty"] == 2
    assert summary["answers_with_at_least_one_citation"] == 1
    assert summary["expected_document_metric_omitted_ambiguous"] == 1
    assert summary["expected_document_metric_omitted_total"] == 3
    assert summary["metrics_mean"] == {"faithfulness": 0.75}


# ============================================================
#  write_report
# ============================================================


def test_write_report_writes_a_reproducible_json_report(tmp_path: Path) -> None:
    output_path = tmp_path / "results" / "reporte.json"
    rows: list[dict[str, Any]] = [
        {
            "case_id": "registro-002",
            "error": None,
            "answer": "Respuesta.",
            "citation_coverage": {"has_any_citation": True},
            "expected_document_metric": "omitted:no_deterministic_mapping_available",
        },
        {
            "case_id": "registro-003",
            "error": "RuntimeError: fallo",
            "answer": "",
            "citation_coverage": None,
            "expected_document_metric": "omitted:no_deterministic_mapping_available",
        },
    ]

    metric_results = {
        "faithfulness": {
            "mean": 1.0,
            "scores_by_case": {"registro-002": 1.0},
            "scored_count": 1,
            "missing_count": 0,
        }
    }
    write_report(
        provider="fake-provider",
        model="fake-model",
        metrics_executed=["faithfulness"],
        rows=rows,
        metric_results=metric_results,
        extra_config={"nota": "prueba"},
        output_path=output_path,
    )

    assert output_path.exists()  # crea el directorio padre si falta
    import json

    report = json.loads(output_path.read_text(encoding="utf-8"))

    assert report["provider"] == "fake-provider"
    assert report["model"] == "fake-model"
    assert report["metrics_executed"] == ["faithfulness"]
    assert report["config"] == {"nota": "prueba"}
    assert report["cases"] == rows
    # El detalle completo por caso (incluidos los None) se guarda tal cual,
    # no solo el promedio agregado en "summary".
    assert report["metric_results"] == metric_results
    assert report["errors"] == [{"case_id": "registro-003", "error": "RuntimeError: fallo"}]
    assert report["summary"]["total_cases"] == 2
    assert len(report["dataset_sha256"]) == 64
    assert isinstance(report["git"], dict)
    assert isinstance(report["git"]["commit"], str)
    assert report["git"]["dirty"] in (True, False, None)

    # El texto del archivo es JSON estándar estricto: ni siquiera contiene
    # las constantes no estándar que un json.dumps() sin allow_nan=False
    # habría podido escribir (y que un parser JSON estricto de otro
    # lenguaje rechazaría).
    raw_text = output_path.read_text(encoding="utf-8")
    for forbidden in ("NaN", "Infinity", "-Infinity"):
        assert forbidden not in raw_text


def test_write_report_raises_if_a_non_finite_value_reaches_the_report_any_other_way(
    tmp_path: Path,
) -> None:
    # allow_nan=False es el control final: un valor no finito que llegara al
    # reporte por cualquier otro campo (no por metric_results, que ya lo
    # normaliza en run_metrics()) debe hacer fallar la escritura, en vez de
    # producir un JSON con Infinity/-Infinity/NaN.
    with pytest.raises(ValueError, match="not JSON compliant"):
        write_report(
            provider="fake-provider",
            model="fake-model",
            metrics_executed=[],
            rows=[],
            metric_results={},
            extra_config={"limite_sospechoso": float("inf")},
            output_path=tmp_path / "results" / "reporte.json",
        )


def test_write_report_includes_the_git_state_it_received_and_warns_when_dirty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixed_git_state = {"commit": "e" * 40, "dirty": True}
    monkeypatch.setattr("evaluation.ragas_common.git_state", lambda: fixed_git_state)

    output_path = tmp_path / "reporte_sucio.json"
    write_report(
        provider="fake-provider",
        model="fake-model",
        metrics_executed=[],
        rows=[],
        metric_results={},
        extra_config={},
        output_path=output_path,
    )

    import json

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["git"] == fixed_git_state

    out = capsys.readouterr().out
    assert "árbol de trabajo tiene cambios sin commit" in out


def test_write_report_does_not_warn_when_git_tree_is_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixed_git_state = {"commit": "f" * 40, "dirty": False}
    monkeypatch.setattr("evaluation.ragas_common.git_state", lambda: fixed_git_state)

    output_path = tmp_path / "reporte_limpio.json"
    write_report(
        provider="fake-provider",
        model="fake-model",
        metrics_executed=[],
        rows=[],
        metric_results={},
        extra_config={},
        output_path=output_path,
    )

    import json

    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["git"] == fixed_git_state

    out = capsys.readouterr().out
    assert "árbol de trabajo tiene cambios sin commit" not in out


# ============================================================
#  wants_validate_only / validate_only
# ============================================================


def test_wants_validate_only_detects_the_flag_in_argv() -> None:
    assert wants_validate_only(["--validate-only"]) is True
    assert wants_validate_only(["--other-flag"]) is False
    assert wants_validate_only([]) is False


def test_validate_only_reports_missing_required_env_vars_and_exits_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("UNA_VARIABLE_QUE_NO_EXISTE", raising=False)
    exit_code = validate_only(["UNA_VARIABLE_QUE_NO_EXISTE"])

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "UNA_VARIABLE_QUE_NO_EXISTE" in out


def test_validate_only_succeeds_when_required_env_vars_are_present(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("UNA_VARIABLE_QUE_SI_EXISTE", "valor")
    exit_code = validate_only(["UNA_VARIABLE_QUE_SI_EXISTE"])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "configuración estática: OK" in out


# ============================================================
#  main() de los adaptadores: la ejecución real (no solo
#  --validate-only) valida la configuración obligatoria ANTES de
#  importar RAGAS -- nunca debe llegar a `from ragas.metrics import ...`
#  si falta una variable de entorno obligatoria.
#
# La garantía se instala como una guarda de import propia de cada prueba
# (ver `_forbid_ragas_import`), no leyendo `sys.modules` al terminar: así
# el resultado no depende de qué otra prueba del mismo proceso de pytest
# haya importado (o no) `ragas` antes o después.
# ============================================================


def _forbid_ragas_import(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instala una guarda temporal sobre ``builtins.__import__`` que hace
    fallar cualquier intento de importar ``ragas`` o un submódulo suyo
    durante la prueba -- delega cualquier otro import al importador real,
    sin tocar ``sys.modules`` (ni leerlo ni modificarlo) en ningún momento."""
    import builtins

    real_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "ragas" or name.startswith("ragas."):
            raise AssertionError(f"import prohibido en esta prueba: {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def _forbid_call(name: str) -> Any:
    def _fail(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"{name} no debía llamarse en esta prueba")

    return _fail


def test_gemma_main_stops_before_importing_ragas_when_required_env_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import evaluation.ragas_eval_gemma as ragas_eval_gemma

    _forbid_ragas_import(monkeypatch)
    monkeypatch.delenv("GOOGLE_API_KEY2", raising=False)
    monkeypatch.setattr(
        ragas_eval_gemma, "load_ground_truth_cases", lambda: [_fake_case("registro-002")]
    )
    # Ni siquiera se llega a construir el juez/embeddings ni a generar
    # respuestas -- ambos fallarían la prueba si se llamaran.
    monkeypatch.setattr(ragas_eval_gemma, "get_ragas_models", _forbid_call("get_ragas_models"))
    monkeypatch.setattr(ragas_eval_gemma, "generate_case_rows", _forbid_call("generate_case_rows"))
    monkeypatch.setattr(sys, "argv", ["ragas_eval_gemma.py"])

    exit_code = ragas_eval_gemma.main()

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "GOOGLE_API_KEY2" in out
    # Ningún secreto que imprimir en este camino -- solo el nombre de la
    # variable faltante.


def test_ollama_main_stops_before_importing_ragas_when_required_env_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import evaluation.ragas_eval_ollama as ragas_eval_ollama

    _forbid_ragas_import(monkeypatch)
    monkeypatch.delenv("OLLAMA_EVAL_BASE_URL", raising=False)
    monkeypatch.delenv("OLLAMA_EVAL_MODEL", raising=False)
    monkeypatch.setattr(
        ragas_eval_ollama, "load_ground_truth_cases", lambda: [_fake_case("registro-002")]
    )
    monkeypatch.setattr(ragas_eval_ollama, "get_ragas_models", _forbid_call("get_ragas_models"))
    monkeypatch.setattr(ragas_eval_ollama, "generate_case_rows", _forbid_call("generate_case_rows"))
    monkeypatch.setattr(sys, "argv", ["ragas_eval_ollama.py"])

    exit_code = ragas_eval_ollama.main()

    assert exit_code == 1
    out = capsys.readouterr().out
    assert "OLLAMA_EVAL_BASE_URL" in out
    assert "OLLAMA_EVAL_MODEL" in out
