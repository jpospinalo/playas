"""Repetibilidad, alertas y causas reproducibles; no consulta revisión visual."""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("comun", BASE / "comun.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
e, m = c.modulo("estadistica"), c.modulo("metricas")
SALIDA = BASE / "resultados/fase3"


def diferencias(a, b, ruta="$"):
    if type(a) is not type(b):
        return [{"campo": ruta, "run1": a, "run2": b}]
    if isinstance(a, dict):
        salida = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                salida.append(
                    {
                        "campo": ruta + "." + str(k),
                        "presente_run1": k in a,
                        "presente_run2": k in b,
                        "run1": a.get(k),
                        "run2": b.get(k),
                    }
                )
            else:
                salida.extend(diferencias(a[k], b[k], ruta + "." + str(k)))
        return salida
    if isinstance(a, list):
        if len(a) != len(b):
            return [{"campo": ruta + ".longitud", "run1": len(a), "run2": len(b)}]
        return [
            d
            for j, (x, y) in enumerate(zip(a, b, strict=True))
            for d in diferencias(x, y, ruta + f"[{j}]")
        ]
    return [] if a == b else [{"campo": ruta, "run1": a, "run2": b}]


def repetibilidad():
    roots = [BASE / f"trabajo/s_mio/run{j}/capas/bronze" for j in (1, 2)]
    nombres = [
        set(
            p.name
            for p in root.iterdir()
            if p.name.endswith((".txt", ".extraction.json", ".quality.json"))
        )
        for root in roots
    ]
    filas = []
    for nombre in sorted(nombres[0] | nombres[1]):
        rutas = [root / nombre for root in roots]
        hashes = [c.huella(p) if p.is_file() else None for p in rutas]
        diff = []
        if hashes[0] != hashes[1]:
            if all(p.is_file() for p in rutas) and nombre.endswith(".json"):
                diff = diferencias(*(json.loads(p.read_text(encoding="utf-8")) for p in rutas))
            elif all(p.is_file() for p in rutas):
                textos = [p.read_text(encoding="utf-8") for p in rutas]
                ps = [t.split("\n\f\n") for t in textos]
                diff = [
                    {
                        "campo": "paginas_con_texto_distinto",
                        "run1_paginas": len(ps[0]),
                        "run2_paginas": len(ps[1]),
                        "paginas": [
                            j + 1
                            for j in range(max(map(len, ps)))
                            if (ps[0][j] if j < len(ps[0]) else None)
                            != (ps[1][j] if j < len(ps[1]) else None)
                        ],
                    }
                ]
            else:
                diff = [
                    {
                        "campo": "archivo_ausente",
                        "run1": rutas[0].is_file(),
                        "run2": rutas[1].is_file(),
                    }
                ]
        filas.append(
            {
                "archivo": nombre,
                "sha256_run1": hashes[0],
                "sha256_run2": hashes[1],
                "identico": hashes[0] == hashes[1],
                "diferencias_campos": diff,
            }
        )
    resultado = {
        "archivos_run1": len(nombres[0]),
        "archivos_run2": len(nombres[1]),
        "identicos": sum(f["identico"] for f in filas),
        "diferencias": sum(not f["identico"] for f in filas),
        "archivos": filas,
        "alcance": "Todos los .txt/.extraction.json/.quality.json presentes en cualquiera de las dos corridas, incluidos documentos fuera de U. Comparación binaria y, si difiere JSON, por campo.",
    }
    c.json_guardar(SALIDA / "repetibilidad.json", resultado)
    c.csv_guardar(SALIDA / "repetibilidad.csv", filas)
    return resultado


def agregar_predictores(fila, calidad):
    fila = dict(fila)
    for nombre, valor in calidad.items():
        fila["calidad_" + nombre] = valor.get("valor")
        fila["bandera_" + nombre] = {"verde": 0, "amarillo": 1, "rojo": 2}.get(valor.get("bandera"))
    return fila


def alertas(filas, documentos, datos):
    paginas = [
        agregar_predictores(f, datos[f["slug"]]["calidad"])
        for f in filas
        if f["comparacion"] == "S_mio_vs_U"
        and f["modo"] == "contenido"
        and f["tipo_pagina"] == "OCR"
    ]
    docs = []
    for f in documentos:
        if (
            f["comparacion"] != "S_mio_vs_U"
            or f["modo"] != "contenido"
            or f["conjunto"] != "paginas_elegibles"
            or not f["paginas_OCR"]
        ):
            continue
        d = datos[f["slug"]]
        conf = [
            d["extr"]["ocr_confidence"].get(str(p))
            for p in d["elegibles"]
            if p in d["extr"]["ocr_pages"]
        ]
        conf = [v for v in conf if isinstance(v, (int, float))]
        docs.append(
            agregar_predictores(
                {
                    **f,
                    "confianza_ocr": sum(conf) / len(conf) if conf else None,
                    "chars_per_page": sum(
                        d["extr"]["chars_per_page"][p - 1] for p in d["elegibles"]
                    )
                    / len(d["elegibles"]),
                },
                d["calidad"],
            )
        )
    predictores = {"confianza_ocr": -1, "chars_per_page": -1}
    calidad_ejemplo = next(iter(datos.values()))["calidad"]
    for nombre, medida in calidad_ejemplo.items():
        predictores["calidad_" + nombre] = -1 if medida["umbral"]["direccion"] == "min" else 1
        predictores["bandera_" + nombre] = 1
    salida = []
    for nivel, poblacion in (("pagina_OCR", paginas), ("documento_con_OCR", docs)):
        for corte in (0.03, 0.05):
            for campo, direccion in predictores.items():
                resultado = e.evaluar_predictor(
                    poblacion, campo, direccion=direccion, corte=corte, unidad="documento"
                )
                salida.append({"nivel": nivel, **resultado})
            print(f"Alertas: {nivel}, CER>{corte:.0%}", flush=True)
    resultado = {
        "resultados": salida,
        "poblacion_paginas_OCR": len(paginas),
        "poblacion_documentos_con_OCR": len(docs),
        "limitaciones": [
            "Spearman sobre valores originales; AUC orientada según riesgo definido a priori.",
            "Bootstrap por documento completo (2.000) también para páginas; se informa cuántos remuestreos tienen ambas clases.",
            "Calidad es documental: repetirla por página no genera información independiente.",
            "Youden y sensibilidad>=0,9 se seleccionan y evalúan dentro de muestra. IC exploratorios, sin garantía de rendimiento futuro.",
            "Documentos mixtos: CER documental abarca todas sus páginas elegibles; la confianza resume solo sus páginas OCR.",
            "La confianza no medida y banderas no medidas se omiten, sin convertirlas en cero. Predictores constantes no admiten umbral.",
        ],
    }
    c.json_guardar(SALIDA / "alertas.json", resultado)
    c.csv_guardar(SALIDA / "alertas.csv", salida)
    return resultado


def clasificar(f, s, u):
    """Indicios solapados, sin atribución causal demostrada ni verdad visual."""
    causas = []
    if f.get("confianza_ocr") is not None and f["confianza_ocr"] < 85:
        causas.append("OCR_baja_confianza")
    if f["orden_lcs"] is not None and f["orden_lcs"] < 0.8 and (f["recuperacion"] or 0) >= 0.9:
        causas.append("columnas_u_orden")
    if f["tabla_u"]:
        causas.append("tablas")
    cab = sum(f["ruido"]["encabezados_pies_repetidos"].values())
    if cab >= 5 and cab >= 0.2 * max(1, f["palabras_hip"] - f["palabras_comunes"]):
        causas.append("encabezados_pies")
    # Ejemplo 2008³ -> 2008 3 en U frente a 20083 en S: evidencia numérica,
    # no se considera cualquier diferencia entre números una llamada pegada.
    un = m.normalizar(u, modo="contenido")
    sn = m.normalizar(s, modo="contenido")
    if any(
        re.search(r"(?<!\d)" + re.escape(a + b) + r"(?!\d)", sn)
        for a, b in re.findall(r"\b(\d{2,4}) (\d{1,2})\b", un)
    ):
        causas.append("notas_llamadas_pegadas")
    if re.search("[\ufb00-\ufb06\ue000-\uf8ff]", s):
        causas.append("ligaduras_o_caracteres_privados")
    if f["capa_ocr_incrustada"]:
        causas.append("capa_OCR_incrustada")
    return causas or ["sin_causa_reglada"]


def causas(filas, documentos, datos):
    paginas = [f for f in filas if f["comparacion"] == "S_mio_vs_U" and f["modo"] == "contenido"]
    docs = [
        f
        for f in documentos
        if f["comparacion"] == "S_mio_vs_U"
        and f["modo"] == "contenido"
        and f["conjunto"] == "paginas_elegibles"
    ]
    clasificaciones = []
    conteo, solapado = Counter(), Counter()
    for f in paginas:
        d = datos[f["slug"]]
        etiquetas = clasificar(f, d["s"][f["pagina"]], d["u"][f["pagina"]])
        nf = {
            k: f[k]
            for k in (
                "slug",
                "pagina",
                "cer",
                "wer",
                "ediciones_caracteres",
                "caracteres_ref",
                "confianza_ocr",
                "orden_lcs",
                "recuperacion",
                "tabla_u",
                "capa_ocr_incrustada",
            )
        }
        nf["causas"] = etiquetas
        clasificaciones.append(nf)
        for etiqueta in etiquetas:
            conteo[etiqueta] += f["ediciones_caracteres"] / len(etiquetas)
            solapado[etiqueta] += f["ediciones_caracteres"]
    peores_pag = sorted(
        clasificaciones,
        key=lambda f: f["cer"] if f["cer"] is not None else float("inf"),
        reverse=True,
    )[:15]
    peores_doc = []
    for f in sorted(
        docs, key=lambda f: f["cer"] if f["cer"] is not None else float("inf"), reverse=True
    )[:5]:
        propias = [p for p in clasificaciones if p["slug"] == f["slug"]]
        causas_doc = Counter(et for p in propias for et in p["causas"])
        peores_doc.append(
            {
                k: f[k]
                for k in ("slug", "cer", "wer", "ediciones_caracteres", "orden_lcs", "recuperacion")
            }
            | {"causas_paginas": dict(causas_doc)}
        )
    total = sum(f["ediciones_caracteres"] for f in paginas)
    top = [
        {
            "causa": k,
            "ediciones_repartidas": v,
            "fraccion_ediciones": v / total if total else None,
            "ediciones_solapadas": solapado[k],
        }
        for k, v in conteo.most_common()
    ]
    resultado = {
        "peores_15_paginas": peores_pag,
        "peores_5_documentos": peores_doc,
        "top_causas": top,
        "ediciones_totales_paginas": total,
        "regla_aporte": "Por página se reparten sus ediciones entre los indicios presentes con peso 1/k; la suma conserva el total. También se informa conteo solapado. Es distribución descriptiva, no atribución causal de cada edición.",
        "umbrales": {
            "baja_confianza": 85,
            "orden_lcs_bajo": 0.8,
            "recuperacion_alta": 0.9,
            "encabezados_min_palabras": 5,
            "encabezados_min_fraccion_extras": 0.2,
        },
    }
    c.json_guardar(SALIDA / "causas.json", resultado)
    c.csv_guardar(SALIDA / "causas_paginas.csv", clasificaciones)
    return resultado


def informe(resumen, repetibilidad, alertas_u, causas_u):
    def pct(v):
        return "—" if v is None else f"{v * 100:.2f}%"

    lineas = [
        "# FASES 3 y 4",
        "",
        "Cifra principal: contenido. Estricto controla diferencias tipográficas. U sigue siendo referencia automática sin verificar.",
        "",
        "S_prof solo se compara por documento completo, sin reconstruir páginas. Digital/OCR documental exige pureza; los mixtos están separados. Se omiten de S_prof los tres documentos con páginas U excluidas y se ofrece S_mio en ese mismo subconjunto.",
        "",
        "| Comparación | Nivel/conjunto | Estrato | Unidades | CER contenido | WER contenido | CER estricto | WER estricto | Recall crítico | Recall inverso | LCS | IC95 CER documentos | Semáforo | Escenario U |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for f in resumen:
        if f["modo"] != "contenido":
            continue
        estricto = next(
            g
            for g in resumen
            if all(g[k] == f[k] for k in ("comparacion", "nivel", "conjunto", "estrato"))
            and g["modo"] == "estricto"
        )
        ic = f["ic95_por_documento"]["cer"]
        rango = (f.get("sensibilidad_error_U") or {}).get("envolvente")
        lineas.append(
            f"| {f['comparacion']} | {f['nivel']}/{f['conjunto']} | {f['estrato']} | {f['unidades']} | {pct(f['cer'])} | {pct(f['wer'])} | {pct(estricto['cer'])} | {pct(estricto['wer'])} | {pct(f['recall_critico'])} | {pct(f['recall_critico_inverso'])} | {pct(f['orden_lcs'])} | {'–'.join(pct(x) for x in ic) if ic else '—'} | {f['semaforo']} | {'–'.join(pct(x) for x in rango) if rango else '—'} |"
        )
    lineas += [
        "",
        "Los JSON conservan ambos modos, todos los IC por página/documento para las ocho métricas y los escenarios e_U=0,24% y 1,23%. La cota CER_obs ± e_U solo es triangular con error de caracteres y denominador común; usar una estimación de error de palabra es una sensibilidad hipotética, no una cota garantizada del CER real.",
        "",
        f"Repetibilidad: {repetibilidad['identicos']}/{repetibilidad['archivos_run1']} archivos idénticos; diferencias: {repetibilidad['diferencias']}.",
        "",
        "## Alertas exploratorias",
        "",
        "| Nivel | CER malo | Predictor | n | Spearman | AUC | IC95 AUC | Youden | Sensibilidad ≥0,9 |",
        "|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for f in alertas_u["resultados"]:
        if f["predictor"] not in {"confianza_ocr", "chars_per_page"}:
            continue
        um = []
        for nombre in ("youden", "sensibilidad_90"):
            d = f[nombre]
            um.append(
                "no identificable"
                if d is None
                else f"{d['operador']}{d['umbral']} (sens. {pct(d['sensibilidad'])}, esp. {pct(d['especificidad'])})"
            )
        lineas.append(
            f"| {f['nivel']} | >{pct(f['corte_cer'])} | {f['predictor']} | {f['n']} | {f['spearman']} | {f['auc']} | {f['ic95_auc']} | {um[0]} | {um[1]} |"
        )
    lineas += [
        "",
        *alertas_u["limitaciones"],
        "",
        "## Causas por ediciones repartidas",
        "",
        "| Causa | Ediciones | Fracción |",
        "|---|---:|---:|",
    ]
    lineas += [
        f"| {f['causa']} | {f['ediciones_repartidas']:.1f} | {pct(f['fraccion_ediciones'])} |"
        for f in causas_u["top_causas"]
    ]
    lineas += [
        "",
        causas_u["regla_aporte"],
        "",
        "Véase causas.json para las 15 peores páginas y los cinco peores documentos. Los 30 segmentos ciegos se entregan con veredicto y nota vacíos; la clave A/B permanece en archivo separado. No se estiman errores adjudicados hasta completar la revisión.",
        "",
    ]
    c.destino(SALIDA / "informe.md").write_text("\n".join(lineas), encoding="utf-8")
