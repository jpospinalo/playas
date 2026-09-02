# evaluation/ragas_common.py
"""Infraestructura común para evaluar el RAG con RAGAS sobre
``legal-ground-truth-v0.1``, compartida por ``ragas_eval_gemma.py`` y
``ragas_eval_ollama.py`` para no duplicar la lógica de carga del dataset,
generación, construcción del dataset RAGAS, ejecución de métricas,
resumen y escritura de reportes.

Cada adaptador solo construye su juez, sus embeddings y su lista real de
métricas; todo lo demás vive aquí. No hay sistema de plugins, clase base
ni contenedor de dependencias — funciones simples que un adaptador llama
en orden.

Genera la respuesta de cada caso con ``generate_answer()`` (una sola vez
por pregunta) y conserva TODOS los documentos que retornó el grafo, sin
truncar la lista después: la evaluación debe observar exactamente el
mismo contexto que produce el flujo real, no una muestra recortada.

Cada puntaje de RAGAS queda asociado a su ``case_id`` explícitamente
(``scores_by_case``), nunca por posición implícita en el ``Dataset`` — ver
``case_ids_evaluated()`` y ``run_metrics()``. Un valor no finito (``NaN``)
que RAGAS devuelva para un caso se conserva como ``None`` en
``scores_by_case`` en vez de descartarse: la ausencia de puntaje es
información, no ruido a eliminar. El reporte que escribe ``write_report()``
guarda ese detalle completo (``metric_results``), no solo el promedio
agregado.

Métrica de "documento esperado": este módulo no la calcula para ningún
caso. Los registros 17–22 tienen referencias documentales aún ambiguas
(no permiten identificar inequívocamente la sentencia esperada) y quedan
excluidos por diseño. Para el resto, calcularla exigiría un mapeo
determinista entre los valores de ``doc_principal``/``doc_secundario``
del dataset (p. ej. ``"N-02 · REMAC 5..."``) y la metadata real que hoy
expone el corpus indexado — mapeo que este módulo, deliberadamente offline,
no puede verificar sin consultar el ChromaDB real, y que no se aproxima por
búsqueda textual. Por eso la métrica se omite para los 21 casos y cada
reporte explica el motivo por caso
(``expected_document_metric``); no se inventa ningún mapeo.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from datasets import Dataset

from evaluation.citation_coverage import analyze_citation_coverage
from evaluation.ground_truth import (
    DATASET_ANNOTATION,
    DATASET_NAME,
    default_dataset_path,
    load_ground_truth_cases,
)
from rag.core.generator import generate_answer

# Los registros 17-22 (numeración original del Excel, igual a los IDs del
# dataset) tienen referencias documentales que aún no permiten identificar
# inequívocamente la sentencia esperada.
AMBIGUOUS_DOCUMENT_CASE_IDS: frozenset[str] = frozenset(
    {
        "registro-017",
        "registro-018",
        "registro-019",
        "registro-020",
        "registro-021",
        "registro-022",
    }
)


# ============================================================
#  1. Identidad del dataset y del código evaluado
# ============================================================


def dataset_sha256(path: Path | None = None) -> str:
    """SHA-256 del JSON del dataset tal como está en disco ahora mismo."""
    dataset_path = path if path is not None else default_dataset_path()
    return hashlib.sha256(dataset_path.read_bytes()).hexdigest()


def git_state() -> dict[str, Any]:
    """Estado de git del árbol que se está evaluando: ``commit`` (HEAD, o
    "desconocido" si git no está disponible o no hay repositorio) y
    ``dirty`` (``True`` si hay cambios sin commit -- versionados o no
    versionados no ignorados --, ``False`` si el árbol está limpio, o
    ``None`` si no se pudo determinar). Se ejecuta con el directorio de
    trabajo fijado a partir de este archivo (``__file__``), nunca del
    directorio desde el que se invocó el proceso, para que el resultado no
    dependa de dónde se ejecute el comando. No calcula ni guarda el diff
    completo, solo si existe alguno."""
    repo_dir = Path(__file__).resolve().parent
    try:
        commit_result = subprocess.run(  # noqa: S603, S607
            ["git", "rev-parse", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        commit = commit_result.stdout.strip()
    except Exception:
        return {"commit": "desconocido", "dirty": None}

    try:
        status_result = subprocess.run(  # noqa: S603, S607
            ["git", "status", "--porcelain"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        dirty: bool | None = bool(status_result.stdout.strip())
    except Exception:
        dirty = None

    return {"commit": commit, "dirty": dirty}


# ============================================================
#  2. Generación: una invocación por caso, sin truncar documentos
# ============================================================


def generate_case_rows(cases: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Invoca ``generate_answer()`` exactamente una vez por caso de
    ``cases`` (en el orden recibido), conservando la lista completa de
    documentos que retornó el grafo. El fallo de un caso (excepción de
    ``generate_answer``) se aísla: se registra en ``error`` y no
    interrumpe los casos siguientes.

    Recibe ``cases`` ya cargado (típicamente ``load_ground_truth_cases()``,
    llamado una sola vez por el adaptador antes de validar la configuración
    obligatoria) en vez de leer el archivo del dataset de nuevo aquí."""
    return [_run_one_case(case) for case in cases]


