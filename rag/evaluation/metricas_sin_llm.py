"""Métricas fijas sin LLM sobre ``legal-ground-truth-v0.2``: cero tokens y
resultado determinista.

Son las métricas que se corren **siempre** que se cambie la ingesta, el
retriever o los prompts, antes de gastar en el juez RAGAS:

Recuperación (corre el retriever híbrido de producción con la pregunta
original; requiere ChromaDB y Ollama de embeddings, sin modelo generador):

- ``acierto_doc_4``: el documento esperado está entre los 4 fragmentos que
  **llegan al modelo** (no en el top-4 de un ranking más largo).
- ``mrr_doc_20``: inverso de la posición del documento esperado en el top-20.
- ``articulos_4``: fracción de las referencias precisas que cita el equipo
  jurídico (artículos con numeración jerárquica como ``5.3.6.2`` y normas con
  número y año, en la respuesta y en ``ubicacion_evidencia``) que aparecen en
  el texto de esos 4 fragmentos. Mide si llega el artículo exacto, no solo el
  documento.
- ``docs_distintos_4``: documentos distintos entre los 4 fragmentos.
- ``fuga_territorial_4``: llega una norma local de un lugar que la pregunta
  no menciona (p. ej. el reglamento de Cartagena ante una pregunta general).

Respuesta (sobre una caché de ``generation_cache.py`` ya generada; no genera):

- ``citas_validas``: el validador de producción acepta las citas ``[docN]``.
- ``refs_sin_respaldo``: normas o artículos que la respuesta cita y que no
  están en ningún fragmento ni en la pregunta.
- ``refs_esperadas_en_respuesta``: fracción de las referencias del equipo
  jurídico que la respuesta menciona.

Uso:
    CHROMA_HOST=… OLLAMA_BASE_URL=… uv run python -m evaluation.metricas_sin_llm
    uv run python -m evaluation.metricas_sin_llm --sin-recuperacion   # solo la caché
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.generation_cache import CACHE_PATH, load_cache
from evaluation.ground_truth_v02 import load_ground_truth_v02
from evaluation.ragas_common import git_state
from evaluation.retrieval_baseline import DEEP_K, PROD_K, PROD_K_CANDIDATES, first_relevant_rank
from evaluation.run_paths import tagged
from rag.core.agent import _validate_citations

REPORT_PATH = Path("evaluation/results/metricas-sin-llm-v0.2.json")

# Lugar → palabras que lo identifican en el título de una norma o en la
# pregunta. Solo se consideran normas locales los documentos ``normativa``.
LUGARES: dict[str, tuple[str, ...]] = {
    "cartagena": ("cartagena", "bocagrande", "playa blanca", "baru", "castillogrande", "boquilla"),
    "santa marta": (
        "santa marta",
        "rodadero",
        "taganga",
        "playa cristal",
        "tayrona",
        "pozos colorados",
    ),
    "turbo": ("turbo",),
}

_NORMA_RE = re.compile(
    r"\b(ley|decreto|resolucion|acuerdo)(?:[\s-]+ley)?\s+(?:no\.?\s*)?(\d{1,5})\s+de\s+(\d{4})"
)
# Solo numeración jerárquica (≥ 3 niveles): "artículo 15" es ambiguo entre normas.
_ARTICULO_RE = re.compile(r"\b\d+\.\d+\.\d+(?:\.\d+)*\b")


def _plano(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar sin depender de la escritura."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def referencias_legales(texto: str) -> set[str]:
    """Normas con número y año (``ley 768/2002``) y artículos jerárquicos
    (``art 5.3.6.2``) citados en ``texto``."""
    plano = _plano(texto)
    refs = {f"{tipo} {numero}/{anio}" for tipo, numero, anio in _NORMA_RE.findall(plano)}
    refs |= {f"art {a}" for a in _ARTICULO_RE.findall(plano)}
    return refs


def norma_local(fragmento: dict[str, Any]) -> str | None:
    """Lugar de una norma local, o ``None`` si no es normativa local."""
    if fragmento.get("doc_type") != "normativa":
        return None
    titulo = _plano(str(fragmento.get("title", "")))
    for lugar, palabras in LUGARES.items():
        if any(p in titulo for p in palabras):
            return lugar
    return None


def _cobertura(esperadas: set[str], encontradas: set[str]) -> float | None:
    return len(esperadas & encontradas) / len(esperadas) if esperadas else None


def _refs_esperadas(caso: dict[str, Any]) -> set[str]:
    return referencias_legales(f"{caso['respuesta']} {caso['ubicacion_evidencia']}")


def metricas_recuperacion(
    caso: dict[str, Any], top4: list[dict[str, Any]], titulos_20: list[str]
) -> dict[str, Any]:
    """Métricas de un caso. ``top4``: fragmentos que llegan al modelo, con
    ``title``, ``doc_type`` y ``texto``; ``titulos_20``: títulos del top-20."""
    esperados = caso["documentos_esperados"]
    titulos_4 = [f["title"] for f in top4]
    pregunta = _plano(caso["pregunta"])
    lugares = {lugar for f in top4 if (lugar := norma_local(f)) is not None}
    return {
        "case_id": caso["id"],
        "tipo": caso["tipo"],
        "titulos_4": titulos_4,
        "acierto_doc_4": first_relevant_rank(titulos_4, esperados) is not None
        if esperados
        else None,
        "posicion_doc_20": first_relevant_rank(titulos_20, esperados) if esperados else None,
        "articulos_4": _cobertura(
            _refs_esperadas(caso), referencias_legales(" ".join(f["texto"] for f in top4))
        ),
        "docs_distintos_4": len(set(titulos_4)),
        "fuga_territorial_4": any(
            not any(p in pregunta for p in LUGARES[lugar]) for lugar in lugares
        ),
    }


def metricas_respuesta(caso: dict[str, Any], answer: str, contexts: list[str]) -> dict[str, Any]:
    """Métricas de una respuesta ya generada, contra sus propios fragmentos."""
    citadas = referencias_legales(answer)
    respaldo = referencias_legales(" ".join(contexts)) | referencias_legales(caso["pregunta"])
    return {
        "case_id": caso["id"],
        "citas_validas": _validate_citations(answer, len(contexts)),
        "refs_sin_respaldo": sorted(citadas - respaldo),
        "refs_esperadas_en_respuesta": _cobertura(_refs_esperadas(caso), citadas),
    }


def _media(valores: Iterable[float]) -> dict[str, Any]:
    lista = list(valores)
    return {"n": len(lista), "valor": sum(lista) / len(lista) if lista else None}


def resumir(filas: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Promedio de cada métrica presente, ignorando los casos donde no aplica
    (``None``). ``mrr_doc_20`` se deriva de ``posicion_doc_20`` sobre los casos
    con documento esperado."""
    if not filas:
        return {}
    resumen: dict[str, dict[str, Any]] = {}
    for clave in ("acierto_doc_4", "articulos_4", "docs_distintos_4", "fuga_territorial_4"):
        if clave in filas[0]:
            resumen[clave] = _media(float(f[clave]) for f in filas if f[clave] is not None)
    if "posicion_doc_20" in filas[0]:
        aplica = [f for f in filas if f.get("acierto_doc_4") is not None]
        resumen["mrr_doc_20"] = _media(
            1 / f["posicion_doc_20"] if f["posicion_doc_20"] else 0.0 for f in aplica
        )
    if "citas_validas" in filas[0]:
        resumen["citas_validas"] = _media(float(f["citas_validas"]) for f in filas)
        resumen["respuestas_con_refs_sin_respaldo"] = _media(
            float(bool(f["refs_sin_respaldo"])) for f in filas
        )
        resumen["refs_esperadas_en_respuesta"] = _media(
            f["refs_esperadas_en_respuesta"]
            for f in filas
            if f["refs_esperadas_en_respuesta"] is not None
        )
    return resumen


