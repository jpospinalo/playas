"""FASE 1 automática, local y reproducible. Entrada siempre de solo lectura.

Ejecutar con Python -I -B. Importa exclusivamente la biblioteca hermana revisable;
nunca importa ni ejecuta contenido de entrada. No tiene clientes de red/LLM/AWS.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
ENTRADA = BASE / "entrada" / "descomprimido"
FIDELIDAD = BASE.parent / "fidelidad" / "trabajo"
SALIDA = BASE / "resultados"
MARCADOR = re.compile(r"<!--\s*página\s+(\d+)\s*-->", re.I)
UMBRALES = {
    "digital_caracteres": 80,
    "recuperacion_minima": 0.85,
    "precision_minima": 0.85,
    "orden_lcs_minimo": 0.65,
}


def _biblioteca():
    spec = importlib.util.spec_from_file_location("metricas_ocr_referencia", BASE / "metricas.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


m = _biblioteca()


def sha256(ruta):
    h = hashlib.sha256()
    with ruta.open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def leer_csv(ruta):
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return list(csv.DictReader(archivo))


def guardar_json(nombre, datos):
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / nombre).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def guardar_csv(nombre, filas, campos):
    SALIDA.mkdir(parents=True, exist_ok=True)
    with (SALIDA / nombre).open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        for fila in filas:
            escritor.writerow(
                {
                    k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                    for k, v in fila.items()
                    if k in campos
                }
            )


def verdadero(valor):
    return str(valor).strip().lower() == "true"


def separar_paginas(texto):
    """Devuelve secuencia de marcas y páginas solo si su número es unívoco."""
    marcas = list(MARCADOR.finditer(texto))
    numeros = [int(x[1]) for x in marcas]
    conteo = Counter(numeros)
    paginas = {
        int(marca[1]): texto[
            marca.end() : marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        ]
        for i, marca in enumerate(marcas)
        if conteo[int(marca[1])] == 1
    }
    prefijo = texto[: marcas[0].start()].strip() if marcas else texto.strip()
    return numeros, paginas, prefijo


def rutas_documento(fila):
    """No permite que campos de datos dirijan lecturas fuera de las raíces."""
    if not re.fullmatch(r"[a-z0-9_]+", fila["slug"]):
        raise ValueError("Slug inválido")
    if fila["categoria"] not in {"jurisprudencia", "normativa"}:
        raise ValueError("Categoría inválida")
    if not re.fullmatch(r"[a-f0-9]{64}", fila["sha256"]):
        raise ValueError("SHA256 inválido")
    md = ENTRADA / "texto" / fila["categoria"] / (fila["slug"] + ".md")
    raw = ENTRADA / "crudo" / fila["categoria"] / (fila["slug"] + ".raw.txt")
    pdf = FIDELIDAD / "originales" / (fila["sha256"][:12] + ".pdf")
    for ruta, raiz in ((md, ENTRADA), (raw, ENTRADA), (pdf, FIDELIDAD / "originales")):
        if not ruta.resolve().is_relative_to(raiz.resolve()):
            raise ValueError("Ruta fuera de la raíz de lectura")
    return md, raw, pdf


def integridad(mapping, metadatos, fitz):
    discrepancias, documentos, textos, paginas_u = [], [], {}, {}
    mapa = json.loads((FIDELIDAD / "mapa_originales.json").read_text(encoding="utf-8"))

    def fallo(tipo, **datos):
        discrepancias.append({"tipo": tipo, **datos})

    slugs = [f["slug"] for f in mapping]
    for slug, n in Counter(slugs).items():
        if n != 1:
            fallo("slug_mapping_duplicado", slug=slug, filas=n)
    esperados = {"texto": set(), "crudo": set()}
    cache_pdf = {}
    for fila in mapping:
        slug = fila["slug"]
        try:
            md, raw, pdf = rutas_documento(fila)
        except ValueError as exc:
            fallo("mapping_invalido", slug=slug, detalle=str(exc))
            continue
        esperados["texto"].add(md.relative_to(ENTRADA / "texto").as_posix())
        esperados["crudo"].add(raw.relative_to(ENTRADA / "crudo").as_posix())
        doc = {
            "slug": slug,
            "categoria": fila["categoria"],
            "sha256_mapping": fila["sha256"],
            "paginas_mapping": int(fila["paginas"]),
            "duplicado_de": fila["duplicado_de"],
        }
        documentos.append(doc)
        if not pdf.is_file():
            fallo("pdf_ausente", slug=slug, archivo=pdf.name)
        else:
            try:
                if pdf not in cache_pdf:
                    with fitz.open(pdf) as original:
                        cache_pdf[pdf] = (sha256(pdf), original.page_count)
                doc["sha256_pdf"], doc["paginas_pdf"] = cache_pdf[pdf]
                if doc["sha256_pdf"] != fila["sha256"]:
                    fallo(
                        "sha256_pdf", slug=slug, esperado=fila["sha256"], obtenido=doc["sha256_pdf"]
                    )
                if doc["paginas_pdf"] != int(fila["paginas"]):
                    fallo(
                        "paginas_pdf",
                        slug=slug,
                        esperado=int(fila["paginas"]),
                        obtenido=doc["paginas_pdf"],
                    )
                if mapa.get(pdf.name, {}).get("sha256") != fila["sha256"]:
                    fallo("mapa_originales", slug=slug, archivo=pdf.name)
            except (OSError, RuntimeError, ValueError) as exc:
                fallo("pdf_ilegible", slug=slug, detalle=str(exc))
        for ruta, campo in ((md, "md"), (raw, "raw")):
            if not ruta.is_file():
                fallo("archivo_ausente", slug=slug, formato=campo)
            else:
                doc["sha256_" + campo] = sha256(ruta)
        if not md.is_file():
            continue
        texto = md.read_text(encoding="utf-8-sig")
        textos[slug] = texto
        numeros, paginas, prefijo = separar_paginas(texto)
        paginas_u[slug] = paginas
        doc["marcadores"] = len(numeros)
        if numeros != list(range(1, int(fila["paginas"]) + 1)):
            fallo(
                "marcadores_no_consecutivos",
                slug=slug,
                obtenidos=numeros,
                esperado=int(fila["paginas"]),
            )
        if prefijo:
            fallo("texto_antes_primer_marcador", slug=slug, caracteres=len(prefijo))
        marcas_crudas = []
        for marca in re.finditer(r"<\|/?(?:det|ref)\|>", texto, flags=re.I):
            anteriores = list(MARCADOR.finditer(texto[: marca.start()]))
            marcas_crudas.append(
                {
                    "marca": marca[0],
                    "linea": texto.count("\n", 0, marca.start()) + 1,
                    "pagina": int(anteriores[-1][1]) if anteriores else None,
                }
            )
        if marcas_crudas:
            fallo("marcas_crudas_en_md", slug=slug, ocurrencias=marcas_crudas)
    por_slug = {f["slug"]: f for f in mapping}
    duplicados = []
    for fila in mapping:
        if not fila["duplicado_de"]:
            continue
        slug, origen = fila["slug"], fila["duplicado_de"]
        iguales = slug in textos and origen in textos and textos[slug] == textos[origen]
        duplicados.append({"slug": slug, "original": origen, "texto_identico": iguales})
        if origen not in por_slug or por_slug.get(origen, {}).get("duplicado_de"):
            fallo("destino_duplicado_invalido", slug=slug, original=origen)
        if not iguales:
            fallo("texto_duplicado_distinto", slug=slug, original=origen)
    archivos = {}
    for carpeta, patron in (("texto", "*.md"), ("crudo", "*.raw.txt")):
        reales = {
            p.relative_to(ENTRADA / carpeta).as_posix()
            for p in (ENTRADA / carpeta).rglob(patron)
            if p.is_file()
        }
        archivos[carpeta] = {
            "esperados": len(esperados[carpeta]),
            "encontrados": len(reales),
            "faltantes": sorted(esperados[carpeta] - reales),
            "sobrantes": sorted(reales - esperados[carpeta]),
        }
        if reales != esperados[carpeta]:
            fallo("correspondencia_archivos", carpeta=carpeta, **archivos[carpeta])
    claves = [(f["slug"], int(f["pagina"])) for f in metadatos]
    claves_esperadas = {
        (f["slug"], p)
        for f in mapping
        if not f["duplicado_de"]
        for p in range(1, int(f["paginas"]) + 1)
    }
    for clave, n in Counter(claves).items():
        if n != 1:
            fallo("metadato_pagina_duplicado", slug=clave[0], pagina=clave[1], filas=n)
    if set(claves) != claves_esperadas:
        fallo(
            "correspondencia_paginas_csv",
            faltantes=sorted(claves_esperadas - set(claves)),
            sobrantes=sorted(set(claves) - claves_esperadas),
        )
    for fila in mapping:
        if fila["duplicado_de"]:
            continue
        propias = [p for p in metadatos if p["slug"] == fila["slug"]]
        for campo, obtenido in (
            ("paginas_con_error", sum(bool(p["error"].strip()) for p in propias)),
            (
                "paginas_marcadas",
                sum(verdadero(p["tope_alcanzado"]) or verdadero(p["repeticion"]) for p in propias),
            ),
        ):
            if int(fila[campo]) != obtenido:
                fallo(
                    "conteo_" + campo,
                    slug=fila["slug"],
                    esperado=int(fila[campo]),
                    obtenido=obtenido,
                )
    conteos = {
        "documentos": len(mapping),
        "paginas_mapping": sum(int(f["paginas"]) for f in mapping),
        "paginas_sin_duplicado": sum(int(f["paginas"]) for f in mapping if not f["duplicado_de"]),
        "paginas_duplicadas": sum(int(f["paginas"]) for f in mapping if f["duplicado_de"]),
        "paginas_procesadas_csv": len(metadatos),
        "marcadores_md": sum(d.get("marcadores", 0) for d in documentos),
        "paginas_marcadas_csv": sum(
            verdadero(f["tope_alcanzado"]) or verdadero(f["repeticion"]) for f in metadatos
        ),
    }
    for campo, esperado in {
        "documentos": 54,
        "paginas_mapping": 1294,
        "paginas_sin_duplicado": 1224,
        "paginas_duplicadas": 70,
        "paginas_procesadas_csv": 1224,
        "marcadores_md": 1294,
        "paginas_marcadas_csv": 7,
    }.items():
        if conteos[campo] != esperado:
            fallo("total_" + campo, esperado=esperado, obtenido=conteos[campo])
    return (
        {
            "ok": not discrepancias,
            "conteos": conteos,
            "archivos": archivos,
            "duplicados": duplicados,
            "documentos": documentos,
            "discrepancias": discrepancias,
            "huellas_entrada": {
                n: sha256(ENTRADA / n) for n in ("mapping.csv", "paginas.csv", "run_info.json")
            },
        },
        textos,
        paginas_u,
    )


def excluir_paginas(mapping, metadatos, paginas):
    meta = {(f["slug"], int(f["pagina"])): f for f in metadatos}
    salida = []
    for doc in mapping:
        for pagina in range(1, int(doc["paginas"]) + 1):
            slug = doc["slug"]
            fila = meta.get((doc["duplicado_de"] or slug, pagina), {})
            evidencia, motivos = [], []
            for campo in ("tope_alcanzado", "repeticion"):
                if verdadero(fila.get(campo, "")):
                    motivos.append(campo)
                    evidencia.append(
                        {
                            "campo": campo,
                            "valor": True,
                            "tokens_generados": fila.get("tokens_generados"),
                        }
                    )
            texto = paginas.get(slug, {}).get(pagina)
            if texto is None:
                motivos.append("pagina_ausente_o_ambigua")
            else:
                for indicio in m.detectar_bucles(texto):
                    motivos.append(indicio["tipo"])
                    evidencia.append(indicio)
            if motivos:
                salida.append(
                    {
                        "slug": slug,
                        "pagina": pagina,
                        "motivo": ";".join(motivos),
                        "evidencia": evidencia,
                    }
                )
    return salida


def motivos_sospecha(fila):
    motivos = []
    for campo, limite, etiqueta in (
        ("recuperacion", UMBRALES["recuperacion_minima"], "posible_omision"),
        ("precision", UMBRALES["precision_minima"], "posible_adicion"),
        ("orden_lcs", UMBRALES["orden_lcs_minimo"], "posible_desorden_o_errores"),
    ):
        if fila[campo] is None or fila[campo] < limite:
            motivos.append(etiqueta)
    return ";".join(motivos)


def comparar(mapping, metadatos, paginas, excluidas, fitz):
    meta = {(f["slug"], int(f["pagina"])): f for f in metadatos}
    fuera = {(f["slug"], f["pagina"]) for f in excluidas}
    resultados, incidencias = [], []
    for doc in mapping:
        slug = doc["slug"]
        _, _, pdf = rutas_documento(doc)
        if not pdf.is_file():
            continue
        propios = paginas.get(slug, {})
        repetidos = m.encabezados_pies(list(propios.values()))
        with fitz.open(pdf) as original:
            for pagina, texto_u in sorted(propios.items()):
                fila = meta.get((doc["duplicado_de"] or slug, pagina))
                if fila is None or not 1 <= pagina <= original.page_count:
                    continue
                caracteres = int(fila["caracteres_capa_texto_pdf"])
                if caracteres < UMBRALES["digital_caracteres"]:
                    continue
                texto_pdf = original[pagina - 1].get_text()
                if len(texto_pdf) != caracteres:
                    incidencias.append(
                        {
                            "slug": slug,
                            "pagina": pagina,
                            "tipo": "caracteres_capa_difieren",
                            "csv": caracteres,
                            "actual": len(texto_pdf),
                        }
                    )
                tabla = bool(re.search(r"<table\b", texto_u, re.I))
                excluida = (slug, pagina) in fuera
                registro = {
                    "slug": slug,
                    "categoria": doc["categoria"],
                    "pagina": pagina,
                    "tabla_u": tabla,
                    "duplicado_de": doc["duplicado_de"],
                    "no_confiable": excluida,
                    "incluida_agregados": not doc["duplicado_de"] and not excluida,
                    "caracteres_capa_csv": caracteres,
                    "caracteres_capa_actual": len(texto_pdf),
                    **m.metricas(texto_u, texto_pdf),
                    "criticos": m.comparar_criticos(texto_u, texto_pdf),
                    "ruido": m.ruido(texto_u, texto_pdf, repetidos),
                }
                registro["motivo_sospecha"] = motivos_sospecha(registro)
                resultados.append(registro)
        print(f"Comparado: {slug}", flush=True)
    return resultados, incidencias


def estratificar(filas):
    grupos = {"total": filas}
    for categoria in ("jurisprudencia", "normativa"):
        grupos[categoria] = [f for f in filas if f["categoria"] == categoria]
    for tabla in (False, True):
        sufijo = "con_tabla" if tabla else "sin_tabla"
        grupos[sufijo] = [f for f in filas if f["tabla_u"] == tabla]
        for categoria in ("jurisprudencia", "normativa"):
            grupos[categoria + "_" + sufijo] = [
                f for f in grupos[categoria] if f["tabla_u"] == tabla
            ]
    return {k: m.agregar(v) for k, v in grupos.items()}


def informe(resumen, integridad_u, excluidas, peores):
    def pct(x):
        return "no definido" if x is None else f"{100 * x:.2f}%"

    def intervalo(ic):
        return "no definido" if ic is None else "–".join(pct(x) for x in ic)

    lineas = [
        "# FASE 1: U frente a la capa de texto",
        "",
        "U es OCR automático sin verificar. La capa de texto es otra extracción imperfecta; estas discrepancias no estiman por sí solas el error frente al PDF visible.",
        "",
        f"Integridad: {'OK' if integridad_u['ok'] else 'DISCREPANCIAS'}. Véase integridad.json.",
        "",
        f"Excluidas como NO CONFIABLES: {len(excluidas)}. Véase paginas_excluidas.csv.",
        "",
        "Cocientes micro; IC95 percentil, 2.000 remuestreos, semilla 27102026. Se excluyen duplicados y páginas no confiables.",
        "",
        "| Estrato | Páginas | Documentos | CER | WER | Recuperación | Precisión | IC CER páginas | IC WER páginas | IC CER documentos | IC WER documentos |",
        "|---|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for nombre, g in resumen["agregados"].items():
        lineas.append(
            f"| {nombre} | {g['paginas']} | {g['documentos']} | {pct(g['cer'])} | {pct(g['wer'])} | {pct(g['recuperacion'])} | {pct(g['precision'])} | {intervalo(g['ic95_por_pagina']['cer'])} | {intervalo(g['ic95_por_pagina']['wer'])} | {intervalo(g['ic95_por_documento']['cer'])} | {intervalo(g['ic95_por_documento']['wer'])} |"
        )
    lineas += [
        "",
        f"Sospechosas sin duplicados: {resumen['sospechosas_sin_duplicados']}; de ellas incluidas en agregados: {resumen['sospechosas_incluidas_agregados']}.",
        "",
        "## Diez peores páginas incluidas, por CER descendente",
        "",
        "| Slug | Página | CER | WER | Recuperación | Precisión | LCS |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for f in peores:
        lineas.append(
            f"| {f['slug']} | {f['pagina']} | {pct(f['cer'])} | {pct(f['wer'])} | {pct(f['recuperacion'])} | {pct(f['precision'])} | {pct(f['orden_lcs'])} |"
        )
    lineas += ["", "## Páginas excluidas", ""]
    lineas.extend(f"- `{f['slug']}`, página {f['pagina']}: {f['motivo']}." for f in excluidas)
    lineas += [
        "",
        "## Límites",
        "",
        "Los umbrales son señales de triaje, no validación visual. Notas pegadas a números, viñetas U+F0B7, columnas de tablas y orden interno del PDF pueden aumentar CER/WER o reducir LCS. Precisión baja indica discrepancia, sin atribuir automáticamente invención a U. Las páginas con menos de 80 caracteres de capa no están evaluadas por estas métricas. Los IC cuantifican remuestreo del corpus observado; no eliminan sesgos compartidos por las fuentes.",
        "",
    ]
    (SALIDA / "informe_fase1.md").write_text("\n".join(lineas), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--calibrar",
        action="store_true",
        help="Ejecutar solo calibración sintética sin abrir PDFs ni entrada",
    )
    args = parser.parse_args()
    calibracion = m.calibrar()
    guardar_json("calibracion.json", calibracion)
    if not calibracion["correcto"]:
        raise SystemExit("Falló la calibración; se detiene la FASE 1")
    if args.calibrar:
        print("Calibración correcta: sustituciones 0,5/1/3%, borrado de números y bucles/control.")
        return
    import fitz

    mapping = leer_csv(ENTRADA / "mapping.csv")
    metadatos = leer_csv(ENTRADA / "paginas.csv")
    integridad_u, _, paginas = integridad(mapping, metadatos, fitz)
    guardar_json("integridad.json", integridad_u)
    excluidas = excluir_paginas(mapping, metadatos, paginas)
    guardar_csv("paginas_excluidas.csv", excluidas, ["slug", "pagina", "motivo", "evidencia"])
    filas, incidencias = comparar(mapping, metadatos, paginas, excluidas, fitz)
    campos = [
        "slug",
        "categoria",
        "pagina",
        "tabla_u",
        "duplicado_de",
        "no_confiable",
        "incluida_agregados",
        "caracteres_capa_csv",
        "caracteres_capa_actual",
        *m.CAMPOS,
        "cer",
        "wer",
        "recuperacion",
        "precision",
        "orden_lcs",
        "orden_precision",
        "lcs",
        "ngramas_ref",
        "ngramas_hip",
        "n",
        "motivo_sospecha",
        "criticos",
        "ruido",
    ]
    guardar_csv("u_vs_capa_texto.csv", filas, campos)
    sospechosas = [f for f in filas if f["motivo_sospecha"] and not f["duplicado_de"]]
    guardar_csv("u_sospechosas.csv", sospechosas, campos)
    incluidas = [f for f in filas if f["incluida_agregados"]]
    peores = sorted(
        incluidas,
        key=lambda f: (f["cer"] if f["cer"] is not None else float("inf"), f["wer"] or 0),
        reverse=True,
    )[:10]
    resumen = {
        "referencia_operativa": "capa de texto PDF; NO verdad visual",
        "pymupdf": fitz.VersionBind,
        "umbrales": UMBRALES,
        "semilla": m.SEMILLA,
        "bootstrap_repeticiones": m.REPETICIONES,
        "paginas_digitales_csv_incluido_duplicado": len(filas),
        "paginas_excluidas": len(excluidas),
        "sospechosas_sin_duplicados": len(sospechosas),
        "sospechosas_incluidas_agregados": sum(f["incluida_agregados"] for f in sospechosas),
        "incidencias_capa_texto": incidencias,
        "agregados": estratificar(incluidas),
        "peores_10": [{k: f[k] for k in campos if k not in {"criticos", "ruido"}} for f in peores],
    }
    guardar_json("resumen.json", resumen)
    informe(resumen, integridad_u, excluidas, peores)
    print(
        json.dumps(
            {
                "integridad_ok": integridad_u["ok"],
                "discrepancias": len(integridad_u["discrepancias"]),
                "excluidas": len(excluidas),
                "sospechosas": len(sospechosas),
                "total": resumen["agregados"]["total"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if integridad_u["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
