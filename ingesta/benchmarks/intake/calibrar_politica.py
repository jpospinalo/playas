"""FASE 4: calibra los umbrales de la política con AJUSTE y la confirma en VALIDACIÓN.

Etiqueta: veredicto por documento frente a U (verde, no distinguible de U,
amarillo, rojo). Aceptar = ``aceptado`` o ``aceptado_con_advertencias``.
Objetivo de seguridad: 0 rojos aceptados en AJUSTE; entre las configuraciones
que lo cumplen se elige la que envía menos verdes y no distinguibles a revisión
y, a igualdad, la menos estricta. VALIDACIÓN no interviene en la elección.

    python -I -X utf8 calibrar_politica.py --senales trabajo/senales_53.json \
        --politica ../../config/intake_policy.yaml --salida resultados/calibracion
"""

from __future__ import annotations

import argparse
import copy
import itertools
import json
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parents[1]))

from ingest.offline.policy import PUBLICABLES, cargar_politica, decidir  # noqa: E402

ETIQUETAS = ("verde", "no distinguible de U", "amarillo", "rojo")
# Rejilla (de menos a más estricta en cada eje). La identidad obligatoria es
# una decisión de política fija, no un parámetro a ajustar.
REJILLA = {
    "ocr_confianza_media_minima": [0, 92, 93, 94, 95],
    # Mínimo por página de defecto grave (70) que la calibración no relaja.
    "ocr_confianza_pagina_minima": [70, 80, 85, 90],
    # Regla de seguridad que la calibración no relaja: como máximo la mitad de las
    # páginas OCR con confianza ≤ 95 (recomendación de la fase anterior, fijada
    # tras ver todas las páginas OCR, incluidas las de validación: sus cifras de
    # validación son algo optimistas). La ingenua la deja en 1,0 y en validación
    # solo atrapa Turbo por una página con 2,1 puntos de margen.
    "ocr_fraccion_paginas_bajas_maxima": [0.5, 0.3, 0.2, 0.1],
    "simbolos_sospechosos_maximos": [1000, 2, 1, 0],
    "anomalias_secuencia_maximas": [1000, 5, 3, 1],
    "tablas_imagen_maximas": [1000, 1, 0],
    "tablas_imagen_caracteres_maximos": [800, 1100, 1500],
    "caida_texto_paginas_maximas": [1000, 1, 0],
}


def evaluar(filas, politica):
    salida = []
    for fila in filas:
        decision, motivos, avisos = decidir(fila["senales"], politica)
        salida.append({**fila, "decision": decision, "motivos": motivos, "avisos": avisos})
    return salida


def resumen(evaluadas):
    matriz = Counter((f["veredicto_u"], f["decision"]) for f in evaluadas)
    aceptados = lambda e: sum(  # noqa: E731
        1 for f in evaluadas if f["veredicto_u"] == e and f["decision"] in PUBLICABLES
    )
    total = lambda e: sum(1 for f in evaluadas if f["veredicto_u"] == e)  # noqa: E731
    return {
        "documentos": len(evaluadas),
        "matriz": {
            e: {
                d: matriz[(e, d)]
                for d in ("aceptado", "aceptado_con_advertencias", "revision_humana", "rechazado")
            }
            for e in ETIQUETAS
        },
        "rojos_aceptados": aceptados("rojo"),
        "rojos": total("rojo"),
        "carga_revision_verdes_y_no_distinguibles": sum(
            1
            for f in evaluadas
            if f["veredicto_u"] in {"verde", "no distinguible de U"}
            and f["decision"] not in PUBLICABLES
        ),
        "verdes_y_no_distinguibles": total("verde") + total("no distinguible de U"),
        "amarillos_aceptados": aceptados("amarillo"),
        "amarillos": total("amarillo"),
    }


def calibrar(ajuste, base, *, robusta=True, rejilla=None):
    rejilla = rejilla or REJILLA
    mejor = None
    claves = list(rejilla)
    for combinacion in itertools.product(*(range(len(rejilla[k])) for k in claves)):
        politica = copy.deepcopy(base)
        for clave, indice in zip(claves, combinacion, strict=True):
            politica["revision"][clave] = rejilla[clave][indice]
        r = resumen(evaluar(ajuste, politica))
        if r["rojos_aceptados"]:
            continue
        if robusta:
            # Robustez: cada rojo debe caer por una señal de su defecto, no por
            # casualidad de la puerta de identidad (calibración ingenua: en
            # validación aceptaba un rojo escaneado).
            sin_identidad = copy.deepcopy(politica)
            sin_identidad["revision"]["identidad_obligatoria"] = False
            if resumen(evaluar(ajuste, sin_identidad))["rojos_aceptados"]:
                continue
        # Menos carga humana; a igualdad, menos estricta (suma de índices) y orden fijo.
        criterio = (r["carga_revision_verdes_y_no_distinguibles"], sum(combinacion), combinacion)
        if mejor is None or criterio < mejor[0]:
            mejor = (criterio, politica, r)
    return mejor


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--senales", type=Path, required=True)
    parser.add_argument("--politica", type=Path, required=True)
    parser.add_argument("--salida", type=Path, required=True)
    args = parser.parse_args()
    filas = json.loads(args.senales.read_text(encoding="utf-8"))
    ajuste = [f for f in filas if f["conjunto"] == "ajuste"]
    validacion = [f for f in filas if f["conjunto"] == "validacion"]
    base = cargar_politica(args.politica)
    # Ingenua: sin robustez y sin la regla de seguridad (para documentar su fallo).
    ingenua = calibrar(
        ajuste,
        base,
        robusta=False,
        rejilla={**REJILLA, "ocr_fraccion_paginas_bajas_maxima": [1.0, 0.5, 0.3, 0.2, 0.1]},
    )
    mejor = calibrar(ajuste, base)
    if mejor is None:
        raise SystemExit("Ninguna configuración logra 0 rojos aceptados en ajuste")
    _, politica, _ = mejor
    resultados = {
        "umbrales_elegidos": {k: politica["revision"][k] for k in REJILLA},
        "ingenua": {
            "umbrales": {k: ingenua[1]["revision"][k] for k in REJILLA},
            "ajuste": resumen(evaluar(ajuste, ingenua[1])),
            "validacion": resumen(evaluar(validacion, ingenua[1])),
        },
        "ajuste": resumen(evaluar(ajuste, politica)),
        "validacion": resumen(evaluar(validacion, politica)),
        "documentos": [
            {
                k: f[k]
                for k in (
                    "slug",
                    "conjunto",
                    "categoria",
                    "veredicto_u",
                    "decision",
                    "motivos",
                    "avisos",
                )
            }
            for f in evaluar(ajuste + validacion, politica)
        ],
    }
    args.salida.mkdir(parents=True, exist_ok=True)
    (args.salida / "calibracion.json").write_text(
        json.dumps(resultados, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: resultados[k] for k in ("umbrales_elegidos", "ajuste", "validacion")},
            ensure_ascii=False,
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
