# evaluation/ragas_eval_gemma.py
"""Adaptador RAGAS: juez Gemini + embeddings de producción, sobre
``legal-ground-truth-v0.1``.

La infraestructura compartida (carga y validación del dataset, generación
sin truncar, construcción del dataset RAGAS, ejecución de métricas, resumen
y reporte reproducible) vive en ``ragas_common.py`` — este módulo solo
aporta su juez (Gemini con limpieza de JSON y control de rate limit), sus
embeddings y su lista de métricas.

Uso:
    uv run python -m evaluation.ragas_eval_gemma                 # evaluación real
    uv run python -m evaluation.ragas_eval_gemma --validate-only # solo valida config, sin red
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any, ClassVar

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import OllamaEmbeddings
from pydantic import SecretStr

from evaluation.ground_truth import load_ground_truth_cases
from evaluation.ragas_common import (
    build_ragas_dataset,
    case_ids_evaluated,
    generate_case_rows,
    normalize_required_env,
    run_metrics,
    validate_only,
    wants_validate_only,
    write_report,
)
from rag.config import OLLAMA_BASE_URL, OLLAMA_EMBEDDING_MODEL

warnings.filterwarnings("ignore", category=FutureWarning)

REPORT_PATH = Path("evaluation/results/legal-ground-truth-v0.1-gemma.json")

# Nota: el valor por defecto de GEMINI_MODEL en este adaptador
# ("gemma-3-27b-it") difiere del default de producción en
# rag.config.GEMINI_MODEL ("gemini-3.1-flash-lite") porque este juez es un
# modelo distinto, elegido para evaluación offline, no el modelo que sirve
# las respuestas del RAG. Esta discrepancia es intencional y preexistente;
# no se reconcilia aquí (sería una decisión de calibración fuera de este
# plan) — solo se documenta.


# ============================================================
#  1. LLM evaluador: Gemini con rate limit y limpieza JSON
# ============================================================


class RateLimitedGemini(ChatGoogleGenerativeAI):
    """
    Wrapper sobre ChatGoogleGenerativeAI para usarlo como juez en RAGAS:

    - Aplica un delay entre llamadas para no acercarse al límite de QPM.
    - Limpia fences ```json ... ``` de la salida.
    - Intenta dejar un bloque JSON limpio.
    - Si tras limpiar la salida queda vacía, devuelve un JSON neutro
      válido para la métrica de faithfulness (NLIStatementOutput).
    """

    RATE_LIMIT_SECONDS: ClassVar[float] = float(os.getenv("RAGAS_LLM_DELAY", "9.0"))

    # ---------- utilidades de limpieza ----------

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        s = text.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            # quitar primera línea ``` o ```json
            lines = lines[1:]
            # quitar última línea si es ```
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        return s

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """
        Si el texto contiene texto adicional + JSON, intenta extraer
        solo el primer bloque bien formado entre '{' y '}'.
        """
        s = text.strip()
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return s
        candidate = s[start : end + 1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            return s

    @classmethod
    def _clean_text(cls, text: str) -> str:
        if not isinstance(text, str):
            return text

        original = text
        s = cls._strip_json_fences(original)
        s = cls._extract_json_block(s)

        # Si después de limpiar nos quedamos sin nada, devolvemos
        # un JSON neutro compatible con NLIStatementOutput
        # (para faithfulness): {"verdicts": []}
        if not s.strip():
            return json.dumps({"verdicts": []}, ensure_ascii=False)

        return s

    def _postprocess_result(self, result):
        gens = getattr(result, "generations", [])

        flat: list[Any] = []
        for item in gens:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)

        for gen in flat:
            # gen.text
            if hasattr(gen, "text") and isinstance(gen.text, str):
                gen.text = self._clean_text(gen.text)

            # gen.message.content (por si RAGAS usa esto)
            msg = getattr(gen, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    msg.content = self._clean_text(content)

        return result

    # ---------- hooks internos de ChatGoogleGenerativeAI ----------

    def _generate(self, messages, stop=None, **kwargs):
        delay = getattr(self, "RATE_LIMIT_SECONDS", 7.0)
        if delay > 0:
            time.sleep(delay)

        kwargs.pop("stream", None)
        res = super()._generate(messages, stop=stop, **kwargs)
        return self._postprocess_result(res)

    async def _agenerate(self, messages, stop=None, **kwargs):
        delay = getattr(self, "RATE_LIMIT_SECONDS", 7.0)
        if delay > 0:
            await asyncio.sleep(delay)

        kwargs.pop("stream", None)
        res = await super()._agenerate(messages, stop=stop, **kwargs)
        return self._postprocess_result(res)


def get_ragas_models(
    google_api_key: str, gemini_model: str
) -> tuple[RateLimitedGemini, OllamaEmbeddings]:
    """
    - LLM evaluador: Gemini (solo para RAGAS, ver nota de módulo sobre
      GEMINI_MODEL). Recibe ``google_api_key`` ya normalizada (no vacía,
      sin espacios) por el llamador -- no vuelve a leer la variable de
      entorno aquí. ``max_tokens`` es el nombre de parámetro público que
      reconoce la firma instalada de ``ChatGoogleGenerativeAI`` (alias del
      campo ``max_output_tokens``); conserva exactamente el mismo límite
      de antes (4098).
    - Embeddings: los mismos que usa producción (``rag.config``), para que
      RAGAS evalúe contra el contexto real que ve el sistema.
    """
    llm_judge = RateLimitedGemini(
        model=gemini_model,
        api_key=SecretStr(google_api_key),
        temperature=0.0,
        max_tokens=4098,
    )

    embeddings = OllamaEmbeddings(
        model=OLLAMA_EMBEDDING_MODEL,
        base_url=OLLAMA_BASE_URL,
    )

    return llm_judge, embeddings


# ============================================================
#  2. Punto de entrada
# ============================================================


def main() -> int:
    if wants_validate_only():
        return validate_only(["GOOGLE_API_KEY2"])

    # 1) Cargar y validar el dataset una sola vez.
    cases = load_ground_truth_cases()

    # 2)-3) Validar la configuración obligatoria ANTES de tocar RAGAS, red
    # o cualquier cliente -- un valor ausente o compuesto solo por espacios
    # nunca debe llegar a un constructor.
    env_values, missing = normalize_required_env(["GOOGLE_API_KEY2"])
    if missing:
        print(f"variables de entorno obligatorias faltantes: {', '.join(missing)}")
        return 1

    # 4) Solo después de validar: importar RAGAS y construir juez/embeddings.
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    gemini_model = os.getenv("GEMINI_MODEL", "gemma-3-27b-it")
    llm_judge, embeddings = get_ragas_models(
        google_api_key=env_values["GOOGLE_API_KEY2"], gemini_model=gemini_model
    )
    metrics = [context_precision, context_recall, faithfulness, answer_relevancy]

    # 5) Generar usando los casos ya cargados en el paso 1.
    rows = generate_case_rows(cases)
    dataset = build_ragas_dataset(rows)
    case_ids = case_ids_evaluated(rows)
    metric_results = run_metrics(dataset, metrics, llm_judge, embeddings, case_ids)

    write_report(
        provider="gemini",
        model=gemini_model,
        metrics_executed=[m.name for m in metrics],
        rows=rows,
        metric_results=metric_results,
        extra_config={
            "embeddings_model": OLLAMA_EMBEDDING_MODEL,
            "embeddings_base_url": OLLAMA_BASE_URL,
        },
        output_path=REPORT_PATH,
    )
    print(f"Reporte escrito en: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
