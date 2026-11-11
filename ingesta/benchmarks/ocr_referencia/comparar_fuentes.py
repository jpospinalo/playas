"""FASES 3 y 4 locales; ejecutar con Python -I -B y el entorno PyMuPDF.

Contenido es el modo principal; estricto se conserva siempre como control.
S_prof se lee de objetos Git, sin checkout ni acceso al data/ de trabajo.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("comun", BASE / "comun.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
m, v, e = (c.modulo(n) for n in ("metricas", "validar_u", "estadistica"))
# Dependencias locales de las métricas, FASE 4 y el muestreo reutilizado.
# La misma lista acredita la caché y registra su procedencia.
CODIGO_CACHE = (
    "metricas.py",
    "comparar_fuentes.py",
    "fase4.py",
    "estadistica.py",
    "preparar_desacuerdos.py",
    "calcular_desacuerdos.py",
    "comun.py",
    "validar_u.py",
)
SALIDA = BASE / "resultados/fase3"
BRONCE = BASE / "trabajo/s_mio/run1/capas/bronze"
INCRUSTADO = "ap_gabriel_antonio_carrero_vs_dimar_y_otros_a44a"
MODOS = ("contenido", "estricto")
EXTRA_CAMPOS = (
    "lcs",
    "ngramas_ref",
    "ngramas_hip",
    "crit_total_ref",
    "crit_total_hip",
    "crit_comunes",
)
RATIOS = {
    **m.COCIENTES,
    "orden_lcs": (6, 7),
    "orden_precision": (6, 8),
    "recall_critico": (11, 9),
    "recall_critico_inverso": (11, 10),
}


def git(*args):
    return subprocess.run(
        ["git", "--no-optional-locks", "-C", str(BASE.parents[2]), *args],
        check=True,
        capture_output=True,
    ).stdout


def catalogo_prof():
    version = git("rev-parse", "origin/corpus").decode().strip()
    if not version.startswith("517c399"):
        raise ValueError("origin/corpus no corresponde a 517c399")
    entradas = git("ls-tree", "-r", "-z", "origin/corpus", "data/documents/bronze")
    catalogo = {}
    for entrada in entradas.split(b"\0"):
        if not entrada:
            continue
        info, ruta = entrada.split(b"\t", 1)
        ruta = ruta.decode("utf-8")
        if not ruta.endswith(".md"):
            continue
        clave = unicodedata.normalize("NFC", ruta)
        if clave in catalogo:
            raise ValueError("Colisión NFC de rutas S_prof")
        catalogo[clave] = {"ruta": ruta, "blob": info.split()[2].decode("ascii")}
    return version, catalogo


def ruta_prof(doc):
    nombre = doc["archivo_original"].rsplit(".", 1)[0] + ".md"
    return unicodedata.normalize("NFC", f"data/documents/bronze/{doc['categoria']}/{nombre}")


def paginas_s(texto, esperadas):
    paginas = texto.split("\n\f\n")
    if len(paginas) == esperadas + 1 and not paginas[-1].strip():
        paginas.pop()
    if len(paginas) != esperadas:
        raise ValueError(f"Separación S_mio: {len(paginas)} páginas; esperadas {esperadas}")
    return {i: t for i, t in enumerate(paginas, 1)}


def semaforo(cer):
    return (
        "no definido"
        if cer is None
        else "verde"
        if cer < 0.01
        else "amarillo"
        if cer <= 0.03
        else "rojo"
    )


def sensibilidad_u(cer):
    if cer is None:
        return None
    escenarios = [
        {
            "e_U": u,
            "intervalo": [max(0, cer - u), cer + u],
            "fraccion_discrepancia_potencial_U": min(1, u / cer) if cer else None,
        }
        for u in (0.0024, 0.0123)
    ]
    return {
        "cer_observado": cer,
        "envolvente": [max(0, cer - 0.0123), cer + 0.0123],
        "escenarios": escenarios,
        "supuesto": "Solo sería cota triangular si e_U fuera CER con igual denominador; el rango dado es error de palabra. Se muestra como sensibilidad hipotética, no CER real identificado. El límite inferior de error U no obliga a atribuirle esa fracción de la discrepancia.",
    }


def comparar_textos(s, u, modo, repetidos=()):
    f = m.metricas(s, u, modo=modo)
    crit = m.comparar_criticos(s, u, modo=modo)
    return {
        **f,
        "semaforo": semaforo(f["cer"]),
        "criticos": crit,
        "crit_total_ref": sum(x["total_ref"] for x in crit.values()),
        "crit_total_hip": sum(x["total_hip"] for x in crit.values()),
        "crit_comunes": sum(x["comunes"] for x in crit.values()),
        "ruido": m.ruido(s, u, repetidos, modo=modo),
    }


def agregar(filas, *, nivel, repeticiones=2000):
    campos = (*m.CAMPOS, *EXTRA_CAMPOS)
    vectores = [tuple(f[k] for k in campos) for f in filas]
    totales = list(map(sum, zip(*vectores, strict=True))) if vectores else [0] * len(campos)
    resultado = {
        "unidades": len(filas),
        "documentos": len({f["slug"] for f in filas}),
        **dict(zip(campos, totales, strict=True)),
        **{k: m.cociente(totales[a], totales[b]) for k, (a, b) in RATIOS.items()},
    }
    for unidad in ("pagina", "documento"):
        if nivel == "documento" and unidad == "pagina":
            resultado["ic95_por_pagina"] = None
            continue
        if not filas:
            resultado["ic95_por_" + unidad] = {k: None for k in RATIOS}
            continue
        if unidad == "documento":
            grupos = defaultdict(list)
            for fila, vector in zip(filas, vectores, strict=True):
                grupos[fila["slug"]].append(vector)
            poblacion = [tuple(map(sum, zip(*grupos[k], strict=True))) for k in sorted(grupos)]
        else:
            poblacion = vectores
        rng = random.Random(m.SEMILLA)
        valores = {k: [] for k in RATIOS}
        for _ in range(repeticiones):
            muestra = rng.choices(poblacion, k=len(poblacion))
            total = tuple(map(sum, zip(*muestra, strict=True)))
            for k, (a, b) in RATIOS.items():
                valores[k].append(m.cociente(total[a], total[b]))
        resultado["ic95_por_" + unidad] = {k: e.ic(vals) for k, vals in valores.items()}
    resultado["criticos_por_categoria"] = {}
    for categoria in m.PATRONES:
        ns = {
            k: sum(f["criticos"][categoria][k] for f in filas)
            for k in ("total_ref", "total_hip", "comunes")
        }
        resultado["criticos_por_categoria"][categoria] = {
            **ns,
            "recall_ref_en_hip": m.cociente(ns["comunes"], ns["total_ref"]),
            "recall_hip_en_ref": m.cociente(ns["comunes"], ns["total_hip"]),
        }
    resultado["semaforo"] = semaforo(resultado["cer"])
    cabeceras, resto = Counter(), Counter()
    for fila in filas:
        cabeceras.update(fila["ruido"]["encabezados_pies_repetidos"])
        resto.update(fila["ruido"]["otras_palabras"])
    resultado["ruido_agregado"] = {
        "palabras_extra": sum(f["ruido"]["palabras_extra"] for f in filas),
        "palabras_encabezados_pies": sum(cabeceras.values()),
        "palabras_resto": sum(resto.values()),
        "etiquetas_pagina": sum(len(f["ruido"]["etiquetas_pagina"]) for f in filas),
        "top_50_encabezados_pies": dict(cabeceras.most_common(50)),
        "top_50_resto": dict(resto.most_common(50)),
    }
    return resultado


def grupos_estratos(filas, nivel):
    grupos = {"total": filas}
    for tipo in ("digital", "OCR", "mixto"):
        grupos[tipo] = [f for f in filas if f["tipo_pagina"] == tipo]
    for cat in ("jurisprudencia", "normativa"):
        grupos[cat] = [f for f in filas if f["categoria"] == cat]
    for valor in (True, False):
        grupos["con_tabla" if valor else "sin_tabla"] = [f for f in filas if f["tabla_u"] == valor]
    grupos["capa_OCR_incrustada"] = [f for f in filas if f["capa_ocr_incrustada"]]
    if nivel == "pagina":
        grupos["capa_ge80"] = [f for f in filas if f["caracteres_capa_texto_pdf"] >= 80]
        grupos["capa_lt80"] = [f for f in filas if f["caracteres_capa_texto_pdf"] < 80]
    return {k: v for k, v in grupos.items() if v}


def cargar(fitz):
    mapping = c.csv_leer(v.ENTRADA / "mapping.csv")
    metadatos = {(f["slug"], int(f["pagina"])): f for f in c.csv_leer(v.ENTRADA / "paginas.csv")}
    excluidas = {
        (f["slug"], int(f["pagina"])) for f in c.csv_leer(BASE / "resultados/paginas_excluidas.csv")
    }
    version, catalogo = catalogo_prof()
    datos, emparejamiento, usados, vistos = {}, [], set(), set()
    for doc in mapping:
        if doc["duplicado_de"] or doc["sha256"] in vistos:
            continue
        vistos.add(doc["sha256"])
        md, _, pdf = v.rutas_documento(doc)
        _, u, prefijo = v.separar_paginas(md.read_text(encoding="utf-8-sig"))
        if prefijo or sorted(u) != list(range(1, int(doc["paginas"]) + 1)):
            raise ValueError("Marcas U no completas/unívocas: " + doc["slug"])
        stem = BRONCE / doc["sha256"]
        s = paginas_s(stem.with_suffix(".txt").read_text(encoding="utf-8-sig"), int(doc["paginas"]))
        extr = json.loads(stem.with_suffix(".extraction.json").read_text(encoding="utf-8"))
        calidad = json.loads(stem.with_suffix(".quality.json").read_text(encoding="utf-8"))
        if (
            extr["doc_id"] != doc["sha256"]
            or extr["sha256"] != doc["sha256"]
            or len(extr["chars_per_page"]) != len(s)
        ):
            raise ValueError("Metadatos S_mio incompatibles: " + doc["slug"])
        clave = ruta_prof(doc)
        if clave not in catalogo:
            raise ValueError("No hay S_prof para " + clave)
        blob = catalogo[clave]
        usados.add(clave)
        prof = git("cat-file", "blob", blob["blob"]).decode("utf-8-sig")
        elegibles = [p for p in sorted(u) if (doc["slug"], p) not in excluidas]
        capa = {}
        with fitz.open(pdf) as archivo:
            if archivo.page_count != len(u):
                raise ValueError("Páginas PDF no coincidentes")
            for p in elegibles:
                capa[p] = archivo[p - 1].get_text()
        datos[doc["slug"]] = {
            "doc": doc,
            "u": u,
            "s": s,
            "prof": prof,
            "extr": extr,
            "calidad": calidad,
            "elegibles": elegibles,
            "capa": capa,
            "meta": {p: metadatos[(doc["slug"], p)] for p in elegibles},
            "pdf": pdf,
        }
        emparejamiento.append(
            {
                "slug": doc["slug"],
                "doc_id": doc["sha256"],
                **blob,
                "paginas_elegibles": len(elegibles),
                "paginas_totales": len(u),
                "comparable_S_prof": len(elegibles) == len(u),
            }
        )
    c.json_guardar(
        SALIDA / "emparejamiento.json",
        {
            "version_S_prof": version,
            "documentos": emparejamiento,
            "md_fuera_de_U": [catalogo[k] for k in sorted(set(catalogo) - usados)],
            "regla": "Ruta exacta tras NFC. Se omite duplicado_de; S_prof no se pagina. Documentos con páginas U excluidas se omiten de comparaciones con S_prof.",
        },
    )
    return datos


def producir_filas(datos):
    filas, documentos = [], []
    for slug, d in datos.items():
        doc, extr, ps = d["doc"], d["extr"], d["elegibles"]
        ocr = m.paginas_ocr(extr)
        tipos = {"OCR" if p in ocr else "digital" for p in ps}
        tipo_doc = next(iter(tipos)) if len(tipos) == 1 else "mixto"
        for modo in MODOS:
            repetidos = m.encabezados_pies([d["s"][p] for p in ps], modo=modo)
            for p in ps:
                comun = {
                    "slug": slug,
                    "categoria": doc["categoria"],
                    "pagina": p,
                    "modo": modo,
                    "tipo_pagina": "OCR" if p in ocr else "digital",
                    "tabla_u": bool(re.search(r"<table\b", d["u"][p], re.I)),
                    "capa_ocr_incrustada": slug == INCRUSTADO,
                    "caracteres_capa_texto_pdf": int(d["meta"][p]["caracteres_capa_texto_pdf"]),
                    "confianza_ocr": extr["ocr_confidence"].get(str(p)),
                    "chars_per_page": extr["chars_per_page"][p - 1],
                    "nivel": "pagina",
                    "conjunto": "paginas_elegibles",
                }
                filas.append(
                    {
                        **comun,
                        "comparacion": "S_mio_vs_U",
                        **comparar_textos(d["s"][p], d["u"][p], modo, repetidos),
                    }
                )
                if comun["caracteres_capa_texto_pdf"] >= 80:
                    filas.append(
                        {
                            **comun,
                            "comparacion": "capa_vs_U",
                            **comparar_textos(d["capa"][p], d["u"][p], modo),
                        }
                    )
            s, u = ("\n\f\n".join(d[k][p] for p in ps) for k in ("s", "u"))
            comun_doc = {
                "slug": slug,
                "categoria": doc["categoria"],
                "pagina": None,
                "modo": modo,
                "nivel": "documento",
                "tipo_pagina": tipo_doc,
                "tabla_u": any("<table" in d["u"][p].lower() for p in ps),
                "capa_ocr_incrustada": slug == INCRUSTADO,
                "paginas": len(ps),
                "paginas_OCR": sum(p in ocr for p in ps),
                "paginas_digitales": sum(p not in ocr for p in ps),
            }
            mio = {
                **comun_doc,
                "comparacion": "S_mio_vs_U",
                "conjunto": "paginas_elegibles",
                **comparar_textos(s, u, modo, repetidos),
            }
            documentos.append(mio)
            if len(ps) == len(d["u"]):
                documentos.append({**mio, "conjunto": "documentos_completos_comparables"})
                for nombre, h, r in (
                    ("S_prof_vs_U", d["prof"], u),
                    ("S_mio_vs_S_prof", s, d["prof"]),
                ):
                    documentos.append(
                        {
                            **comun_doc,
                            "comparacion": nombre,
                            "conjunto": "documentos_completos_comparables",
                            **comparar_textos(h, r, modo),
                        }
                    )
        print("Métricas completas: " + slug, flush=True)
    return filas, documentos


def refrescar_ruido_documental(documentos, datos):
    """S_prof: recurrencia de líneas sin atribuir posición de página inexistente."""
    cache = {}
    for fila in documentos:
        slug, modo = fila["slug"], fila["modo"]
        if (slug, modo) not in cache:
            d = datos[slug]
            textos = {k: "\n\f\n".join(d[k][p] for p in d["elegibles"]) for k in ("s", "u")}
            textos["prof"] = d["prof"]
            repetidos = m.encabezados_pies([d["s"][p] for p in d["elegibles"]], modo=modo)
            lineas = Counter(m.normalizar(x, modo=modo) for x in d["prof"].splitlines())
            prof_repetidos = {x for x, n in lineas.items() if x and len(x) <= 250 and n >= 3}
            cache[slug, modo] = (textos, repetidos, prof_repetidos)
        textos, repetidos, prof_repetidos = cache[slug, modo]
        h, r = {
            "S_mio_vs_U": ("s", "u"),
            "S_prof_vs_U": ("prof", "u"),
            "S_mio_vs_S_prof": ("s", "prof"),
        }[fila["comparacion"]]
        fila["ruido"] = m.ruido(
            textos[h], textos[r], prof_repetidos if h == "prof" else repetidos, modo=modo
        )


def cargar_metricas_csv(ruta):
    def convertir(valor):
        if valor == "":
            return None
        if valor in {"True", "False"}:
            return valor == "True"
        if valor.startswith(("{", "[")):
            return json.loads(valor)
        if re.fullmatch(r"-?\d+", valor):
            return int(valor)
        if re.fullmatch(r"-?\d+(?:\.\d+)?e[+-]?\d+|-?\d+\.\d+", valor, re.I):
            return float(valor)
        return valor

    return [{k: convertir(v) for k, v in fila.items()} for fila in c.csv_leer(ruta)]


def version_pymupdf():
    import fitz

    return fitz.VersionBind


def huellas_fuentes(datos):
    """SHA256 de los bytes de cada fuente usada, sin informes regenerables."""
    _, catalogo = catalogo_prof()
    huellas = {"U": {}, "S_mio": {}, "S_prof": {}, "capa_pdf": {}, "pymupdf": version_pymupdf()}
    for slug, d in datos.items():
        huellas["capa_pdf"][slug] = hashlib.sha256(
            json.dumps(d["capa"], ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        doc = d["doc"]
        md = v.rutas_documento(doc)[0]
        huellas["U"][str(md.relative_to(BASE))] = c.huella(md)
        for sufijo in (".txt", ".extraction.json", ".quality.json"):
            ruta = BRONCE / (doc["sha256"] + sufijo)
            huellas["S_mio"][str(ruta.relative_to(BASE))] = c.huella(ruta)
        blob = catalogo[ruta_prof(doc)]
        huellas["S_prof"][blob["ruta"]] = {
            "blob": blob["blob"],
            "sha256": hashlib.sha256(git("cat-file", "blob", blob["blob"])).hexdigest(),
        }
    return huellas


def manifiesto_corridas():
    """Nombres y bytes de ambas corridas completas, también fuera de U."""
    return {
        f"run{j}": {
            p.relative_to(raiz).as_posix(): c.huella(p)
            for p in sorted(raiz.rglob("*"))
            if p.is_file()
        }
        if raiz.is_dir()
        else None
        for j in (1, 2)
        for raiz in [BASE / f"trabajo/s_mio/run{j}"]
    }


ARCHIVOS_FASE4 = ("repetibilidad.json", "alertas.json", "causas.json")


def procedencia_fase4(manifiesto):
    return {
        "corridas": manifiesto,
        "informes": {nombre: c.huella(SALIDA / nombre) for nombre in ARCHIVOS_FASE4},
    }


def comprobar_cache_fase4(manifiesto):
    ruta = SALIDA / "procedencia.json"
    if not ruta.is_file() or any(v is None for v in manifiesto.values()):
        return False
    anterior = json.loads(ruta.read_text(encoding="utf-8")).get("fase4", {})
    if anterior.get("corridas") != manifiesto:
        return False
    return all(
        (SALIDA / nombre).is_file()
        and anterior.get("informes", {}).get(nombre) == c.huella(SALIDA / nombre)
        for nombre in ARCHIVOS_FASE4
    )


def obtener_fase4(fases, filas, documentos, datos, *, reutilizar, manifiesto):
    if reutilizar and comprobar_cache_fase4(manifiesto):
        return tuple(json.loads((SALIDA / n).read_text(encoding="utf-8")) for n in ARCHIVOS_FASE4)
    return (
        fases.repetibilidad(),
        fases.alertas(filas, documentos, datos),
        fases.causas(filas, documentos, datos),
    )


def claves_filas(filas):
    """Identidad completa de cada fila; conserva duplicados para rechazarlos."""
    campos = ("slug", "pagina", "modo", "comparacion", "nivel", "conjunto")
    return sorted(["" if f[k] is None else str(f[k]) for k in campos] for f in filas)


def claves_esperadas(datos):
    """Universo de páginas/documentos obtenido de las entradas, sin métricas."""
    paginas, documentos = [], []
    for slug, d in datos.items():
        for modo in MODOS:
            for p in d["elegibles"]:
                comparaciones = ["S_mio_vs_U"]
                if int(d["meta"][p]["caracteres_capa_texto_pdf"]) >= 80:
                    comparaciones.append("capa_vs_U")
                for comparacion in comparaciones:
                    paginas.append([slug, str(p), modo, comparacion, "pagina", "paginas_elegibles"])
            documentos.append([slug, "", modo, "S_mio_vs_U", "documento", "paginas_elegibles"])
            if len(d["elegibles"]) == len(d["u"]):
                for comparacion in ("S_mio_vs_U", "S_prof_vs_U", "S_mio_vs_S_prof"):
                    documentos.append(
                        [
                            slug,
                            "",
                            modo,
                            comparacion,
                            "documento",
                            "documentos_completos_comparables",
                        ]
                    )
    return {"paginas.csv": sorted(paginas), "documentos.csv": sorted(documentos)}


def procedencia_csv(datos):
    return {
        nombre: {"sha256": c.huella(SALIDA / nombre), "claves": claves}
        for nombre, claves in claves_esperadas(datos).items()
    }


def comprobar_csv(datos, registros):
    """Rechaza CSV alterados o incompletos, incluso con hash actualizado."""
    for nombre, esperadas in claves_esperadas(datos).items():
        registro = registros.get(nombre, {})
        ruta = SALIDA / nombre
        if not ruta.is_file() or registro.get("sha256") != c.huella(ruta):
            raise ValueError("CSV alterado o ausente: " + nombre)
        if registro.get("claves") != esperadas:
            raise ValueError("Claves esperadas incompatibles: " + nombre)
        try:
            claves = claves_filas(c.csv_leer(ruta))
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("CSV inválido: " + nombre) from exc
        if claves != esperadas:
            raise ValueError("CSV incompleto o con claves duplicadas/inesperadas: " + nombre)


def comprobar_cache(datos, *, huellas_actuales=None):
    """Reanuda solo si normalización y entradas comprobables coinciden."""
    procedencia = json.loads((SALIDA / "procedencia.json").read_text(encoding="utf-8"))
    for ruta, esperado in procedencia["huellas_entrada"].items():
        if c.huella(BASE / ruta) != esperado:
            raise ValueError("Entrada modificada: " + ruta)
    if "huellas_fuentes" not in procedencia:
        return False  # Una procedencia antigua no permite acreditar los CSV.
    actuales = huellas_fuentes(datos) if huellas_actuales is None else huellas_actuales
    for fuente in ("U", "S_mio", "S_prof"):
        anteriores = procedencia["huellas_fuentes"].get(fuente, {})
        for ruta in anteriores.keys() | actuales[fuente].keys():
            if anteriores.get(ruta) != actuales[fuente].get(ruta):
                raise ValueError(f"{fuente} cambió: {ruta}")
    if (
        any(procedencia["huellas_fuentes"].get(k) != actuales[k] for k in ("capa_pdf", "pymupdf"))
        or procedencia.get("pymupdf") != actuales["pymupdf"]
    ):
        return False
    # También la clasificación OCR/digital forma parte de la caché. Las
    # entradas se verifican siempre, incluso cuando hay que recalcular código.
    codigo_coincide = all(
        procedencia["huellas_codigo"].get(nombre) == c.huella(BASE / nombre)
        for nombre in CODIGO_CACHE
    )
    if not codigo_coincide or "csv_metricas" not in procedencia:
        return False
    comprobar_csv(datos, procedencia["csv_metricas"])
    return True


def preparar_muestreo(filas, datos, fitz):
    """Recalcular métricas también conserva un muestreo con revisión humana."""
    ruta = SALIDA / "desacuerdos.csv"
    if ruta.exists() and any(
        f.get("veredicto", "").strip() or f.get("nota", "").strip() for f in c.csv_leer(ruta)
    ):
        print(
            "Se conserva el muestreo de desacuerdos con adjudicaciones/notas existentes.",
            flush=True,
        )
        return
    c.modulo("preparar_desacuerdos").preparar(filas, datos, fitz)


def resumir(filas, documentos):
    conjuntos = defaultdict(list)
    for fila in filas + documentos:
        conjuntos[(fila["comparacion"], fila["nivel"], fila["conjunto"], fila["modo"])].append(fila)
    resumen = []
    for (comparacion, nivel, conjunto, modo), propias in conjuntos.items():
        for estrato, grupo in grupos_estratos(propias, nivel).items():
            g = agregar(grupo, nivel=nivel)
            if comparacion in {"S_mio_vs_U", "S_prof_vs_U"}:
                g["sensibilidad_error_U"] = sensibilidad_u(g["cer"])
            resumen.append(
                {
                    "comparacion": comparacion,
                    "nivel": nivel,
                    "conjunto": conjunto,
                    "modo": modo,
                    "estrato": estrato,
                    **g,
                }
            )
        print("Agregados e IC: " + str((comparacion, nivel, conjunto, modo)), flush=True)
    return resumen


def calibrar():
    base = (
        "Artículo 15. Ley 99 de 1993; Decreto 2324 de 1984. Fecha 12/03/2024 y "
        "7 de agosto de 2020. Radicado 47001-2333-000-2021-00198-00. "
        "“Niñez”—protección… nota \\( [^{12}] \\) y \\( [3] \\). "
    )
    paginas = [
        (f"sintetica_{j}", (base + f"Contexto {j}: litoral, costa y ambiente. ") * (j + 3))
        for j in range(8)
    ]
    return {modo: m.calibrar(paginas, modo=modo) for modo in MODOS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibrar", action="store_true")
    parser.add_argument(
        "--reanudar",
        action="store_true",
        help="Reutilizar CSV verificados si el código coincide; si cambió, recalcular métricas, IC y FASE 4",
    )
    parser.add_argument(
        "--solo-resumen",
        action="store_true",
        help="Con --reanudar: conservar FASE 4 y recortes ya completos, recalcular solo ruido, agregados e informe",
    )
    args = parser.parse_args()
    if args.solo_resumen and not args.reanudar:
        parser.error("--solo-resumen requiere --reanudar")
    sys.stdout.reconfigure(encoding="utf-8")
    calibracion = calibrar()
    c.json_guardar(SALIDA / "calibracion.json", calibracion)
    if not all(x["correcto"] for x in calibracion.values()):
        raise SystemExit("Falló la calibración; no se interpreta el corpus")
    if args.calibrar:
        print("Calibración correcta en contenido y estricto.")
        return
    import fitz

    datos = cargar(fitz)
    huellas_actuales = huellas_fuentes(datos)
    cache_valida = (
        comprobar_cache(datos, huellas_actuales=huellas_actuales) if args.reanudar else False
    )
    if args.solo_resumen and not cache_valida:
        parser.error("El código cambió; se requiere recalcular FASE 4 sin --solo-resumen")
    if cache_valida:
        filas, documentos = (
            cargar_metricas_csv(SALIDA / n) for n in ("paginas.csv", "documentos.csv")
        )
    else:
        if args.reanudar:
            print(
                "El código de métricas/clasificación cambió; se recalculan todas las filas.",
                flush=True,
            )
        filas, documentos = producir_filas(datos)
    refrescar_ruido_documental(documentos, datos)
    c.csv_guardar(SALIDA / "paginas.csv", filas)
    c.csv_guardar(SALIDA / "documentos.csv", documentos)
    csv_metricas = procedencia_csv(datos)
    comprobar_csv(datos, csv_metricas)
    resumen = resumir(filas, documentos)
    c.json_guardar(
        SALIDA / "resumen.json",
        {
            "modo_principal": "contenido",
            "semilla": m.SEMILLA,
            "bootstrap": 2000,
            "estratos_documentales": "digital/OCR solo documentos puros; mixto separado; con_tabla documental significa alguna página con tabla, no solo su contenido.",
            "agregados": resumen,
        },
    )
    fases = c.modulo("fase4")
    manifiesto = manifiesto_corridas()
    repetibilidad, alertas, causas = obtener_fase4(
        fases, filas, documentos, datos, reutilizar=args.solo_resumen, manifiesto=manifiesto
    )
    if not args.solo_resumen:
        preparar_muestreo(filas, datos, fitz)
    fases.informe(resumen, repetibilidad, alertas, causas)
    c.json_guardar(
        SALIDA / "procedencia.json",
        {
            "pymupdf": fitz.VersionBind,
            "fase4": procedencia_fase4(manifiesto),
            "huellas_fuentes": huellas_actuales,
            "csv_metricas": csv_metricas,
            "huellas_codigo": {nombre: c.huella(BASE / nombre) for nombre in CODIGO_CACHE},
            "huellas_entrada": {
                str(p.relative_to(BASE)): c.huella(p)
                for p in (
                    v.ENTRADA / "mapping.csv",
                    v.ENTRADA / "paginas.csv",
                    BASE / "resultados/paginas_excluidas.csv",
                )
            },
        },
    )
    print("FASES 3 y 4 completadas. Desacuerdos pendientes de adjudicación.")


if __name__ == "__main__":
    main()
