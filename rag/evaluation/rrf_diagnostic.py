# evaluation/rrf_diagnostic.py
"""C1.1 — Diagnóstico reproducible de RRF (Weighted Reciprocal Rank Fusion).

Script de evaluación (Ola C — no cambia comportamiento de producción). Reutiliza
la infraestructura existente de ``evaluation/`` (mismo directorio, misma
convención de `main()` + JSON de salida que ``ragas_eval_gemma.py`` /
``ragas_eval_ollama.py``) en vez de crear un segundo framework de evaluación.

No reimplementa la fusión RRF: construye escenarios sintéticos (documentos
BM25-exclusivos, vectoriales-exclusivos y compartidos) y los pasa por
``HybridEnsembleRetriever._fuse()`` — el mismo método que corre en producción
vía ``retrieve_forced_node`` (ver ``core/agent.py``) — usando sub-retrievers
estáticos (mismo patrón que ``tests/unit/test_retriever_limit.py`` /
``test_retriever_invariants.py``). Los pesos (0.3 BM25 / 0.7 vector) y la
constante ``c=160`` no se hardcodean por separado: se leen directamente de
``get_ensemble_retriever`` y de ``HybridEnsembleRetriever`` para que este
diagnóstico nunca pueda divergir en silencio de la configuración real de
producción. No se modifica ningún peso, umbral, ``c`` ni ``k`` — este script
es puramente de lectura/diagnóstico, no se invoca desde la ruta online.

Pregunta que este diagnóstico responde con evidencia numérica reproducible:
si la búsqueda vectorial entrega al menos ``k`` candidatos, ¿compite
normalmente un candidato exclusivo de BM25 contra ellos? La respuesta corta,
demostrada abajo, es no: con los pesos y la ``c`` actuales, el mejor caso
posible para un candidato exclusivo de BM25 (rank 1 en BM25) solo alcanza a
superar a un candidato vectorial-exclusivo cuando ese candidato vectorial
ocupa un rank mayor a ~215 — muy por fuera de cualquier ``k``/``k_candidates``
realista de este sistema (máximo actual: 20, ver ``QueryRequest.k_candidates``
en ``api/schemas.py``).
"""

from __future__ import annotations

import inspect
import json
import os
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag.core.retriever import HybridEnsembleRetriever, get_ensemble_retriever

# ============================================================
#  1. Configuración real de producción (leída, nunca hardcodeada aparte)
# ============================================================

_ensemble_sig = inspect.signature(get_ensemble_retriever)
BM25_WEIGHT: float = _ensemble_sig.parameters["bm25_weight"].default
VECTOR_WEIGHT: float = _ensemble_sig.parameters["vector_weight"].default
RRF_C: int = HybridEnsembleRetriever.model_fields["c"].default

# Rango realista de k_candidates en este sistema — ver QueryRequest.k_candidates
# (api/schemas.py): ge=4, le=20.
REALISTIC_K_CANDIDATES_RANGE = range(4, 21)


class _StaticRetriever(BaseRetriever):
    """Mismo patrón que ``tests/unit/test_retriever_limit.py``: retriever que
    ignora la consulta y siempre devuelve la misma lista sintética, para
    poder controlar exactamente qué documentos ve cada sub-retriever."""

    docs: list[Document]

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del query, run_manager
        return self.docs


def _doc(identifier: str) -> Document:
    return Document(
        page_content=f"contenido sintético de {identifier}", metadata={"chunk_id": identifier}
    )


def _rrf_score(rank: int, weight: float, c: int = RRF_C) -> float:
    """Fórmula RRF ponderada — idéntica a la de ``HybridEnsembleRetriever._fuse()``.

    Se usa aquí únicamente como referencia analítica independiente para
    explicar los números; la evidencia real viene de invocar el retriever de
    producción (ver ``_run_fusion_scenario``), no de este cálculo manual.
    """
    return weight / (rank + c)


