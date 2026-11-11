"""Señales baratas de calidad para decidir si un documento necesita revisión.

No corrigen nada: marcan. Se usan en la política del intake.

- Secuencia de artículos y parágrafos (defecto 2): numeración no monótona,
  duplicada o con un símbolo pegado al número («Artículo 13%», «Parágrafo 4 %»),
  típico de un «°» mal leído por el OCR.
- Imágenes grandes en páginas digitales (defecto 3): texto que puede estar dentro
  de una imagen (tablas escaneadas incrustadas) y que la capa digital no tiene.
- Caída de texto (defecto 4): páginas con mucho menos texto que el resto.
"""

from __future__ import annotations

import re
import statistics

# Encabezado de artículo al inicio de línea: «ARTÍCULO 2°.», «Artículo 2.2.3.2.5 Déficit».
_ARTICULO = re.compile(
    r"(?im)^[ \t]*(?P<etiqueta>ART[ÍI]CULO|Art[íi]culo|PAR[ÁA]GRAFO|Par[áa]grafo)[ \t]+"
    r"(?P<numero>\d{1,4}(?:\.\d{1,4})*)[ \t]*(?P<marca>[º°o]|[%*”\"?!]|)"
    r"(?=[ \t]*[.:\-–—]|[ \t]+[A-ZÁÉÍÓÚÑ(])"
)
# Un símbolo pegado al número de un encabezado es casi siempre un «°» mal leído.
_MARCA_SOSPECHOSA = set('%*”"?!')


def _clave(numero):
    return tuple(int(p) for p in numero.split("."))


def secuencia_articulos(texto, paginas_ocr=None):
    """Anomalías en la numeración de artículos y parágrafos del texto.

    Ignora lo anterior al primer tramo de tres artículos consecutivos (los
    considerandos citan artículos de otras normas). Los saltos se informan
    aparte porque un extracto puede omitir artículos legítimamente. Con
    ``paginas_ocr`` (texto con páginas separadas por «\\n\\f\\n»), los símbolos
    sospechosos solo cuentan en esas páginas: es allí donde el OCR confunde «°».
    """
    articulos, parrafos, ejemplos = [], [], []
    simbolos = 0
    limites, posicion = [], 0
    for pagina in texto.split("\n\f\n"):
        limites.append(posicion + len(pagina))
        posicion += len(pagina) + 3

    def pagina_de(offset):
        return next(i for i, fin in enumerate(limites, 1) if offset <= fin)

    for m in _ARTICULO.finditer(texto):
        es_articulo = m["etiqueta"][:3].casefold() == "art"
        if m["marca"] in _MARCA_SOSPECHOSA and (
            paginas_ocr is None or pagina_de(m.start()) in paginas_ocr
        ):
            simbolos += 1
            if len(ejemplos) < 5:
                ejemplos.append(" ".join(m.group().split()))
        if es_articulo:
            articulos.append((_clave(m["numero"]), m.start()))
            parrafos.append([])
        elif parrafos:
            parrafos[-1].append(_clave(m["numero"]))
    claves = [c for c, _ in articulos]
    inicio = next(
        (
            i
            for i in range(len(claves) - 2)
            if len(claves[i]) == 1
            and claves[i + 1] == (claves[i][0] + 1,)
            and claves[i + 2] == (claves[i][0] + 2,)
        ),
        None,
    )
    if inicio is None:
        # Numeración con puntos (decretos únicos) o muy corta: se evalúa entera.
        inicio = 0
    principal = claves[inicio:]
    descensos = sum(1 for a, b in zip(principal, principal[1:], strict=False) if b < a)
    duplicados = len(principal) - len(set(principal))
    saltos = sum(
        1
        for a, b in zip(principal, principal[1:], strict=False)
        if len(a) == len(b) == 1 and b[0] - a[0] > 1
    )
    parrafos_anomalos = sum(
        1 for grupo in parrafos for a, b in zip(grupo, grupo[1:], strict=False) if b <= a
    )
    return {
        "articulos": len(principal),
        "descensos": descensos,
        "duplicados": duplicados,
        "saltos": saltos,
        "paragrafos_no_monotonos": parrafos_anomalos,
        "simbolos_sospechosos": simbolos,
        "anomalias": descensos + duplicados + parrafos_anomalos + simbolos,
        "ejemplos_simbolos": ejemplos,
    }


def caida_texto(caracteres_por_pagina, *, umbral=0.35):
    """Páginas interiores con menos del ``umbral`` de la mediana del documento.

    Se excluyen la primera y la última página (portadas y finales cortos) y las
    páginas vacías se cuentan aparte, porque una página en blanco no es pérdida.
    """
    interiores = list(enumerate(caracteres_por_pagina, 1))[1:-1]
    con_texto = [c for _, c in interiores if c > 0]
    if len(con_texto) < 3:
        return {"paginas": [], "mediana": None, "vacias": []}
    mediana = statistics.median(con_texto)
    return {
        "paginas": [p for p, c in interiores if 0 < c < umbral * mediana],
        "mediana": mediana,
        "vacias": [p for p, c in interiores if c == 0],
    }


