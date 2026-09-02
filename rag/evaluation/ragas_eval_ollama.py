# evaluation/ragas_eval_ollama.py
"""Adaptador RAGAS: juez servido por Ollama + embeddings de producción,
sobre ``legal-ground-truth-v0.1``.

La infraestructura compartida (carga y validación del dataset, generación
sin truncar, construcción del dataset RAGAS, ejecución de métricas, resumen
y reporte reproducible) vive en ``ragas_common.py`` — este módulo solo
aporta su juez (Ollama con limpieza y normalización estricta de JSON), sus
embeddings y su lista de métricas.

Uso:
    uv run python -m evaluation.ragas_eval_ollama                 # evaluación real
    uv run python -m evaluation.ragas_eval_ollama --validate-only # solo valida config, sin red
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path
from typing import Any

from langchain_ollama import ChatOllama, OllamaEmbeddings

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

REPORT_PATH = Path("evaluation/results/legal-ground-truth-v0.1-ollama.json")

# Métricas activas: solo `answer_relevancy` (ver la lista `metrics` en
# main(), más abajo). Elegir o calibrar qué métricas correr es una decisión
# de evaluación deliberada, no una limitación técnica de este adaptador;
# esta lista se conserva sin cambios.


# ============================================================
#  1. Juez en Ollama con limpieza estricta de JSON
# ============================================================


class JsonStrictOllama(ChatOllama):
    """
    Variante de ChatOllama pensada para RAGAS.

    Objetivo:
    - Limpiar fences markdown y texto basura alrededor del JSON.
    - Extraer el primer bloque JSON válido si hay ruido.
    - Normalizar SOLO tipos de campos clave que RAGAS espera:
        * verdict        -> 0/1
        * Attributed     -> bool
        * noncommittal   -> bool
        * question       -> str
    - No cambiar la estructura ni los nombres de las claves.
      Esto permite que funcione con:
        - context_precision
        - context_recall
        - faithfulness
        - answer_relevancy
    """

    # ---------- utilidades internas de limpieza ----------

    @staticmethod
    def _strip_json_fences(text: str) -> str:
        """
        Elimina fences Markdown ```...``` de la salida.
        """
        s = text.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            # quitar la primera línea ``` o ```json, etc.
            lines = lines[1:]
            # quitar la última línea si es ```
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        return s

    @staticmethod
    def _extract_json_block(text: str) -> str:
        """
        Si el texto contiene un JSON embebido (p.ej. texto antes/después),
        intenta extraer el primer bloque bien formado entre '{' y '}'.
        Si no lo consigue, devuelve el texto original.
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

    @staticmethod
    def _normalize_verdict(raw: Any) -> int:
        """
        Normaliza cualquier valor a 0 o 1.

        Regla: values >= 0.5 -> 1, sino 0.
        (Soporta bool, str numérica, int, float).
        """
        if isinstance(raw, bool):
            return 1 if raw else 0

        try:
            val = float(raw)
        except Exception:
            return 0
        return 1 if val >= 0.5 else 0

    @staticmethod
    def _normalize_bool(raw: Any) -> bool:
        """
        Normaliza un valor a bool.
        """
        if isinstance(raw, bool):
            return raw
        try:
            # acepta 0/1, "0"/"1", etc.
            return bool(float(raw))
        except Exception:
            # si no sabemos qué es, ser conservadores
            return False

    @classmethod
    def _coerce_types_for_ragas(cls, data: Any) -> Any:
        """
        Recorre recursivamente el JSON y corrige solo tipos de campos
        relevantes para RAGAS, sin cambiar la estructura.
        """
        if isinstance(data, dict):
            new: dict[str, Any] = {}
            for k, v in data.items():
                if k == "verdict":
                    new[k] = cls._normalize_verdict(v)
                elif k == "Attributed":
                    new[k] = cls._normalize_bool(v)
                elif k == "noncommittal":
                    new[k] = cls._normalize_bool(v)
                elif k == "question":
                    # answer_relevancy: asegura que sea string
                    new[k] = "" if v is None else str(v)
                else:
                    new[k] = cls._coerce_types_for_ragas(v)
            return new
        elif isinstance(data, list):
            return [cls._coerce_types_for_ragas(x) for x in data]
        else:
            return data

    @classmethod
    def _normalize_json(cls, text: str) -> str:
        """
        Normaliza la salida de texto del modelo a un JSON limpio sin
        alterar el esquema.

        Pasos:
        - Quita fences.
        - Intenta extraer el bloque JSON principal.
        - Si parsea:
            * Corrige tipos de campos clave (verdict, Attributed, noncommittal, question)
            * Devuelve json.dumps(data)
        - Si NO parsea:
            * Devuelve el texto tal cual (RAGAS mostrará warning, igual que sin wrapper).
        """
        s = text.strip()
        if not s:
            # cadena vacía, que RAGAS tratará como inválida si esperaba JSON
            return s

        s_candidate = cls._extract_json_block(s)

        try:
            data = json.loads(s_candidate)
        except Exception:
            # No se pudo parsear como JSON. Devolver la mejor aproximación.
            return s_candidate

        data = cls._coerce_types_for_ragas(data)
        return json.dumps(data, ensure_ascii=False)

    # ---------- postprocesado de la respuesta de LangChain ----------

    def _postprocess_result(self, result):
        """
        Ajusta in-place result.generations para que tanto:
          - gen.message.content
          - gen.text

        contengan un string JSON limpio cuando el modelo haya generado JSON.
        """
        gens = getattr(result, "generations", [])

        # Aplanar posibles listas anidadas: List[List[Generation]] o List[Generation]
        flat_gens = []
        for item in gens:
            if isinstance(item, list):
                flat_gens.extend(item)
            else:
                flat_gens.append(item)

        for gen in flat_gens:
            # 1) message.content
            msg = getattr(gen, "message", None)
            if msg is not None:
                content = getattr(msg, "content", None)
                if isinstance(content, str):
                    cleaned = self._strip_json_fences(content)
                    cleaned = self._normalize_json(cleaned)
                    msg.content = cleaned

            # 2) gen.text
            text = getattr(gen, "text", None)
            if isinstance(text, str):
                cleaned_text = self._strip_json_fences(text)
                cleaned_text = self._normalize_json(cleaned_text)
                gen.text = cleaned_text

        return result

    # ---------- hooks internos de ChatOllama ----------

    def _generate(self, messages, stop=None, **kwargs):
        # Forzar que NO use streaming aunque RAGAS/LangChain lo pida
        kwargs.pop("stream", None)
        res = super()._generate(messages, stop=stop, stream=False, **kwargs)
        return self._postprocess_result(res)

    async def _agenerate(self, messages, stop=None, **kwargs):
        # Igual en la versión async
        kwargs.pop("stream", None)
        res = await super()._agenerate(messages, stop=stop, stream=False, **kwargs)
        return self._postprocess_result(res)


