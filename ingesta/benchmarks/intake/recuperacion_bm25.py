"""FASE 5: recuperación PROXY con BM25 sobre los chunks de una colección Chroma local.

No sustituye a la evaluación vectorial (hit@4/MRR con embeddings reales, que
requiere Ollama): con embeddings falsos el ranking vectorial no significa nada,
así que este proxy léxico solo indica si los chunks de un documento recién
publicado son recuperables por las preguntas del ground truth. Sin LLM.

    python -I -X utf8 recuperacion_bm25.py --coleccion bench_intake_base --puerto 8011 \
        --ground-truth trabajo/gt_v02.json --raw C:/Users/Migue/r --salida trabajo/bm25_antes.json
    python -I -X utf8 recuperacion_bm25.py --comparar trabajo/bm25_antes.json trabajo/bm25_despues.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import unicodedata
from collections import Counter
from pathlib import Path

K1, B = 1.5, 0.75


def tokens(texto):
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", texto)


class BM25:
    def __init__(self, documentos):
        self.docs = [Counter(tokens(d)) for d in documentos]
        self.largos = [sum(d.values()) for d in self.docs]
        self.medio = sum(self.largos) / max(1, len(self.largos))
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def puntuar(self, consulta):
        q = tokens(consulta)
        salida = []
        for d, largo in zip(self.docs, self.largos, strict=True):
            s = 0.0
            for t in q:
                f = d.get(t)
                if f:
                    s += self.idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * largo / self.medio))
            salida.append(s)
        return salida


def clave(nombre):
    # Solo se quita la extensión conocida: los nombres llevan puntos («Cía. S. en C.»).
    nombre = unicodedata.normalize("NFC", Path(nombre).name)
    return re.sub(r"\.(pdf|md)$", "", nombre, flags=re.I).casefold().strip()


def evaluar(coleccion, puerto, ground_truth, raw):
    import chromadb

    datos = (
        chromadb.HttpClient(host="127.0.0.1", port=puerto)
        .get_collection(coleccion)
        .get(include=["documents", "metadatas"])
    )
    # Documento de cada chunk por su ruta de origen (alias), comparable con el ground truth.
    # Nombre original de cada documento por su SHA-256 (el nombre en el buzón es libre).
    nombres = {
        hashlib.sha256(p.read_bytes()).hexdigest(): clave(p.name)
        for p in raw.rglob("*")
        if p.is_file() and p.suffix.lower() in {".pdf", ".md"}
    }
    origen = [nombres.get(m.get("doc_id"), "") for m in datos["metadatas"]]
    alias = set(nombres.values())
    indice = BM25(datos["documents"])
    casos = json.loads(ground_truth.read_text(encoding="utf-8"))["cases"]
    filas = []
    for caso in casos:
        esperados = {clave(e) for e in caso["documentos_esperados"]}
        if not esperados & set(alias):
            continue
        puntos = indice.puntuar(caso["pregunta"])
        orden = sorted(range(len(puntos)), key=lambda i: -puntos[i])[:20]
        rango = next((r for r, i in enumerate(orden, 1) if origen[i] in esperados), None)
        filas.append(
            {
                "id": caso["id"],
                "esperados": sorted(esperados),
                "presente": any(o in esperados for o in origen),
                "rango": rango,
                "hit4": int(rango is not None and rango <= 4),
                "rr": 1 / rango if rango else 0.0,
            }
        )
    return {"coleccion": coleccion, "chunks": len(datos["ids"]), "casos": filas}


def resumen(filas):
    n = len(filas)
    return {
        "n": n,
        "hit4": sum(f["hit4"] for f in filas) / n if n else None,
        "mrr": sum(f["rr"] for f in filas) / n if n else None,
    }


def comparar(antes, despues, grupos, repeticiones=10000, semilla=20261110):
    a = {f["id"]: f for f in antes["casos"]}
    d = {f["id"]: f for f in despues["casos"]}
    salida = {}
    for nombre, ids in grupos.items():
        ids = [i for i in ids if i in a and i in d]
        rnd = random.Random(semilla)
        difs = {"hit4": [], "mrr": []}
        for _ in range(repeticiones):
            muestra = [rnd.choice(ids) for _ in ids] if ids else []
            for m, k in (("hit4", "hit4"), ("mrr", "rr")):
                if muestra:
                    difs[m].append(sum(d[i][k] - a[i][k] for i in muestra) / len(muestra))
        salida[nombre] = {
            "n": len(ids),
            "antes": resumen([a[i] for i in ids]),
            "despues": resumen([d[i] for i in ids]),
            **{
                f"ic95_delta_{m}": [
                    sorted(v)[int(0.025 * len(v))],
                    sorted(v)[int(0.975 * len(v)) - 1],
                ]
                if v
                else None
                for m, v in difs.items()
            },
        }
    return salida


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coleccion")
    parser.add_argument("--puerto", type=int, default=8011)
    parser.add_argument("--ground-truth", type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--salida", type=Path)
    parser.add_argument("--comparar", nargs=2, type=Path)
    parser.add_argument("--nuevos", nargs="*", default=[], help="claves de documentos nuevos")
    args = parser.parse_args()
    if args.comparar:
        antes, despues = (json.loads(p.read_text(encoding="utf-8")) for p in args.comparar)
        nuevos = {clave(n) for n in args.nuevos}
        ids_nuevos = [f["id"] for f in despues["casos"] if set(f["esperados"]) & nuevos]
        ids_resto = [f["id"] for f in despues["casos"] if not set(f["esperados"]) & nuevos]
        print(
            json.dumps(
                comparar(antes, despues, {"nuevos": ids_nuevos, "resto": ids_resto}), indent=1
            )
        )
        return
    resultado = evaluar(args.coleccion, args.puerto, args.ground_truth, args.raw)
    resultado["resumen"] = resumen(resultado["casos"])
    args.salida.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(resultado["resumen"]))


if __name__ == "__main__":
    main()
