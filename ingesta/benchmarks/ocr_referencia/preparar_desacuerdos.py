"""Muestreo ciego estratificado y recortes; no adjudica ni abre revisión visual."""

from __future__ import annotations

import importlib.util
import random
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("comun", BASE / "comun.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
m = c.modulo("metricas")
SEMILLA = 27102026
SALIDA = BASE / "resultados/fase3"


def alinear(ref, hip):
    """Levenshtein exacto de palabras con traza compacta; empate diagonal/borrar/insertar."""
    n, mh = len(ref), len(hip)
    traza = [bytearray([2] * (mh + 1))]
    anterior = list(range(mh + 1))
    for i, x in enumerate(ref, 1):
        fila = [i] + [0] * mh
        pasos = bytearray(mh + 1)
        pasos[0] = 1
        for j, y in enumerate(hip, 1):
            diagonal = anterior[j - 1] + (x != y)
            borrar, insertar = anterior[j] + 1, fila[j - 1] + 1
            v = min(diagonal, borrar, insertar)
            fila[j] = v
            pasos[j] = 0 if diagonal == v else 1 if borrar == v else 2
        traza.append(pasos)
        anterior = fila
    i, j = n, mh
    ops = []
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


def segmentos(s, u):
    hs, rs = m.normalizar(s, modo="contenido").split(), m.normalizar(u, modo="contenido").split()
    ops = alinear(rs, hs)
    seleccion = []
    vistos = set()
    for j, op in enumerate(ops):
        if op[0] == "igual":
            continue
        # Máximo 17 operaciones y cuatro de contexto a cada lado, 25 palabras.
        fin = j + 1
        while fin < len(ops) and ops[fin][0] != "igual" and fin - j < 17:
            fin += 1
        izquierda = max(0, j - 4)
        derecha = min(len(ops), fin + 4)
        trozo = ops[izquierda:derecha]
        ir, fr = trozo[0][1], trozo[-1][2]
        ih, fh = trozo[0][3], trozo[-1][4]
        # Si un lado pierde muchas palabras se amplía su contexto independientemente.
        if fr - ir < 3:
            ir = max(0, ir - 2)
            fr = min(len(rs), max(fr, ir + 3))
        if fh - ih < 3:
            ih = max(0, ih - 2)
            fh = min(len(hs), max(fh, ih + 3))
        hu, hr = " ".join(hs[ih:fh]), " ".join(rs[ir:fr])
        clave = (ir, fr, ih, fh)
        if (
            hu == hr
            or clave in vistos
            or not 3 <= len(hu.split()) <= 25
            or not 3 <= len(hr.split()) <= 25
        ):
            continue
        vistos.add(clave)
        diferencia = " ".join(rs[op[1] : ops[fin - 1][2]] + hs[op[3] : ops[fin - 1][4]])
        critico = any(re.search(p, diferencia) for p in m.PATRONES.values())
        seleccion.append(
            {
                "s": hu,
                "u": hr,
                "critico": critico,
                "rango_s": [ih, fh],
                "rango_u": [ir, fr],
                "ediciones_segmento": sum(x[0] != "igual" for x in ops[j:fin]),
            }
        )
    return seleccion


def localizar(palabras_pdf, texto):
    """Ancla única de 3..6 palabras normalizadas, cerca del centro del segmento."""
    tokens, indices = [], []
    for j, w in enumerate(palabras_pdf):
        normal = m.normalizar(w[4], modo="contenido").split()
        tokens.extend(normal)
        indices.extend([j] * len(normal))
    p = texto.split()
    for n in range(min(6, len(p)), 2, -1):
        for a in sorted(range(len(p) - n + 1), key=lambda j: abs(j + n / 2 - len(p) / 2)):
            ventana = p[a : a + n]
            hallados = [j for j in range(len(tokens) - n + 1) if tokens[j : j + n] == ventana]
            if len(hallados) == 1:
                j = hallados[0]
                return sorted(set(indices[j : j + n]))
    return []


def recortar(d, p, segmento, identificador, fitz):
    ruta = BASE / "trabajo/recortes_desacuerdos" / f"{identificador}.png"
    with fitz.open(d["pdf"]) as pdf:
        page = pdf[p - 1]
        palabras = page.get_text("words")
        indices = localizar(palabras, segmento["u"]) or localizar(palabras, segmento["s"])
        if indices:
            rect = fitz.Rect(palabras[indices[0]][:4])
            for j in indices[1:]:
                rect |= fitz.Rect(palabras[j][:4])
            # Ancho completo: el contexto puede extenderse varias líneas más
            # allá del ancla y no debe quedar cortado horizontalmente.
            rect = fitz.Rect(page.rect.x0, rect.y0 - 100, page.rect.x1, rect.y1 + 100) & page.rect
            metodo = "palabras_PyMuPDF_ancla_unica"
        else:
            rect = page.rect
            metodo = "pagina_completa_sin_ancla_unica"
        pix = page.get_pixmap(dpi=200, clip=rect, alpha=False)
        pix.save(str(c.destino(ruta)))
        if not ruta.is_file() or pix.width < 1 or pix.height < 1:
            raise ValueError("Recorte vacío")
        return {
            "ruta": ruta.relative_to(BASE).as_posix(),
            "coordenadas_pdf": list(rect),
            "metodo": metodo,
            "dpi": 200,
            "ancho": pix.width,
            "alto": pix.height,
        }


def preparar(filas, datos, fitz):
    ruta_csv = SALIDA / "desacuerdos.csv"
    if ruta_csv.exists() and any(
        f.get("veredicto", "").strip() or f.get("nota", "").strip() for f in c.csv_leer(ruta_csv)
    ):
        raise ValueError("Hay adjudicaciones/notas existentes; no se sobrescriben")
    rng = random.Random(SEMILLA)
    candidatas = [
        f
        for f in filas
        if f["comparacion"] == "S_mio_vs_U"
        and f["modo"] == "contenido"
        and f["ediciones_palabras"] > 0
    ]
    elegidos = []
    cache = {}
    for tipo, ncrit, nazar in (("digital", 8, 7), ("OCR", 7, 8)):
        propias = [f for f in candidatas if f["tipo_pagina"] == tipo]
        usados = set()
        for clase, cantidad in (("critico", ncrit), ("azar", nazar)):
            orden = list(propias)
            rng.shuffle(orden)
            seleccionados = 0
            for f in orden:
                clave = (f["slug"], f["pagina"])
                if clave in usados:
                    continue
                if clave not in cache:
                    d = datos[f["slug"]]
                    cache[clave] = segmentos(d["s"][f["pagina"]], d["u"][f["pagina"]])
                pool = [s for s in cache[clave] if clase != "critico" or s["critico"]]
                if not pool:
                    continue
                seg = rng.choice(pool)
                elegidos.append((f, seg, clase))
                usados.add(clave)
                seleccionados += 1
                if seleccionados == cantidad:
                    break
            if seleccionados != cantidad:
                raise ValueError(
                    f"Muestreo insuficiente: {tipo}/{clase}: {seleccionados}/{cantidad}"
                )
    rng.shuffle(elegidos)
    filas_csv, claves, manifiesto = [], [], []
    for j, (f, seg, clase) in enumerate(elegidos, 1):
        identificador = f"D{j:03d}"
        sa = rng.choice([True, False])
        recorte = recortar(datos[f["slug"]], f["pagina"], seg, identificador, fitz)
        filas_csv.append(
            {
                "id": identificador,
                "slug": f["slug"],
                "pagina": f["pagina"],
                "tipo_pagina": f["tipo_pagina"],
                "texto_A": seg["s"] if sa else seg["u"],
                "texto_B": seg["u"] if sa else seg["s"],
                "recorte": recorte["ruta"],
                "muestreo": clase,
                "veredicto": "",
                "nota": "",
            }
        )
        claves.append({"id": identificador, "quien_es_A": "S" if sa else "U"})
        manifiesto.append(
            {
                "id": identificador,
                "critico": seg["critico"],
                "muestreo": clase,
                "rango_s": seg["rango_s"],
                "rango_u": seg["rango_u"],
                **recorte,
            }
        )
    c.csv_guardar(ruta_csv, filas_csv)
    c.csv_guardar(SALIDA / "clave_desacuerdos.csv", claves)
    c.json_guardar(
        SALIDA / "muestreo_desacuerdos.json",
        {
            "semilla": SEMILLA,
            "n": 30,
            "digital": 15,
            "OCR": 15,
            "prioridad_critica": 15,
            "azar": 15,
            "normalizacion": "contenido",
            "un_segmento_por_pagina": True,
            "regla": "Páginas barajadas sin reemplazo dentro de tipo; 8 digitales+7 OCR de prioridad crítica, 7+8 al azar. En prioridad crítica se exige regex en el tramo editado; azar puede incluir críticos por casualidad. A/B se asigna después de mezclar con la misma semilla. No inferir prevalencia poblacional de esta muestra.",
            "recortes": manifiesto,
        },
    )
    print("Preparados 30 desacuerdos ciegos y recortes.", flush=True)