def _run_one_case(case: dict[str, str]) -> dict[str, Any]:
    start = time.monotonic()
    error: str | None = None
    answer = ""
    docs: list[Any] = []
    try:
        answer, docs = generate_answer(case["pregunta"])
        answer = answer or ""
        docs = list(docs or [])
    except Exception as exc:  # aislamiento por caso: un fallo no tumba el resto
        error = f"{type(exc).__name__}: {exc}"
    duration = time.monotonic() - start

    citation: dict[str, Any] | None = None
    if error is None:
        citation = analyze_citation_coverage(answer, len(docs)).as_dict()

    expected_document_metric = (
        "omitted:ambiguous_reference"
        if case["id"] in AMBIGUOUS_DOCUMENT_CASE_IDS
        else "omitted:no_deterministic_mapping_available"
    )

    return {
        "case_id": case["id"],
        "pregunta": case["pregunta"],
        "respuesta_esperada": case["respuesta"],
        "answer": answer,
        "contexts": [getattr(d, "page_content", str(d)) for d in docs],
        "doc_count": len(docs),
        "citation_coverage": citation,
        "error": error,
        "duration_seconds": duration,
        "expected_document_metric": expected_document_metric,
    }


# ============================================================
#  3. Dataset RAGAS y ejecución de métricas
# ============================================================


class RagasMetricsError(RuntimeError):
    """Resultado de RAGAS que no se puede interpretar con seguridad: una
    columna de métrica solicitada no aparece en el resultado, la cantidad
    de valores no coincide con la cantidad de casos evaluados, o
    ``evaluate()`` devolvió un tipo distinto del esperado. Nunca se
    silencia ninguno de estos casos — ver ``run_metrics()``."""


def build_ragas_dataset(rows: list[dict[str, Any]]) -> Dataset:
    """Construye el ``Dataset`` de RAGAS solo con los casos que generaron
    respuesta sin error — un caso fallido no puede evaluarse con RAGAS,
    pero sigue presente en el reporte final con su error registrado."""
    ragas_rows = [
        {
            "question": row["pregunta"],
            "answer": row["answer"],
            "contexts": row["contexts"] or [""],
            "ground_truth": row["respuesta_esperada"],
        }
        for row in rows
        if row["error"] is None
    ]
    return Dataset.from_list(ragas_rows)


def case_ids_evaluated(rows: list[dict[str, Any]]) -> list[str]:
    """``case_id`` de los casos que ``build_ragas_dataset()`` incluiría en
    el ``Dataset`` (mismo filtro, ``error is None``), en el mismo orden.
    El adaptador pasa este resultado como ``evaluated_case_ids`` a
    ``run_metrics()`` junto con el ``Dataset`` construido a partir de las
    mismas ``rows`` — así cada puntaje de RAGAS queda asociado a su caso
    por identidad, nunca por la posición implícita del ``Dataset``."""
    return [row["case_id"] for row in rows if row["error"] is None]


def _empty_metric_results(metrics: list[Any]) -> dict[str, dict[str, Any]]:
    return {
        metric.name: {
            "mean": None,
            "scores_by_case": {},
            "scored_count": 0,
            "missing_count": 0,
        }
        for metric in metrics
    }


