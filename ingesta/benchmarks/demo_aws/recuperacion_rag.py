"""Recuperación real (sin LLM) con el retriever híbrido de la aplicación `rag`.

Usa ``rag.core.retriever.get_ensemble_retriever`` (BM25 + vectores de Ollama, fusión
RRF) igual que el arnés de Julián (``retrieval_baseline_julian.py``, copiado sin
cambios de origin/julian-rincon/evaluacion-ragas-linea-base) y sus funciones
``first_relevant_rank`` y ``summarize_retrieval``: hit@4 con la pasada de producción
(k=4, k_candidates=8) y MRR/hit@20 con la pasada profunda (k=20). Cruza chunk →
documento por el metadato ``title`` en NFC.

El índice BM25 de la aplicación se construye UNA vez por proceso: cada medición
corre en un proceso nuevo, así refleja el estado actual de la colección.

    # desde rag/, con su entorno:
    CHROMA_HOST=127.0.0.1 CHROMA_PORT=8000 CHROMA_COLLECTION=atlas_demo_e2e \\
    OLLAMA_BASE_URL=http://<ollama>:11434 PYTHONPATH=backend \\
    python recuperacion_rag.py medir --ground-truth gt_v02.json --salida antes.json
    python recuperacion_rag.py comparar antes.json despues.json --nuevos "AP Gieseken ..." ...
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import random
import sys
import time
import unicodedata
from pathlib import Path

AQUI = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("julian", AQUI / "retrieval_baseline_julian.py")
julian = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(julian)


def nfc(texto):
    return unicodedata.normalize("NFC", texto)


def medir(ground_truth):
    from rag.core.retriever import get_ensemble_retriever, init_retrievers

    init_retrievers()
    prod = get_ensemble_retriever(k=julian.PROD_K, k_candidates=julian.PROD_K_CANDIDATES)
    deep = get_ensemble_retriever(k=julian.DEEP_K, k_candidates=julian.DEEP_K)
    casos = json.loads(Path(ground_truth).read_text(encoding="utf-8"))["cases"]
    filas = []
    for caso in casos:
        if not caso["documentos_esperados"]:
            continue
        inicio = time.monotonic()
        top_prod = julian._titles(prod.invoke(caso["pregunta"]))
        top_deep = julian._titles(deep.invoke(caso["pregunta"]))
        rango = julian.first_relevant_rank(top_deep, caso["documentos_esperados"])
        filas.append(
            {
                "case_id": caso["id"],
                "documentos_esperados": [nfc(d) for d in caso["documentos_esperados"]],
                "top_prod": top_prod,
                "rank": rango,
                "hit4": int(rango is not None and rango <= julian.PROD_K),
                "rr": 1 / rango if rango else 0.0,
                "doc_recall_at_4": julian.doc_recall_at_k(
                    top_prod, caso["documentos_esperados"], julian.PROD_K
                ),
                "segundos": round(time.monotonic() - inicio, 2),
            }
        )
    return filas


def comparar(antes, despues, nuevos, repeticiones=10000, semilla=20261110):
    nuevos = {nfc(n) for n in nuevos}
    a = {f["case_id"]: f for f in antes["casos"]}
    d = {f["case_id"]: f for f in despues["casos"]}
    grupos = {
        "nuevos": [i for i in d if set(d[i]["documentos_esperados"]) & nuevos],
        "resto": [i for i in d if not set(d[i]["documentos_esperados"]) & nuevos],
    }
    salida = {}
    for nombre, ids in grupos.items():
        ids = [i for i in ids if i in a]
        rnd = random.Random(semilla)
        difs = {"hit4": [], "rr": []}
        for _ in range(repeticiones if ids else 0):
            muestra = [rnd.choice(ids) for _ in ids]
            for k in difs:
                difs[k].append(sum(d[i][k] - a[i][k] for i in muestra) / len(muestra))

        def media(filas, k):
            return sum(f[k] for f in filas) / len(filas) if filas else None

        def ic(v):
            v = sorted(v)
            return [v[int(0.025 * len(v))], v[int(0.975 * len(v)) - 1]] if v else None

        salida[nombre] = {
            "n": len(ids),
            "hit4_antes": media([a[i] for i in ids], "hit4"),
            "hit4_despues": media([d[i] for i in ids], "hit4"),
            "mrr_antes": media([a[i] for i in ids], "rr"),
            "mrr_despues": media([d[i] for i in ids], "rr"),
            "ic95_delta_hit4": ic(difs["hit4"]),
            "ic95_delta_mrr": ic(difs["rr"]),
        }
    return salida


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="orden", required=True)
    m = sub.add_parser("medir")
    m.add_argument("--ground-truth", type=Path, required=True)
    m.add_argument("--salida", type=Path, required=True)
    c = sub.add_parser("comparar")
    c.add_argument("antes", type=Path)
    c.add_argument("despues", type=Path)
    c.add_argument("--nuevos", nargs="+", required=True, help="títulos de los documentos nuevos")
    args = parser.parse_args()
    if args.orden == "medir":
        filas = medir(args.ground_truth)
        resumen = julian.summarize_retrieval([{**f, "todos": "todos"} for f in filas], "todos")
        args.salida.write_text(
            json.dumps({"casos": filas, "resumen": resumen}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        print(json.dumps(resumen, ensure_ascii=False))
        return 0
    antes, despues = (json.loads(p.read_text(encoding="utf-8")) for p in (args.antes, args.despues))
    print(json.dumps(comparar(antes, despues, args.nuevos), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
