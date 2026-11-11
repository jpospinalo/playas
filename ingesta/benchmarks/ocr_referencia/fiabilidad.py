"""Fiabilidad documental de bronze/silver/gold; evaluación local, sin red.

Ejecutar desde cualquier directorio con Python -I -B. Las rutas relativas de
--capas se resuelven desde este benchmark, también para una futura runB.
Nunca se importan módulos de entrada/ ni del pipeline de ingesta.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean

BASE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("comun_fiabilidad", BASE / "comun.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
m, e, v = (c.modulo(n) for n in ("metricas", "estadistica", "validar_u"))

# Regla solicitada de sensibilidad a U; e_U es error POR PALABRA, no un IC
# del CER verdadero. Esta ventana es una regla operativa, no una cota inferencial.
ERROR_U = 0.0054
IC_ERROR_U = (0.0031, 0.0088)
UMBRAL_VERDE = 0.01
LIMITE_VERDE = 0.0046
LIMITE_NO_DISTINGUIBLE = 0.0154
UMBRAL_ROJO = 0.03
COBERTURA_GOLD_ROJA = 0.99
PERDIDA_SILVER_OTRA_ROJA = 0.05
PERDIDA_SILVER_OTRA_AMARILLA = 0.02
RECALL_CRITICO_AMARILLO = 0.90
UMBRAL_CONFIANZA = 95
SEMILLA = 20261110
REPETICIONES = 2000
MAX_BYTES = 5_000_000
COLORES = ("verde", "no distinguible de U", "amarillo", "rojo", "sin evaluar")
ORDEN_COLOR = {color: i for i, color in enumerate(COLORES)}
TABLA = re.compile(r"<table\b[^>]*>(.*?)</table\s*>", re.I | re.S)
CELDA = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", re.I | re.S)
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
ARTICULO = re.compile(r"\b(?:artículo|art\.)\s+\d+", re.I)
SUMABLES = (*m.CAMPOS, "lcs", "ngramas_ref", "crit_comunes", "crit_total_ref")
HUELLAS_AUDITORIA = ("huella_u", "huella_bronce", "huella_gold")
MARCADOR_JURIDICO = re.compile(
    r"\b(?:art[ií]culo|par[aá]grafo|considerando|resuelve|decreta|cap[ií]tulo|t[ií]tulo|numeral|literal)\b|\bart\.",
    re.I,
)
FOLIO = re.compile(r"(?:\d+|p[aá]gina\s+\d+\s+de\s+\d+)", re.I)
CRITERIO_MOBILIARIO = (
    "Las claves de cleaned.removed_furniture_keys son solo candidatos. Se acepta una línea "
    "si su clave independiente (dígitos → #, minúsculas, espacios colapsados) aparece entre "
    "las tres primeras o tres últimas líneas no vacías en al menos tres páginas y el 30 % "
    "de todas las páginas del documento, y no contiene marcadores jurídicos "
    "(artículo, art., parágrafo, considerando, resuelve, decreta, capítulo, título, numeral, literal). "
    "También se acepta un folio de margen: «Página N de M», o un número aislado solo si "
    "su valor menos el número de página da un desplazamiento constante observado en al "
    "menos dos páginas (secuencia de paginación); un importe aislado no se exonera. Los "
    "candidatos rechazados se contabilizan en perdida_silver_otra. Las páginas excluidas "
    "de U se controlan sin U: su pérdida bronce→silver no mobiliario aplica los mismos "
    "umbrales (2 %/5 %) y, si no se puede evaluar, impide el verde."
)


def leer_texto(ruta):
    """Decodifica sin traducción CRLF: todos los offsets son de código Unicode."""
    return Path(ruta).read_bytes().decode("utf-8")


def leer_json(ruta):
    return json.loads(leer_texto(ruta))


def ruta_local(ruta):
    ruta = Path(ruta)
    return (BASE / ruta).resolve() if not ruta.is_absolute() else ruta.resolve()


def cargar_auditoria(ruta, documentos):
    """Resuelve sufijos unívocos y valida toda la auditoría antes de aplicarla."""
    por_sufijo = defaultdict(list)
    for doc in documentos:
        por_sufijo[doc["slug"][-4:]].append(doc["slug"])
    salida = {}
    with Path(ruta).open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        requeridas = {
            "sufijo",
            "veredicto_auditado",
            "causa_dominante",
            "justificacion",
            *HUELLAS_AUDITORIA,
        }
        if not requeridas <= set(lector.fieldnames or []):
            raise ValueError("Columnas de auditoría incompletas")
        for fila in lector:
            sufijo = (fila["sufijo"] or "").strip()
            candidatos = por_sufijo.get(sufijo, [])
            if len(sufijo) != 4 or len(candidatos) != 1:
                raise ValueError(f"Sufijo de auditoría inexistente o ambiguo: {sufijo}")
            color = (fila["veredicto_auditado"] or "").strip()
            if color not in COLORES[:4]:
                raise ValueError(f"Veredicto auditado inválido: {color}")
            slug = candidatos[0]
            if slug in salida:
                raise ValueError(f"Sufijo de auditoría duplicado: {sufijo}")
            salida[slug] = {
                "veredicto_auditado": color,
                "causa_auditada": fila["causa_dominante"] or "",
                "justificacion_auditoria": fila["justificacion"] or "",
                **{k: (fila[k] or "").strip().lower() for k in HUELLAS_AUDITORIA},
            }
    return salida


def aplicar_auditoria(documentos, auditoria):
    for fila in documentos:
        revision = auditoria.get(fila["slug"], {})
        for k in ("veredicto_auditado", "causa_auditada", "justificacion_auditoria"):
            fila[k] = revision.get(k, "")
        motivo = ""
        if not revision:
            motivo = "sin auditoría"
        elif any(
            not re.fullmatch(r"[0-9a-f]{64}", revision.get(k, "")) or revision[k] != fila.get(k)
            for k in HUELLAS_AUDITORIA
        ):
            motivo = "huellas distintas o ausentes"
        elif (
            fila["veredicto_automatico"] == "sin evaluar"
            or fila.get("capas_faltantes")
            or fila.get("paginas_sin_u")
        ):
            motivo = "evaluación incompleta"
        elif any(
            fila.get(k) is None for k in ("gold_cobertura_silver", "gold_cobertura_efectiva_silver")
        ):
            motivo = "cobertura gold sin evaluar"
        fila["estado_auditoria"] = "no aplicable: " + motivo if motivo else "aplicada"
        fila["veredicto_final"] = (
            fila["veredicto_automatico"] if motivo else fila["veredicto_auditado"]
        )
        if not motivo:
            # La revisión visual solo sustituye el componente bronce/U.
            # Las puertas de las capas posteriores se imponen después.
            fila["veredicto_final"], puerta = veredicto(
                None,
                color_bronce=fila["veredicto_auditado"],
                perdida_otra=fila.get("perdida_silver_otra"),
                cobertura=min(
                    fila["gold_cobertura_silver"], fila["gold_cobertura_efectiva_silver"]
                ),
                gold_discrepancias_cuerpo=fila.get("gold_discrepancias_cuerpo", 0),
                gold_cabeceras_invalidas=fila.get("gold_cabeceras_invalidas", 0),
                perdida_sin_u=fila.get("paginas_sin_u_perdida_silver"),
                estado_sin_u=fila.get("paginas_sin_u_estado", "sin páginas"),
            )
            if puerta:
                fila["motivo_principal"] = puerta


def cargar_hashes(ruta):
    """Lee sha256sum por ruta relativa, sin depender del orden ni del separador."""
    salida = {}
    for numero, linea in enumerate(leer_texto(ruta).splitlines(), 1):
        if not linea.strip():
            continue
        coincidencia = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", linea)
        if not coincidencia:
            raise ValueError(f"SHA256 inválido en {ruta}:{numero}")
        huella, nombre = coincidencia.groups()
        nombre = nombre.replace("\\", "/")
        if nombre.startswith("./"):
            nombre = nombre[2:]
        partes = nombre.split("/")
        if (
            len(partes) < 4
            or partes[0] not in {"pdf", "md"}
            or partes[1] != "capas"
            or partes[2] not in {"bronze", "silver", "gold"}
            or any(p in {"", ".", ".."} for p in partes)
        ):
            raise ValueError(f"Ruta relativa de capas inválida: {nombre}")
        if nombre in salida:
            raise ValueError(f"Ruta de hashes duplicada: {nombre}")
        salida[nombre] = huella.lower()
    return salida


def comparar_hashes(ruta_a, ruta_b):
    a, b = cargar_hashes(ruta_a), cargar_hashes(ruta_b)
    rutas = sorted(a.keys() | b.keys())

    def contar(nombres):
        iguales = sum(p in a and p in b and a[p] == b[p] for p in nombres)
        return {"archivos": len(nombres), "identicos": iguales, "distintos": len(nombres) - iguales}

    return {
        **contar(rutas),
        "por_etapa": {
            etapa: contar([p for p in rutas if p.split("/")[2] == etapa])
            for etapa in ("bronze", "silver", "gold")
        },
        "por_tipo": {
            tipo: {
                **contar([p for p in rutas if p.startswith(tipo + "/")]),
                "por_etapa": {
                    etapa: contar([p for p in rutas if p.startswith(f"{tipo}/capas/{etapa}/")])
                    for etapa in ("bronze", "silver", "gold")
                },
            }
            for tipo in ("pdf", "md")
        },
        "rutas_distintas": [p for p in rutas if p not in a or p not in b or a[p] != b[p]],
        "solo_runA": sorted(a.keys() - b.keys()),
        "solo_runB": sorted(b.keys() - a.keys()),
    }


def palabras(texto):
    return Counter(m.normalizar(texto, modo="contenido").split())


def union_tramos(tramos, longitud):
    """Unión exacta de intervalos semiabiertos; rechaza offsets incoherentes."""
    unidos = []
    for inicio, fin in sorted(tramos):
        if not isinstance(inicio, int) or not isinstance(fin, int):
            raise ValueError("Offsets no enteros")
        if not 0 <= inicio <= fin <= longitud:
            raise ValueError(f"Tramo fuera del texto: [{inicio}, {fin}) / {longitud}")
        if inicio == fin:
            continue
        if unidos and inicio <= unidos[-1][1]:
            unidos[-1] = (unidos[-1][0], max(fin, unidos[-1][1]))
        else:
            unidos.append((inicio, fin))
    return unidos


def complemento(tramos, longitud):
    huecos, cursor = [], 0
    for inicio, fin in union_tramos(tramos, longitud):
        if inicio > cursor:
            huecos.append((cursor, inicio))
        cursor = fin
    if cursor < longitud:
        huecos.append((cursor, longitud))
    return huecos


def intersecar_tramos(a, b, longitud):
    a, b = union_tramos(a, longitud), union_tramos(b, longitud)
    salida, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        inicio, fin = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if inicio < fin:
            salida.append((inicio, fin))
        if a[i][1] <= b[j][1]:
            i += 1
        else:
            j += 1
    return salida


def texto_tramos(texto, tramos):
    # Separar huecos evita inventar palabras pegando sus extremos.
    return "\n\n".join(texto[a:b] for a, b in tramos)


def cobertura_gold(silver, tramos):
    unidos = union_tramos(tramos, len(silver))
    huecos = complemento(unidos, len(silver))
    cubiertos = sum(b - a for a, b in unidos)
    return {
        "gold_caracteres_silver": len(silver),
        "gold_caracteres_cubiertos": cubiertos,
        "gold_cobertura_silver": m.cociente(cubiertos, len(silver)),
        "gold_numero_huecos": len(huecos),
        "gold_caracteres_huecos": len(silver) - cubiertos,
        "gold_huecos_mayores": [
            {"inicio": a, "fin": b, "caracteres": b - a, "muestra": silver[a:b][:80]}
            for a, b in sorted(huecos, key=lambda t: (t[0] - t[1], t[0]))[:5]
        ],
    }


def clave_mobiliario(linea):
    """Clave local verificable sin depender de decisiones del pipeline."""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", linea.lower())).strip()


def mobiliario_independiente(bronce, candidatos):
    """Frecuencia por páginas completas, contando una sola vez cada margen."""
    paginas = bronce.split("\n\f\n")
    frecuencia = Counter()
    for pagina in paginas:
        lineas = [x for x in pagina.splitlines() if x.strip()]
        frecuencia.update({clave_mobiliario(x) for x in (*lineas[:3], *lineas[-3:])})
    candidatos = {clave_mobiliario(x) for x in candidatos}
    return {
        k
        for k, n in frecuencia.items()
        if k in candidatos
        and n >= 3
        and n / len(paginas) >= 0.30
        and not MARCADOR_JURIDICO.search(k)
    }


def margenes(texto):
    """Índices (1-based, sobre splitlines) de las 3 primeras y 3 últimas líneas no vacías."""
    llenas = [i for i, x in enumerate(texto.splitlines(), 1) if x.strip()]
    return set(llenas[:3]) | set(llenas[-3:])


def desplazamientos_folio(paginas):
    """Desplazamientos valor − página observados en ≥ 2 páginas para folios numéricos de margen."""
    conteo = Counter()
    for numero, texto in enumerate(paginas, 1):
        lineas = texto.splitlines()
        vistos = set()
        for i in margenes(texto):
            valor = lineas[i - 1].strip()
            if valor.isdigit():
                vistos.add(int(valor) - numero)
        conteo.update(vistos)
    return {d for d, n in conteo.items() if n >= 2}


def es_folio(linea, pagina, en_margen, desplazamientos):
    """Un número aislado solo es folio si está en el margen y sigue la paginación."""
    valor = linea.strip()
    if not en_margen or not FOLIO.fullmatch(valor):
        return False
    return not valor.isdigit() or int(valor) - pagina in desplazamientos


def es_mobiliario(linea, claves_verificadas, folio=False):
    return folio or (
        clave_mobiliario(linea) in claves_verificadas and not MARCADOR_JURIDICO.search(linea)
    )


def lineas_eliminadas(bronce, mapa, claves_mobiliario=()):
    """Fragmentos eliminados, por página y línea, sin inferir alineamientos.

    Una línea parcialmente cubierta solo aporta el fragmento no cubierto.
    Se omiten fragmentos blancos y separadores de página.
    """
    candidatos = {clave_mobiliario(x) for x in claves_mobiliario}
    claves_mobiliario = mobiliario_independiente(bronce, candidatos)
    huecos = complemento([(t["source_start"], t["source_end"]) for t in mapa], len(bronce))
    lineas, desplazamiento, indice = [], 0, 0
    paginas = bronce.split("\n\f\n")
    desplazamientos = desplazamientos_folio(paginas)
    for pagina, texto in enumerate(paginas, 1):
        posicion = desplazamiento
        en_margen = margenes(texto)
        for numero, linea in enumerate(texto.splitlines(keepends=True), 1):
            folio = es_folio(linea, pagina, numero in en_margen, desplazamientos)
            fin = posicion + len(linea)
            while indice < len(huecos) and huecos[indice][1] <= posicion:
                indice += 1
            j = indice
            while j < len(huecos) and huecos[j][0] < fin:
                a, b = max(posicion, huecos[j][0]), min(fin, huecos[j][1])
                fragmento = bronce[a:b].strip()
                if fragmento:
                    lineas.append(
                        {
                            "pagina": pagina,
                            "linea": numero,
                            "inicio": a,
                            "fin": b,
                            "texto": fragmento,
                            # Clasifica la línea ORIGINAL, nunca el fragmento:
                            # un separador insertado puede cubrir su primera letra.
                            "mobiliario": es_mobiliario(linea, claves_mobiliario, folio),
                            "candidato_rechazado": (
                                clave_mobiliario(linea) in candidatos
                                and not es_mobiliario(linea, claves_mobiliario, folio)
                            ),
                        }
                    )
                j += 1
            posicion = fin
        desplazamiento += len(texto) + 3
    return lineas


def perdida_paginas_sin_u(paginas, eliminadas, elegibles):
    """Conservación bronce→silver, sin U, de las páginas que U no puede evaluar.

    Fracción de caracteres no blancos de cada página eliminados por silver fuera
    de líneas verificadas como mobiliario; se informa la página peor.
    """
    peor, detalle = None, []
    for numero, texto in enumerate(paginas, 1):
        if numero in elegibles:
            continue
        total = len(re.sub(r"\s", "", texto))
        perdidos = sum(
            len(re.sub(r"\s", "", x["texto"]))
            for x in eliminadas
            if x["pagina"] == numero and not x["mobiliario"]
        )
        valor = m.cociente(perdidos, total) if total else 0.0
        detalle.append({"pagina": numero, "caracteres": total, "perdidos_otros": perdidos})
        peor = valor if peor is None else max(peor, valor)
    if peor is None:
        return {"paginas_sin_u_perdida_silver": None, "paginas_sin_u_estado": "sin páginas"}
    return {
        "paginas_sin_u_perdida_silver": peor,
        "paginas_sin_u_estado": "evaluada",
        "paginas_sin_u_detalle": detalle,
    }


def perdida_silver(referencia, bronce, silver, *, eliminadas=()):
    """Descompone la pérdida total conservando su denominador y multiplicidad.

    Solo se exoneran ocurrencias en fragmentos efectivamente eliminados por
    offset_map de líneas verificadas como mobiliario; el resto es pérdida otra.
    Una palabra repetida en ambos tipos de línea no se cuenta dos veces.
    """
    u, b, s = palabras(referencia), palabras(bronce), palabras(silver)
    recuperadas = u & b
    conservadas = recuperadas & s
    perdidas = recuperadas - conservadas
    mobiliario = palabras("\n".join(linea["texto"] for linea in eliminadas if linea["mobiliario"]))
    perdidas_mobiliario = perdidas & mobiliario
    perdidas_otras = perdidas - perdidas_mobiliario
    denominador = sum(recuperadas.values())
    return {
        "silver_palabras_u_bronce": denominador,
        "silver_palabras_perdidas": sum(perdidas.values()),
        "silver_perdida": m.cociente(sum(perdidas.values()), denominador),
        "perdida_silver": m.cociente(sum(perdidas.values()), denominador),
        "silver_palabras_perdidas_mobiliario": sum(perdidas_mobiliario.values()),
        "silver_palabras_perdidas_otras": sum(perdidas_otras.values()),
        "perdida_silver_mobiliario": m.cociente(sum(perdidas_mobiliario.values()), denominador),
        "perdida_silver_otra": m.cociente(sum(perdidas_otras.values()), denominador),
        "silver_palabras": sum(s.values()),
        "silver_palabras_ruido": sum((s - u).values()),
        "silver_ruido": m.cociente(sum((s - u).values()), sum(s.values())),
        "bronce_palabras": sum(b.values()),
        "bronce_palabras_ruido": sum((b - u).values()),
        "bronce_ruido": m.cociente(sum((b - u).values()), sum(b.values())),
    }


def cortes_delicados(texto, posiciones):
    """Cuenta posiciones únicas dentro de números o entre artículo y su número.

    En números incluye ambos lados del punto/coma decimal o de millares. En
    artículos incluye cualquier punto del espacio que separa etiqueta y número.
    Se inspeccionan comienzos y finales de cuerpos, aunque haya solapamiento.
    """
    posiciones = sorted({p for p in posiciones if 0 < p < len(texto)})
    numeros = [(x.start(), x.end()) for x in NUMERO.finditer(texto)]
    articulos = []
    for coincidencia in ARTICULO.finditer(texto):
        numero = re.search(r"\d", coincidencia[0])
        etiqueta = re.match(r"(?:artículo|art\.)", coincidencia[0], re.I)
        articulos.append(
            (coincidencia.start() + etiqueta.end(), coincidencia.start() + numero.start())
        )
    return {
        "gold_cortes_numeros": sum(any(a < p < b for a, b in numeros) for p in posiciones),
        "gold_cortes_articulos": sum(any(a <= p <= b for a, b in articulos) for p in posiciones),
    }


def cuasi_duplicados(cuerpos):
    """Pares i,j con |i-j|>1, Jaccard de conjuntos de shingles de 5 palabras >=0,9.

    Orden = offsets de silver, desempate por orden original. Menos de cinco
    palabras no forma shingles. Los duplicados exactos también pueden contar
    aquí; la columna exacta cuenta copias sobrantes, esta cuenta pares.
    """
    ventanas, indice, pares = [], defaultdict(list), 0
    for j, cuerpo in enumerate(cuerpos):
        tokens = m.normalizar(cuerpo, modo="contenido").split()
        actual = {tuple(tokens[k : k + 5]) for k in range(len(tokens) - 4)}
        candidatos = set()
        for ventana in actual:
            candidatos.update(indice[ventana])
        for i in candidatos:
            if j - i <= 1:
                continue
            otra = ventanas[i]
            if min(len(actual), len(otra)) < 0.9 * max(len(actual), len(otra)):
                continue
            interseccion = len(actual & otra)
            if interseccion / (len(actual) + len(otra) - interseccion) >= 0.9:
                pares += 1
        ventanas.append(actual)
        for ventana in actual:
            indice[ventana].append(j)
    return pares


def cuerpo_gold(chunk):
    prefijo = chunk["metadata"]["header"] + "\n\n"
    contenido = chunk["page_content"]
    valida = contenido.startswith(prefijo)
    return (contenido[len(prefijo) :] if valida else contenido), valida


def reconstruir_gold(silver, chunks, tramos_evaluables=None):
    """Texto real: solape por offsets solo para cuerpos verificados contra silver.

    Un cuerpo discrepante no permite recortar páginas excluidas por sus offsets:
    solo entra si su intervalo completo pertenece a páginas evaluables.
    """
    elegibles = union_tramos(
        [(0, len(silver))] if tramos_evaluables is None else tramos_evaluables, len(silver)
    )
    no_evaluables = complemento(elegibles, len(silver))
    fragmentos, discrepantes = [], []
    for chunk in chunks:
        meta = chunk["metadata"]
        a, b = meta["clean_start"], meta["clean_end"]
        union_tramos([(a, b)], len(silver))
        cuerpo, valida = cuerpo_gold(chunk)
        intersecciones = intersecar_tramos([(a, b)], elegibles, len(silver))
        if valida and cuerpo == silver[a:b]:
            fragmentos.extend((x, y, cuerpo[x - a : y - a]) for x, y in intersecciones)
        # Los separadores blancos entre páginas evaluables no son una página
        # excluida. No se recorta nunca el TEXTO de un cuerpo discrepante.
        elif (
            tramos_evaluables is None
            or intersecciones
            or (a == b and any(x <= a < y for x, y in elegibles))
        ) and not any(
            silver[x:y].strip() for x, y in intersecar_tramos([(a, b)], no_evaluables, len(silver))
        ):
            discrepantes.append(cuerpo)
    partes, cursor = [], None
    for a, b, texto in sorted(fragmentos):
        if cursor is not None and b <= cursor:
            continue
        inicio = max(a, cursor) if cursor is not None else a
        if cursor is not None and a > cursor:
            partes.append("\n\n")
        partes.append(texto[inicio - a :])
        cursor = b
    return "\n\n".join(["".join(partes), *discrepantes])


def analizar_gold(silver, chunks):
    chunks = sorted(
        chunks, key=lambda x: (x["metadata"]["clean_start"], x["metadata"]["clean_end"])
    )
    tramos, efectivos, cuerpos, discrepancias, cabeceras_invalidas = [], [], [], 0, 0
    for chunk in chunks:
        meta = chunk["metadata"]
        a, b = meta["clean_start"], meta["clean_end"]
        tramos.append((a, b))
        cuerpo, valida = cuerpo_gold(chunk)
        cabeceras_invalidas += not valida
        discrepancias += not valida or cuerpo != silver[a:b]
        if valida and cuerpo == silver[a:b]:
            efectivos.append((a, b))
        cuerpos.append(cuerpo)
    unidos = union_tramos(tramos, len(silver))
    cobertura_efectiva = cobertura_gold(silver, efectivos)
    return {
        **cobertura_gold(silver, tramos),
        "gold_cobertura_declarada_silver": cobertura_gold(silver, tramos)["gold_cobertura_silver"],
        "gold_cobertura_efectiva_silver": cobertura_efectiva["gold_cobertura_silver"],
        "gold_caracteres_cubiertos_efectivos": cobertura_efectiva["gold_caracteres_cubiertos"],
        "gold_discrepancias_cuerpo": discrepancias,
        "gold_cabeceras_invalidas": cabeceras_invalidas,
        "gold_numero_chunks": len(chunks),
        "gold_mediana_caracteres_cuerpo": e.percentil(list(map(len, cuerpos)), 0.5),
        "gold_chunks_cortos": sum(len(x) < 200 for x in cuerpos),
        "gold_duplicados_exactos": len(cuerpos) - len(set(cuerpos)),
        "gold_cuasi_duplicados": cuasi_duplicados(cuerpos),
        **cortes_delicados(silver, [p for tramo in tramos for p in tramo]),
    }, unidos


def veredicto(
    cer,
    *,
    color_bronce=None,
    perdida_otra=None,
    cobertura=None,
    recall_critico=None,
    gold_discrepancias_cuerpo=0,
    gold_cabeceras_invalidas=0,
    perdida_sin_u=None,
    estado_sin_u="sin páginas",
):
    """Solo pérdida silver OTRA degrada; 0,46 % incierto y 1,54 % amarillo.

    Las páginas excluidas de U se controlan sin U (bronce→silver): su pérdida
    degrada con los mismos umbrales y, si no se pudo evaluar, impide el verde.
    """
    if gold_cabeceras_invalidas:
        return "rojo", "gold: cabecera inválida"
    if gold_discrepancias_cuerpo:
        return "rojo", "gold: cuerpo ≠ silver"
    if color_bronce is not None:
        color = color_bronce
    elif cer is None:
        color = "sin evaluar"
    elif cer < LIMITE_VERDE:
        color = "verde"
    elif cer < LIMITE_NO_DISTINGUIBLE:
        color = "no distinguible de U"
    elif cer <= UMBRAL_ROJO:
        color = "amarillo"
    else:
        color = "rojo"
    motivos = []
    if cobertura is not None and cobertura < COBERTURA_GOLD_ROJA:
        motivos.append(("rojo", "cobertura gold", cobertura))
    if perdida_otra is not None and perdida_otra > PERDIDA_SILVER_OTRA_ROJA:
        motivos.append(("rojo", "pérdida silver otra", perdida_otra))
    elif perdida_otra is not None and perdida_otra > PERDIDA_SILVER_OTRA_AMARILLA:
        motivos.append(("amarillo", "pérdida silver otra", perdida_otra))
    if perdida_sin_u is not None and perdida_sin_u > PERDIDA_SILVER_OTRA_ROJA:
        motivos.append(("rojo", "pérdida silver en páginas sin U", perdida_sin_u))
    elif perdida_sin_u is not None and perdida_sin_u > PERDIDA_SILVER_OTRA_AMARILLA:
        motivos.append(("amarillo", "pérdida silver en páginas sin U", perdida_sin_u))
    if recall_critico is not None and recall_critico < RECALL_CRITICO_AMARILLO:
        motivos.append(("amarillo", "recall crítico", recall_critico))
    for minimo, factor, valor in motivos:
        if color == "sin evaluar" or ORDEN_COLOR[minimo] > ORDEN_COLOR[color]:
            return minimo, f"{factor}: {porcentaje(valor)}"
    if estado_sin_u == "no evaluada" and color == "verde":
        return "no distinguible de U", "páginas sin U no verificadas"
    return color, ""


def sumar_metricas(filas):
    totales = {k: sum(f[k] for f in filas) for k in SUMABLES}
    return {
        **totales,
        **{
            k: m.cociente(totales[m.CAMPOS[a]], totales[m.CAMPOS[b]])
            for k, (a, b) in m.COCIENTES.items()
        },
        "orden_lcs": m.cociente(totales["lcs"], totales["ngramas_ref"]),
        "recall_critico": m.cociente(totales["crit_comunes"], totales["crit_total_ref"]),
    }


def resumir_estrato(filas):
    resultado = sumar_metricas(filas)
    intervalos = m.bootstrap(filas, semilla=SEMILLA, repeticiones=REPETICIONES)
    # Reutiliza el MISMO bootstrap para LCS y críticos con sus denominadores.
    auxiliares = [
        {
            **f,
            "ediciones_caracteres": f["lcs"],
            "caracteres_ref": f["ngramas_ref"],
            "ediciones_palabras": f["crit_comunes"],
            "palabras_ref": f["crit_total_ref"],
        }
        for f in filas
    ]
    adicionales = m.bootstrap(auxiliares, semilla=SEMILLA, repeticiones=REPETICIONES)
    intervalos.update(orden_lcs=adicionales["cer"], recall_critico=adicionales["wer"])
    resultado.update(
        paginas=len(filas),
        ic_amplio="sí" if len(filas) < 10 else "no",
        criticos_faltantes=abreviar([x for f in filas for x in f["criticos_faltantes"]]),
    )
    for nombre, intervalo in intervalos.items():
        resultado[f"{nombre}_ic95_inferior"] = intervalo[0] if intervalo else None
        resultado[f"{nombre}_ic95_superior"] = intervalo[1] if intervalo else None
    return resultado


def abreviar(elementos, limite=12):
    return [str(x)[:100] for x in elementos[:limite]] + (
        [f"… {len(elementos) - limite} más"] if len(elementos) > limite else []
    )


def evaluar_pagina(bronce, referencia):
    comparacion = m.comparar_criticos(bronce, referencia, modo="contenido")
    metricas = m.metricas(bronce, referencia, modo="contenido")
    unificadas = (
        m.metricas(bronce.replace("º", "°"), referencia.replace("º", "°"), modo="contenido")
        if "º" in bronce or "º" in referencia
        else metricas
    )
    return {
        **metricas,
        "ediciones_caracteres_grado_unificado": unificadas["ediciones_caracteres"],
        "crit_total_ref": sum(x["total_ref"] for x in comparacion.values()),
        "crit_comunes": sum(x["comunes"] for x in comparacion.values()),
        "criticos_faltantes": [
            f"{tipo}: {valor}"
            for tipo, datos in comparacion.items()
            for valor in datos["faltantes_en_hip"]
        ],
    }


def sensibilidad_grado(documentos, paginas):
    """Agrega las mismas páginas evaluadas desde las capas seleccionadas por CLI."""
    salida = {}
    for doc in documentos:
        filas = [p for p in paginas if p["slug"] == doc["slug"] and p["estado"] == "evaluada"]
        salida[doc["slug"]] = {
            "cer": m.cociente(
                sum(p["ediciones_caracteres"] for p in filas),
                sum(p["caracteres_ref"] for p in filas),
            ),
            "cer_grado_unificado": m.cociente(
                sum(p["ediciones_caracteres_grado_unificado"] for p in filas),
                sum(p["caracteres_ref"] for p in filas),
            ),
            **{k: doc[k] for k in ("huella_u", "huella_bronce")},
        }
    evaluadas = [p for p in paginas if p["estado"] == "evaluada"]
    denominador = sum(p["caracteres_ref"] for p in evaluadas)
    salida["_corpus"] = {
        "cer": m.cociente(sum(p["ediciones_caracteres"] for p in evaluadas), denominador),
        "cer_grado_unificado": m.cociente(
            sum(p["ediciones_caracteres_grado_unificado"] for p in evaluadas), denominador
        ),
    }
    return salida


def alertas_ocr(extraccion, filas):
    ocr = m.paginas_ocr(extraccion)
    confianzas = extraccion.get("ocr_confidence", {})
    conocidas = {p: confianzas.get(str(p)) for p in sorted(ocr)}
    conocidas = {
        p: x for p, x in conocidas.items() if isinstance(x, (int, float)) and math.isfinite(x)
    }
    alertadas = {p for p, x in conocidas.items() if x <= UMBRAL_CONFIANZA}
    evaluadas = {f["pagina"]: f for f in filas if f["tipo_pagina"] == "OCR"}
    malas = {p for p, f in evaluadas.items() if f["cer"] is not None and f["cer"] > UMBRAL_ROJO}
    aciertos = len(alertadas & malas)
    return {
        "ocr_confianza_media": mean(conocidas.values()) if conocidas else None,
        "ocr_confianza_minima": min(conocidas.values()) if conocidas else None,
        "ocr_paginas_sin_confianza": len(ocr) - len(conocidas),
        "ocr_paginas_alertadas": len(alertadas),
        "ocr_fraccion_alertadas": m.cociente(len(alertadas), len(ocr)),
        "ocr_alertas_evaluables": len(alertadas & evaluadas.keys()),
        "ocr_alertas_sin_u_evaluable": len(alertadas - evaluadas.keys()),
        "ocr_aciertos": aciertos,
        "ocr_fallos": len(malas - alertadas),
        "ocr_sensibilidad": m.cociente(aciertos, len(malas)),
        "ocr_precision_alertas": m.cociente(aciertos, len(alertadas & evaluadas.keys())),
    }


def cargar_capas(raiz, doc_id):
    rutas = rutas_capas(raiz, doc_id)
    salida = {"faltantes": [k for k, p in rutas.items() if not p.is_file()]}
    for nombre, ruta in rutas.items():
        if not ruta.is_file():
            salida[nombre] = None
        elif nombre in {"bronce", "silver"}:
            salida[nombre] = leer_texto(ruta)
        elif nombre == "gold":
            salida[nombre] = [json.loads(x) for x in leer_texto(ruta).splitlines() if x.strip()]
        else:
            salida[nombre] = leer_json(ruta)
    return salida


def rutas_capas(raiz, doc_id):
    return {
        "bronce": raiz / "bronze" / (doc_id + ".txt"),
        "extraccion": raiz / "bronze" / (doc_id + ".extraction.json"),
        "silver": raiz / "silver" / (doc_id + ".txt"),
        "contexto": raiz / "silver" / (doc_id + ".context.json"),
        "gold": raiz / "gold" / (doc_id + ".jsonl"),
    }


def validar_contexto(capas, numero_paginas):
    limpio = capas["contexto"]["cleaned"]
    if limpio["text"] != capas["silver"]:
        raise ValueError("El texto del contexto no coincide con silver.txt")
    if [p["page"] for p in limpio["pages"]] != list(range(1, numero_paginas + 1)):
        raise ValueError("Páginas del contexto incompatibles con bronce")
    for nombre, longitud, tramos in (
        (
            "limpios",
            len(capas["silver"]),
            [(p["clean_start"], p["clean_end"]) for p in limpio["pages"]],
        ),
        (
            "fuente",
            len(capas["bronce"]),
            [(p["source_start"], p["source_end"]) for p in limpio["offset_map"]],
        ),
    ):
        try:
            union_tramos(tramos, longitud)
        except ValueError as exc:
            raise ValueError(f"Offsets {nombre}: {exc}") from exc
    return limpio


def evaluar_documento(doc, raiz, conjunto, excluidas):
    slug, doc_id = doc["slug"], doc["sha256"]
    capas = cargar_capas(raiz, doc_id)
    fila = {
        "slug": slug,
        "doc_id": doc_id[:12],
        "categoria": doc["categoria"],
        "paginas": int(doc["paginas"]),
        "conjunto": conjunto,
        "paginas_excluidas_u": sorted(p for s, p in excluidas if s == slug),
        "capas_faltantes": capas["faltantes"],
    }
    fila["numero_paginas_excluidas_u"] = len(fila["paginas_excluidas_u"])
    ruta_u, _, _ = v.rutas_documento(doc)
    fila.update(
        {
            k: c.huella(ruta) if ruta.is_file() else ""
            for k, ruta in {
                "huella_u": ruta_u,
                "huella_bronce": rutas_capas(raiz, doc_id)["bronce"],
                "huella_gold": rutas_capas(raiz, doc_id)["gold"],
            }.items()
        }
    )
    numeros, u, prefijo = (
        v.separar_paginas(leer_texto(ruta_u)) if ruta_u.is_file() else ([], {}, "")
    )
    if prefijo or len(numeros) != len(set(numeros)):
        raise ValueError("Marcas U no unívocas o prefijo sin página: " + slug)
    if set(numeros) - set(range(1, fila["paginas"] + 1)):
        raise ValueError("U tiene páginas fuera del documento: " + slug)
    elegibles = [p for p in range(1, fila["paginas"] + 1) if (slug, p) not in excluidas and p in u]
    fila["paginas_sin_u"] = [
        p for p in range(1, fila["paginas"] + 1) if p not in u and (slug, p) not in excluidas
    ]
    fila["tiene_tablas"] = (
        "sí" if any(re.search(r"<table\b", u[p], re.I) for p in elegibles) else "no"
    )
    detalles, evaluadas = [], []
    eliminadas = []
    if capas["bronce"] is not None and capas["extraccion"] is not None:
        bronce, extr = capas["bronce"], capas["extraccion"]
        paginas = bronce.split("\n\f\n")
        if (
            extr["doc_id"] != doc_id
            or extr["sha256"] != doc_id
            or len(paginas) != fila["paginas"]
            or len(extr["chars_per_page"]) != len(paginas)
        ):
            raise ValueError("Identidad o número de páginas incompatible: " + slug)
        ocr = m.paginas_ocr(extr)
        if not ocr <= set(range(1, len(paginas) + 1)):
            raise ValueError("Páginas OCR fuera del documento: " + slug)
        fila.update(
            paginas_ocr=len(ocr),
            paginas_digitales=len(paginas) - len(ocr),
            paginas_ocr_fallidas=len(extr.get("ocr_failed_pages", [])),
        )
        for p, texto in enumerate(paginas, 1):
            base = {
                "slug": slug,
                "doc_id": doc_id[:12],
                "categoria": doc["categoria"],
                "conjunto": conjunto,
                "pagina": p,
                "tipo_pagina": "OCR" if p in ocr else "digital",
                "confianza_ocr": extr.get("ocr_confidence", {}).get(str(p)) if p in ocr else None,
            }
            if (slug, p) in excluidas or p not in u:
                detalles.append(
                    {**base, "estado": "excluida de U" if (slug, p) in excluidas else "sin U"}
                )
                continue
            f = {**base, "estado": "evaluada", **evaluar_pagina(texto, u[p])}
            tablas = TABLA.findall(u[p])
            celdas = "\n".join(celda for tabla in tablas for celda in CELDA.findall(tabla))
            celdas_u = palabras(celdas)
            f.update(
                tiene_tabla="sí" if tablas else "no",
                tabla_palabras_ref=sum(celdas_u.values()),
                tabla_palabras_comunes=sum((celdas_u & palabras(texto)).values()),
            )
            evaluadas.append(f)
            detalles.append(f)
        for estrato, fs in (
            ("digital", [f for f in evaluadas if f["tipo_pagina"] == "digital"]),
            ("ocr", [f for f in evaluadas if f["tipo_pagina"] == "OCR"]),
            ("total", evaluadas),
        ):
            fila.update(
                {f"bronce_{estrato}_{k}": valor for k, valor in resumir_estrato(fs).items()}
            )
        tablas = [f for f in evaluadas if f["tiene_tabla"] == "sí"]
        fila.update(
            tabla_paginas=len(tablas),
            tabla_cer=sumar_metricas(tablas)["cer"],
            tabla_palabras_ref=sum(f["tabla_palabras_ref"] for f in tablas),
            tabla_palabras_comunes=sum(f["tabla_palabras_comunes"] for f in tablas),
        )
        fila["tabla_recall_palabras"] = m.cociente(
            fila["tabla_palabras_comunes"], fila["tabla_palabras_ref"]
        )
        fila.update(alertas_ocr(extr, evaluadas))
        if capas["silver"] is not None and capas["contexto"] is not None:
            limpio = validar_contexto(capas, len(paginas))
            referencia = "\n\n".join(u[p] for p in elegibles)
            bronce_evaluable = "\n\n".join(paginas[p - 1] for p in elegibles)
            tramos_evaluables = [
                (p["clean_start"], p["clean_end"])
                for p in limpio["pages"]
                if p["page"] in elegibles
            ]
            silver_evaluable = texto_tramos(capas["silver"], tramos_evaluables)
            claves = limpio["removed_furniture_keys"]
            todas_eliminadas = lineas_eliminadas(bronce, limpio["offset_map"], claves)
            eliminadas = [x for x in todas_eliminadas if x["pagina"] in elegibles]
            fila.update(perdida_paginas_sin_u(paginas, todas_eliminadas, set(elegibles)))
            fila.update(
                perdida_silver(
                    referencia, bronce_evaluable, silver_evaluable, eliminadas=eliminadas
                )
            )
            # Las páginas excluidas nunca intervienen tampoco en las muestras.
            eliminadas = [x for x in eliminadas if not x["mobiliario"]]
            fila["silver_claves_mobiliario_eliminadas"] = abreviar(limpio["removed_furniture_keys"])
            if capas["gold"] is not None:
                gold, _ = analizar_gold(capas["silver"], capas["gold"])
                fila.update(gold)
                reconstruido = reconstruir_gold(capas["silver"], capas["gold"], tramos_evaluables)
                u_palabras = palabras(referencia)
                fila["gold_palabras_u"] = sum(u_palabras.values())
                fila["gold_palabras_u_cubiertas"] = sum(
                    (u_palabras & palabras(reconstruido)).values()
                )
                fila["gold_recuperacion_u"] = m.cociente(
                    fila["gold_palabras_u_cubiertas"], fila["gold_palabras_u"]
                )
    if any(p not in elegibles for p in range(1, fila["paginas"] + 1)):
        fila.setdefault("paginas_sin_u_perdida_silver", None)
        fila.setdefault("paginas_sin_u_estado", "no evaluada")
    else:
        fila.setdefault("paginas_sin_u_perdida_silver", None)
        fila.setdefault("paginas_sin_u_estado", "sin páginas")
    color, motivo = veredicto(
        fila.get("bronce_total_cer"),
        perdida_sin_u=fila["paginas_sin_u_perdida_silver"],
        estado_sin_u=fila["paginas_sin_u_estado"],
        perdida_otra=fila.get("perdida_silver_otra"),
        cobertura=fila.get("gold_cobertura_silver"),
        recall_critico=fila.get("bronce_total_recall_critico"),
        gold_discrepancias_cuerpo=fila.get("gold_discrepancias_cuerpo", 0),
        gold_cabeceras_invalidas=fila.get("gold_cabeceras_invalidas", 0),
    )
    if color != "verde" and not motivo and fila.get("bronce_total_cer") is not None:
        candidatos = [
            (fila.get("bronce_ocr_ediciones_caracteres", 0), "CER OCR", fila.get("bronce_ocr_cer")),
            (
                fila.get("bronce_digital_ediciones_caracteres", 0),
                "CER digital",
                fila.get("bronce_digital_cer"),
            ),
        ]
        # Tablas decide el motivo si concentra más ediciones que el resto.
        ed_tablas = sum(f["ediciones_caracteres"] for f in evaluadas if f["tiene_tabla"] == "sí")
        if ed_tablas > sum(f["ediciones_caracteres"] for f in evaluadas) / 2:
            motivo = f"tablas: CER {porcentaje(fila['tabla_cer'])}"
        else:
            _, factor, valor = max(candidatos, key=lambda x: x[0])
            motivo = f"{factor}: {porcentaje(valor)}"
    # La ejecución parcial no puede emitir una aprobación documental completa.
    fila["veredicto_automatico"] = (
        "sin evaluar" if capas["faltantes"] or fila["paginas_sin_u"] else color
    )
    fila["motivo_principal"] = motivo
    fila["veredicto_auditado"] = ""
    fila["veredicto_final"] = fila["veredicto_automatico"]
    return fila, detalles, eliminadas


def originales_md(raiz):
    """Solo MD locales; nunca interpreta source_path como ruta absoluta libre."""
    if not raiz.is_dir():
        return []
    return [p for p in raiz.rglob("*.md") if p.resolve().is_relative_to(raiz.resolve())]


def unicos_por_hash(rutas):
    """Copias byte-idénticas no son ambigüedad: conserva una por SHA-256."""
    vistos = {}
    for p in sorted(rutas):
        vistos.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), p)
    return list(vistos.values())


def buscar_original_md(nombre, doc_id, originales):
    candidatos = [p for p in originales if hashlib.sha256(p.read_bytes()).hexdigest() == doc_id]
    if candidatos:
        return unicos_por_hash(candidatos)
    nombre = unicodedata.normalize("NFC", nombre.replace("\\", "/"))
    candidatos = [
        p for p in originales if unicodedata.normalize("NFC", p.name) == Path(nombre).name
    ]
    if candidatos:
        return unicos_por_hash(candidatos)
    # Los originales preparados se llaman <sha256 corto>.md. Su manifiesto
    # local permite encontrar el alias aun si el doc_id de la corrida difiere.
    manifiesto = BASE.parent / "fidelidad/trabajo/mapa_originales.json"
    if manifiesto.is_file():
        mapa = leer_json(manifiesto)
        for p in originales:
            registro = mapa.get(p.name, {})
            alias = unicodedata.normalize("NFC", registro.get("ruta", ""))
            if alias == nombre and c.huella(p) == registro.get("sha256"):
                candidatos.append(p)
    return unicos_por_hash(candidatos)


def evaluar_md(raiz, originales):
    filas = []
    for archivo in sorted((raiz / "bronze").glob("*.extraction.json")):
        extr = leer_json(archivo)
        if not str(extr.get("original_file", "")).lower().endswith(".md"):
            continue
        doc_id = extr["doc_id"]
        capas = cargar_capas(raiz, doc_id)
        contexto = capas["contexto"] or {}
        nombre = contexto.get("source_path", extr["original_file"])
        fila = {
            "documento": nombre,
            "doc_id": doc_id[:12],
            "referencia": "SIN referencia de OCR",
            "capas_faltantes": capas["faltantes"],
        }
        if capas["bronce"] is None:
            filas.append(fila)
            continue
        bronce_bytes = (raiz / "bronze" / (doc_id + ".txt")).read_bytes()
        candidatos = buscar_original_md(nombre, doc_id, originales)
        if len(candidatos) == 1:
            original = candidatos[0].read_bytes()
            fila["bronce_identico_bytes"] = "sí" if original == bronce_bytes else "no"
            fila["original_sha256_coincide"] = (
                "sí" if hashlib.sha256(original).hexdigest() == doc_id else "no"
            )
            fila["original_bytes"] = len(original)
            texto_original = original.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
            normalizado = "\n\f\n".join(
                unicodedata.normalize("NFC", p) for p in texto_original.split("\f")
            )
            fila["cambio_bronce"] = (
                "idéntico"
                if original == bronce_bytes
                else "BOM/NFC/saltos de línea/separadores de página"
                if normalizado.encode("utf-8") == bronce_bytes
                else "otro cambio de contenido"
            )
        else:
            fila["bronce_identico_bytes"] = None
            fila["cambio_bronce"] = "original local no disponible o ambiguo"
        fila["bronce_bytes"] = len(bronce_bytes)
        fila["bronce_caracteres"] = len(capas["bronce"])
        if capas["silver"] is not None:
            fila["silver_caracteres"] = len(capas["silver"])
            fila["perdida_bronce_silver_caracteres"] = m.cociente(
                len(capas["bronce"]) - len(capas["silver"]), len(capas["bronce"])
            )
            if capas["contexto"] is not None:
                limpio = validar_contexto(capas, len(capas["bronce"].split("\n\f\n")))
                huecos = complemento(
                    [(p["source_start"], p["source_end"]) for p in limpio["offset_map"]],
                    len(capas["bronce"]),
                )
                fila["bronce_caracteres_sin_mapa"] = sum(b - a for a, b in huecos)
            if capas["gold"] is not None:
                fila.update(analizar_gold(capas["silver"], capas["gold"])[0])
        filas.append(fila)
    return filas


def resumen_grupo(documentos, paginas):
    evaluadas = [p for p in paginas if p["estado"] == "evaluada"]
    salida = {
        "documentos": len(documentos),
        "paginas_evaluadas": len(evaluadas),
        "colores": {
            color: sum(f["veredicto_final"] == color for f in documentos) for color in COLORES
        },
        "colores_automaticos": {
            color: sum(f["veredicto_automatico"] == color for f in documentos) for color in COLORES
        },
        "agregado": {},
        "agregado_capas": {},
        "por_documento": {},
    }
    for estrato, fs in (
        ("total", evaluadas),
        ("digital", [p for p in evaluadas if p["tipo_pagina"] == "digital"]),
        ("ocr", [p for p in evaluadas if p["tipo_pagina"] == "OCR"]),
    ):
        salida["agregado"][estrato] = sumar_metricas(fs)
    for campo in [
        *(
            f"bronce_{s}_{k}"
            for s in ("total", "digital", "ocr")
            for k in (*m.COCIENTES, "orden_lcs", "recall_critico")
        ),
        "silver_perdida",
        "perdida_silver_mobiliario",
        "perdida_silver_otra",
        "silver_ruido",
        "bronce_ruido",
        "gold_cobertura_silver",
        "gold_cobertura_declarada_silver",
        "gold_cobertura_efectiva_silver",
        "gold_recuperacion_u",
        "tabla_cer",
        "tabla_recall_palabras",
        "gold_numero_chunks",
        "gold_mediana_caracteres_cuerpo",
        "gold_chunks_cortos",
        "gold_duplicados_exactos",
        "gold_cuasi_duplicados",
        "gold_cortes_numeros",
        "gold_cortes_articulos",
        "gold_discrepancias_cuerpo",
        "ocr_confianza_media",
        "ocr_confianza_minima",
        "ocr_fraccion_alertadas",
        "ocr_sensibilidad",
        "ocr_precision_alertas",
    ]:
        valores = [f[campo] for f in documentos if f.get(campo) is not None]
        salida["por_documento"][campo] = {
            "n": len(valores),
            "media": mean(valores) if valores else None,
            "mediana": e.percentil(valores, 0.5),
        }
    for nombre, numerador, denominador in (
        ("silver_perdida", "silver_palabras_perdidas", "silver_palabras_u_bronce"),
        (
            "perdida_silver_mobiliario",
            "silver_palabras_perdidas_mobiliario",
            "silver_palabras_u_bronce",
        ),
        ("perdida_silver_otra", "silver_palabras_perdidas_otras", "silver_palabras_u_bronce"),
        ("silver_ruido", "silver_palabras_ruido", "silver_palabras"),
        ("bronce_ruido", "bronce_palabras_ruido", "bronce_palabras"),
        ("gold_cobertura_silver", "gold_caracteres_cubiertos", "gold_caracteres_silver"),
        ("gold_cobertura_declarada_silver", "gold_caracteres_cubiertos", "gold_caracteres_silver"),
        (
            "gold_cobertura_efectiva_silver",
            "gold_caracteres_cubiertos_efectivos",
            "gold_caracteres_silver",
        ),
        ("gold_recuperacion_u", "gold_palabras_u_cubiertas", "gold_palabras_u"),
        ("tabla_recall_palabras", "tabla_palabras_comunes", "tabla_palabras_ref"),
    ):
        disponibles = [
            f for f in documentos if f.get(numerador) is not None and f.get(denominador) is not None
        ]
        n, d = sum(f[numerador] for f in disponibles), sum(f[denominador] for f in disponibles)
        salida["agregado_capas"][nombre] = {
            "documentos": len(disponibles),
            "numerador": n,
            "denominador": d,
            "valor": m.cociente(n, d),
        }
    return salida


def resumen_agregado(documentos, paginas):
    salida = {}
    # Las categorías se cruzan con conjunto: nunca presentar ajuste como validación.
    for conjunto in ("ajuste", "validacion"):
        docs = [f for f in documentos if f["conjunto"] == conjunto]
        pags = [f for f in paginas if f["conjunto"] == conjunto]
        salida[conjunto] = resumen_grupo(docs, pags)
        salida[conjunto]["categorias"] = {
            categoria: resumen_grupo(
                [f for f in docs if f["categoria"] == categoria],
                [f for f in pags if f["categoria"] == categoria],
            )
            for categoria in sorted({f["categoria"] for f in documentos})
        }
    return salida


def porcentaje(valor):
    return "n/d" if valor is None else f"{100 * valor:.2f} %"


def celda_md(valor):
    return str(valor).replace("|", "\\|").replace("\n", " ").replace("\r", " ").replace("<", "&lt;")


def informe_auditoria(documentos):
    lineas = [
        "",
        "## Auditoría visual ciega de los 6 peores",
        "",
        "Se seleccionaron los seis documentos con mayor CER automático y, por documento, "
        "las 6 páginas evaluables con más ediciones (o todas si había menos de seis). "
        "Se comparó la imagen de cada página a 200 dpi con los textos X/Y. "
        "Los rangos impares se asignaron al auditor A = Claude y los pares al auditor B = Codex. "
        "Ambos trabajaron independientes y sin ver la clave. La asignación X/Y fue aleatoria "
        "con semilla 20261110. Limitación: el formato de U —tablas HTML, párrafos en una línea— "
        "delata la fuente, así que la ceguera es parcial. La adjudicación por documento recoge "
        "las observaciones de ambos auditores y conserva las métricas automáticas.",
        "Solo se aplica si coinciden los SHA256 actuales de U, bronce y gold, la evaluación "
        "está completa y la cobertura gold es evaluable. estado_auditoria explica cada rechazo. "
        "La revisión sustituye solo el componente bronce/U; después se vuelven a imponer "
        "las puertas de pérdida silver, cobertura gold e integridad de cuerpos y cabeceras.",
        "",
        "Evidencias: [auditoria_revision_A_claude.tsv](auditoria_revision_A_claude.tsv), "
        "[auditoria_revision_B_codex.tsv](auditoria_revision_B_codex.tsv), "
        "[auditoria_clave.csv](auditoria_clave.csv) y "
        "[veredictos adjudicados](auditoria_veredictos.csv).",
    ]
    for fila in sorted(
        (f for f in documentos if f["veredicto_auditado"]),
        key=lambda f: (-(f.get("bronce_total_cer") or 0), f["slug"]),
    ):
        lineas.extend(
            [
                "",
                f"### {fila['slug']}",
                "",
                "| Veredicto automático → final | Estado | Causa | Justificación |",
                "|---|---|---|---|",
                "| "
                + " | ".join(
                    celda_md(x)
                    for x in (
                        fila["veredicto_automatico"] + " → " + fila["veredicto_final"],
                        fila["estado_auditoria"],
                        fila["causa_auditada"],
                        fila["justificacion_auditoria"],
                    )
                )
                + " |",
            ]
        )
    return lineas


def informe_sensibilidad(datos):
    corpus = datos["_corpus"]
    if corpus["cer"] is None or corpus["cer_grado_unificado"] is None:
        return ["", "## Sensibilidad º/°", "", "No disponible: sin páginas evaluables."]
    lineas = [
        "",
        "## Sensibilidad º/°",
        "",
        "Fuente: [sensibilidad_grado.json](sensibilidad_grado.json). "
        "Se unifican º y ° solo para este análisis; no modifica las métricas principales.",
        "",
        f"CER corpus: {100 * corpus['cer']:.6f} % → "
        f"{100 * corpus['cer_grado_unificado']:.6f} %; "
        f"reducción de {100 * (corpus['cer'] - corpus['cer_grado_unificado']):.4f} pp.",
        "",
        "Documentos con cambio absoluto > 0,05 puntos porcentuales:",
        "",
        "| Documento | CER | CER º/° unificado | Reducción (pp) |",
        "|---|---:|---:|---:|",
    ]
    for slug, valores in sorted(datos.items()):
        if valores["cer"] is None or valores["cer_grado_unificado"] is None:
            continue
        diferencia = 100 * (valores["cer"] - valores["cer_grado_unificado"])
        if slug != "_corpus" and abs(diferencia) > 0.05:
            lineas.append(
                f"| {celda_md(slug)} | {porcentaje(valores['cer'])} | "
                f"{porcentaje(valores['cer_grado_unificado'])} | {diferencia:.4f} |"
            )
    return lineas


def informe_repetibilidad(datos):
    lineas = [
        "",
        "## Repetibilidad",
        "",
        "Fuentes: [hashes_runA.txt](../../trabajo/corridas/hashes_runA.txt) y "
        "[hashes_runB.txt](../../trabajo/corridas/hashes_runB.txt), manifiestos sha256sum de "
        "todos los archivos de capas de ambas corridas. Se comparan SHA256 por ruta relativa, "
        "independientemente del orden de las líneas. Una ruta ausente cuenta como distinta. "
        "Resultado completo: [repetibilidad.json](repetibilidad.json).",
        "",
        f"Archivos: {datos['archivos']}; idénticos: {datos['identicos']}; "
        f"distintos: {datos['distintos']}.",
        "",
        "| Tipo / etapa | Archivos | Idénticos | Distintos |",
        "|---|---:|---:|---:|",
    ]
    for nombre, grupo in [
        *datos["por_etapa"].items(),
        *datos["por_tipo"].items(),
        *(
            (tipo + " / " + etapa, grupo)
            for tipo, tipos in datos["por_tipo"].items()
            for etapa, grupo in tipos["por_etapa"].items()
        ),
    ]:
        lineas.append(
            f"| {nombre} | {grupo['archivos']} | {grupo['identicos']} | {grupo['distintos']} |"
        )
    lineas.extend(
        [
            "",
            "Las capas de runB no se descargaron y la EC2 ya se terminó; "
            "se omite la ejecución con --capas runB. "
            + (
                "Los 550 hashes coinciden por ruta: según estos manifiestos las capas son "
                "byte-idénticas y los CSV de métricas serían idénticos (salvo rutas). "
                "Es una inferencia de los hashes, no una segunda ejecución del comparador."
                if datos["archivos"] == datos["identicos"] == 550
                else "Los manifiestos no acreditan 550 archivos idénticos; "
                "no se afirma identidad de los CSV de métricas."
            ),
        ]
    )
    return lineas


def informe(documentos, docs_md, resumen):
    lineas = [
        "# Fiabilidad por documento",
        "",
        f"Estado: **{'COMPLETO' if resumen['completo'] else 'PARCIAL: faltan capas o referencias'}**. "
        f"PDF únicos: {len(documentos)}/53; MD: {len(docs_md)}. Calibración: {resumen['calibracion']['correctas']}/{resumen['calibracion']['total']}.",
        "",
        "## Regla del veredicto",
        "",
        "e_U = 0,0054 (error por palabra estimado de U; IC95 0,31–0,88 %). CER = bronce total, "
        "suma de ediciones / suma de caracteres de referencia. Verde: CER + e_U < 1 % "
        "(CER < 0,46 %). No distinguible de U: 0,46 % ≤ CER < 1,54 %; "
        "la ventana [CER − e_U, CER + e_U] toca el umbral de 1 %. "
        "Amarillo: 1,54 % ≤ CER ≤ 3 %. Rojo: CER > 3 %.",
        "",
        "Cobertura gold de silver < 99 % o perdida_silver_otra > 5 % → rojo. "
        "perdida_silver_otra > 2 % o recall crítico < 90 % → como mínimo amarillo. "
        "La pérdida de mobiliario institucional y paginación no degrada el veredicto; "
        "la pérdida total se conserva para trazabilidad. "
        "Son umbrales operativos solicitados: e_U mide palabras y no identifica un IC del CER verdadero. "
        "Se conserva el veredicto automático; si estado_auditoria = aplicada, veredicto_final "
        "parte del veredicto_auditado bronce/U y reaplica las puertas silver/gold. "
        "Una evaluación automática incompleta indica sin evaluar. "
        "La auditoría cambia la atribución y el veredicto, no las métricas frente a U.",
        "",
        "## Método",
        "",
        "Desde ingesta/: `python -I -B benchmarks/ocr_referencia/fiabilidad.py "
        "--capas trabajo/corridas/runA/pdf/capas`. Para runB: "
        "`--capas trabajo/corridas/runB/pdf/capas`. md/capas hermana se detecta "
        "automáticamente; --capas-md permite indicarla. Las rutas relativas parten "
        "de benchmarks/ocr_referencia/. CSV y JSON expresan las tasas como fracciones de 0 a 1.",
        "",
        "Modo contenido de metricas.py para todas las fuentes. CER/WER documentales y por estrato "
        "suman ediciones y denominadores por página; recuperación/precisión conservan multiplicidad. "
        "Críticos se comparan por página (categorías solapadas); orden = LCS de n-gramas de "
        "orden_lectura. IC95 percentil, bootstrap de páginas dentro de documento/estrato, "
        f"{REPETICIONES} repeticiones, semilla {SEMILLA}. ic_amplio = sí con menos de 10 páginas "
        "evaluables; un IC de una sola página es degenerado. Ausencia de denominador = n/d.",
        "",
        "Las siete páginas excluidas de U no participan en ninguna métrica con U ni en las muestras "
        "de líneas eliminadas. Cobertura gold, integridad de cuerpos y cortes usan el documento "
        "completo, sin U. Los contadores de confianza usan todas las páginas OCR; sensibilidad y "
        "precisión usan únicamente las evaluables frente a U. Una confianza ausente no alerta y "
        "cuenta como fallo si su CER > 3 %. La media de confianza pondera páginas por igual.",
        "",
        "Silver: pérdida = |(U ∩ bronce) − (U ∩ bronce ∩ silver)| / |U ∩ bronce|; "
        "ruido = |silver − U| / |silver|, con multiconjuntos documentales sobre páginas evaluables. "
        "La pérdida total permanece en silver_perdida (alias perdida_silver). "
        "perdida_silver_mobiliario atribuye primero las ocurrencias perdidas que caben en las "
        "palabras de fragmentos efectivamente eliminados según offset_map dentro de líneas "
        "del bronce verificadas como mobiliario. Las ocurrencias conservadas no exoneran "
        "palabras iguales eliminadas del cuerpo. "
        "perdida_silver_otra es el resto. Ambas tasas usan |U ∩ bronce| y suman la pérdida total, "
        "sin contar dos veces palabras repetidas entre mobiliario y contenido. "
        "Silver se pagina usando cleaned.pages. El CER de tablas incluye la página completa; "
        "recall de celdas compara el multiconjunto del texto td/th dentro de table con toda la página del bronce.",
        CRITERIO_MOBILIARIO,
        "",
        "offset_map asocia los separadores insertados a un carácter fuente (por ejemplo, la D "
        "de Departamento al inicio de página). Por eso el complemento de los offsets puede "
        "mostrar un fragmento eliminado sin su primera letra: es un artefacto del mapa, no "
        "pérdida adicional de contenido. El mobiliario se clasifica sobre la línea completa "
        "original, antes de recortar fragmentos. silver_lineas_eliminadas.md selecciona los "
        "cinco documentos con mayor perdida_silver_otra y lista además todos los candidatos rechazados.",
        "",
        "Gold: cobertura declarada = unión de [clean_start, clean_end) sobre silver "
        "(gold_cobertura_silver, alias gold_cobertura_declarada_silver); cobertura efectiva = "
        "unión solo de cuerpos con cabecera válida y texto idéntico al intervalo de silver "
        "(gold_cobertura_efectiva_silver). El recall U usa el TEXTO real de los cuerpos, "
        "quitando la cabecera válida y deduplicando solapes por offsets solo si el cuerpo coincide. "
        "Los discrepantes aportan su texto real completo; si cruzan páginas excluidas, se omiten "
        "del recall porque no hay un mapa fiable para recortarlos. Cualquier discrepancia o "
        "cabecera inválida impone rojo incluso tras aplicar la auditoría bronce/U. Los huecos mayores "
        "incluyen blancos. Duplicados exactos = copias sobrantes de cuerpos idénticos. "
        "Cuasi-duplicados = pares no adyacentes (|i−j|>1, orden por offsets) con Jaccard ≥ 0,9 "
        "entre conjuntos de shingles de cinco palabras normalizadas; menos de cinco palabras "
        "no forma shingles. Puede incluir pares exactos. Cortes = posiciones únicas de inicio/fin "
        "de cuerpo dentro de números (incluye punto/coma) o entre Artículo/Art. y su número.",
        "",
        "Motivo principal: primero la degradación que eleva el color (gold, silver, críticos); "
        "en otro caso tablas si concentra más de la mitad de ediciones, o el estrato digital/OCR "
        "con más ediciones. La tabla muestra los peores documentos primero. El CSV contiene "
        "todos los estratos, denominadores e intervalos. Detalle por página: trabajo/fiabilidad/paginas.csv.",
        "",
        "## PDF, del peor al mejor",
        "",
        "| Documento | Conjunto | Págs. | CER total | CER OCR | Pérdida silver otra | Gold declarada | Gold efectiva | Veredicto automático | Veredicto final | Causa (auditoría) | Motivo |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for f in documentos:
        valores = [
            f["slug"],
            "validación" if f["conjunto"] == "validacion" else "ajuste",
            f["paginas"],
            porcentaje(f.get("bronce_total_cer")),
            porcentaje(f.get("bronce_ocr_cer")),
            porcentaje(f.get("perdida_silver_otra")),
            porcentaje(f.get("gold_cobertura_silver")),
            porcentaje(f.get("gold_cobertura_efectiva_silver")),
            f["veredicto_automatico"],
            f["veredicto_final"],
            f["causa_auditada"],
            f["motivo_principal"],
        ]
        lineas.append("| " + " | ".join(celda_md(x) for x in valores) + " |")
    lineas.extend(
        [
            "",
            "## Resumen por conjunto y categoría",
            "",
            "Validación = cifras limpias del conjunto fijado. Ajuste es exploratorio. "
            "Media/mediana ponderan documentos por igual; agregado suma ediciones/denominadores.",
            "",
            "Colores: V = verde, U = no distinguible de U, A = amarillo, R = rojo.",
            "",
            "Total V / U / A / R / sin evaluar: finales "
            + " / ".join(str(resumen["colores_total"][x]) for x in COLORES)
            + "; automáticos "
            + " / ".join(str(resumen["colores_automaticos_total"][x]) for x in COLORES)
            + ".",
            "",
            "| Conjunto / categoría | Docs. | CER agregado | CER media | CER mediana | WER agregado | Colores finales V / U / A / R / sin evaluar | Colores automáticos V / U / A / R / sin evaluar |",
            "|---|---:|---:|---:|---:|---:|---|---|",
        ]
    )
    for conjunto, grupo in resumen["por_conjunto"].items():
        for nombre, g in [
            (conjunto, grupo),
            *((conjunto + " / " + cat, dato) for cat, dato in grupo["categorias"].items()),
        ]:
            estad = g["por_documento"]["bronce_total_cer"]
            lineas.append(
                f"| {nombre} | {g['documentos']} | {porcentaje(g['agregado']['total']['cer'])} | {porcentaje(estad['media'])} | {porcentaje(estad['mediana'])} | {porcentaje(g['agregado']['total']['wer'])} | {' / '.join(str(g['colores'][x]) for x in COLORES)} | {' / '.join(str(g['colores_automaticos'][x]) for x in COLORES)} |"
            )
    lineas.extend(
        [
            "",
            "Las medias y medianas de las demás métricas y los agregados por estrato están en resumen.json.",
        ]
    )
    lineas.extend(informe_auditoria(documentos))
    lineas.extend(informe_sensibilidad(resumen["sensibilidad_grado"]))
    lineas.extend(informe_repetibilidad(resumen["repetibilidad"]))
    lineas.extend(
        [
            "",
            "## Documentos MD — SIN referencia de OCR",
            "",
            "Pérdida de caracteres = (longitud bronce − longitud silver) / longitud bronce. "
            "Identidad se comprueba sobre bytes contra un original local con SHA256 coincidente "
            "o nombre unívoco; si falta se indica n/d. No se presupone identidad por el doc_id.",
            "",
            "| Documento | Bronce idéntico | Cambio | Pérdida caracteres | Gold declarada | Gold efectiva | Chunks cortos | Duplicados / cuasi | Cortes número / artículo | Cuerpos distintos |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for f in docs_md:
        valores = [
            f["documento"],
            f.get("bronce_identico_bytes") or "n/d",
            f.get("cambio_bronce", "n/d"),
            porcentaje(f.get("perdida_bronce_silver_caracteres")),
            porcentaje(f.get("gold_cobertura_silver")),
            porcentaje(f.get("gold_cobertura_efectiva_silver")),
            f.get("gold_chunks_cortos", "n/d"),
            f"{f.get('gold_duplicados_exactos', 'n/d')} / {f.get('gold_cuasi_duplicados', 'n/d')}",
            f"{f.get('gold_cortes_numeros', 'n/d')} / {f.get('gold_cortes_articulos', 'n/d')}",
            f.get("gold_discrepancias_cuerpo", "n/d"),
        ]
        lineas.append("| " + " | ".join(celda_md(x) for x in valores) + " |")
    lineas.extend(
        [
            "",
            "## Anomalías y disponibilidad",
            "",
            "```json",
            json.dumps(resumen["anomalias"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    )
    return "\n".join(lineas)


def informe_lineas_eliminadas(documentos, eliminadas):
    muestra = [
        "# Líneas del bronce eliminadas por silver",
        "",
        "Hasta 15 fragmentos por documento, para los cinco documentos con mayor perdida_silver_otra. "
        "Complemento exacto de offset_map.source_*; no se realiza alineamiento. "
        "Solo líneas originales no mobiliario. También se omiten blancos y páginas excluidas. "
        "Los separadores insertados se asocian a un carácter fuente; un fragmento puede aparecer "
        "sin su primera letra por este artefacto del mapa, no por pérdida adicional. "
        "Los fragmentos parciales no implican eliminación de toda la línea. "
        "La muestra sigue el orden del bronce y no atribuye causalidad a cada eliminación.",
        CRITERIO_MOBILIARIO,
        "",
    ]
    peores = sorted(
        (f for f in documentos if f.get("perdida_silver_otra") is not None),
        key=lambda f: (-f["perdida_silver_otra"], f["slug"]),
    )[:5]
    for f in peores:
        muestra.extend(
            [f"## {f['slug']} — pérdida otra {porcentaje(f['perdida_silver_otra'])}", ""]
        )
        for linea in eliminadas[f["slug"]][:15]:
            muestra.append(
                f"- Página {linea['pagina']}, línea {linea['linea']}, [{linea['inicio']}, {linea['fin']}): {celda_md(linea['texto'][:400])}"
            )
        if not eliminadas[f["slug"]]:
            muestra.append("Sin líneas no mobiliario eliminadas en páginas evaluables.")
        muestra.append("")
    muestra.extend(["## Todos los candidatos rechazados (páginas evaluables)", ""])
    for f in sorted(documentos, key=lambda x: x["slug"]):
        rechazados = [x for x in eliminadas[f["slug"]] if x["candidato_rechazado"]]
        if rechazados:
            muestra.extend([f"### {f['slug']}", ""])
            for linea in rechazados:
                muestra.append(
                    f"- Candidato rechazado; página {linea['pagina']}, línea {linea['linea']}, "
                    f"[{linea['inicio']}, {linea['fin']}): {celda_md(linea['texto'])}"
                )
            muestra.append("")
    return "\n".join(muestra)


def guardar_atomico(ruta, contenido=None, datos=None):
    """comun.json_guardar valida destino/JSON; publicación mediante os.replace."""
    ruta = c.destino(ruta)
    descriptor, nombre = tempfile.mkstemp(dir=ruta.parent, prefix="." + ruta.name, suffix=".tmp")
    os.close(descriptor)
    temporal = Path(nombre)
    try:
        if datos is not None:
            c.json_guardar(temporal, datos)
        else:
            temporal.write_text(contenido, encoding="utf-8", newline="\n")
        if ruta.is_relative_to(BASE / "resultados") and temporal.stat().st_size > MAX_BYTES:
            raise ValueError("Salida excede 5 MB: " + ruta.name)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def guardar_csv(ruta, filas, campos=None):
    # comun.csv_guardar ya es atómico. Precomprueba el límite antes de publicar.
    ruta = c.destino(ruta)
    temporal = ruta.with_name("." + ruta.name + ".comprobacion.tmp")
    try:
        c.csv_guardar(temporal, filas, campos)
        if ruta.is_relative_to(BASE / "resultados") and temporal.stat().st_size > MAX_BYTES:
            raise ValueError("Salida excede 5 MB: " + ruta.name)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def calibracion_existente():
    fuentes = c.modulo("comparar_fuentes")
    calibracion = fuentes.calibrar()
    pruebas = [p for dato in calibracion.values() for p in dato["pruebas"]]
    controles = [p for dato in calibracion.values() for p in dato["bucles"]]
    if not all(p["correcto"] for p in pruebas + controles):
        raise ValueError("Falló la calibración existente")
    return {
        "correctas": sum(p["correcto"] for p in pruebas),
        "total": len(pruebas),
        "controles_bucles_correctos": sum(p["correcto"] for p in controles),
        "controles_bucles": len(controles),
    }


class Argumentos(argparse.ArgumentParser):
    """Conserva el comportamiento de argparse y presenta su ayuda en español."""

    def format_help(self):
        return (
            super().format_help().replace("usage: ", "uso: ", 1).replace("options:", "opciones:", 1)
        )

    def format_usage(self):
        return super().format_usage().replace("usage: ", "uso: ", 1)


def principal():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = Argumentos(description=__doc__, add_help=False)
    parser.add_argument("-h", "--help", action="help", help="Muestra esta ayuda y termina")
    parser.add_argument(
        "--capas",
        type=ruta_local,
        default=BASE / "trabajo/corridas/runA/pdf/capas",
        help="Raíz con bronze/silver/gold; relativa al benchmark o absoluta (también runB)",
    )
    parser.add_argument(
        "--capas-md", type=ruta_local, help="Por defecto, md/capas hermana de pdf/capas"
    )
    parser.add_argument(
        "--originales-md", type=ruta_local, help="Raíz local opcional de los MD originales"
    )
    parser.add_argument(
        "--permitir-incompletas",
        action="store_true",
        help="Desarrollo con bronce previo o MD: marca sin evaluar lo que falta",
    )
    parser.add_argument(
        "--salida",
        type=ruta_local,
        default=BASE / "resultados/fiabilidad",
        help="Directorio de los cinco informes dentro del benchmark",
    )
    args = parser.parse_args()
    if not sys.flags.isolated:
        parser.error("Lectura de U requiere ejecutar Python con -I")
    if not args.capas.is_dir():
        parser.error("No existe la raíz de capas: " + str(args.capas))
    division = leer_json(BASE / "division_ajuste_validacion.json")
    if (
        division["semilla"] != SEMILLA
        or len(division["ajuste"]) != 21
        or len(division["validacion"]) != 32
    ):
        parser.error("División distinta de 21 ajuste / 32 validación, semilla 20261110")
    conjuntos = {
        slug: conjunto for conjunto in ("ajuste", "validacion") for slug in division[conjunto]
    }
    if len(conjuntos) != 53:
        parser.error("División con duplicados o conjuntos solapados")
    mapping, vistos = [], set()
    for doc in c.csv_leer(v.ENTRADA / "mapping.csv"):
        v.rutas_documento(doc)
        if doc["duplicado_de"] or doc["sha256"] in vistos:
            continue
        vistos.add(doc["sha256"])
        mapping.append(doc)
    if len(mapping) != 53 or {d["slug"] for d in mapping} != conjuntos.keys():
        parser.error("Mapping no coincide con los 53 documentos de la división")
    fuentes_auditoria = BASE / "resultados/fiabilidad"
    auditoria = cargar_auditoria(fuentes_auditoria / "auditoria_veredictos.csv", mapping)
    repetibilidad = comparar_hashes(
        BASE / "trabajo/corridas/hashes_runA.txt", BASE / "trabajo/corridas/hashes_runB.txt"
    )
    excluidas = {
        (r["slug"], int(r["pagina"])) for r in c.csv_leer(BASE / "resultados/paginas_excluidas.csv")
    }
    if len(excluidas) != 7:
        parser.error("Se esperaban exactamente siete páginas excluidas")
    if not args.permitir_incompletas:
        faltantes = []
        for doc in mapping:
            ausentes = [
                k for k, p in rutas_capas(args.capas, doc["sha256"]).items() if not p.is_file()
            ]
            if ausentes:
                faltantes.append(doc["slug"] + ": " + ", ".join(ausentes))
        if faltantes:
            parser.error(
                "Faltan capas; use --permitir-incompletas para desarrollo:\n" + "\n".join(faltantes)
            )
    calibracion = calibracion_existente()
    print(f"Calibración: {calibracion['correctas']}/{calibracion['total']}", flush=True)
    documentos, paginas, eliminadas = [], [], {}
    for indice, doc in enumerate(mapping, 1):
        print(f"Documento {indice}/53: {doc['slug']}", flush=True)
        fila, detalle, muestra = evaluar_documento(
            doc, args.capas, conjuntos[doc["slug"]], excluidas
        )
        documentos.append(fila)
        paginas.extend(detalle)
        eliminadas[doc["slug"]] = muestra
    sensibilidad = sensibilidad_grado(documentos, paginas)
    raiz_md = args.capas_md or args.capas.parent.parent / "md/capas"
    if not raiz_md.is_dir() and args.capas == BASE / "trabajo/ejemplo_capas_md/capas":
        raiz_md = args.capas
    raices_originales = (
        [args.originales_md]
        if args.originales_md
        else [
            BASE.parents[2] / "data/documents/bronze",
            BASE.parent / "fidelidad/trabajo/originales",
        ]
    )
    originales = [p for raiz in raices_originales for p in originales_md(raiz)]
    docs_md = evaluar_md(raiz_md, originales)
    aplicar_auditoria(documentos, auditoria)
    documentos.sort(
        key=lambda f: (
            -ORDEN_COLOR[f["veredicto_final"]],
            -(f.get("bronce_total_cer") or 0),
            f["slug"],
        )
    )
    anomalias = {
        "capas_faltantes": {
            f["slug"]: f["capas_faltantes"] for f in documentos if f["capas_faltantes"]
        },
        "paginas_sin_u": {f["slug"]: f["paginas_sin_u"] for f in documentos if f["paginas_sin_u"]},
        "cuerpos_discrepantes": {
            f.get("slug", f.get("documento")): f["gold_discrepancias_cuerpo"]
            for f in documentos + docs_md
            if f.get("gold_discrepancias_cuerpo")
        },
        "cobertura_gold_menor_99": {
            f.get("slug", f.get("documento")): f["gold_cobertura_silver"]
            for f in documentos + docs_md
            if f.get("gold_cobertura_silver") is not None
            and f["gold_cobertura_silver"] < COBERTURA_GOLD_ROJA
        },
        "md_sin_original_local": [
            f["documento"] for f in docs_md if f.get("bronce_identico_bytes") is None
        ],
        "md_capas_faltantes": {
            f["documento"]: f["capas_faltantes"] for f in docs_md if f["capas_faltantes"]
        },
        "md_doc_id_distinto_del_sha256_original": [
            f["documento"] for f in docs_md if f.get("original_sha256_coincide") == "no"
        ],
        "numero_md_distinto_de_dos": len(docs_md) if len(docs_md) != 2 else None,
    }
    resumen = {
        "completo": not anomalias["capas_faltantes"]
        and not anomalias["paginas_sin_u"]
        and len(docs_md) == 2
        and not any(f["capas_faltantes"] for f in docs_md),
        "capas": str(args.capas),
        "capas_md": str(raiz_md),
        "semilla": SEMILLA,
        "bootstrap_repeticiones": REPETICIONES,
        "calibracion": calibracion,
        "regla": {
            "e_U": ERROR_U,
            "ic95_e_U": IC_ERROR_U,
            "verde_cer_menor": LIMITE_VERDE,
            "amarillo_cer_desde": LIMITE_NO_DISTINGUIBLE,
            "rojo_cer_mayor": UMBRAL_ROJO,
            "gold_rojo_cobertura_menor": COBERTURA_GOLD_ROJA,
            "silver_campo_degradacion": "perdida_silver_otra",
            "silver_rojo_perdida_otra_mayor": PERDIDA_SILVER_OTRA_ROJA,
            "silver_amarillo_perdida_otra_mayor": PERDIDA_SILVER_OTRA_AMARILLA,
            "critico_amarillo_recall_menor": RECALL_CRITICO_AMARILLO,
        },
        "colores_total": {
            color: sum(f["veredicto_final"] == color for f in documentos) for color in COLORES
        },
        "colores_automaticos_total": {
            color: sum(f["veredicto_automatico"] == color for f in documentos) for color in COLORES
        },
        "sensibilidad_grado": sensibilidad,
        "repetibilidad": repetibilidad,
        "por_conjunto": resumen_agregado(documentos, paginas),
        "anomalias": anomalias,
        "documentos_md": docs_md,
    }
    muestra = informe_lineas_eliminadas(documentos, eliminadas)
    guardar_csv(
        BASE / "trabajo/fiabilidad/paginas.csv",
        paginas,
        campos=list(dict.fromkeys(k for f in paginas for k in f)) or ["slug", "pagina", "estado"],
    )
    guardar_csv(args.salida / "fiabilidad_por_documento.csv", documentos)
    guardar_csv(
        args.salida / "fiabilidad_md.csv",
        docs_md,
        campos=None if docs_md else ["documento", "doc_id", "referencia"],
    )
    guardar_atomico(args.salida / "resumen.json", datos=resumen)
    guardar_atomico(args.salida / "sensibilidad_grado.json", datos=sensibilidad)
    guardar_atomico(args.salida / "repetibilidad.json", datos=repetibilidad)
    guardar_atomico(args.salida / "silver_lineas_eliminadas.md", contenido=muestra)
    guardar_atomico(
        args.salida / "fiabilidad_por_documento.md", contenido=informe(documentos, docs_md, resumen)
    )
    print(
        "Informe " + ("completo" if resumen["completo"] else "parcial") + ": " + str(args.salida),
        flush=True,
    )
    print(
        json.dumps(
            {
                "total": resumen["colores_total"],
                **{k: g["colores"] for k, g in resumen["por_conjunto"].items()},
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    principal()