def _run_fusion_scenario(
    bm25_docs: list[Document], vector_docs: list[Document], max_results: int = 50
) -> list[str]:
    """Ejecuta la fusión RRF real de producción sobre listas sintéticas.

    Usa ``HybridEnsembleRetriever`` con los pesos/``c`` reales leídos arriba —
    el mismo código que corre en ``retrieve_forced_node`` — así que el
    resultado es evidencia directa del comportamiento real, no una
    reimplementación paralela.
    """
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(docs=bm25_docs),
            _StaticRetriever(docs=vector_docs),
        ],
        weights=[BM25_WEIGHT, VECTOR_WEIGHT],
        c=RRF_C,
        max_results=max_results,
    )
    result = retriever.invoke("consulta sintética")
    return [d.metadata["chunk_id"] for d in result]


# ============================================================
#  2. Escenarios sintéticos generales
# ============================================================


def scenario_exclusive_bm25_candidate() -> dict[str, Any]:
    """Un candidato que solo aparece en BM25 (rank 1), sin ningún resultado
    vectorial — debe ganar la fusión por ausencia de competencia, no por
    fuerza de su score."""
    order = _run_fusion_scenario(
        bm25_docs=[_doc("bm25_excl")],
        vector_docs=[],
    )
    return {
        "nombre": "candidato_exclusivo_bm25_sin_competencia_vectorial",
        "bm25_docs": ["bm25_excl"],
        "vector_docs": [],
        "orden_resultante": order,
        "score_bm25_excl_rank1": _rrf_score(1, BM25_WEIGHT),
    }


def scenario_exclusive_vector_candidates() -> dict[str, Any]:
    """Varios candidatos que solo aparecen en la búsqueda vectorial, sin
    ningún resultado BM25 — deben conservar su orden vectorial."""
    order = _run_fusion_scenario(
        bm25_docs=[],
        vector_docs=[_doc("v1"), _doc("v2"), _doc("v3")],
    )
    return {
        "nombre": "candidatos_exclusivos_vectoriales_sin_competencia_bm25",
        "bm25_docs": [],
        "vector_docs": ["v1", "v2", "v3"],
        "orden_resultante": order,
        "scores": {
            "v1": _rrf_score(1, VECTOR_WEIGHT),
            "v2": _rrf_score(2, VECTOR_WEIGHT),
            "v3": _rrf_score(3, VECTOR_WEIGHT),
        },
    }


def scenario_shared_candidate() -> dict[str, Any]:
    """Un candidato que aparece en ambas listas debe acumular la contribución
    de ambos rankings (no solo la del mejor de los dos)."""
    order = _run_fusion_scenario(
        bm25_docs=[_doc("shared"), _doc("bm25_only")],
        vector_docs=[_doc("vector_only"), _doc("shared")],
    )
    return {
        "nombre": "candidato_compartido_acumula_ambas_contribuciones",
        "bm25_docs": ["shared", "bm25_only"],
        "vector_docs": ["vector_only", "shared"],
        "orden_resultante": order,
        "scores": {
            "shared": _rrf_score(1, BM25_WEIGHT) + _rrf_score(2, VECTOR_WEIGHT),
            "bm25_only": _rrf_score(2, BM25_WEIGHT),
            "vector_only": _rrf_score(1, VECTOR_WEIGHT),
        },
    }


def scenario_final_ranking_mixed() -> dict[str, Any]:
    """Escenario mixto general (exclusivos de ambos tipos + compartido) con
    los pesos y la ``c`` reales de producción — contribución numérica por
    ranking y orden final."""
    order = _run_fusion_scenario(
        bm25_docs=[_doc("a"), _doc("b"), _doc("c")],
        vector_docs=[_doc("b"), _doc("d")],
    )
    scores = {
        "a": _rrf_score(1, BM25_WEIGHT),
        "b": _rrf_score(2, BM25_WEIGHT) + _rrf_score(1, VECTOR_WEIGHT),
        "c": _rrf_score(3, BM25_WEIGHT),
        "d": _rrf_score(2, VECTOR_WEIGHT),
    }
    return {
        "nombre": "ranking_final_mixto_pesos_reales",
        "bm25_docs": ["a", "b", "c"],
        "vector_docs": ["b", "d"],
        "pesos": {"bm25": BM25_WEIGHT, "vector": VECTOR_WEIGHT},
        "c": RRF_C,
        "orden_resultante": order,
        "orden_esperado_por_score": sorted(scores, key=lambda k: scores[k], reverse=True),
        "scores": scores,
    }


# ============================================================
#  3. Pregunta central: ¿compite un exclusivo BM25 (mejor rank posible)
#     contra un exclusivo vectorial, cuando la búsqueda vectorial entrega
#     al menos k candidatos?
# ============================================================