def run_metrics(
    dataset: Dataset,
    metrics: list[Any],
    judge: Any,
    embeddings: Any,
    evaluated_case_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Ejecuta exactamente las métricas que recibe del adaptador — este
    módulo no decide cuáles correr, esa decisión es de cada adaptador.

    ``evaluated_case_ids`` debe ser el resultado de
    ``case_ids_evaluated(rows)`` sobre las mismas ``rows`` (y en el mismo
    orden) con las que se llamó ``build_ragas_dataset()`` para construir
    ``dataset`` — se verifica antes de evaluar. El resultado, por métrica,
    incluye ``scores_by_case`` (``case_id`` -> puntaje o ``None`` si RAGAS
    no devolvió un valor finito para ese caso), ``mean`` (solo de los
    puntajes válidos), ``scored_count`` y ``missing_count``. Un ``None``
    en ``scores_by_case`` es una métrica faltante para un caso que sí
    llegó a evaluarse — no confundir con los casos que nunca llegaron
    porque su generación falló (esos se identifican por ``error`` en
    ``rows``, nunca aparecen aquí)."""
    if len(dataset) != len(evaluated_case_ids):
        raise RagasMetricsError(
            f"dataset tiene {len(dataset)} filas pero evaluated_case_ids tiene "
            f"{len(evaluated_case_ids)} — ambos deben construirse a partir de las "
            "mismas rows y el mismo filtro (error is None), en el mismo orden."
        )

    if not evaluated_case_ids:
        # Ningún caso llegó a esta etapa (todas las generaciones fallaron, o
        # no había casos para empezar): no se invoca ragas.evaluate() con un
        # dataset vacío. Se devuelve un resultado vacío y controlado por cada
        # métrica solicitada, en vez de dejar que RAGAS falle de forma
        # confusa sobre un dataset sin filas.
        return _empty_metric_results(metrics)

    from ragas import evaluate
    from ragas.dataset_schema import EvaluationResult
    from ragas.run_config import RunConfig

    for metric in metrics:
        metric.llm = judge
        metric.embeddings = embeddings

    run_config = RunConfig(timeout=600, max_workers=1)
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=judge,
        embeddings=embeddings,
        raise_exceptions=False,
        run_config=run_config,
    )
    # `evaluate()` solo devuelve `Executor` cuando se llama con
    # `return_executor=True` (no es el caso aquí). Se comprueba el tipo de
    # forma explícita — no con `assert`, que Python puede desactivar con
    # optimización — para que un cambio futuro en esa llamada falle aquí de
    # forma clara en vez de un AttributeError confuso más adelante.
    if not isinstance(result, EvaluationResult):
        raise RagasMetricsError(
            f"evaluate() devolvió {type(result).__name__}, se esperaba EvaluationResult "
            "(revisar si se pasó return_executor=True)."
        )
    df = result.to_pandas()

    out: dict[str, dict[str, Any]] = {}
    for metric in metrics:
        name = metric.name
        if name not in df.columns:
            raise RagasMetricsError(
                f"la métrica solicitada {name!r} no aparece en el resultado de RAGAS "
                f"(columnas disponibles: {sorted(df.columns)}) — no se omite en silencio."
            )
        raw_values = df[name].tolist()
        if len(raw_values) != len(evaluated_case_ids):
            raise RagasMetricsError(
                f"la métrica {name!r} devolvió {len(raw_values)} valores para "
                f"{len(evaluated_case_ids)} casos evaluados — no se puede asociar con "
                "seguridad cada puntaje a su case_id."
            )
        scores_by_case: dict[str, float | None] = {}
        for case_id, raw_value in zip(evaluated_case_ids, raw_values, strict=True):
            try:
                score = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise RagasMetricsError(
                    f"la métrica {name!r} devolvió un valor no numérico "
                    f"({raw_value!r}) para {case_id!r}"
                ) from exc
            # No finito (NaN, +inf, -inf) se conserva como None -- información,
            # no se descarta -- y nunca se serializa como Infinity/-Infinity/NaN
            # (constantes no estándar de JSON): ver allow_nan=False en write_report().
            scores_by_case[case_id] = score if math.isfinite(score) else None
        valid_values = [v for v in scores_by_case.values() if v is not None]
        out[name] = {
            "mean": float(sum(valid_values) / len(valid_values)) if valid_values else None,
            "scores_by_case": scores_by_case,
            "scored_count": len(valid_values),
            "missing_count": len(scores_by_case) - len(valid_values),
        }
    return out


# ============================================================
#  4. Resumen y reporte reproducible
# ============================================================


def summarize(
    rows: list[dict[str, Any]], metric_results: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    errors = [row for row in rows if row["error"]]
    non_empty_answers = [row for row in rows if row["error"] is None and row["answer"].strip()]
    with_citation = [
        row
        for row in rows
        if row["citation_coverage"] is not None and row["citation_coverage"]["has_any_citation"]
    ]
    omitted_ambiguous = [
        row for row in rows if row["expected_document_metric"] == "omitted:ambiguous_reference"
    ]
    return {
        "total_cases": len(rows),
        "generation_errors": len(errors),
        "answers_non_empty": len(non_empty_answers),
        "answers_with_at_least_one_citation": len(with_citation),
        "expected_document_metric_omitted_ambiguous": len(omitted_ambiguous),
        "expected_document_metric_omitted_total": len(rows),
        "metrics_mean": {name: vals["mean"] for name, vals in metric_results.items()},
    }


def write_report(
    *,
    provider: str,
    model: str,
    metrics_executed: list[str],
    rows: list[dict[str, Any]],
    metric_results: dict[str, dict[str, Any]],
    extra_config: dict[str, Any],
    output_path: Path,
) -> None:
    """Escribe un reporte reproducible en ``output_path``. No versionado
    (``evaluation/results/`` está ignorado por git; ver ``evaluation/.gitignore``).

    No impide escribir el reporte si el árbol tiene cambios sin commit,
    pero lo advierte por stdout y lo registra fielmente en ``git.dirty`` —
    ver ``git_state()``."""
    git = git_state()
    if git["dirty"]:
        print(
            "advertencia: el árbol de trabajo tiene cambios sin commit; "
            "este reporte no corresponde exactamente al commit registrado en git.commit."
        )
    report = {
        "dataset": DATASET_NAME,
        "annotation": DATASET_ANNOTATION,
        "dataset_sha256": dataset_sha256(),
        "git": git,
        "provider": provider,
        "model": model,
        "metrics_executed": metrics_executed,
        "config": extra_config,
        "cases": rows,
        "metric_results": metric_results,
        "summary": summarize(rows, metric_results),
        "errors": [
            {"case_id": row["case_id"], "error": row["error"]} for row in rows if row["error"]
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: control final -- si algún campo no normalizado llegara
    # a contener NaN/Infinity/-Infinity, json.dumps() falla explícitamente en
    # vez de escribir esas constantes no estándar (json.loads() no las acepta
    # con parsers estrictos de otros lenguajes).
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )


# ============================================================
#  5. Validación estática sin red (--validate-only)
# ============================================================


def wants_validate_only(argv: list[str] | None = None) -> bool:
    """`True` si el proceso se invocó con ``--validate-only``."""
    args = argv if argv is not None else sys.argv[1:]
    return "--validate-only" in args


def normalize_required_env(required_env_names: list[str]) -> tuple[dict[str, str], list[str]]:
    """Normaliza y valida variables de entorno obligatorias.

    Considera ausente un valor ``None``, una cadena vacía, o una cadena
    compuesta solo por espacios — así un valor así nunca llega a un
    constructor de cliente. Retorna ``(valores, faltantes)``: ``valores``
    solo contiene los nombres presentes, ya recortados con ``.strip()``;
    ``faltantes`` lista los nombres ausentes, en el mismo orden recibido.
    Nunca imprime ni registra los valores — solo los nombres."""
    values: dict[str, str] = {}
    missing: list[str] = []
    for name in required_env_names:
        raw = os.getenv(name)
        stripped = raw.strip() if raw is not None else ""
        if stripped:
            values[name] = stripped
        else:
            missing.append(name)
    return values, missing


def validate_only(required_env_names: list[str]) -> int:
    """Carga y valida el dataset, valida qué variables de entorno
    obligatorias están definidas (ver ``normalize_required_env()``), e
    imprime un resumen — sin llamar a ningún LLM, a Ollama, a ChromaDB ni a
    AWS (esta función no importa ni usa nada de eso). Retorna un código de
    salida (0 = OK, 1 = falta configuración)."""
    cases = load_ground_truth_cases()
    print(f"dataset: {DATASET_NAME}")
    print(f"annotation: {DATASET_ANNOTATION}")
    print(f"cases: {len(cases)}")
    print(f"dataset_sha256: {dataset_sha256()}")

    _values, missing = normalize_required_env(required_env_names)
    if missing:
        print(f"variables de entorno obligatorias faltantes: {', '.join(missing)}")
        return 1
    print("configuración estática: OK (variables obligatorias definidas; no se validan valores)")
    return 0
