"""Política de calidad del intake: señales de un documento → decisión con motivos.

Decisiones: ``aceptado`` y ``aceptado_con_advertencias`` se publican;
``revision_humana`` y ``rechazado`` se generan y guardan pero NO entran en la
colección viva. Los umbrales viven en ``ingesta/config/intake_policy.yaml`` y se
calibraron con los documentos de AJUSTE frente al veredicto por documento.
Sin LLM: todo es determinista y local.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

from ..legal_metadata import extract_legal_metadata, identity_gate
from .signals import (
    caida_texto,
    imagenes_en_paginas_digitales,
    perdida_bronce_silver,
    secuencia_articulos,
    tablas_imagen_sospechosas,
)

DECISIONES = ("aceptado", "aceptado_con_advertencias", "revision_humana", "rechazado")
PUBLICABLES = {"aceptado", "aceptado_con_advertencias"}
POLITICA_POR_DEFECTO = Path(__file__).resolve().parents[2] / "config" / "intake_policy.yaml"


def cargar_politica(ruta=None):
    """Lee la política YAML y valida que estén todos los umbrales esperados."""
    import yaml  # PyYAML llega con el extra offline (dependencia de chromadb).

    ruta = Path(ruta) if ruta else POLITICA_POR_DEFECTO
    politica = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    faltan = [
        f"{seccion}.{clave}"
        for seccion, claves in _CLAVES.items()
        for clave in claves
        if clave not in (politica.get(seccion) or {})
    ]
    if faltan:
        raise ValueError("Política incompleta: faltan " + ", ".join(faltan))
    return politica


_CLAVES = {
    "rechazo": ("caracteres_minimos_documento",),
    "revision": (
        "ocr_confianza_media_minima",
        "ocr_confianza_pagina_minima",
        "ocr_umbral_pagina_baja",
        "ocr_fraccion_paginas_bajas_maxima",
        "ocr_paginas_fallidas_maximas",
        "identidad_obligatoria",
        "simbolos_sospechosos_maximos",
        "anomalias_secuencia_maximas",
        "tablas_imagen_maximas",
        "tablas_imagen_fraccion_minima",
        "tablas_imagen_caracteres_maximos",
        "caida_texto_paginas_maximas",
        "caracteres_reemplazo_maximo",
        "paginas_ocr_incrustado_maximas",
        "perdida_silver_maxima",
    ),
    "advertencia": (
        "identidad_recomendada",
        "chunks_cortos_fraccion_maxima",
        "saltos_articulos_maximos",
        "perdida_silver_advertencia",
    ),
}


def senales_documento(capas, doc_id, pdf=None, doc_type="jurisprudencia"):
    """Señales de un documento desde sus capas (y el PDF original, si lo hay)."""
    capas = Path(capas)
    bronce = (capas / "bronze" / (doc_id + ".txt")).read_text(encoding="utf-8")
    extraccion = json.loads(
        (capas / "bronze" / (doc_id + ".extraction.json")).read_text(encoding="utf-8")
    )
    paginas = bronce.split("\n\f\n")
    paginas_ocr = set(extraccion.get("ocr_pages", []))
    confianzas = [c for c in (extraccion.get("ocr_confidence") or {}).values() if c is not None]
    metadata = extract_legal_metadata(bronce, doc_type)
    identidad = identity_gate(metadata, doc_type)
    secuencia = secuencia_articulos(bronce, paginas_ocr)
    imagenes = []
    if pdf is not None and Path(pdf).suffix.lower() == ".pdf":
        import fitz

        with fitz.open(pdf) as documento:
            imagenes = imagenes_en_paginas_digitales(documento, paginas_ocr)
    # Pérdida bronze→silver fuera del mobiliario verificado, y texto que se publica.
    perdida_silver, caracteres_silver = None, None
    contexto = capas / "silver" / (doc_id + ".context.json")
    if contexto.exists():
        limpio = json.loads(contexto.read_text(encoding="utf-8"))["cleaned"]
        perdida_silver = perdida_bronce_silver(bronce, limpio.get("offset_map", []))
        caracteres_silver = len(re.sub(r"\s", "", limpio.get("text", "")))
    chunks = []
    gold = capas / "gold" / (doc_id + ".jsonl")
    if gold.exists():
        for linea in gold.read_text(encoding="utf-8").splitlines():
            meta = json.loads(linea)["metadata"]
            chunks.append(meta["clean_end"] - meta["clean_start"])
    return {
        "doc_type": doc_type,
        "paginas": len(paginas),
        "caracteres": len(re.sub(r"\s", "", bronce)),
        "caracteres_reemplazo": bronce.count("�") / max(1, len(bronce)),
        "paginas_ocr": len(paginas_ocr),
        "ocr_paginas_fallidas": len(extraccion.get("ocr_failed_pages", [])),
        "ocr_paginas_sin_confianza": len(paginas_ocr) - len(confianzas),
        "ocr_confianza_media": statistics.fmean(confianzas) if confianzas else None,
        "ocr_confianza_minima": min(confianzas) if confianzas else None,
        "ocr_confianzas": sorted(confianzas),
        "identidad": identidad,
        "secuencia": {k: v for k, v in secuencia.items() if k != "ejemplos_simbolos"},
        "simbolos_ejemplos": secuencia["ejemplos_simbolos"],
        "imagenes_digitales": imagenes,
        "caida_texto": caida_texto(extraccion.get("chars_per_page", []))["paginas"],
        "chunks": len(chunks),
        "chunks_cortos": sum(1 for n in chunks if n < 200),
        "perdida_silver": perdida_silver,
        "caracteres_silver": caracteres_silver,
        # Imagen de página completa con capa de texto: OCR incrustado sin verificar.
        "paginas_ocr_incrustado": [m["pagina"] for m in imagenes if m["pagina_completa"]],
    }


def decidir(senales, politica, *, duplicado_exacto=False, cuasi_duplicado_de=None):
    """Aplica la política. Devuelve (decisión, motivos de revisión/rechazo, advertencias)."""
    rechazo, revision, advertencia = (politica[k] for k in ("rechazo", "revision", "advertencia"))
    motivos, avisos = [], []
    publicados = senales.get("caracteres_silver")
    if publicados is not None and publicados < rechazo["caracteres_minimos_documento"]:
        return (
            "rechazado",
            [f"sin texto útil tras la limpieza: {publicados} caracteres en silver"],
            [],
        )
    if senales["caracteres"] < rechazo["caracteres_minimos_documento"]:
        return (
            "rechazado",
            [
                f"sin texto útil: {senales['caracteres']} caracteres (mínimo {rechazo['caracteres_minimos_documento']})"
            ],
            [],
        )
    if duplicado_exacto:
        avisos.append("duplicado exacto de un documento ya procesado: sin trabajo nuevo")
    if cuasi_duplicado_de:
        motivos.append(
            f"cuasi-duplicado de {cuasi_duplicado_de}: posible versión nueva, no se fusiona"
        )
    if senales["paginas_ocr"]:
        media, minima = senales["ocr_confianza_media"], senales["ocr_confianza_minima"]
        bajas = sum(1 for c in senales["ocr_confianzas"] if c <= revision["ocr_umbral_pagina_baja"])
        fraccion = bajas / senales["paginas_ocr"]
        if senales["ocr_paginas_sin_confianza"]:
            motivos.append(f"{senales['ocr_paginas_sin_confianza']} página(s) OCR sin confianza")
        if media is not None and media < revision["ocr_confianza_media_minima"]:
            motivos.append(
                f"confianza OCR media {media:.1f} < {revision['ocr_confianza_media_minima']}"
            )
        if minima is not None and minima < revision["ocr_confianza_pagina_minima"]:
            motivos.append(
                f"página OCR con confianza {minima:.1f} < {revision['ocr_confianza_pagina_minima']}"
            )
        if fraccion > revision["ocr_fraccion_paginas_bajas_maxima"]:
            motivos.append(
                f"{fraccion:.0%} de páginas OCR con confianza ≤ {revision['ocr_umbral_pagina_baja']}"
                f" (máximo {revision['ocr_fraccion_paginas_bajas_maxima']:.0%})"
            )
    if senales["ocr_paginas_fallidas"] > revision["ocr_paginas_fallidas_maximas"]:
        motivos.append(f"{senales['ocr_paginas_fallidas']} página(s) con OCR fallido")
    if senales["caracteres_reemplazo"] > revision["caracteres_reemplazo_maximo"]:
        motivos.append(f"caracteres de reemplazo U+FFFD: {senales['caracteres_reemplazo']:.2%}")
    identidad = senales["identidad"]
    if revision["identidad_obligatoria"] and not identidad["pasa"]:
        motivos.append("identidad incompleta: faltan " + ", ".join(identidad["faltan"]))
    elif advertencia["identidad_recomendada"] and identidad["recomendados_ausentes"]:
        avisos.append("identidad sin " + ", ".join(identidad["recomendados_ausentes"]))
    secuencia = senales["secuencia"]
    if secuencia["simbolos_sospechosos"] > revision["simbolos_sospechosos_maximos"]:
        motivos.append(
            f"{secuencia['simbolos_sospechosos']} número(s) de artículo/parágrafo con símbolo"
            " pegado en páginas OCR (posible «°» mal leído)"
        )
    if senales["doc_type"] == "normativa":
        anomalias = secuencia["descensos"] + secuencia["duplicados"]
        if anomalias > revision["anomalias_secuencia_maximas"]:
            motivos.append(f"numeración de artículos no monótona o duplicada ({anomalias})")
        if secuencia["saltos"] > advertencia["saltos_articulos_maximos"]:
            avisos.append(f"{secuencia['saltos']} salto(s) en la numeración de artículos")
    tablas = tablas_imagen_sospechosas(
        senales["imagenes_digitales"],
        fraccion_minima=revision["tablas_imagen_fraccion_minima"],
        caracteres_maximos=revision["tablas_imagen_caracteres_maximos"],
    )
    if len(tablas) > revision["tablas_imagen_maximas"]:
        motivos.append(
            f"páginas digitales con imágenes grandes y poco texto (posible tabla-imagen): {tablas}"
        )
    if len(senales["caida_texto"]) > revision["caida_texto_paginas_maximas"]:
        motivos.append(f"caída fuerte de texto en páginas {senales['caida_texto']}")
    incrustado = senales.get("paginas_ocr_incrustado") or []
    if len(incrustado) > revision["paginas_ocr_incrustado_maximas"]:
        motivos.append(f"capa OCR incrustada sin verificar: páginas {incrustado}")
    perdida = senales.get("perdida_silver")
    if perdida is not None:
        if perdida > revision["perdida_silver_maxima"]:
            motivos.append(f"la limpieza elimina {perdida:.1%} del texto fuera del mobiliario")
        elif perdida > advertencia["perdida_silver_advertencia"]:
            avisos.append(f"la limpieza elimina {perdida:.1%} del texto fuera del mobiliario")
    if senales["chunks"]:
        cortos = senales["chunks_cortos"] / senales["chunks"]
        if cortos > advertencia["chunks_cortos_fraccion_maxima"]:
            avisos.append(f"{cortos:.0%} de chunks con menos de 200 caracteres")
    if motivos:
        return "revision_humana", motivos, avisos
    return ("aceptado_con_advertencias" if avisos else "aceptado"), [], avisos
