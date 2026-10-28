"""Métricas fijas sin LLM sobre ``legal-ground-truth-v0.2``: cero tokens y
resultado determinista.

Son las métricas que se corren **siempre** que se cambie la ingesta, el
retriever o los prompts, antes de gastar en el juez RAGAS:

Recuperación con la pregunta original (corre el retriever híbrido de
producción; requiere ChromaDB y Ollama de embeddings, sin modelo generador):

- ``acierto_doc_4``: el documento esperado está entre los 4 fragmentos que
  **llegan al modelo** (no en el top-4 de un ranking más largo).
- ``acierto_doc_20`` y ``mrr_doc_20``: presencia e inverso de la posición del
  documento esperado en el top-20.
- ``doc_recall_4``: fracción de los documentos esperados (hay casos con dos)
  presentes en los 4 fragmentos.
- ``articulos_4``: fracción de las referencias precisas que cita el equipo
  jurídico (artículos con numeración jerárquica como ``5.3.6.2`` y normas con
  número y año, en la respuesta y en ``ubicacion_evidencia``) que aparecen en
  el texto de esos 4 fragmentos. Mide si llega el artículo exacto, no solo el
  documento.
- ``docs_distintos_4``: documentos distintos entre los 4 fragmentos.
- ``fuga_territorial_4``: llega una norma local de un lugar que la pregunta
  no menciona (p. ej. el reglamento de Cartagena ante una pregunta general).

Grafo completo (sobre una caché de ``generation_cache.py`` ya generada; no
genera nada):

- ``acierto_doc_4_grafo`` y ``articulos_4_grafo``: lo mismo que arriba, pero
  con los fragmentos que recuperó el grafo con la consulta enriquecida.
- ``citas_validas``: el validador de producción acepta las citas ``[docN]``.
- ``respuestas_con_refs_sin_respaldo``: la respuesta cita normas o artículos
  que no están en ningún fragmento ni en la pregunta.
- ``refs_esperadas_en_respuesta``: fracción de las referencias del equipo
  jurídico que la respuesta menciona.

Cada métrica global lleva un intervalo de confianza del 95 % por bootstrap con
semilla fija, y el reporte se desglosa por tipo de pregunta, revisión y clase
de documento esperado. Si existe la línea base versionada
(``data/linea-base-sin-llm-v0.2.json``), se compara contra ella: una métrica
es regresión si sale del intervalo de la línea base en la dirección mala.

Uso:
    CHROMA_HOST=… OLLAMA_BASE_URL=… uv run python -m evaluation.metricas_sin_llm
    uv run python -m evaluation.metricas_sin_llm --sin-recuperacion   # solo la caché
    uv run python -m evaluation.metricas_sin_llm --guardar-linea-base
"""

from __future__ import annotations

import argparse
import json
import random
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evaluation.generation_cache import CACHE_PATH, load_cache
from evaluation.ground_truth_v02 import load_ground_truth_v02
from evaluation.ragas_common import git_state
from evaluation.retrieval_baseline import (
    DEEP_K,
    PROD_K,
    PROD_K_CANDIDATES,
    doc_recall_at_k,
    first_relevant_rank,
)
from evaluation.run_paths import tagged
from rag.core.agent import _validate_citations

REPORT_PATH = Path("evaluation/results/metricas-sin-llm-v0.2.json")
BASELINE_PATH = Path("evaluation/data/linea-base-sin-llm-v0.2.json")

SEMILLA = 20261028
REPETICIONES = 2000

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


@dataclass(frozen=True)
class Metrica:
    clave: str
    seccion: str  # "recuperacion" o "respuesta"
    sentido: int  # 1: más alto es mejor; -1: más bajo es mejor; 0: informativa