def _fragmentos(docs: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "title": str((d.metadata or {}).get("title", "")),
            "doc_type": (d.metadata or {}).get("doc_type"),
            "texto": d.page_content,
        }
        for d in docs
    ]


def correr_recuperacion(casos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from rag.core.retriever import get_ensemble_retriever, init_retrievers

    init_retrievers()
    prod = get_ensemble_retriever(k=PROD_K, k_candidates=PROD_K_CANDIDATES)
    deep = get_ensemble_retriever(k=DEEP_K, k_candidates=DEEP_K)
    filas = []
    for caso in casos:
        top4 = _fragmentos(prod.invoke(caso["pregunta"]))
        titulos_20 = [f["title"] for f in _fragmentos(deep.invoke(caso["pregunta"]))]
        filas.append(metricas_recuperacion(caso, top4, titulos_20))
        print(f"{caso['id']}: acierto={filas[-1]['acierto_doc_4']}")
    return filas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="etiqueta de la corrida")
    parser.add_argument("--cache", type=Path, default=CACHE_PATH, help="caché de generación")
    parser.add_argument(
        "--sin-recuperacion", action="store_true", help="no correr el retriever (solo la caché)"
    )
    args = parser.parse_args()

    casos = load_ground_truth_v02()
    por_id = {c["id"]: c for c in casos}
    reporte: dict[str, Any] = {
        "dataset": "legal-ground-truth-v0.2",
        "fecha": datetime.now(UTC).isoformat(),
        "git": git_state(),
        "tag": args.tag,
    }
    if not args.sin_recuperacion:
        filas = correr_recuperacion(casos)
        reporte["recuperacion"] = {"global": resumir(filas), "casos": filas}
    cache = load_cache(args.cache)
    if cache:
        filas_r = [
            metricas_respuesta(por_id[r["case_id"]], r["answer"], r["contexts"] or [])
            for r in cache
            if r.get("answer") and r.get("contexts")
        ]
        reporte["respuesta"] = {
            "cache": str(args.cache),
            "global": resumir(filas_r),
            "casos": filas_r,
        }

    ruta = tagged(REPORT_PATH, args.tag)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    for seccion in ("recuperacion", "respuesta"):
        for clave, m in reporte.get(seccion, {}).get("global", {}).items():
            valor = "n/a" if m["valor"] is None else f"{m['valor']:.3f}"
            print(f"{seccion:12} {clave:34} {valor}  (n={m['n']})")
    print(f"Reporte: {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
