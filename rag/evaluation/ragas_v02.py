"""Fases 3 y 4 de la línea base: métricas RAGAS (API ``ragas.metrics.collections``)
sobre la caché de generación de ``legal-ground-truth-v0.2``.

No vuelve a generar: lee ``generation_cache.CACHE_PATH`` y solo evalúa los
casos con ``outcome == "respondida"``. Los demás (respuesta fija, sin
recuperación) se reportan aparte, porque puntuarlos mediría la respuesta
fija y no la calidad del sistema (ver ``docs/EVALUACION_LINEA_BASE.md``, §5).

Juez: ``gpt-5-nano`` (el modelo del proyecto), con la API key de ``rag/.env``.
Embeddings: ``embeddinggemma`` del Ollama del proyecto, mediante su API
compatible con OpenAI (``/v1``), sin costo.

Métricas por caso:

| Pregunta | Métrica |
|---|---|
| ¿El buscador trajo la evidencia? | ``context_recall``, ``context_precision`` |
| ¿El modelo se apega a los chunks? | ``faithfulness`` |
| ¿Responde lo que se preguntó? | ``answer_relevancy`` |
| ¿Se parece a la respuesta jurídica? | ``factual_precision``, ``factual_recall``, ``factual_f1``, ``answer_accuracy``, ``semantic_similarity`` |

``factual_*`` sale de **una sola** ejecución de ``FactualCorrectness``: se
usan sus dos pasos de descomposición y verificación de afirmaciones y se
calculan precisión, cobertura y F1 con los mismos conteos (ver
``prf_from_counts``), en vez de pagar tres corridas, una por ``mode``.

Uso:
    CHROMA_HOST=… OLLAMA_BASE_URL=… uv run python -m evaluation.ragas_v02 --limit 3   # piloto
    … uv run python -m evaluation.ragas_v02                                           # todos
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from evaluation.generation_cache import CACHE_PATH, estimate_cost_usd, load_cache

RESULTS_PATH = Path("evaluation/results/ragas-v0.2.jsonl")
JUDGE_MODEL = "gpt-5-nano"
JUDGE_MAX_TOKENS = 16000

METRIC_NAMES = [
    "context_recall",
    "context_precision",
    "faithfulness",
    "answer_relevancy",
    "factual_precision",
    "factual_recall",
    "factual_f1",
    "answer_accuracy",
    "semantic_similarity",
]

# Umbral único del diagnóstico por caso (tabla §1.5 del documento).
DIAGNOSIS_THRESHOLD = 0.5


# ============================================================
#  1. Partes puras (probadas en tests/unit/test_ragas_v02.py)
# ============================================================


def prf_from_counts(tp: int, fp: int, fn: int) -> dict[str, float]:
    """Precisión, cobertura y F1 a partir de verdaderos positivos (afirmaciones
    de la respuesta presentes en la referencia), falsos positivos y falsos
    negativos (afirmaciones de la referencia ausentes en la respuesta)."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def diagnose(scores: dict[str, float | None]) -> str:
    """Clasifica un caso según la tabla de diagnóstico del documento:
    primero la recuperación, luego la fidelidad y por último la cobertura
    frente a la respuesta jurídica."""
    needed = ("context_recall", "faithfulness", "factual_recall")
    if any(scores.get(name) is None for name in needed):
        return "sin_datos"
    if scores["context_recall"] < DIAGNOSIS_THRESHOLD:  # type: ignore[operator]
        return "recuperacion"
    if scores["faithfulness"] < DIAGNOSIS_THRESHOLD:  # type: ignore[operator]
        return "alucinacion"
    if scores["factual_recall"] < DIAGNOSIS_THRESHOLD:  # type: ignore[operator]
        return "incompleta_o_general"
    return "correcta"