METRICAS: tuple[Metrica, ...] = (
    Metrica("acierto_doc_4", "recuperacion", 1),
    Metrica("acierto_doc_20", "recuperacion", 1),
    Metrica("mrr_doc_20", "recuperacion", 1),
    Metrica("doc_recall_4", "recuperacion", 1),
    Metrica("articulos_4", "recuperacion", 1),
    Metrica("docs_distintos_4", "recuperacion", 0),
    Metrica("fuga_territorial_4", "recuperacion", -1),
    Metrica("acierto_doc_4_grafo", "respuesta", 1),
    Metrica("articulos_4_grafo", "respuesta", 1),
    Metrica("citas_validas", "respuesta", 1),
    Metrica("respuestas_con_refs_sin_respaldo", "respuesta", -1),
    Metrica("refs_esperadas_en_respuesta", "respuesta", 1),
)
SENTIDO = {m.clave: m.sentido for m in METRICAS}

# Métricas que se desglosan por grupo en el reporte Markdown.
DESGLOSE = (
    "acierto_doc_4",
    "mrr_doc_20",
    "articulos_4",
    "fuga_territorial_4",
    "acierto_doc_4_grafo",
    "respuestas_con_refs_sin_respaldo",
)
GRUPOS = ("tipo", "revisado", "clase_esperada")


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


def clase_esperada(documentos: list[str]) -> str:
    """Clase de los documentos esperados: las sentencias del corpus se
    titulan ``AP <demandante> VS <demandado>``; el resto es normativa."""
    if not documentos:
        return "sin documento"
    clases = {"jurisprudencia" if d.startswith("AP ") else "normativa" for d in documentos}
    return clases.pop() if len(clases) == 1 else "mixta"


def _cobertura(esperadas: set[str], encontradas: set[str]) -> float | None:
    return len(esperadas & encontradas) / len(esperadas) if esperadas else None


def _refs_esperadas(caso: dict[str, Any]) -> set[str]:
    return referencias_legales(f"{caso['respuesta']} {caso['ubicacion_evidencia']}")


def _grupos(caso: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": caso["id"],
        "tipo": caso["tipo"],
        "revisado": str(caso.get("revisado")),
        "clase_esperada": clase_esperada(caso["documentos_esperados"]),
    }


def metricas_recuperacion(
    caso: dict[str, Any], top4: list[dict[str, Any]], titulos_20: list[str]
) -> dict[str, Any]:
    """Métricas de un caso. ``top4``: fragmentos que llegan al modelo, con
    ``title``, ``doc_type`` y ``texto``; ``titulos_20``: títulos del top-20.
    Las métricas que no aplican al caso valen ``None``."""
    esperados = caso["documentos_esperados"]
    titulos_4 = [f["title"] for f in top4]
    pregunta = _plano(caso["pregunta"])
    lugares = {lugar for f in top4 if (lugar := norma_local(f)) is not None}
    posicion = first_relevant_rank(titulos_20, esperados) if esperados else None
    return {
        **_grupos(caso),
        "titulos_4": titulos_4,
        "lugares_4": sorted(lugares),
        "acierto_doc_4": first_relevant_rank(titulos_4, esperados) is not None
        if esperados
        else None,
        "acierto_doc_20": posicion is not None if esperados else None,
        "posicion_doc_20": posicion,
        "mrr_doc_20": (1 / posicion if posicion else 0.0) if esperados else None,
        "doc_recall_4": doc_recall_at_k(titulos_4, esperados, len(titulos_4))
        if esperados
        else None,
        "articulos_4": _cobertura(
            _refs_esperadas(caso), referencias_legales(" ".join(f["texto"] for f in top4))
        ),
        "docs_distintos_4": len(set(titulos_4)),
        "fuga_territorial_4": any(
            not any(p in pregunta for p in LUGARES[lugar]) for lugar in lugares
        ),
    }


