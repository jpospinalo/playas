"""Métricas locales compartidas por las fases 1 y 3; solo biblioteca estándar.

Todas las fuentes pasan por la misma normalización. No se considera ninguna
extracción automática como verdad. Los denominadores vacíos se expresan con None.
"""

from __future__ import annotations

import math
import random
import re
import unicodedata
from collections import Counter, defaultdict
from html import unescape
from html.parser import HTMLParser

SEMILLA = 27102026
REPETICIONES = 2000
SUPERINDICES = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
MESES = "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre"
PATRONES = {
    "numero": r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)",
    "fecha": rf"\b\d{{1,2}}\s+de\s+(?:{MESES})\s+de\s+\d{{4}}\b|\b\d{{1,2}}[/.\-]\d{{1,2}}[/.\-]\d{{2,4}}\b|\b\d{{4}}[/-]\d{{1,2}}[/-]\d{{1,2}}\b",
    "radicado": r"\b\d{2,5}(?:\s*[-–]\s*\d{2,5}){3,7}\b|\b\d{21,23}\b",
    "articulo": r"\b(?:artículo|art\.)\s*(?:n[.º°o]*\s*)?\d+[a-zº°]*\b",
    "ley": r"\bley\s+(?:n[.º°o]*\s*)?\d+\s+de\s+\d{4}\b",
    "decreto": r"\bdecreto\s+(?:n[.º°o]*\s*)?\d+\s+de\s+\d{4}\b",
}
PAGINACION = re.compile(r"\bpágina\s+\d+(?:\s+de\s+\d+)?\b", re.I)
# Solo etiquetas completas de vocabulario HTML conocido y atributos con sintaxis
# válida. Un '<A la policía...' sin cierre, frecuente en capas defectuosas, es
# texto literal: nunca se entrega como fragmento incompleto a HTMLParser.
_NOMBRES_HTML = "table|thead|tbody|tfoot|tr|td|th|caption|colgroup|col|p|div|span|br|b|i|strong|em|u|s|sup|sub|a|img|ul|ol|li|h[1-6]|blockquote|pre|code|hr"
_ATRIBUTO_HTML = r"""\s+[a-zA-Z_:][-\w:.]*(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s<>`="']+))?"""
_ETIQUETA_HTML = re.compile(
    rf"<!--[\s\S]*?-->|</?(?:{_NOMBRES_HTML})(?:{_ATRIBUTO_HTML})*\s*/?>", re.I
)
CAMPOS = (
    "ediciones_caracteres",
    "caracteres_ref",
    "ediciones_palabras",
    "palabras_ref",
    "palabras_hip",
    "palabras_comunes",
)
COCIENTES = {
    "cer": (0, 1),
    "wer": (2, 3),
    "recuperacion": (5, 3),
    "precision": (5, 4),
}