def aggregate_scores(
    rows: list[dict[str, Any]], key: str, metric_names: list[str]
) -> dict[str, dict[str, Any]]:
    """Promedio por grupo de cada métrica, ignorando los ``None``."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row[key]), []).append(row)
    summary: dict[str, dict[str, Any]] = {}
    for group, items in sorted(groups.items()):
        entry: dict[str, Any] = {"n": len(items)}
        for name in metric_names:
            values = [r["scores"].get(name) for r in items if r["scores"].get(name) is not None]
            entry[name] = sum(values) / len(values) if values else None
        summary[group] = entry
    return summary


class UsageCounter:
    """Suma el ``usage`` de cada respuesta de la API de OpenAI."""

    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def add(self, usage: dict[str, Any] | None) -> None:
        self.calls += 1
        if usage:
            self.input_tokens += int(usage.get("prompt_tokens") or 0)
            self.output_tokens += int(usage.get("completion_tokens") or 0)


# Contador del caso en curso. Cada caso corre en su propia tarea de asyncio
# (y las métricas en subtareas que copian el contexto), así que el uso de una
# llamada se atribuye solo al caso que la hizo, aunque haya casos en paralelo.
_CASE_USAGE: ContextVar[UsageCounter | None] = ContextVar("case_usage", default=None)


@asynccontextmanager
async def case_usage() -> AsyncIterator[UsageCounter]:
    counter = UsageCounter()
    token = _CASE_USAGE.set(counter)
    try:
        yield counter
    finally:
        _CASE_USAGE.reset(token)


def record_usage(total: UsageCounter, usage: dict[str, Any] | None) -> None:
    """Suma ``usage`` al total de la corrida y al contador del caso en curso."""
    total.add(usage)
    current = _CASE_USAGE.get()
    if current is not None:
        current.add(usage)


# ============================================================
#  2. Juez, embeddings y métricas
# ============================================================


def _build_judge(counter: UsageCounter, reasoning_effort: str) -> Any:
    import httpx
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory

    from rag.config import OPENAI_API_KEY

    async def count_usage(response: httpx.Response) -> None:
        await response.aread()
        try:
            record_usage(counter, response.json().get("usage"))
        except (ValueError, AttributeError):
            record_usage(counter, None)

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        http_client=httpx.AsyncClient(event_hooks={"response": [count_usage]}, timeout=300),
    )
    return llm_factory(
        JUDGE_MODEL,
        client=client,
        max_tokens=JUDGE_MAX_TOKENS,
        reasoning_effort=reasoning_effort,
    )


def _build_embeddings() -> Any:
    from openai import AsyncOpenAI
    from ragas.embeddings import OpenAIEmbeddings

    from rag.config import OLLAMA_BASE_URL, OLLAMA_EMBEDDING_MODEL

    client = AsyncOpenAI(base_url=f"{OLLAMA_BASE_URL.rstrip('/')}/v1", api_key="ollama")
    return OpenAIEmbeddings(client=client, model=OLLAMA_EMBEDDING_MODEL)


def _build_metrics(judge: Any, embeddings: Any) -> dict[str, Any]:
    from ragas.metrics.collections import (
        AnswerAccuracy,
        AnswerRelevancy,
        ContextPrecision,
        ContextRecall,
        FactualCorrectness,
        Faithfulness,
        SemanticSimilarity,
    )

    return {
        "context_recall": ContextRecall(llm=judge),
        "context_precision": ContextPrecision(llm=judge),
        "faithfulness": Faithfulness(llm=judge),
        "answer_relevancy": AnswerRelevancy(llm=judge, embeddings=embeddings),
        "factual": FactualCorrectness(llm=judge),
        "answer_accuracy": AnswerAccuracy(llm=judge),
        "semantic_similarity": SemanticSimilarity(embeddings=embeddings),
    }


async def _factual_prf(metric: Any, response: str, reference: str) -> dict[str, float]:
    # Mismos dos pasos que FactualCorrectness.ascore (ragas 0.4.3), una sola vez.
    response_vs_reference = await metric._decompose_and_verify_claims(response, reference)
    reference_vs_response = await metric._decompose_and_verify_claims(reference, response)
    tp = int(response_vs_reference.sum())
    fp = int((~response_vs_reference).sum())
    fn = int((~reference_vs_response).sum())
    return prf_from_counts(tp, fp, fn)


async def _score_case(metrics: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    q, a, ref, ctx = row["pregunta"], row["answer"], row["respuesta_esperada"], row["contexts"]
    calls = {
        "context_recall": metrics["context_recall"].ascore(
            user_input=q, retrieved_contexts=ctx, reference=ref
        ),
        "context_precision": metrics["context_precision"].ascore(
            user_input=q, reference=ref, retrieved_contexts=ctx
        ),
        "faithfulness": metrics["faithfulness"].ascore(
            user_input=q, response=a, retrieved_contexts=ctx
        ),
        "answer_relevancy": metrics["answer_relevancy"].ascore(user_input=q, response=a),
        "factual": _factual_prf(metrics["factual"], a, ref),
        "answer_accuracy": metrics["answer_accuracy"].ascore(
            user_input=q, response=a, reference=ref
        ),
        "semantic_similarity": metrics["semantic_similarity"].ascore(reference=ref, response=a),
    }
    results = await asyncio.gather(*calls.values(), return_exceptions=True)
    scores: dict[str, float | None] = {}
    errors: dict[str, str] = {}
    for name, result in zip(calls, results, strict=True):
        if isinstance(result, BaseException):
            errors[name] = f"{type(result).__name__}: {result}"[:500]
            if name == "factual":
                scores.update(factual_precision=None, factual_recall=None, factual_f1=None)
            else:
                scores[name] = None
        elif name == "factual":
            scores.update(
                factual_precision=result["precision"],
                factual_recall=result["recall"],
                factual_f1=result["f1"],
            )
        else:
            scores[name] = float(result.value) if result.value is not None else None
    return {"scores": scores, "errors": errors}


# ============================================================
#  3. Ejecución con reanudación
# ============================================================


def _load_done(path: Path) -> set[str]:
    if not path.exists():
        return set()
    with path.open(encoding="utf-8") as f:
        return {json.loads(line)["case_id"] for line in f if line.strip()}


async def _run(rows: list[dict[str, Any]], concurrency: int, reasoning_effort: str) -> None:
    counter = UsageCounter()
    metrics = _build_metrics(_build_judge(counter, reasoning_effort), _build_embeddings())
    semaphore = asyncio.Semaphore(concurrency)
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    with RESULTS_PATH.open("a", encoding="utf-8") as f:

        async def one(row: dict[str, Any]) -> None:
            start = time.monotonic()
            async with semaphore, case_usage() as usage:
                result = await _score_case(metrics, row)
            out = {
                "case_id": row["case_id"],
                "tipo": row["tipo"],
                "revisado": row["revisado"],
                "scores": result["scores"],
                "diagnostico": diagnose(result["scores"]),
                "errors": result["errors"],
                "judge": JUDGE_MODEL,
                "reasoning_effort": reasoning_effort,
                "duration_seconds": round(time.monotonic() - start, 2),
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd_est": estimate_cost_usd(usage.input_tokens, usage.output_tokens),
            }
            f.write(json.dumps(out, ensure_ascii=False) + "\n")
            f.flush()
            shown = {k: (round(v, 2) if v is not None else None) for k, v in out["scores"].items()}
            print(f"{row['case_id']}: {out['diagnostico']} {shown} errores={list(out['errors'])}")

        await asyncio.gather(*(one(row) for row in rows))

    total = estimate_cost_usd(counter.input_tokens, counter.output_tokens)
    print(
        f"Juez: {counter.calls} llamadas · {counter.input_tokens} tokens de entrada · "
        f"{counter.output_tokens} de salida · costo estimado ${total:.4f}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="solo los primeros N pendientes")
    parser.add_argument("--concurrency", type=int, default=3, help="casos en paralelo")
    parser.add_argument(
        "--reasoning-effort",
        default="low",
        choices=["minimal", "low", "medium", "high"],
        help="esfuerzo de razonamiento del juez gpt-5-nano",
    )
    args = parser.parse_args()

    done = _load_done(RESULTS_PATH)
    cached = load_cache(CACHE_PATH)
    todo = [r for r in cached if r["outcome"] == "respondida" and r["case_id"] not in done]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"Caché: {len(cached)} · ya evaluados: {len(done)} · por evaluar: {len(todo)}")
    asyncio.run(_run(todo, args.concurrency, args.reasoning_effort))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