def metricas_respuesta(
    caso: dict[str, Any],
    answer: str,
    contexts: list[str],
    context_titles: list[str] | None = None,
) -> dict[str, Any]:
    """Métricas de una respuesta ya generada, contra sus propios fragmentos."""
    citadas = referencias_legales(answer)
    respaldo = referencias_legales(" ".join(contexts)) | referencias_legales(caso["pregunta"])
    sin_respaldo = sorted(citadas - respaldo)
    esperados = caso["documentos_esperados"]
    return {
        **_grupos(caso),
        "acierto_doc_4_grafo": first_relevant_rank(context_titles, esperados) is not None
        if esperados and context_titles is not None
        else None,
        "articulos_4_grafo": _cobertura(
            _refs_esperadas(caso), referencias_legales(" ".join(contexts))
        ),
        "citas_validas": _validate_citations(answer, len(contexts)),
        "refs_sin_respaldo": sin_respaldo,
        # Por caso: la respuesta tiene al menos una referencia sin respaldo.
        "respuestas_con_refs_sin_respaldo": bool(sin_respaldo),
        "refs_esperadas_en_respuesta": _cobertura(_refs_esperadas(caso), citadas),
    }


def intervalo_95(valores: list[float]) -> list[float] | None:
    """Intervalo de confianza del 95 % de la media por bootstrap percentil,
    con semilla fija para que sea reproducible."""
    if len(valores) < 2:
        return None
    rng = random.Random(SEMILLA)
    n = len(valores)
    medias = sorted(sum(rng.choices(valores, k=n)) / n for _ in range(REPETICIONES))
    return [medias[int(0.025 * REPETICIONES)], medias[int(0.975 * REPETICIONES) - 1]]


def _valores(filas: Iterable[dict[str, Any]], clave: str) -> list[float]:
    return [float(f[clave]) for f in filas if f.get(clave) is not None]


def resumir(filas: list[dict[str, Any]], con_intervalo: bool = True) -> dict[str, dict[str, Any]]:
    """Media, ``n`` y (opcional) intervalo del 95 % de cada métrica presente,
    ignorando los casos donde no aplica (``None``)."""
    resumen: dict[str, dict[str, Any]] = {}
    for m in METRICAS:
        if not filas or m.clave not in filas[0]:
            continue
        valores = _valores(filas, m.clave)
        resumen[m.clave] = {
            "n": len(valores),
            "valor": sum(valores) / len(valores) if valores else None,
        }
        if con_intervalo:
            resumen[m.clave]["ic95"] = intervalo_95(valores)
    return resumen


def resumir_por(filas: list[dict[str, Any]], campo: str) -> dict[str, dict[str, dict[str, Any]]]:
    """``resumir`` (sin intervalo) por cada valor de ``campo``."""
    grupos = sorted({str(f[campo]) for f in filas})
    return {
        g: resumir([f for f in filas if str(f[campo]) == g], con_intervalo=False) for g in grupos
    }