class _TextoHTML(HTMLParser):
    """Separa celdas/bloques; conserva el texto y decodifica entidades, sin ejecutar HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes = []

    def handle_data(self, data):
        self.partes.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"td", "th", "tr", "table", "p", "div", "br", "li", "sup"}:
            self.partes.append(" ")

    def handle_endtag(self, tag):
        self.handle_starttag(tag, [])


def normalizar(texto, *, modo="estricto"):
    """NFC, minúsculas y espacios; conserva puntuación, números y tildes.

    Heurística conservadora ANTES de minúsculas: letra-\\nminúscula se une
    sin guion; ante mayúscula se elimina el salto pero se conserva el guion
    (NACIONAL-\\nARMANDA -> nacional-armanda). No es un diccionario: puede
    errar con compuestos partidos ante minúscula; se aplica idéntica a todos.
    HTML se aplana por celdas, Markdown pierde solo delimitadores reconocidos.
    Los superíndices Unicode/HTML/LaTeX numéricos quedan como número aparte.
    """
    if modo not in {"estricto", "contenido"}:
        raise ValueError("Modo de normalización desconocido")
    texto = unicodedata.normalize("NFC", texto).replace("\r\n", "\n").replace("\r", "\n")
    # Solo el guion ASCII original indica partición: una raya tipográfica al
    # final de línea conserva la separación aunque contenido equipare su forma.
    texto = re.sub(
        r"([^\W\d_])-[ \t]*\n[ \t]*([^\W\d_])",
        lambda m: m[1] + ("" if m[2].islower() else "-") + m[2],
        texto,
    )
    if modo == "contenido":
        texto = texto.translate(
            str.maketrans(
                {
                    "“": '"',
                    "”": '"',
                    "„": '"',
                    "«": '"',
                    "»": '"',
                    "‘": "'",
                    "’": "'",
                    "‚": "'",
                    "–": "-",
                    "—": "-",
                    "…": "...",
                }
            )
        )
    texto = texto.replace("\f", " ")
    texto = re.sub(r"<!--\s*(?:página|page)\s+\d+\s*-->", " ", texto, flags=re.I)
    texto = re.sub(r"\b(?:página\s+\d+\s+de|page\s+\d+\s+of)\s+\d+\b", " ", texto, flags=re.I)
    texto = re.sub(r"(?im)^[ \t]*(?:página|pág\.?|page)\s+\d+[ \t]*$", " ", texto)
    texto = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: " " + m[0].translate(SUPERINDICES) + " ", texto)
    texto = re.sub(
        r"\\\(\s*\[\s*(?:\^\{(\d+)\}|(\d+))\s*\]\s*\\\)",
        lambda m: " " + (m[1] or m[2]) + " ",
        texto,
    )
    texto = re.sub(
        r"\\\(\s*\^\{(\d+)\}\s*\\\)|\^\{(\d+)\}", lambda m: " " + (m[1] or m[2]) + " ", texto
    )
    html = _TextoHTML()
    posicion = 0
    for etiqueta in _ETIQUETA_HTML.finditer(texto):
        html.handle_data(unescape(texto[posicion : etiqueta.start()]))
        html.feed(etiqueta[0])
        posicion = etiqueta.end()
    html.handle_data(unescape(texto[posicion:]))
    html.close()
    texto = "".join(html.partes)
    if modo == "contenido":
        texto = texto.translate(
            str.maketrans(
                {
                    "“": '"',
                    "”": '"',
                    "„": '"',
                    "«": '"',
                    "»": '"',
                    "‘": "'",
                    "’": "'",
                    "‚": "'",
                    "–": "-",
                    "—": "-",
                    "…": "...",
                }
            )
        )
    texto = re.sub(r"!\[[^\]]*\]\([^\n]*?\)", " ", texto)
    texto = re.sub(r"\[([^\]\n]+)\]\([^\n]*?\)", r"\1", texto)
    texto = re.sub(r"(?m)^[ \t]*(?:`{3,}|~{3,})[^\n]*$", " ", texto)
    texto = re.sub(r"(?m)^[ \t]*(?:[-*_][ \t]*){3,}$", " ", texto)
    texto = re.sub(
        r"(?m)^[ \t]*\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$", " ", texto
    )
    texto = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]+", "", texto)
    # Una desigualdad o un signo numérico no son marcado Markdown. No se
    # consumen saltos de línea ni prefijos parciales de citas anidadas.
    no_numerico = r"[^\s\d+\-−±><=.,]"
    # Protege también importes: moneda, paréntesis y signos pueden preceder
    # al primer dígito. Solo espacios horizontales, nunca la línea siguiente.
    cantidad = r"(?:(?:US\$|COP|[$€(+\-−±])[ \t]*)*[.,]?\d"
    texto = re.sub(rf"(?im)^[ \t]*(?:>[ \t]*)+[ \t]+(?!{cantidad})(?={no_numerico})", "", texto)
    marca = "[-*]" if modo == "estricto" else "[-+*]"
    contenido = r"[^\W\d_]" if modo == "estricto" else no_numerico
    vineta = rf"{marca}[ \t]+(?!{cantidad})(?={contenido})"
    texto = re.sub(rf"(?im)^[ \t]*(?:{vineta})", "", texto)
    texto = re.sub(r"(?m)[ \t]+#{1,6}[ \t]*$", "", texto)
    for patron in (
        r"\*\*(.+?)\*\*",
        r"__(.+?)__",
        r"(?<!\w)\*([^*\n]+)\*(?!\w)",
        r"(?<!\w)_([^_\n]+)_(?!\w)",
        r"~~(.+?)~~",
        r"`([^`\n]+)`",
    ):
        texto = re.sub(patron, r"\1", texto)
    return " ".join(texto.replace("|", " ").lower().split())


def distancia(a, b):
    """Levenshtein exacto Myers, copiado de fidelidad/comparar.py revisado."""
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


def paginas_ocr(extraccion):
    """Páginas que requirieron OCR, tanto exitosas como fallidas."""
    return set(extraccion.get("ocr_pages", [])) | set(extraccion.get("ocr_failed_pages", []))


def longitud_lcs(a, b):
    """LCS exacta con vectores de bits; no usa alineación heurística."""
    mascaras = {}
    for i, elemento in enumerate(a):
        mascaras[elemento] = mascaras.get(elemento, 0) | (1 << i)
    estado = 0
    for elemento in b:
        x = mascaras.get(elemento, 0) | estado
        estado = x & ~(x - ((estado << 1) | 1))
    return estado.bit_count()


def orden_lectura(hipotesis, referencia, *, normalizados=False, modo="estricto"):
    """Recall/precisión de LCS de trigramas de palabras normalizadas solapados.

    n=min(3, palabras_ref, palabras_hip), con mínimo 1. Conserva multiplicidad
    y orden; sensible también a errores/omisiones, no prueba por sí solo desorden.
    """
    h, r = (
        (hipotesis, referencia)
        if normalizados
        else (normalizar(hipotesis, modo=modo), normalizar(referencia, modo=modo))
    )
    hp, rp = h.split(), r.split()
    n = max(1, min(3, len(hp), len(rp)))
    hs = [tuple(hp[i : i + n]) for i in range(len(hp) - n + 1)]
    rs = [tuple(rp[i : i + n]) for i in range(len(rp) - n + 1)]
    lcs = longitud_lcs(rs, hs)
    return {
        "orden_lcs": cociente(lcs, len(rs)),
        "orden_precision": cociente(lcs, len(hs)),
        "lcs": lcs,
        "ngramas_ref": len(rs),
        "ngramas_hip": len(hs),
        "n": n,
    }


def metricas(hipotesis, referencia, *, normalizados=False, modo="estricto"):
    h, r = (
        (hipotesis, referencia)
        if normalizados
        else (normalizar(hipotesis, modo=modo), normalizar(referencia, modo=modo))
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
        **orden_lectura(h, r, normalizados=True),
    }


def criticos(texto, *, modo="estricto"):
    texto = normalizar(texto, modo=modo)
    return {
        tipo: Counter(m[0] for m in re.finditer(patron, texto)) for tipo, patron in PATRONES.items()
    }


def comparar_criticos(hipotesis, referencia, *, modo="estricto"):
    """Multiconjuntos, coincidencia exacta normalizada, categorías solapadas.

    Recall inverso = proporción de elementos de la hipótesis presentes en la
    referencia. Faltantes/extras conservan multiplicidad; no se equiparan citas
    jurídicamente equivalentes escritas de forma distinta.
    """
    h, r = criticos(hipotesis, modo=modo), criticos(referencia, modo=modo)
    salida = {}
    for tipo in PATRONES:
        comunes = sum((h[tipo] & r[tipo]).values())
        nr, nh = sum(r[tipo].values()), sum(h[tipo].values())
        salida[tipo] = {
            "total_ref": nr,
            "total_hip": nh,
            "comunes": comunes,
            "recall_ref_en_hip": cociente(comunes, nr),
            "recall_hip_en_ref": cociente(comunes, nh),
            "faltantes_en_hip": sorted((r[tipo] - h[tipo]).elements()),
            "faltantes_en_ref": sorted((h[tipo] - r[tipo]).elements()),
        }
    return salida


def encabezados_pies(paginas, *, modo="estricto"):
    """Líneas <=250 caracteres en primeras/últimas 3, en >=30% y >=3 páginas."""
    conteo = Counter()
    for texto in paginas:
        lineas = [normalizar(x, modo=modo) for x in texto.splitlines() if normalizar(x, modo=modo)]
        conteo.update({x for x in lineas[:3] + lineas[-3:] if len(x) <= 250})
    limite = max(3, math.ceil(len(paginas) * 0.3))
    return {x for x, n in conteo.items() if n >= limite}


def ruido(hipotesis, referencia, repetidos=(), *, modo="estricto"):
    """Extras multiconjunto, separando candidatos a encabezado/pie y paginación.

    Las páginas eliminadas por normalización se informan como etiquetas crudas,
    fuera de los extras. Encabezados/pies son candidatos automáticos, no certeza.
    """
    extra = Counter(normalizar(hipotesis, modo=modo).split()) - Counter(
        normalizar(referencia, modo=modo).split()
    )
    candidatos = Counter()
    for linea in hipotesis.splitlines():
        limpia = normalizar(linea, modo=modo)
        if limpia in repetidos:
            candidatos.update(limpia.split())
    cabeceras = extra & candidatos
    return {
        "palabras_extra": sum(extra.values()),
        "encabezados_pies_repetidos": dict(sorted(cabeceras.items())),
        "otras_palabras": dict(sorted((extra - cabeceras).items())),
        "etiquetas_pagina": PAGINACION.findall(hipotesis),
    }


def _sumas(filas):
    return [sum(f[k] for f in filas) for k in CAMPOS]


def _percentil(valores, p):
    pos = (len(valores) - 1) * p
    a, b = math.floor(pos), math.ceil(pos)
    return valores[a] + (valores[b] - valores[a]) * (pos - a)


def bootstrap(filas, *, unidad="pagina", repeticiones=REPETICIONES, semilla=SEMILLA):
    """IC95 percentil de cocientes micro; página o clúster documento completo.

    El remuestreo documental mantiene juntas todas sus páginas elegibles. Los
    estratos solo contienen sus propias páginas y documentos. Semilla fija.
    """
    if unidad not in {"pagina", "documento"} or repeticiones < 1:
        raise ValueError("Unidad inválida o repeticiones < 1")
    if not filas:
        return {k: None for k in COCIENTES}
    if unidad == "documento":
        grupos = defaultdict(list)
        for fila in filas:
            grupos[fila["slug"]].append(fila)
        vectores = [_sumas(grupos[k]) for k in sorted(grupos)]
    else:
        vectores = [[f[k] for k in CAMPOS] for f in filas]
    rng = random.Random(semilla)
    valores = {k: [] for k in COCIENTES}
    for _ in range(repeticiones):
        muestra = rng.choices(vectores, k=len(vectores))
        total = [sum(v[i] for v in muestra) for i in range(len(CAMPOS))]
        for k, (n, d) in COCIENTES.items():
            if total[d]:
                valores[k].append(total[n] / total[d])
    return {
        k: [_percentil(sorted(v), 0.025), _percentil(sorted(v), 0.975)] if v else None
        for k, v in valores.items()
    }


def agregar(filas, *, repeticiones=REPETICIONES):
    totales = _sumas(filas)
    return {
        "paginas": len(filas),
        "documentos": len({f["slug"] for f in filas}),
        **dict(zip(CAMPOS, totales, strict=True)),
        **{k: cociente(totales[n], totales[d]) for k, (n, d) in COCIENTES.items()},
        "ic95_por_pagina": bootstrap(filas, repeticiones=repeticiones),
        "ic95_por_documento": bootstrap(filas, unidad="documento", repeticiones=repeticiones),
    }


def detectar_bucles(texto):
    """Indicios conservadores: líneas >=20 caracteres, >=5 copias y >=30% del
    texto; o cobertura >=40% por ventanas de 8 palabras con >=6 apariciones,
    confirmada por >=6 copias CONSECUTIVAS de un período de 1..80 palabras
    que cubran >=40% del texto. Esto evita catálogos con fórmulas comunes.
    Mínimo 80 palabras para n-gramas. La cobertura usa unión de posiciones,
    evitando sumar varias veces ventanas solapadas. No demuestra truncamiento.
    """
    evidencias = []
    lineas = [normalizar(x) for x in texto.splitlines() if normalizar(x)]
    total = sum(map(len, lineas))
    for linea, n in Counter(lineas).most_common():
        cobertura = n * len(linea) / total if total else 0
        if len(linea) >= 20 and n >= 5 and cobertura >= 0.30:
            evidencias.append(
                {
                    "tipo": "lineas_repetidas",
                    "copias": n,
                    "cobertura": cobertura,
                    "muestra": linea[:160],
                }
            )
    palabras = normalizar(texto).split()
    if len(palabras) >= 80:
        ventanas = [tuple(palabras[i : i + 8]) for i in range(len(palabras) - 7)]
        frecuentes = {v for v, n in Counter(ventanas).items() if n >= 6}
        posiciones = set()
        for i, ventana in enumerate(ventanas):
            if ventana in frecuentes:
                posiciones.update(range(i, i + 8))
        cobertura = len(posiciones) / len(palabras)
        if cobertura >= 0.40:
            mejor = {"longitud": 0, "periodo": 0, "inicio": 0}
            for periodo in range(1, min(80, len(palabras) // 6) + 1):
                racha = 0
                for i in range(periodo, len(palabras)):
                    racha = racha + 1 if palabras[i] == palabras[i - periodo] else 0
                    longitud = racha + periodo
                    if racha >= 5 * periodo and longitud > mejor["longitud"]:
                        mejor = {
                            "longitud": longitud,
                            "periodo": periodo,
                            "inicio": i - longitud + 1,
                        }
            if mejor["longitud"] / len(palabras) >= 0.40:
                evidencias.append(
                    {
                        "tipo": "ngramas_repetidos",
                        "n": 8,
                        "min_copias": 6,
                        "cobertura": cobertura,
                        "cobertura_consecutiva": mejor["longitud"] / len(palabras),
                        "periodo_palabras": mejor["periodo"],
                        "ventanas_distintas": len(frecuentes),
                        "muestra": " ".join(
                            palabras[mejor["inicio"] : mejor["inicio"] + mejor["periodo"]]
                        )[:160],
                    }
                )
    return evidencias


def calibrar(paginas=None, *, modo="estricto"):
    """Sustituciones deterministas y borrado de dígitos; casos de bucles/control.

    Sustituye caracteres no blancos por U+FFFD, ausente en el original. Tasa
    sobre TODOS los caracteres normalizados, redondeada a entero. Así el colapso
    de espacios no perturba la dosis y CER debe recuperarla exactamente.
    """
    if paginas is None:
        paginas = [
            (
                "sintetica",
                (
                    "Artículo 15. Ley 99 de 1993; Decreto 2324 de 1984. "
                    "Fecha 12/03/2024 y 7 de agosto de 2020. Radicado 47001-2333-000-2021-00198-00. "
                    "Protección del litoral, niñez y ambiente. "
                )
                * 100,
            )
        ]
    pruebas = []
    for nombre, texto in paginas:
        limpio = normalizar(texto, modo=modo)
        posiciones = [i for i, c in enumerate(limpio) if not c.isspace()]
        if not limpio or "\ufffd" in limpio:
            raise ValueError("Calibración requiere texto no vacío sin U+FFFD")
        for tasa in (0.005, 0.01, 0.03):
            n = round(len(limpio) * tasa)
            rng = random.Random(SEMILLA)
            copia = list(limpio)
            for i in rng.sample(posiciones, n):
                copia[i] = "\ufffd"
            obtenido = metricas("".join(copia), limpio, modo=modo)["cer"]
            esperado = n / len(limpio)
            pruebas.append(
                {
                    "pagina": nombre,
                    "tipo": "sustituciones",
                    "tasa": tasa,
                    "sustituciones": n,
                    "caracteres_ref": len(limpio),
                    "esperado": esperado,
                    "cer": obtenido,
                    "correcto": abs(obtenido - esperado) < 1e-12,
                }
            )
        borrado = re.sub(r"\d", "", limpio)
        crit = comparar_criticos(borrado, limpio, modo=modo)
        presentes = [v for v in crit.values() if v["total_ref"]]
        pruebas.append(
            {
                "pagina": nombre,
                "tipo": "borrado_numeros",
                "cer": metricas(borrado, limpio, modo=modo)["cer"],
                "criticos": crit,
                "correcto": bool(presentes) and all(v["recall_ref_en_hip"] == 0 for v in presentes),
            }
        )
    casos = {
        "bucle_lineas": (
            "Se repite esta frase sin aportar ninguna información nueva.\n" * 12,
            True,
        ),
        "bucle_sin_saltos": (
            "la autoridad marítima debe proteger los bienes de uso público " * 30,
            True,
        ),
        "control_cita_duplicada": ("Artículo 15 de la Ley 99 de 1993.\n" * 2, False),
        "control_diverso": (" ".join(f"palabra{i}" for i in range(300)), False),
        "control_frase_juridica": (
            "\n".join(
                f"Considerando {i}: "
                + "la autoridad marítima debe proteger los bienes de uso público "
                + " ".join(f"hecho{i}x{j}" for j in range(60))
                for i in range(8)
            ),
            False,
        ),
        "control_catalogo_circulares": (
            "\n".join(
                f"Circular {i} fecha {i}/03/2021: suscrita por el señor capitán de puerto "
                "por la cual se establecen medidas de seguridad integral marítima "
                f"para el evento único {i}."
                for i in range(12)
            ),
            False,
        ),
    }
    bucles = [
        {
            "caso": k,
            "esperado": esperado,
            "evidencias": detectar_bucles(t),
            "correcto": bool(detectar_bucles(t)) == esperado,
        }
        for k, (t, esperado) in casos.items()
    ]
    return {
        "modo": modo,
        "semilla": SEMILLA,
        "pruebas": pruebas,
        "bucles": bucles,
        "correcto": all(p["correcto"] for p in pruebas + bucles),
    }