def imagenes_en_paginas_digitales(pdf, paginas_ocr=(), *, area_minima=0.20):
    """Fracción del área de cada página digital cubierta por imágenes.

    ``pdf`` es un documento abierto con PyMuPDF. Devuelve las páginas digitales
    cuya área de imágenes supera ``area_minima`` con su fracción y caracteres.
    Una página OCR no cuenta: allí la imagen ES el texto y pasa por Tesseract.
    ``pagina_completa`` marca una imagen de casi toda la página con capa de texto
    (escaneo con OCR incrustado), que es otro caso distinto de una tabla-imagen.
    """
    marcadas = []
    for indice, pagina in enumerate(pdf, 1):
        if indice in paginas_ocr:
            continue
        area_pagina = abs(pagina.rect) or 1.0
        cajas = [info["bbox"] for info in pagina.get_image_info()]
        cubierta = 0.0
        for caja in cajas:
            x0, y0, x1, y1 = caja
            # Recorta a la página: una imagen puede sobresalir del cuadro visible.
            x0, y0 = max(x0, pagina.rect.x0), max(y0, pagina.rect.y0)
            x1, y1 = min(x1, pagina.rect.x1), min(y1, pagina.rect.y1)
            if x1 > x0 and y1 > y0:
                cubierta += (x1 - x0) * (y1 - y0)
        fraccion = min(1.0, cubierta / area_pagina)
        if fraccion >= area_minima:
            caracteres = len(re.sub(r"\s", "", pagina.get_text("text")))
            marcadas.append(
                {
                    "pagina": indice,
                    "fraccion_imagen": fraccion,
                    "caracteres": caracteres,
                    "pagina_completa": fraccion >= 0.9,
                }
            )
    return marcadas


def tablas_imagen_sospechosas(marcadas, *, fraccion_minima=0.25, caracteres_maximos=1100):
    """Páginas digitales con imágenes grandes y poco texto (posible tabla-imagen)."""
    return [
        m["pagina"]
        for m in marcadas
        if not m["pagina_completa"]
        and m["fraccion_imagen"] >= fraccion_minima
        and m["caracteres"] <= caracteres_maximos
    ]


_JURIDICO = re.compile(
    r"art[íi]culo|\bart\.|par[áa]grafo|considerando|resuelve|decreta|cap[íi]tulo|t[íi]tulo|"
    r"numeral|literal",
    re.I,
)


def _margenes(lineas):
    llenas = [i for i, linea in enumerate(lineas) if linea.strip()]
    return set(llenas[:3]) | set(llenas[-3:])


def _clave_linea(linea):
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", linea.casefold())).strip()


def mobiliario_verificado(paginas):
    """Claves de líneas que son mobiliario por un criterio independiente del limpiador.

    Una clave (dígitos → #) cuenta si aparece en los márgenes (3 primeras o 3 últimas
    líneas no vacías) de ≥ 3 páginas y del ≥ 30 % de ellas, no contiene marcadores
    jurídicos y sus apariciones son idénticas o solo cambia un número que sigue la
    paginación (folio). Líneas que solo difieren en importes o plazos NO cuentan.
    """
    apariciones = {}
    for numero, texto in enumerate(paginas, 1):
        lineas = texto.splitlines()
        vistas = set()
        for i in _margenes(lineas):
            clave = _clave_linea(lineas[i])
            if clave and clave not in vistas and not _JURIDICO.search(lineas[i]):
                vistas.add(clave)
                apariciones.setdefault(clave, []).append((numero, " ".join(lineas[i].split())))
    verificadas = set()
    for clave, lista in apariciones.items():
        if len(lista) < 3 or len(lista) / max(1, len(paginas)) < 0.30:
            continue
        textos = {t for _, t in lista}
        if len(textos) == 1:
            verificadas.add(clave)
            continue
        numeros = [re.findall(r"\d+", t) for _, t in lista]
        if len({len(n) for n in numeros}) != 1:
            continue
        varian = [j for j in range(len(numeros[0])) if len({n[j] for n in numeros}) > 1]
        if len(varian) == 1:
            desplazamientos = {
                int(n[varian[0]]) - p for (p, _), n in zip(lista, numeros, strict=True)
            }
            if len(desplazamientos) == 1:
                verificadas.add(clave)
    return verificadas


def perdida_bronce_silver(bronce, offset_map):
    """Fracción de caracteres no blancos del bronce que silver elimina fuera del mobiliario.

    Los tramos eliminados son el complemento de ``offset_map`` (source_start/end).
    Se descuentan solo las líneas de mobiliario verificado (ver mobiliario_verificado).
    """
    paginas = bronce.split("\n\f\n")
    claves = mobiliario_verificado(paginas)
    cubierto = bytearray(len(bronce))
    for tramo in offset_map:
        inicio, fin = max(0, tramo["source_start"]), min(len(bronce), tramo["source_end"])
        cubierto[inicio:fin] = b"\1" * max(0, fin - inicio)
    total = perdidos = 0
    posicion = 0
    for texto in paginas:
        for linea in texto.splitlines(keepends=True):
            fin = posicion + len(linea)
            utiles = sum(1 for c in linea if not c.isspace())
            total += utiles
            if utiles and _clave_linea(linea) not in claves:
                perdidos += sum(
                    1 for j, c in enumerate(linea, posicion) if not c.isspace() and not cubierto[j]
                )
            posicion = fin
        posicion += 3  # separador «\n\f\n»
    return perdidos / total if total else 0.0