def comparar(
    actual: dict[str, dict[str, Any]],
    filas_actuales: list[dict[str, Any]],
    base: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Compara contra la línea base. ``estado``: ``regresion`` o ``mejora`` si
    el valor sale del intervalo de la línea base en esa dirección, si no
    ``igual``; ``casos_peor`` y ``casos_mejor`` cuentan los casos que cambian."""
    por_caso = {f["case_id"]: f for f in filas_actuales}
    resultado: dict[str, dict[str, Any]] = {}
    for clave, b in base["global"].items():
        a = actual.get(clave)
        if a is None or a["valor"] is None or b["valor"] is None:
            continue
        sentido = SENTIDO.get(clave, 0)
        estado = "igual"
        if sentido and b.get("ic95"):
            bajo, alto = b["ic95"]
            if a["valor"] < bajo:
                estado = "regresion" if sentido > 0 else "mejora"
            elif a["valor"] > alto:
                estado = "mejora" if sentido > 0 else "regresion"
        peor, mejor = [], []
        for case_id, vb in base.get("casos", {}).get(clave, {}).items():
            va = por_caso.get(case_id, {}).get(clave)
            if va is None or vb is None or not sentido:
                continue
            if sentido * (float(va) - vb) < 0:
                peor.append(case_id)
            elif sentido * (float(va) - vb) > 0:
                mejor.append(case_id)
        resultado[clave] = {
            "base": b["valor"],
            "actual": a["valor"],
            "delta": a["valor"] - b["valor"],
            "estado": estado,
            "casos_peor": sorted(peor),
            "casos_mejor": sorted(mejor),
        }
    return resultado


def linea_base(reporte: dict[str, Any]) -> dict[str, Any]:
    """Resumen global y valores por caso de un reporte, para versionar."""
    global_: dict[str, Any] = {}
    casos: dict[str, dict[str, float | None]] = {}
    for seccion in ("recuperacion", "respuesta"):
        datos = reporte.get(seccion)
        if not datos:
            continue
        global_.update(datos["global"])
        for clave in datos["global"]:
            casos[clave] = {
                f["case_id"]: None if f[clave] is None else float(f[clave]) for f in datos["casos"]
            }
    return {
        "dataset": reporte["dataset"],
        "fecha": reporte["fecha"],
        "git": reporte["git"],
        "cache": reporte.get("respuesta", {}).get("cache"),
        "global": global_,
        "casos": casos,
    }


# ── Reporte Markdown ─────────────────────────────────────────────────────────


def _num(valor: float | None) -> str:
    return "n/a" if valor is None else f"{valor:.3f}"


def _ic(ic: list[float] | None) -> str:
    return "—" if not ic else f"[{ic[0]:.3f}, {ic[1]:.3f}]"


def _ids(ids: list[str]) -> str:
    return ", ".join(i.removeprefix("registro-") for i in ids) or "—"


def reporte_markdown(reporte: dict[str, Any]) -> str:
    git = reporte["git"]
    lineas = [
        "# Métricas fijas sin LLM — legal-ground-truth-v0.2",
        "",
        f"- Fecha: {reporte['fecha']}",
        f"- Commit: `{str(git.get('commit', ''))[:7]}`"
        + (" (con cambios sin commit)" if git.get("dirty") else ""),
        f"- Caché de generación: `{reporte.get('respuesta', {}).get('cache', '—')}`",
        "- Intervalos: bootstrap del 95 % sobre los casos, semilla fija.",
        "",
    ]
    comparacion = reporte.get("comparacion", {})
    for seccion, titulo in (
        ("recuperacion", "Recuperación con la pregunta original"),
        ("respuesta", "Grafo completo (caché)"),
    ):
        datos = reporte.get(seccion)
        if not datos:
            continue
        lineas += [f"## {titulo}", ""]
        cab = "| Métrica | Valor | IC 95 % | n |"
        sep = "|---|---:|---|---:|"
        if comparacion:
            cab += " Línea base | Δ | Estado | Casos peor / mejor |"
            sep += "---:|---:|---|---|"
        lineas += [cab, sep]
        for clave, m in datos["global"].items():
            fila = f"| `{clave}` | {_num(m['valor'])} | {_ic(m.get('ic95'))} | {m['n']} |"
            if comparacion:
                c = comparacion.get(clave)
                fila += (
                    f" {_num(c['base'])} | {c['delta']:+.3f} | {c['estado']} | "
                    f"{len(c['casos_peor'])} / {len(c['casos_mejor'])} |"
                    if c
                    else " — | — | — | — |"
                )
            lineas.append(fila)
        lineas.append("")
        for campo in GRUPOS:
            claves = [k for k in DESGLOSE if k in datos["global"]]
            lineas += [
                f"| {campo} | n | " + " | ".join(f"`{k}`" for k in claves) + " |",
                "|---|---:|" + "---:|" * len(claves),
            ]
            for grupo, resumen in datos["por_" + campo].items():
                n = max((resumen[k]["n"] for k in claves), default=0)
                valores = " | ".join(_num(resumen[k]["valor"]) for k in claves)
                lineas.append(f"| {grupo} | {n} | {valores} |")
            lineas.append("")

    lineas += ["## Casos a revisar", ""]
    rec = reporte.get("recuperacion", {}).get("casos", [])
    resp = reporte.get("respuesta", {}).get("casos", [])
    fallos = [f["case_id"] for f in rec if f["acierto_doc_4"] is False]
    fugas = [
        f"{f['case_id']} ({', '.join(f['lugares_4'])})" for f in rec if f["fuga_territorial_4"]
    ]
    sin_resp = [
        f"{f['case_id']} ({', '.join(f['refs_sin_respaldo'])})"
        for f in resp
        if f["refs_sin_respaldo"]
    ]
    lineas += [
        f"- Sin el documento esperado en los 4 fragmentos ({len(fallos)}): {_ids(fallos)}",
        f"- Fuga territorial ({len(fugas)}): {'; '.join(fugas) or '—'}",
        f"- Referencias sin respaldo ({len(sin_resp)}): {'; '.join(sin_resp) or '—'}",
    ]
    for clave, c in comparacion.items():
        if c["casos_peor"]:
            lineas.append(
                f"- Empeoran en `{clave}` frente a la línea base: {_ids(c['casos_peor'])}"
            )
    return "\n".join(lineas) + "\n"


# ── Ejecución ────────────────────────────────────────────────────────────────


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


def _seccion(filas: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "global": resumir(filas),
        **{f"por_{campo}": resumir_por(filas, campo) for campo in GRUPOS},
        "casos": filas,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default=None, help="etiqueta de la corrida")
    parser.add_argument("--cache", type=Path, default=CACHE_PATH, help="caché de generación")
    parser.add_argument(
        "--sin-recuperacion", action="store_true", help="no correr el retriever (solo la caché)"
    )
    parser.add_argument(
        "--linea-base", type=Path, default=BASELINE_PATH, help="línea base contra la que comparar"
    )
    parser.add_argument(
        "--guardar-linea-base",
        action="store_true",
        help="guardar esta corrida como la nueva línea base (versionada)",
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
        reporte["recuperacion"] = _seccion(correr_recuperacion(casos))
    cache = load_cache(args.cache)
    if cache:
        filas_r = [
            metricas_respuesta(
                por_id[r["case_id"]], r["answer"], r["contexts"] or [], r.get("context_titles")
            )
            for r in cache
            if r.get("answer") and r.get("contexts")
        ]
        reporte["respuesta"] = {"cache": str(args.cache), **_seccion(filas_r)}

    if args.guardar_linea_base:
        args.linea_base.write_text(
            json.dumps(linea_base(reporte), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Línea base guardada: {args.linea_base}")
    elif args.linea_base.exists():
        base = json.loads(args.linea_base.read_text(encoding="utf-8"))
        actual = {**reporte.get("recuperacion", {}).get("global", {})}
        actual.update(reporte.get("respuesta", {}).get("global", {}))
        filas = {f["case_id"]: dict(f) for f in reporte.get("recuperacion", {}).get("casos", [])}
        for f in reporte.get("respuesta", {}).get("casos", []):
            filas.setdefault(f["case_id"], {}).update(f)
        reporte["comparacion"] = comparar(actual, list(filas.values()), base)

    ruta = tagged(REPORT_PATH, args.tag)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    ruta_md = ruta.with_suffix(".md")
    ruta_md.write_text(reporte_markdown(reporte), encoding="utf-8")
    for seccion in ("recuperacion", "respuesta"):
        for clave, m in reporte.get(seccion, {}).get("global", {}).items():
            estado = reporte.get("comparacion", {}).get(clave, {}).get("estado", "")
            print(f"{seccion:12} {clave:34} {_num(m['valor'])}  (n={m['n']}) {estado}")
    regresiones = [
        k for k, c in reporte.get("comparacion", {}).items() if c["estado"] == "regresion"
    ]
    if regresiones:
        print(f"REGRESIÓN frente a la línea base: {', '.join(regresiones)}")
    print(f"Reporte: {ruta} y {ruta_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
