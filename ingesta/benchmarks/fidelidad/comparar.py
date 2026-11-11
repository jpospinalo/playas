"""Comparación local reproducible. No importa servicios ni dependencias externas.

La normalización es común a TODAS las fuentes (también C1/C2).
Ver README.md para alcance, denominadores y limitaciones del consenso.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
FUENTES = ("S", "A", "V", "C1", "C2")
SEMILLA = 27102026
REGLAS = [
    "NFC y minúsculas; CRLF/CR se convierten a LF.",
    "Se une letra-guion ASCII-salto de línea-letra (incluido espacio horizontal).",
    "Se quitan FF y líneas completas Página/Pág./Page N [de/of N], <!-- page N --> y [[página N]].",
    "También se quitan 'página N de M' y 'page N of M' en cualquier posición (incluso junto a URL).",
    "No se quitan líneas que solo son un número, encabezados ni pies repetidos.",
    "Se quitan imágenes Markdown ![alt](ruta) y etiquetas HTML img.",
    "Se quitan # de encabezados al inicio, delimitadores ** y __ de negrita y líneas separadoras de tabla Markdown.",
    "La barra | se trata como separador de celdas y se sustituye por espacio en todas las "
    "fuentes (las transcripciones la usan como convención; también desaparece la barra "
    "literal de encabezados como 'Colombia | SUIN Juriscol').",
    "Cada racha de dígitos en superíndice (⁰-⁹, ¹²³) se convierte en un número aparte, "
    "precedido de espacio ('2008³' -> '2008 3'), para no ocultar extracciones que fusionan "
    "la llamada de nota con el número anterior ('20083'). No se aplica NFKC para no ocultar "
    "ligaduras.",
    "Se conservan enlaces, cursivas, puntuación, dígitos y tildes.",
    "Finalmente todo espacio Unicode se colapsa a un espacio y se recortan extremos.",
]
SUPERINDICES = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")


def normalizar(texto, *, fragmento=False):
    texto = unicodedata.normalize("NFC", texto).lower().replace("\r\n", "\n").replace("\r", "\n")
    texto = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: " " + m.group(0).translate(SUPERINDICES), texto)
    texto = re.sub(r"(?<=[^\W\d_])-[ \t]*\n[ \t]*(?=[^\W\d_])", "", texto)
    texto = texto.replace("\f", "\n")
    if not fragmento:
        texto = re.sub(
            r"(?im)^[ \t]*(?:página|pág\.?|page)\s+\d+(?:\s*(?:de|of|/)\s*\d+)?[ \t]*$", "", texto
        )
        texto = re.sub(
            r"(?im)^[ \t]*(?:<!--\s*page\s+\d+\s*-->|\[\[página\s+\d+\]\])[ \t]*$", "", texto
        )
        texto = re.sub(r"\b(?:página\s+\d+\s+de|page\s+\d+\s+of)\s+\d+\b", " ", texto)
    texto = re.sub(r"!\[[^\]]*\]\([^\n]*?\)|<img\b[^>]*>", "", texto)
    if not fragmento:
        texto = re.sub(
            r"(?m)^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$", "", texto
        )
    texto = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+", "", texto)
    texto = texto.replace("**", "").replace("__", "").replace("|", " ")
    return " ".join(texto.split())


def distancia(a, b):
    """Levenshtein exacto propio mediante vectores de bits (Myers), sin librerías.

    Admite cadenas o listas de palabras. Solo distancia, sin aproximaciones.
    """
    if len(a) > len(b):
        a, b = b, a
    if not a:
        return len(b)
    mascaras = {}
    for i, elemento in enumerate(a):
        mascaras[elemento] = mascaras.get(elemento, 0) | (1 << i)
    ancho = len(a)
    limite = (1 << ancho) - 1
    superior = 1 << (ancho - 1)
    positivos, negativos, total = limite, 0, ancho
    for elemento in b:
        iguales = mascaras.get(elemento, 0)
        vertical = iguales | negativos
        horizontal = (((iguales & positivos) + positivos) ^ positivos) | iguales
        hp = negativos | ~(horizontal | positivos)
        hn = positivos & horizontal
        total += bool(hp & superior) - bool(hn & superior)
        hp = (hp << 1) | 1
        hn <<= 1
        positivos = (hn | ~(vertical | hp)) & limite
        negativos = hp & vertical
    return total


def cociente(n, d):
    return n / d if d else None


def metricas(hipotesis, referencia, *, normalizados=False):
    h, r = (
        (hipotesis, referencia) if normalizados else (normalizar(hipotesis), normalizar(referencia))
    )
    hp, rp = h.split(), r.split()
    comunes = sum((Counter(hp) & Counter(rp)).values())
    dc, dp = distancia(h, r), distancia(hp, rp)
    return {
        "ediciones_caracteres": dc,
        "caracteres_ref": len(r),
        "ediciones_palabras": dp,
        "palabras_ref": len(rp),
        "palabras_hip": len(hp),
        "palabras_comunes": comunes,
        "cer": cociente(dc, len(r)),
        "wer": cociente(dp, len(rp)),
        "recuperacion": cociente(comunes, len(rp)),
        "precision": cociente(comunes, len(hp)),
    }


def alinear(ref, hip):
    """Alineación óptima de palabras, traceback compacto; empate diagonal, borrar, insertar.

    Devuelve operaciones (tipo, inicio_ref, fin_ref, inicio_hip, fin_hip).
    """
    n, m = len(ref), len(hip)
    traza = [bytearray([2] * (m + 1))]
    anterior = list(range(m + 1))
    for i, palabra in enumerate(ref, 1):
        fila = [i] + [0] * m
        decisiones = bytearray(m + 1)
        decisiones[0] = 1
        for j, otra in enumerate(hip, 1):
            diagonal = anterior[j - 1] + (palabra != otra)
            borrar, insertar = anterior[j] + 1, fila[j - 1] + 1
            valor = min(diagonal, borrar, insertar)
            fila[j] = valor
            decisiones[j] = 0 if diagonal == valor else (1 if borrar == valor else 2)
        traza.append(decisiones)
        anterior = fila
    i, j, ops = n, m, []
    while i or j:
        paso = traza[i][j]
        if paso == 0:
            ops.append(("igual" if ref[i - 1] == hip[j - 1] else "cambio", i - 1, i, j - 1, j))
            i, j = i - 1, j - 1
        elif paso == 1:
            ops.append(("borrado", i - 1, i, j, j))
            i -= 1
        else:
            ops.append(("insercion", i, i, j - 1, j))
            j -= 1
    return list(reversed(ops))


def proyectar(ops, inicio, fin):
    """Rango de hipótesis para un intervalo del objetivo, incluido inserto en borde izquierdo.

    Un segmento de longitud cero captura SOLO inserciones en esa posición.
    """
    seleccion = [
        op
        for op in ops
        if (op[1] < fin and op[2] > inicio)
        or (op[1] == op[2] and (inicio <= op[1] < fin if fin > inicio else op[1] == inicio))
    ]
    if seleccion:
        return min(op[3] for op in seleccion), max(op[4] for op in seleccion)
    pos = max((op[4] for op in ops if op[2] <= inicio), default=0)
    return pos, pos


MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
PATRONES = {
    "radicado": r"\b\d{5}\s*[-–]\s*\d{2,4}(?:\s*[-–]\s*\d{2})?\s*[-–]\s*\d{2,3}\s*[-–]\s*\d{4}\s*[-–]\s*\d{4,5}(?:\s*[-–]\s*\d{2})?\b|\b\d{21,23}\b",
    "fecha": rf"\b\d{{1,2}}\s+de\s+(?:{MESES})\s+de\s+\d{{4}}\b|\b\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}\b|\b\d{{4}}[/-]\d{{1,2}}[/-]\d{{1,2}}\b",
    "articulo": r"\b(?:artículo|art\.)\s*(?:n[.º°o]*\s*)?\d+[a-zº°]*\b",
    "ley": r"\bley\s+(?:n[.º°o]*\s*)?\d+\s+de\s+\d{4}\b",
    "decreto": r"\bdecreto\s+(?:n[.º°o]*\s*)?\d+\s+de\s+\d{4}\b",
    "numero": r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)",
}


def criticos(texto):
    texto = normalizar(texto)
    return {
        tipo: Counter(m.group() for m in re.finditer(patron, texto))
        for tipo, patron in PATRONES.items()
    }


def comparar_criticos(hipotesis, referencia):
    h, r = criticos(hipotesis), criticos(referencia)
    resultado = []
    # El multiconjunto evita que una aparición recuperada cubra dos referencias.
    for tipo in PATRONES:
        comun = h[tipo] & r[tipo]
        resultado.append(
            {
                "categoria": tipo,
                "total_ref": sum(r[tipo].values()),
                "recuperados": sum(comun.values()),
                "recall": cociente(sum(comun.values()), sum(r[tipo].values())),
                "faltantes": list((r[tipo] - h[tipo]).elements()),
                "extras_o_cambiados": list((h[tipo] - r[tipo]).elements()),
            }
        )
    return resultado


def bootstrap(filas, repeticiones=2000, semilla=SEMILLA):
    """Remuestreo de páginas con reemplazo, cociente de sumas (micro), percentiles.

    Una fila por página; se mantienen juntos numerador y denominador.
    """
    rng = random.Random(semilla)
    resultados = {"cer": [], "wer": []}
    if not filas:
        return {k: None for k in resultados}
    for _ in range(repeticiones):
        muestra = rng.choices(filas, k=len(filas))
        for nombre, num, den in (
            ("cer", "ediciones_caracteres", "caracteres_ref"),
            ("wer", "ediciones_palabras", "palabras_ref"),
        ):
            valor = cociente(sum(f[num] for f in muestra), sum(f[den] for f in muestra))
            if valor is not None:
                resultados[nombre].append(valor)

    def percentil(valores, p):
        posicion = (len(valores) - 1) * p
        bajo = math.floor(posicion)
        return valores[bajo] + (valores[math.ceil(posicion)] - valores[bajo]) * (posicion - bajo)

    return {
        nombre: [percentil(sorted(vals), 0.025), percentil(sorted(vals), 0.975)] if vals else None
        for nombre, vals in resultados.items()
    }


def agregar(filas):
    campos = (
        "ediciones_caracteres",
        "caracteres_ref",
        "ediciones_palabras",
        "palabras_ref",
        "palabras_hip",
        "palabras_comunes",
    )
    suma = {k: sum(f[k] for f in filas) for k in campos}
    return {
        "paginas": len(filas),
        **suma,
        "cer": cociente(suma["ediciones_caracteres"], suma["caracteres_ref"]),
        "wer": cociente(suma["ediciones_palabras"], suma["palabras_ref"]),
        "recuperacion": cociente(suma["palabras_comunes"], suma["palabras_ref"]),
        "precision": cociente(suma["palabras_comunes"], suma["palabras_hip"]),
        "ic95_bootstrap_paginas": bootstrap(filas),
    }


def consenso(textos, objetivo):
    """Segmentos de desacuerdo por unión de intervalos superpuestos del objetivo.

    No se usa difflib: todas las proyecciones provienen de Levenshtein óptimo.
    Los insertos finales son intervalos vacíos (aportan cero caracteres al %).
    """
    palabras = {k: normalizar(v).split() for k, v in textos.items()}
    ref = palabras[objetivo]
    alineaciones = {k: alinear(ref, v) for k, v in palabras.items() if k != objetivo}
    intervalos = sorted(
        {(i, j) for ops in alineaciones.values() for t, i, j, _, _ in ops if t != "igual"}
    )
    unidos = []
    for inicio, fin in intervalos:
        if unidos and (inicio < unidos[-1][1] or inicio == unidos[-1][0]):
            unidos[-1][1] = max(fin, unidos[-1][1])
        else:
            unidos.append([inicio, fin])
    segmentos = []
    posiciones = list(re.finditer(r"\S+", normalizar(textos[objetivo])))
    for inicio, fin in unidos:
        rangos = {objetivo: [inicio, fin]}
        for k, ops in alineaciones.items():
            rangos[k] = list(proyectar(ops, inicio, fin))
        fragmentos = {k: " ".join(palabras[k][a:b]) for k, (a, b) in rangos.items()}
        grupos = defaultdict(list)
        for fuente, fragmento in fragmentos.items():
            if fuente != objetivo:
                grupos[fragmento].append(fuente)
        apoyos = grupos.get(fragmentos[objetivo], [])
        contra = [
            v
            for k, v in grupos.items()
            if k != fragmentos[objetivo] and len(v) >= 2 and (k or {"C1", "C2"}.intersection(v))
        ]
        clase = (
            "en_disputa"
            if contra and apoyos
            else "contradicho_por_consenso"
            if contra
            else "respaldado"
            if apoyos
            else "indeterminado"
        )
        caracteres = posiciones[fin - 1].end() - posiciones[inicio].start() if fin > inicio else 0
        segmentos.append(
            {
                "objetivo": objetivo,
                "inicio": inicio,
                "fin": fin,
                "rangos": rangos,
                "textos": fragmentos,
                "clase": clase,
                "coinciden_objetivo": apoyos,
                "n_coinciden_objetivo": len(apoyos),
                "grupos_contra": contra,
                "n_max_contra": max(map(len, contra), default=0),
                "caracteres_objetivo": caracteres,
                "critico": any(
                    any(x.values()) for x in criticos(" ".join(fragmentos.values())).values()
                ),
            }
        )
    return segmentos


def controles(textos, objetivo="S", ancho=12):
    if objetivo not in textos or len(textos) < 2:
        return []
    palabras = {k: normalizar(v).split() for k, v in textos.items()}
    ref = palabras[objetivo]
    alineaciones = {k: alinear(ref, v) for k, v in palabras.items() if k != objetivo}
    salida = []
    # Ventanas disjuntas para que el muestreo no repita un mismo control.
    for inicio in range(0, len(ref), ancho):
        fin = min(inicio + ancho, len(ref))
        if fin - inicio < 4:
            continue
        rangos = {
            objetivo: [inicio, fin],
            **{k: list(proyectar(v, inicio, fin)) for k, v in alineaciones.items()},
        }
        fragmentos = {k: " ".join(palabras[k][a:b]) for k, (a, b) in rangos.items()}
        if len(set(fragmentos.values())) == 1:
            salida.append(
                {
                    "objetivo": objetivo,
                    "inicio": inicio,
                    "fin": fin,
                    "rangos": rangos,
                    "textos": fragmentos,
                    "clase": "control",
                    "critico": False,
                }
            )
    return salida


def prioridad(segmento):
    """Niveles de revisión; S prima dentro del nivel crítico."""
    if segmento["objetivo"] == "S":
        if segmento["clase"] in ("contradicho_por_consenso", "en_disputa", "indeterminado"):
            return "a"
        if any(
            fuente in segmento["textos"] and segmento["textos"][fuente] != segmento["textos"]["S"]
            for fuente in ("C1", "C2")
        ):
            return "b"
    if segmento["critico"]:
        return "c"
    if segmento["objetivo"] == "V" and segmento["clase"] in (
        "contradicho_por_consenso",
        "en_disputa",
    ):
        return "d"
    return "e"


def orden_revision(segmento):
    return (
        segmento["prioridad"],
        segmento["objetivo"] != "S" if segmento["prioridad"] == "c" else False,
        segmento["documento"],
        segmento["pagina"],
        segmento["inicio"],
        segmento["objetivo"],
    )


def solapan_segmentos(primero, segundo):
    if (primero["documento"], primero["pagina"]) != (segundo["documento"], segundo["pagina"]):
        return False
    return any(
        max(inicio, a) < min(fin, b) or inicio == fin == a == b
        for fuente, (inicio, fin) in primero["rangos"].items()
        if fuente in segundo["rangos"]
        for a, b in [segundo["rangos"][fuente]]
    )


def agrupar_desacuerdos(segmentos, textos_paginas):
    """Agrupa vecinos a <=3 palabras y fusiona solapes en cualquier fuente.

    Se conservan todas las lecturas, incluidos los huecos entre diferencias.
    La clase/objetivo de la fila son los del miembro de mayor prioridad.
    El JSON mantiene los segmentos originales para los porcentajes y cobertura.
    """

    def combinar(primero, segundo):
        representante = min((primero, segundo), key=orden_revision)
        rangos = {
            fuente: [min(primero["rangos"][fuente][0], a), max(primero["rangos"][fuente][1], b)]
            for fuente, (a, b) in segundo["rangos"].items()
        }
        palabras = textos_paginas[(representante["documento"], representante["pagina"])]
        objetivo = representante["objetivo"]
        return {
            **representante,
            "inicio": rangos[objetivo][0],
            "fin": rangos[objetivo][1],
            "rangos": rangos,
            "textos": {k: " ".join(palabras[k][a:b]) for k, (a, b) in rangos.items()},
            "critico": primero["critico"] or segundo["critico"],
        }

    vecinos = []
    for segmento in sorted(
        segmentos, key=lambda s: (s["documento"], s["pagina"], s["objetivo"], s["inicio"])
    ):
        segmento = {**segmento, "prioridad": prioridad(segmento)}
        if (
            vecinos
            and all(vecinos[-1][k] == segmento[k] for k in ("documento", "pagina", "objetivo"))
            and segmento["inicio"] - vecinos[-1]["fin"] <= 3
        ):
            vecinos[-1] = combinar(vecinos[-1], segmento)
        else:
            vecinos.append(segmento)
    unidos = []
    for segmento in vecinos:
        # Una fusión puede conectar otros rangos ya recorridos: cerrar transitivamente.
        while True:
            indice = next(
                (i for i, otro in enumerate(unidos) if solapan_segmentos(segmento, otro)), None
            )
            if indice is None:
                break
            segmento = combinar(segmento, unidos.pop(indice))
        unidos.append(segmento)
    return sorted(unidos, key=orden_revision)


def cubierto(segmento, elegidos):
    return any(
        (segmento["documento"], segmento["pagina"]) == (fila["documento"], fila["pagina"])
        and all(
            fuente in fila["rangos"]
            and fila["rangos"][fuente][0] <= inicio
            and fin <= fila["rangos"][fuente][1]
            for fuente, (inicio, fin) in segmento["rangos"].items()
        )
        for fila in elegidos
    )


def inyectar(texto, tasa, semilla=SEMILLA):
    texto = normalizar(texto)
    rng = random.Random(semilla)
    posiciones = rng.sample(range(len(texto)), round(len(texto) * tasa))
    copia = list(texto)
    # U+FFFD nunca aparece en las páginas limpias y no altera espacios/normalización.
    if "\ufffd" in texto:
        raise ValueError("La página limpia contiene el símbolo reservado para calibración")
    for i in posiciones:
        copia[i] = "\ufffd"
    return "".join(copia), len(posiciones)


def calibrar(paginas):
    salida = []
    for identificador, texto in paginas:
        limpio = normalizar(texto)
        if not limpio:
            continue
        for tasa in (0.005, 0.01, 0.03):
            alterado, n = inyectar(limpio, tasa)
            obtenido = metricas(alterado, limpio)["cer"]
            esperado = n / len(limpio)
            # Al sustituir espacios, el colapso puede quitar uno en un extremo.
            tolerancia = 2 / len(limpio)
            salida.append(
                {
                    "pagina": identificador,
                    "tasa": tasa,
                    "sustituciones": n,
                    "caracteres_ref": len(limpio),
                    "cer": obtenido,
                    "esperado": esperado,
                    "tolerancia": tolerancia,
                    "correcto": abs(obtenido - esperado) <= tolerancia,
                }
            )
        sin_numeros = re.sub(r"\d", "", limpio)
        filas = comparar_criticos(sin_numeros, limpio)
        presentes = [f for f in filas if f["total_ref"]]
        salida.append(
            {
                "pagina": identificador,
                "prueba": "borrado_numeros",
                "ocurrencias_ref": sum(f["total_ref"] for f in presentes),
                "ocurrencias_recuperadas": sum(f["recuperados"] for f in presentes),
                "recall_esperado": 0 if presentes else None,
                "correcto": all(f["recall"] == 0 for f in presentes),
            }
        )
    agregados = []
    for tasa in (0.005, 0.01, 0.03):
        grupo = [f for f in salida if f.get("tasa") == tasa]
        den = sum(f["caracteres_ref"] for f in grupo)
        agregados.append(
            {
                "tasa_solicitada": tasa,
                "paginas": len(grupo),
                "caracteres_ref": den,
                "sustituciones": sum(f["sustituciones"] for f in grupo),
                "cer_micro": cociente(sum(f["cer"] * f["caracteres_ref"] for f in grupo), den),
                "tolerancia_redondeo_micro": cociente(len(grupo), den),
            }
        )
    return {
        "semilla": SEMILLA,
        "pruebas": salida,
        "resumen_sustituciones": agregados,
        "correcto": bool(salida) and all(f["correcto"] for f in salida),
    }


def guardar_json(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(contenido, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def guardar_csv(ruta, filas, campos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def cargar_pagina(base, fuente, doc, pagina):
    # No se listan directorios: únicamente se accede a la fuente solicitada por CLI.
    ruta = base / "fuentes" / fuente / doc / f"{pagina:03d}.txt"
    metadatos = base / "fuentes" / fuente / "paginas.json"
    if metadatos.is_file():
        for fila in json.loads(metadatos.read_text(encoding="utf-8")).get("paginas", []):
            if fila["documento"] == doc and fila["pagina"] == pagina:
                if fila["estado"] in ("solo_documento", "PENDIENTE", "fuente ausente", "no aplica"):
                    return None, fila["estado"]
    if not ruta.is_file():
        return None, "fuente ausente"
    texto = ruta.read_text(encoding="utf-8-sig")
    return texto, "disponible"


_MAPAS_COORDENADAS = {}


def crear_recorte(base, documento, pagina, segmento, destino):
    """Usa coordenadas PyMuPDF o TSV del MISMO Tesseract; fallback explícito."""
    import fitz

    coordenadas = base / "trabajo" / "coordenadas" / documento["id"] / f"{pagina:03d}.json"
    palabras = json.loads(coordenadas.read_text(encoding="utf-8")) if coordenadas.exists() else []
    fuente = "S" if "S" in segmento["rangos"] else segmento["objetivo"]
    ruta_texto = base / "fuentes" / fuente / documento["id"] / f"{pagina:03d}.txt"
    texto = normalizar(ruta_texto.read_text(encoding="utf-8")) if ruta_texto.exists() else ""
    inicio, fin = segmento["rangos"].get(fuente, (0, 0))
    tokens = texto.split()
    clave = (str(base), documento["id"], pagina, fuente)
    lista, cajas = [], []
    for palabra in palabras:
        for token in normalizar(palabra["texto"]).split():
            lista.append(token)
            cajas.append(palabra)
    if clave not in _MAPAS_COORDENADAS:
        _MAPAS_COORDENADAS[clave] = alinear(tokens, lista)
    ops = _MAPAS_COORDENADAS[clave]
    # Un borrado de la hipótesis se localiza mediante dos palabras a cada lado.
    if inicio == fin:
        inicio, fin = max(0, inicio - 2), min(len(tokens), fin + 2)
    a, b = proyectar(ops, inicio, fin)
    iguales = sum(op[0] == "igual" and inicio <= op[1] < fin for op in ops)
    encontrados = cajas[a:b] if fin > inicio and iguales / (fin - inicio) >= 0.7 else []
    with fitz.open(base / "trabajo" / "originales" / documento["archivo"]) as pdf:
        hoja = pdf[pagina - 1]
        caja = hoja.rect
        modo = "pagina_completa: segmento no localizado"
        if encontrados:
            ymin = min(p["bbox"][1] for p in encontrados) - 35
            ymax = max(p["bbox"][3] for p in encontrados) + 35
            # Ancho completo para conservar contexto y evitar cortar columnas vecinas.
            caja = fitz.Rect(0, max(0, ymin), hoja.rect.width, min(hoja.rect.height, ymax))
            modo = "recorte: coordenadas " + (
                "TSV Tesseract" if documento["tipo_pagina"] == "ocr" else "PyMuPDF"
            )
        destino.parent.mkdir(parents=True, exist_ok=True)
        hoja.get_pixmap(matrix=fitz.Matrix(2, 2), clip=caja, alpha=False).save(destino)
    return modo


def ejecutar(base, fuentes, recortes=True):
    seleccion = json.loads((base / "seleccion.json").read_text(encoding="utf-8"))
    destino = base / "resultados"
    filas, criticas, segmentos, candidatos_control, disponibilidad = [], [], [], [], []
    resumen_consenso = []
    textos_paginas = {}
    for documento in seleccion["documentos"]:
        doc = documento["id"]
        for pagina in documento["paginas"]:
            contexto = {"documento": doc, "pagina": pagina, "tipo_pagina": documento["tipo_pagina"]}
            textos = {}
            for fuente in fuentes:
                texto, estado = cargar_pagina(base, fuente, doc, pagina)
                disponibilidad.append({**contexto, "fuente": fuente, "estado": estado})
                if texto is not None:
                    textos[fuente] = texto
            textos_paginas[(doc, pagina)] = {k: normalizar(v).split() for k, v in textos.items()}
            # Pares ordenados: ambas direcciones, referencia declarada en cada fila.
            for hip, texto in textos.items():
                for ref, referencia in textos.items():
                    if hip == ref:
                        continue
                    filas.append(
                        {
                            **contexto,
                            "fuente": hip,
                            "referencia": ref,
                            **metricas(texto, referencia),
                        }
                    )
                    if hip == "S":
                        for critica in comparar_criticos(texto, referencia):
                            criticas.append(
                                {**contexto, "fuente": hip, "referencia": ref, **critica}
                            )
            for objetivo in ("S", "V"):
                if objetivo not in textos:
                    continue
                partes = consenso(textos, objetivo)
                total = len(normalizar(textos[objetivo]))
                malos = sum(
                    p["caracteres_objetivo"]
                    for p in partes
                    if p["clase"] == "contradicho_por_consenso"
                )
                disputados = sum(
                    p["caracteres_objetivo"] for p in partes if p["clase"] == "en_disputa"
                )
                resumen_consenso.append(
                    {
                        **contexto,
                        "objetivo": objetivo,
                        "caracteres": total,
                        "caracteres_contradichos": malos,
                        "caracteres_en_disputa": disputados,
                        "porcentaje_PROVISIONAL": 100 * malos / total if total else None,
                        "porcentaje_con_disputa_PROVISIONAL": (
                            100 * (malos + disputados) / total if total else None
                        ),
                        "fuentes_comparadas": [k for k in textos if k != objetivo],
                        "segmentos": len(partes),
                    }
                )
                segmentos.extend({**contexto, **p} for p in partes)
            if set(textos) == set(fuentes):
                candidatos_control.extend({**contexto, **p} for p in controles(textos))
    grupos = defaultdict(list)
    for fila in filas:
        # Por documento Y global; siempre separado por digital/OCR.
        for doc in (fila["documento"], "TODOS"):
            grupos[(doc, fila["tipo_pagina"], fila["fuente"], fila["referencia"])].append(fila)
    resumen = [
        {"documento": doc, "tipo_pagina": tipo, "fuente": hip, "referencia": ref, **agregar(grupo)}
        for (doc, tipo, hip, ref), grupo in sorted(grupos.items())
    ]
    guardar_csv(
        destino / "metricas_paginas.csv",
        filas,
        [
            "documento",
            "pagina",
            "tipo_pagina",
            "fuente",
            "referencia",
            "ediciones_caracteres",
            "caracteres_ref",
            "ediciones_palabras",
            "palabras_ref",
            "palabras_hip",
            "palabras_comunes",
            "cer",
            "wer",
            "recuperacion",
            "precision",
        ],
    )
    for critica in criticas:
        for campo in ("faltantes", "extras_o_cambiados"):
            critica[campo] = json.dumps(critica[campo], ensure_ascii=False)
    guardar_csv(
        destino / "criticos.csv",
        criticas,
        [
            "documento",
            "pagina",
            "tipo_pagina",
            "fuente",
            "referencia",
            "categoria",
            "total_ref",
            "recuperados",
            "recall",
            "faltantes",
            "extras_o_cambiados",
        ],
    )
    candidatos = agrupar_desacuerdos(segmentos, textos_paginas)
    desacuerdos = candidatos[:150]
    # Los controles se filtran y se reservan contra TODAS las fuentes, también
    # entre sí: con texto repetido una proyección puede reutilizar palabras.
    rng = random.Random(SEMILLA)
    rng.shuffle(candidatos_control)
    controles_elegidos = []
    for control in candidatos_control:
        if any(solapan_segmentos(control, ocupado) for ocupado in desacuerdos + controles_elegidos):
            continue
        controles_elegidos.append({**control, "prioridad": "control"})
        if len(controles_elegidos) == 20:
            break
    elegidos = [(s, "desacuerdo") for s in desacuerdos] + [
        (s, "control") for s in controles_elegidos
    ]
    cobertura_s = {}
    for clase in ("contradicho_por_consenso", "en_disputa", "indeterminado"):
        originales = [s for s in segmentos if s["objetivo"] == "S" and s["clase"] == clase]
        incluidos = sum(cubierto(s, desacuerdos) for s in originales)
        cobertura_s[clase] = {"total": len(originales), "incluidos": incluidos}
    prioritarios = [s for s in candidatos if s["prioridad"] in ("a", "b")]
    seleccion_revision = {
        "filas_por_prioridad": dict(Counter(s["prioridad"] for s in desacuerdos)),
        "candidatos_a_b_agrupados": len(prioritarios),
        "limite_a_b_superado": len(prioritarios) > 150,
        "filas_a_b_fuera": max(0, len(prioritarios) - 150),
        "cobertura_segmentos_S": cobertura_s,
        "todos_S_contradichos_en_disputa_incluidos": all(
            cobertura_s[clase]["incluidos"] == cobertura_s[clase]["total"]
            for clase in ("contradicho_por_consenso", "en_disputa")
        ),
    }
    revision = []
    documentos = {d["id"]: d for d in seleccion["documentos"]}
    for numero, (segmento, tipo) in enumerate(elegidos, 1):
        identificador = f"r{numero:03d}"
        ruta = base / "imagenes" / "recortes" / f"{identificador}.png"
        localizacion = (
            crear_recorte(
                base, documentos[segmento["documento"]], segmento["pagina"], segmento, ruta
            )
            if recortes
            else "no generado"
        )
        revision.append(
            {
                "id": identificador,
                **{k: segmento[k] for k in ("documento", "pagina", "tipo_pagina")},
                "tipo": tipo,
                "clase": segmento["clase"],
                "prioridad": segmento["prioridad"],
                **{f"texto_{k}": segmento["textos"].get(k, "") for k in FUENTES},
                "fuentes_presentes": ",".join(segmento["textos"]),
                "objetivo": segmento["objetivo"],
                "rangos": json.dumps(segmento["rangos"], sort_keys=True),
                "recorte": ruta.relative_to(base).as_posix() if recortes else "",
                "localizacion": localizacion,
                "quien_acierta": "",
                "nota": "",
            }
        )
    guardar_csv(
        destino / "desacuerdos.csv",
        revision,
        [
            "id",
            "documento",
            "pagina",
            "tipo_pagina",
            "tipo",
            "texto_S",
            "texto_A",
            "texto_V",
            "texto_C1",
            "texto_C2",
            "recorte",
            "quien_acierta",
            "nota",
            "fuentes_presentes",
            "objetivo",
            "rangos",
            "localizacion",
            "clase",
            "prioridad",
        ],
    )
    totales_consenso = []
    for objetivo in ("S", "V"):
        for tipo in ("digital", "ocr", "TODAS"):
            grupo = [
                f
                for f in resumen_consenso
                if f["objetivo"] == objetivo and (tipo == "TODAS" or f["tipo_pagina"] == tipo)
            ]
            den = sum(f["caracteres"] for f in grupo)
            num = sum(f["caracteres_contradichos"] for f in grupo)
            disputa = sum(f["caracteres_en_disputa"] for f in grupo)
            totales_consenso.append(
                {
                    "objetivo": objetivo,
                    "tipo_pagina": tipo,
                    "paginas": len(grupo),
                    "caracteres": den,
                    "caracteres_contradichos": num,
                    "caracteres_en_disputa": disputa,
                    "porcentaje_con_disputa_PROVISIONAL": (
                        100 * (num + disputa) / den if den else None
                    ),
                    "porcentaje_PROVISIONAL": 100 * num / den if den else None,
                }
            )
    guardar_json(
        destino / "consenso.json",
        {
            "advertencia": "PROVISIONAL: acuerdo de extractores, no verdad verificada. A y S pueden compartir errores. El apoyo simultáneo a un consenso contrario se clasifica en_disputa. Dos vacíos sin C1/C2 no forman consenso contrario.",
            "resumen": totales_consenso,
            "paginas": resumen_consenso,
            "segmentos": segmentos,
        },
    )
    guardar_json(
        destino / "metricas_resumen.json",
        {
            "fuentes_solicitadas": fuentes,
            "normalizacion": REGLAS,
            "semilla": SEMILLA,
            "bootstrap_remuestreos": 2000,
            "disponibilidad": disponibilidad,
            "resumen": resumen,
            "revision": {
                **seleccion_revision,
                "desacuerdos": sum(t == "desacuerdo" for _, t in elegidos),
                "controles": sum(t == "control" for _, t in elegidos),
                "coincidencia_controles": "Todas las fuentes solicitadas deben estar presentes y coincidir; si no hay suficientes ventanas se informa un conteo menor de 20",
            },
        },
    )
    return {
        **seleccion_revision,
        "filas_metricas": len(filas),
        "filas_criticos": len(criticas),
        "segmentos_consenso": len(segmentos),
        "desacuerdos": sum(t == "desacuerdo" for _, t in elegidos),
        "controles": sum(t == "control" for _, t in elegidos),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument("--fuentes", nargs="+", choices=FUENTES, default=list(FUENTES))
    parser.add_argument("--calibrar", action="store_true")
    parser.add_argument("--sin-recortes", action="store_true")
    args = parser.parse_args()
    if args.calibrar:
        seleccion = json.loads((args.base / "seleccion.json").read_text(encoding="utf-8"))
        paginas = []
        # Calibración solo con digitales A, nunca lee C1/C2.
        for doc in seleccion["documentos"]:
            if doc["tipo_pagina"] == "digital":
                for pagina in doc["paginas"]:
                    texto, _ = cargar_pagina(args.base, "A", doc["id"], pagina)
                    if texto:
                        paginas.append((f"{doc['id']}/{pagina:03d}", texto))
        resultado = calibrar(paginas)
        guardar_json(args.base / "resultados" / "calibracion.json", resultado)
        print(
            json.dumps(
                {
                    "calibracion_correcta": resultado["correcto"],
                    "pruebas": len(resultado["pruebas"]),
                }
            )
        )
        if not resultado["correcto"]:
            raise SystemExit(1)
    else:
        print(
            json.dumps(
                ejecutar(args.base, list(dict.fromkeys(args.fuentes)), not args.sin_recortes)
            )
        )


if __name__ == "__main__":
    main()