def bm25_exclusive_vs_vector_sweep(
    k_range: range = REALISTIC_K_CANDIDATES_RANGE,
) -> dict[str, Any]:
    """Para cada k en el rango realista de ``k_candidates`` del sistema
    (4–20), construye un escenario donde BM25 entrega un único candidato
    exclusivo en su mejor rank posible (rank 1) y la búsqueda vectorial
    entrega exactamente k candidatos exclusivos (ranks 1..k). Ejecuta la
    fusión real y registra en qué posición termina el candidato BM25.

    Si el candidato BM25 exclusivo (rank 1) nunca alcanza a competir con el
    último candidato vectorial (rank k) dentro de este rango, queda
    demostrado que —bajo la configuración real de producción— un candidato
    exclusivo de BM25 no compite normalmente con los candidatos vectoriales
    cuando la búsqueda vectorial ya entrega al menos k resultados.
    """
    rows: list[dict[str, Any]] = []
    for k in k_range:
        vector_docs = [_doc(f"v{i}") for i in range(1, k + 1)]
        order = _run_fusion_scenario(
            bm25_docs=[_doc("bm25_excl")],
            vector_docs=vector_docs,
            max_results=k + 1,
        )
        bm25_position = order.index("bm25_excl") + 1  # 1-indexado, legible en el reporte
        rows.append(
            {
                "k": k,
                "score_bm25_excl_rank1": _rrf_score(1, BM25_WEIGHT),
                "score_vector_ultimo_rank_k": _rrf_score(k, VECTOR_WEIGHT),
                "posicion_final_bm25_excl": bm25_position,
                "bm25_excl_supera_al_ultimo_vectorial": bm25_position <= k,
            }
        )

    # Punto de cruce analítico: k a partir del cual un vectorial en su peor
    # rank (k) empieza a perder frente al mejor caso posible de BM25 (rank 1).
    # weight_bm25/(1+c) = weight_vector/(k+c)  =>  k = weight_vector*(1+c)/weight_bm25 - c
    crossover_k = (VECTOR_WEIGHT * (1 + RRF_C) / BM25_WEIGHT) - RRF_C

    return {
        "nombre": "bm25_exclusivo_vs_vectorial_barrido_de_k",
        "pesos": {"bm25": BM25_WEIGHT, "vector": VECTOR_WEIGHT},
        "c": RRF_C,
        "rango_k_evaluado": [k_range.start, k_range.stop - 1],
        "filas": rows,
        "bm25_compite_en_algun_k_del_rango": any(
            r["bm25_excl_supera_al_ultimo_vectorial"] for r in rows
        ),
        "k_de_cruce_analitico": crossover_k,
        "conclusion": (
            "Con los pesos y la c reales de producción, un candidato exclusivo de "
            "BM25 en su mejor rank posible (1) solo alcanza a superar al peor "
            "candidato vectorial-exclusivo cuando ese candidato vectorial ocupa un "
            f"rank mayor a ~{crossover_k:.1f} — muy por fuera del rango realista de "
            "k_candidates de este sistema (4-20). Dentro de ese rango realista, el "
            "candidato exclusivo de BM25 nunca compite con los candidatos "
            "vectoriales cuando la búsqueda vectorial ya entrega al menos k "
            "resultados."
        ),
    }


# ============================================================
#  4. Punto de entrada — guarda evidencia JSON reproducible
# ============================================================


def run_all_scenarios() -> dict[str, Any]:
    return {
        "configuracion_leida_de_produccion": {
            "bm25_weight": BM25_WEIGHT,
            "vector_weight": VECTOR_WEIGHT,
            "c": RRF_C,
        },
        "escenarios": [
            scenario_exclusive_bm25_candidate(),
            scenario_exclusive_vector_candidates(),
            scenario_shared_candidate(),
            scenario_final_ranking_mixed(),
        ],
        "barrido_bm25_exclusivo_vs_vectorial": bm25_exclusive_vs_vector_sweep(),
    }


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def main(report_json_path: str = "evaluation/rrf_diagnostic_report.json") -> None:
    results = run_all_scenarios()

    _ensure_parent_dir(report_json_path)
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Diagnóstico RRF guardado en: {report_json_path}")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
