"""Alineación por anclas entre páginas PDF y Markdown, sin ampliar párrafos."""

from __future__ import annotations

import re
import unicodedata


def tokens(contenido):
    return list(re.finditer(r"\w+", unicodedata.normalize("NFC", contenido).lower()))


def anclas(pagina, markdown):
    """Anclas únicas de 6 palabras al inicio y fin, sin usar otras transcripciones.

    Se toleran hasta 35 palabras de encabezado/pie diferentes. El tramo se
    corta en las anclas, sin ampliar párrafos que podrían cruzar páginas.
    Se conserva el Markdown original NFC, incluida su puntuación.
    """
    p, v = tokens(pagina), tokens(markdown)
    pp, vv = [m.group() for m in p], [m.group() for m in v]
    n = 6
    if len(pp) < 2 * n:
        return None, {"motivo": "página demasiado corta para dos anclas"}
    indices = {}
    for i in range(len(vv) - n + 1):
        indices.setdefault(tuple(vv[i : i + n]), []).append(i)
    inicios, finales = [], []
    margen = min(35, max(6, len(pp) // 6))
    for i in range(min(margen + 1, len(pp) - n + 1)):
        posiciones = indices.get(tuple(pp[i : i + n]), [])
        if len(posiciones) == 1:
            inicios.append((i, posiciones[0]))
    for i in range(max(0, len(pp) - n - margen), len(pp) - n + 1):
        posiciones = indices.get(tuple(pp[i : i + n]), [])
        if len(posiciones) == 1:
            finales.append((i, posiciones[0]))
    if not inicios or not finales:
        return None, {
            "motivo": "faltan n-gramas únicos de inicio o fin",
            "anclas_inicio": len(inicios),
            "anclas_fin": len(finales),
        }
    pi, vi = min(inicios)
    pf, vf = max(finales)
    proporcion = (vf + n - vi) / max(1, pf + n - pi)
    if vf <= vi or not 0.45 <= proporcion <= 2.2:
        return None, {
            "motivo": "anclas invertidas o extensión incompatible",
            "proporcion": proporcion,
        }
    inicio = v[vi].start()
    comienzo_linea = markdown.rfind("\n", 0, inicio) + 1
    if re.fullmatch(r"[ #*_\t]*", markdown[comienzo_linea:inicio]):
        inicio = comienzo_linea
    fin_token = vf + n - 1
    fin = v[fin_token + 1].start() if fin_token + 1 < len(v) else len(markdown)
    return (inicio, fin), {
        "metodo": "dos n-gramas únicos de 6 palabras; primeros/últimos <=35 tokens; corte en anclas sin ampliar líneas",
        "inicio_char": inicio,
        "fin_char": fin,
        "ancla_inicio_palabra_pdf": pi,
        "ancla_fin_palabra_pdf": pf,
        "palabras_antes_ancla": pi,
        "palabras_despues_ancla": len(pp) - pf - n,
        "advertencia": "el texto anterior/posterior a las anclas queda fuera; las diferencias de borde pueden deberse a esta alineación parcial",
    }
