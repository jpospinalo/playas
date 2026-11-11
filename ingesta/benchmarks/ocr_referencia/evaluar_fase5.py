"""FASE 5: compara variantes de OCR contra U en páginas de un conjunto fijado.

Lee el texto por página de cada variante (bronce completo ``<doc_id>.txt`` o
archivos ``<doc_id>_<pag>.txt`` de ``variantes_ocr.py``), lo compara con U con
``metricas`` (modo "contenido") y agrega CER/WER sumando ediciones, con IC
bootstrap por documento. Páginas OCR o digitales de S_mio, nunca excluidas de U.
El recall número/año usa exclusivamente la categoría crítica existente ``numero``.

    python -I evaluar_fase5.py --conjunto ajuste --variante base=bronce:trabajo/s_mio/run1/capas/bronze \
        --variante tsv=bronce:trabajo/s_mio/run3/capas/bronze --variante z2_psm6=pagina:trabajo/variantes/z2_psm6
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))

import metricas  # noqa: E402
from comun import csv_leer, json_guardar  # noqa: E402

DESC = BASE / "entrada" / "descomprimido"


def paginas_u(slug, categoria):
    texto = (DESC / "texto" / categoria / (slug + ".md")).read_text(encoding="utf-8")
    partes = re.split(r"<!-- página (\d+) -->", texto)
    return {int(partes[i]): partes[i + 1] for i in range(1, len(partes), 2)}


def texto_variante(tipo, ruta, doc_id, pagina):
    if tipo == "bronce":
        archivo = ruta / (doc_id + ".txt")
        if not archivo.exists():
            return None
        paginas = archivo.read_text(encoding="utf-8").split("\n\f\n")
        # Una página vacía, incluso la última, es una hipótesis válida.
        return paginas[pagina - 1] if 1 <= pagina <= len(paginas) else None
    if tipo != "pagina":
        raise ValueError("Tipo de variante desconocido: " + tipo)
    archivo = ruta / f"{doc_id}_{pagina:03d}.txt"
    return archivo.read_text(encoding="utf-8") if archivo.exists() else None


def agregar(filas, repeticiones=2000, semilla=20261110):
    if not filas:
        raise ValueError("Evaluación sin páginas")

    def tasa(fs, campo, base):
        return metricas.cociente(sum(f[campo] for f in fs), sum(f[base] for f in fs))

    cocientes = {
        "cer": ("ed_c", "ref_c"),
        "wer": ("ed_p", "ref_p"),
        "recall_critico": ("crit_ok", "crit_ref"),
        "recall_numero_anio": ("num_ok", "num_ref"),
    }

    docs = sorted({f["slug"] for f in filas})
    rnd = random.Random(semilla)
    muestras = {k: [] for k in cocientes}
    for _ in range(repeticiones):
        elegidos = [rnd.choice(docs) for _ in docs]
        fs = [f for d in elegidos for f in filas if f["slug"] == d]
        for nombre, (campo, base) in cocientes.items():
            valor = tasa(fs, campo, base)
            if valor is not None:
                muestras[nombre].append(valor)

    def intervalo(valores):
        if not valores:
            return None
        valores = sorted(valores)
        n = len(valores)
        return [valores[int(0.025 * n)], valores[max(0, int(0.975 * n) - 1)]]

    return {
        "paginas": len(filas),
        "documentos": len(docs),
        **{k: tasa(filas, campo, base) for k, (campo, base) in cocientes.items()},
        **{f"ic95_{k}_documento": intervalo(v) for k, v in muestras.items()},
        "bootstrap_validos": {k: len(v) for k, v in muestras.items()},
    }


def poblacion_esperada(slugs, mapping, excluidas, base_bronce, tipo_paginas):
    """Fija páginas y referencias exclusivamente desde el bronce base y U."""
    poblacion, faltantes_u = [], []
    for slug in sorted(slugs):
        doc_id = mapping[slug]["sha256"]
        extraccion = json.loads(
            (base_bronce / (doc_id + ".extraction.json")).read_text(encoding="utf-8")
        )
        u = paginas_u(slug, mapping[slug]["categoria"])
        ocr = metricas.paginas_ocr(extraccion)
        total = len(extraccion["chars_per_page"])
        elegidas = ocr if tipo_paginas == "ocr" else set(range(1, total + 1)) - ocr
        for pagina in sorted(elegidas):
            if (slug, pagina) in excluidas:
                continue
            if pagina not in u:
                faltantes_u.append(f"{slug}:{pagina}")
                continue
            poblacion.append(
                {"slug": slug, "doc_id": doc_id, "pagina": pagina, "referencia": u[pagina]}
            )
    if faltantes_u:
        raise ValueError("Faltan referencias U: " + ", ".join(faltantes_u))
    if not poblacion:
        raise ValueError("Evaluación sin páginas")
    return poblacion


def cargar_variantes(poblacion, variantes):
    textos, cobertura = {}, {}
    for nombre, (tipo, ruta) in variantes.items():
        textos[nombre] = [texto_variante(tipo, ruta, p["doc_id"], p["pagina"]) for p in poblacion]
        faltantes = [
            {k: p[k] for k in ("slug", "doc_id", "pagina")}
            for p, texto in zip(poblacion, textos[nombre], strict=True)
            if texto is None
        ]
        presentes = len(poblacion) - len(faltantes)
        cobertura[nombre] = {
            "esperadas": len(poblacion),
            "presentes": presentes,
            "faltantes": len(faltantes),
            "cobertura": metricas.cociente(presentes, len(poblacion)),
            "paginas_faltantes": faltantes,
        }
    return textos, cobertura


def porcentaje(valor):
    return "n/d" if valor is None else f"{100 * valor:.2f}%"


def intervalo_texto(intervalo):
    return "n/d" if intervalo is None else "[" + ", ".join(porcentaje(v) for v in intervalo) + "]"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conjunto", choices=["ajuste", "validacion", "todos"], required=True)
    parser.add_argument("--variante", action="append", required=True, help="nombre=tipo:ruta")
    parser.add_argument("--paginas", choices=["ocr", "digital"], default="ocr")
    parser.add_argument(
        "--permitir-faltantes",
        action="store_true",
        help="Evaluar faltantes como hipótesis vacías y reportar cobertura",
    )
    parser.add_argument("--salida", type=Path, default=BASE / "resultados" / "fase5")
    args = parser.parse_args()
    division = json.loads((BASE / "division_ajuste_validacion.json").read_text(encoding="utf-8"))
    mapping = {r["slug"]: r for r in csv_leer(DESC / "mapping.csv")}
    excluidas = {
        (r["slug"], int(r["pagina"]))
        for r in csv_leer(BASE / "resultados" / "paginas_excluidas.csv")
    }
    base_bronce = BASE / "trabajo" / "s_mio" / "run1" / "capas" / "bronze"
    variantes = {}
    for v in args.variante:
        nombre, resto = v.split("=", 1)
        tipo, ruta = resto.split(":", 1)
        if nombre in variantes or tipo not in {"bronce", "pagina"}:
            parser.error("Nombre duplicado o tipo de variante desconocido: " + v)
        variantes[nombre] = (tipo, (BASE / ruta) if not Path(ruta).is_absolute() else Path(ruta))
    filas = {n: [] for n in variantes}
    slugs = (
        division["ajuste"] + division["validacion"]
        if args.conjunto == "todos"
        else division[args.conjunto]
    )
    try:
        poblacion = poblacion_esperada(slugs, mapping, excluidas, base_bronce, args.paginas)
        textos, cobertura = cargar_variantes(poblacion, variantes)
    except ValueError as exc:
        parser.error(str(exc))
    salida = args.salida / f"{args.conjunto}_{args.paginas}.json"
    json_guardar(salida.with_name(salida.stem + "_cobertura.json"), cobertura)
    faltantes = [
        f"{n}: {p['slug']}:{p['pagina']} ({p['doc_id']})"
        for n, c in cobertura.items()
        for p in c["paginas_faltantes"]
    ]
    if faltantes and not args.permitir_faltantes:
        parser.error(
            "Faltan textos de variantes (véase cobertura; use --permitir-faltantes para hipótesis vacías):\n"
            + "\n".join(faltantes)
        )
    if faltantes:
        print("Faltantes evaluados como hipótesis vacías:\n" + "\n".join(faltantes))
    for nombre, hipotesis in textos.items():
        for p, texto in zip(poblacion, hipotesis, strict=True):
            faltante = texto is None
            texto = "" if faltante else texto
            m = metricas.metricas(texto, p["referencia"], modo="contenido")
            c = metricas.comparar_criticos(texto, p["referencia"], modo="contenido")
            filas[nombre].append(
                {
                    "slug": p["slug"],
                    "pagina": p["pagina"],
                    "faltante": faltante,
                    "ed_c": m["ediciones_caracteres"],
                    "ref_c": m["caracteres_ref"],
                    "ed_p": m["ediciones_palabras"],
                    "ref_p": m["palabras_ref"],
                    "crit_ref": sum(x["total_ref"] for x in c.values()),
                    "crit_ok": sum(x["comunes"] for x in c.values()),
                    "num_ref": c["numero"]["total_ref"],
                    "num_ok": c["numero"]["comunes"],
                }
            )
    resumen = {n: agregar(f) for n, f in filas.items()}
    json_guardar(
        salida,
        {
            "conjunto": args.conjunto,
            "paginas": args.paginas,
            "semilla_division": division["semilla"],
            "permitir_faltantes": args.permitir_faltantes,
            "cobertura": cobertura,
            "resumen": resumen,
            "filas": filas,
        },
    )
    for n, r in resumen.items():
        print(
            f"{n:12} pags={r['paginas']:3} docs={r['documentos']:2} CER={porcentaje(r['cer'])} "
            f"IC95doc={intervalo_texto(r['ic95_cer_documento'])} "
            f"WER={porcentaje(r['wer'])} recall_crit={porcentaje(r['recall_critico'])} "
            f"recall_numero_anio={porcentaje(r['recall_numero_anio'])} "
            f"cobertura={cobertura[n]['presentes']}/{cobertura[n]['esperadas']}"
        )


if __name__ == "__main__":
    main()