def get_ragas_models(
    judge_base_url: str, judge_model_name: str
) -> tuple[JsonStrictOllama, OllamaEmbeddings]:
    """
    Modelos para RAGAS:

    - LLM juez: el modelo servido por Ollama en ``judge_base_url``
      (endpoint de evaluación, distinto del Ollama de producción), con el
      modelo indicado por ``judge_model_name``. Ambos llegan ya
      normalizados (no vacíos, sin espacios) desde OLLAMA_EVAL_BASE_URL /
      OLLAMA_EVAL_MODEL -- este adaptador no vuelve a leer esas variables
      de entorno aquí.
    - Embeddings: los mismos que usa producción (``rag.config``), para que
      RAGAS evalúe contra el contexto real que ve el sistema.
    """
    llm_judge = JsonStrictOllama(
        model=judge_model_name,
        base_url=judge_base_url,
        temperature=0.0,
        num_ctx=2048,
        num_predict=256,
        format="json",
        keep_alive=60,  # o elimina el parámetro para usar el default
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
        return validate_only(["OLLAMA_EVAL_BASE_URL", "OLLAMA_EVAL_MODEL"])

    # 1) Cargar y validar el dataset una sola vez.
    cases = load_ground_truth_cases()

    # 2)-3) Validar la configuración obligatoria ANTES de tocar RAGAS, red
    # o cualquier cliente -- un valor ausente o compuesto solo por espacios
    # nunca debe llegar a un constructor.
    env_values, missing = normalize_required_env(["OLLAMA_EVAL_BASE_URL", "OLLAMA_EVAL_MODEL"])
    if missing:
        print(f"variables de entorno obligatorias faltantes: {', '.join(missing)}")
        return 1

    # 4) Solo después de validar: importar RAGAS y construir juez/embeddings.
    from ragas.metrics import answer_relevancy

    judge_base_url = env_values["OLLAMA_EVAL_BASE_URL"]
    judge_model_name = env_values["OLLAMA_EVAL_MODEL"]
    llm_judge, embeddings = get_ragas_models(
        judge_base_url=judge_base_url, judge_model_name=judge_model_name
    )
    metrics = [answer_relevancy]

    # 5) Generar usando los casos ya cargados en el paso 1.
    rows = generate_case_rows(cases)
    dataset = build_ragas_dataset(rows)
    case_ids = case_ids_evaluated(rows)
    metric_results = run_metrics(dataset, metrics, llm_judge, embeddings, case_ids)

    write_report(
        provider="ollama",
        model=judge_model_name,
        metrics_executed=[m.name for m in metrics],
        rows=rows,
        metric_results=metric_results,
        extra_config={
            "judge_base_url": judge_base_url,
            "embeddings_model": OLLAMA_EMBEDDING_MODEL,
            "embeddings_base_url": OLLAMA_BASE_URL,
        },
        output_path=REPORT_PATH,
    )
    print(f"Reporte escrito en: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
