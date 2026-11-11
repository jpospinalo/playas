"""Estadística sin dependencias: rangos con empates, ROC y bootstrap por clúster."""

from __future__ import annotations

import math
import random
from collections import defaultdict

SEMILLA = 27102026


def percentil(v, p):
    v = sorted(x for x in v if x is not None and math.isfinite(x))
    if not v:
        return None
    z = (len(v) - 1) * p
    a, b = math.floor(z), math.ceil(z)
    return v[a] + (v[b] - v[a]) * (z - a)


def ic(v):
    return [percentil(v, 0.025), percentil(v, 0.975)] if any(x is not None for x in v) else None


def rangos_ponderados(valores, pesos):
    orden = sorted(range(len(valores)), key=lambda i: valores[i])
    rangos = [0.0] * len(valores)
    acumulado, j = 0, 0
    while j < len(orden):
        k = j + 1
        while k < len(orden) and valores[orden[k]] == valores[orden[j]]:
            k += 1
        total = sum(pesos[orden[t]] for t in range(j, k))
        rango = acumulado + (total + 1) / 2
        for t in range(j, k):
            rangos[orden[t]] = rango
        acumulado += total
        j = k
    return rangos


def spearman(x, y, pesos=None):
    if len(x) != len(y):
        raise ValueError("Longitudes diferentes")
    pesos = [1] * len(x) if pesos is None else pesos
    rx, ry = rangos_ponderados(x, pesos), rangos_ponderados(y, pesos)
    if not sum(pesos):
        return None
    media = (sum(pesos) + 1) / 2
    vx = sum(w * (a - media) ** 2 for a, w in zip(rx, pesos, strict=True))
    vy = sum(w * (a - media) ** 2 for a, w in zip(ry, pesos, strict=True))
    cov = sum(w * (a - media) * (b - media) for a, b, w in zip(rx, ry, pesos, strict=True))
    return cov / math.sqrt(vx * vy) if vx and vy else None


def roc(scores, etiquetas, pesos=None):
    """AUC ponderada con medio crédito en empates; mayor score = mayor riesgo."""
    pesos = [1] * len(scores) if pesos is None else pesos
    grupos = defaultdict(lambda: [0, 0])
    for score, y, peso in zip(scores, etiquetas, pesos, strict=True):
        grupos[score][int(bool(y))] += peso
    positivos = sum(p for _, p in grupos.values())
    negativos = sum(n for n, _ in grupos.values())
    if not positivos or not negativos:
        return {"auc": None, "youden": None, "sensibilidad_90": None}
    antes, area = 0, 0
    for score in sorted(grupos):
        n, p = grupos[score]
        area += p * (antes + 0.5 * n)
        antes += n
    tp, fp = 0, 0
    candidatos = [{"umbral_riesgo": None, "sensibilidad": 0.0, "especificidad": 1.0, "youden": 0.0}]
    for score in sorted(grupos, reverse=True):
        n, p = grupos[score]
        if not n + p:
            continue
        tp, fp = tp + p, fp + n
        sensibilidad, especificidad = tp / positivos, 1 - fp / negativos
        candidatos.append(
            {
                "umbral_riesgo": score,
                "sensibilidad": sensibilidad,
                "especificidad": especificidad,
                "youden": sensibilidad + especificidad - 1,
            }
        )
    mejor = max(candidatos, key=lambda c: (c["youden"], c["especificidad"]))
    sensible = max(
        (c for c in candidatos if c["sensibilidad"] >= 0.9),
        key=lambda c: (c["especificidad"], -c["sensibilidad"]),
    )
    return {"auc": area / (positivos * negativos), "youden": mejor, "sensibilidad_90": sensible}


def evaluar_predictor(
    filas, campo, *, direccion=1, corte=0.03, unidad="documento", repeticiones=2000
):
    """Asociación exploratoria, umbrales dentro de muestra; no validación externa.

    direccion=-1 para valores bajos de confianza/caracteres. Las medidas de
    calidad documentales repetidas en páginas remuestrean documentos enteros.
    """
    datos = [
        f
        for f in filas
        if isinstance(f.get(campo), (int, float))
        and math.isfinite(f[campo])
        and f.get("cer") is not None
    ]
    x, y = [f[campo] for f in datos], [f["cer"] for f in datos]
    scores, etiquetas = [direccion * v for v in x], [v > corte for v in y]
    base = roc(scores, etiquetas)
    rho = spearman(x, y)
    grupos = defaultdict(list)
    for j, f in enumerate(datos):
        grupos[f["slug"] if unidad == "documento" else j].append(j)
    clusters = list(grupos.values())
    salida = {
        "predictor": campo,
        "n": len(datos),
        "documentos": len({f["slug"] for f in datos}),
        "faltantes": len(filas) - len(datos),
        "malas": sum(etiquetas),
        "corte_cer": corte,
        "direccion_riesgo": "menor" if direccion < 0 else "mayor",
        "spearman": rho,
        "unidad_bootstrap": unidad,
        "repeticiones": repeticiones,
        **base,
    }
    constante = len(set(x)) < 2
    valores = {"auc": [], "spearman": []}
    umbrales = {
        k: {c: [] for c in ("umbral", "sensibilidad", "especificidad")}
        for k in ("youden", "sensibilidad_90")
    }
    rng = random.Random(SEMILLA)
    validos = 0
    if not constante and len(datos) > 1:
        for _ in range(repeticiones):
            pesos = [0] * len(datos)
            for grupo in rng.choices(clusters, k=len(clusters)):
                for j in grupo:
                    pesos[j] += 1
            r = roc(scores, etiquetas, pesos)
            valores["auc"].append(r["auc"])
            valores["spearman"].append(spearman(x, y, pesos))
            validos += r["auc"] is not None
            for nombre in umbrales:
                if r[nombre] is None:
                    continue
                for c in ("sensibilidad", "especificidad"):
                    umbrales[nombre][c].append(r[nombre][c])
                if r[nombre]["umbral_riesgo"] is not None:
                    umbrales[nombre]["umbral"].append(direccion * r[nombre]["umbral_riesgo"])
    salida["constante"] = constante
    salida["bootstrap_validos_dos_clases"] = validos
    salida["ic95_auc"] = (
        [base["auc"], base["auc"]] if constante and base["auc"] is not None else ic(valores["auc"])
    )
    salida["ic95_spearman"] = ic(valores["spearman"])
    for nombre in umbrales:
        valor = salida[nombre]
        if valor is not None:
            valor["umbral"] = (
                direccion * valor["umbral_riesgo"] if valor["umbral_riesgo"] is not None else None
            )
            valor["operador"] = "<=" if direccion < 0 else ">="
            valor["accion"] = "no_alertar" if valor["umbral"] is None else "alertar"
            valor["ic95"] = {k: ic(v) for k, v in umbrales[nombre].items()}
    if constante:
        salida["youden"] = salida["sensibilidad_90"] = None
        salida["limitacion"] = "Predictor constante; no admite umbral discriminante"
    return salida
