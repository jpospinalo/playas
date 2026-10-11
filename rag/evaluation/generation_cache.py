"""Fase 2 de la línea base: ejecuta el grafo real de producción una sola vez
por caso de ``legal-ground-truth-v0.2`` y guarda todo en una caché
reutilizable, para que las métricas (fase 4) se puedan recalcular sin volver
a pagar la generación.

Por caso guarda, además de la respuesta y los chunks, lo que el grafo decidió
en el camino (ver ``docs/EVALUACION_LINEA_BASE.md``, §5):

- ``route``: si la pregunta se clasificó ``in_scope`` (solo entonces hay
  recuperación) o se desvió a ``needs_clarification``/``out_of_scope``/
  ``conversation``;
- ``enriched_query``: la consulta reescrita con la que buscó el retriever;
- ``outcome``: ``respondida``, ``sin_evidencia``, ``citas_invalidas`` o
  ``sin_recuperacion:<ruta>``, para separar las respuestas fijas de las
  generadas;
- tokens consumidos (``UsageTracker``) y costo estimado.

La caché es un JSONL que se escribe caso a caso: si la corrida se
interrumpe, al relanzarla solo procesa los casos pendientes.

Uso:
    CHROMA_HOST=… OLLAMA_BASE_URL=… uv run python -m evaluation.generation_cache [--limit N] [--concurrency 4]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from rag.core.agent import (
    _INVALID_CITATIONS_RESPONSE,
    _NO_EVIDENCE_RESPONSE,
)
from rag.core.llm_factory import _extract_in_out_tokens

CACHE_PATH = Path("evaluation/results/generation-cache-v0.2.jsonl")

# Precio público de gpt-5-nano por millón de tokens (USD). Solo para estimar
# el gasto de la corrida; la factura real es la del panel de OpenAI.
PRICE_INPUT_PER_M = 0.05
PRICE_OUTPUT_PER_M = 0.40


def classify_outcome(route: str | None, answer: str) -> str:
    """Separa las respuestas generadas de las respuestas fijas del grafo."""
    if route != "in_scope":
        return f"sin_recuperacion:{route}"
    if answer == _NO_EVIDENCE_RESPONSE:
        return "sin_evidencia"
    if answer == _INVALID_CITATIONS_RESPONSE:
        return "citas_invalidas"
    return "respondida"


class UsageTracker(BaseCallbackHandler):
    """Suma los tokens de todas las llamadas a LLM de una ejecución."""

    def __init__(self) -> None:
        super().__init__()
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        inp, out = _extract_in_out_tokens(response)
        self.input_tokens += inp or 0
        self.output_tokens += out or 0
        self.calls += 1


def estimate_cost_usd(
    input_tokens: int,
    output_tokens: int,
    price_input_per_m: float = PRICE_INPUT_PER_M,
    price_output_per_m: float = PRICE_OUTPUT_PER_M,
) -> float:
    return round(
        input_tokens / 1e6 * price_input_per_m + output_tokens / 1e6 * price_output_per_m, 6
    )


def pending_cases(cases: list[dict[str, Any]], done_ids: set[str]) -> list[dict[str, Any]]:
    return [case for case in cases if case["id"] not in done_ids]


def load_cache(path: Path = CACHE_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


async def _run_case(graph: Any, case: dict[str, Any]) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage

    from rag.core.agent import extract_answer_from_state

    tracker = UsageTracker()
    config = {
        "configurable": {"thread_id": f"eval:{uuid.uuid4()}"},
        "recursion_limit": 10,
        "callbacks": [tracker],
    }
    state_input = {
        "question": case["pregunta"],
        "standalone_question": None,
        "enriched_query": None,
        "query_route": None,
        "messages": [HumanMessage(content=case["pregunta"])],
        "sources": [],
    }
    start = time.monotonic()
    error: str | None = None
    final_state: dict[str, Any] = {}
    try:
        final_state = await graph.ainvoke(state_input, config=config)
    except Exception as exc:  # aislamiento por caso: un fallo no tumba el resto
        error = f"{type(exc).__name__}: {exc}"
    answer = extract_answer_from_state(final_state) if final_state else ""
    sources = final_state.get("sources") or []
    route = final_state.get("query_route")
    return {
        "case_id": case["id"],
        "tipo": case["tipo"],
        "revisado": case["revisado"],
        "documentos_esperados": case["documentos_esperados"],
        "pregunta": case["pregunta"],
        "respuesta_esperada": case["respuesta"],
        "route": route,
        "enriched_query": final_state.get("enriched_query"),
        "answer": answer,
        "contexts": [d.page_content for d in sources],
        "context_titles": [str((d.metadata or {}).get("title", "")) for d in sources],
        "outcome": classify_outcome(route, answer) if error is None else "error",
        "error": error,
        "duration_seconds": round(time.monotonic() - start, 2),
        "llm_calls": tracker.calls,
        "input_tokens": tracker.input_tokens,
        "output_tokens": tracker.output_tokens,
        "cost_usd_est": estimate_cost_usd(tracker.input_tokens, tracker.output_tokens),
    }


async def _run(cases: list[dict[str, Any]], path: Path, concurrency: int) -> None:
    from rag.core.agent import build_graph
    from rag.core.retriever import init_retrievers

    init_retrievers()
    graph = build_graph()
    path.parent.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrency)
    total = 0.0

    with path.open("a", encoding="utf-8") as f:

        async def one(case: dict[str, Any]) -> None:
            nonlocal total
            async with semaphore:
                row = await _run_case(graph, case)
            # Sin await entre escribir y sumar: el event loop no intercala
            # otra corrutina aquí, así que las líneas del JSONL no se mezclan.
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            total += row["cost_usd_est"]
            print(
                f"{row['case_id']}: {row['outcome']} · {len(row['contexts'])} chunks · "
                f"{row['duration_seconds']}s · ${row['cost_usd_est']:.4f} (acum. ${total:.4f})",
                flush=True,
            )

        await asyncio.gather(*(one(case) for case in cases))


def main() -> int:
    from evaluation.ground_truth_v02 import load_ground_truth_v02

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="solo los primeros N pendientes")
    parser.add_argument("--concurrency", type=int, default=4, help="casos en paralelo")
    args = parser.parse_args()

    done = {row["case_id"] for row in load_cache()}
    todo = pending_cases(load_ground_truth_v02(), done)
    if args.limit is not None:
        todo = todo[: args.limit]
    print(f"En caché: {len(done)} · por generar: {len(todo)}")
    asyncio.run(_run(todo, CACHE_PATH, args.concurrency))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
