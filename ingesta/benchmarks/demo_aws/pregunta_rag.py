"""FASE 4: una pregunta con el código de recuperación REAL de la aplicación `rag`.

Ejecuta ``get_ensemble_retriever`` (BM25 + vectores, RRF) sobre la colección
indicada y muestra los fragmentos con su cita tal como los vería el modelo
(``build_context_block``). Sin LLM. El BM25 de la aplicación se construye al
importar/arrancar: este script es un proceso nuevo, así ve la colección actual.

    CHROMA_HOST=127.0.0.1 CHROMA_COLLECTION=atlas_demo_base OLLAMA_BASE_URL=http://IP:11434 \\
    PYTHONPATH=backend python pregunta_rag.py "¿Qué dijo el tribunal sobre ...?" [--k 4]
"""

from __future__ import annotations

import argparse
import json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pregunta")
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--json", action="store_true", help="salida JSON")
    args = parser.parse_args()
    from rag.core.retriever import get_ensemble_retriever, init_retrievers
    from rag.core.tools import build_context_block

    init_retrievers()
    docs = get_ensemble_retriever(k=args.k, k_candidates=2 * args.k).invoke(args.pregunta)
    filas = [
        {
            "posicion": i,
            "title": d.metadata.get("title"),
            "source": d.metadata.get("source"),
            "chunk_id": d.metadata.get("chunk_id"),
            "doc_type": d.metadata.get("doc_type"),
            "section_name": d.metadata.get("section_name"),
            "pages": d.metadata.get("pages"),
            "texto": d.page_content[:300],
        }
        for i, d in enumerate(docs, 1)
    ]
    if args.json:
        print(json.dumps(filas, ensure_ascii=False, indent=1))
        return
    print(f"Pregunta: {args.pregunta}\n")
    for f in filas:
        print(f"{f['posicion']}. {f['title']}  (páginas {f['pages']}, sección {f['section_name']})")
        print(f"   chunk_id={f['chunk_id']}")
        print("   " + f["texto"].replace("\n", " ")[:220] + "…\n")
    print("Cabeceras de cita que recibiría el modelo:")
    for linea in build_context_block(docs).splitlines():
        if linea.startswith("[doc"):
            print("   " + linea)


if __name__ == "__main__":
    main()
