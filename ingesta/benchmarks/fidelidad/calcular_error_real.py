"""Evalúa exclusivamente segmentos adjudicados por una persona en desacuerdos.csv.

No lee fuentes: la referencia se reconstruye a partir de las celdas revisadas.
La fidelidad resultante es condicional a la muestra revisada, no una estimación
insesgada de todas las páginas (los desacuerdos priorizan contenido crítico).
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

from comparar import BASE, FUENTES, agregar, guardar_json, metricas, normalizar


def evaluar(filas, permitir_incompleto=False):
    grupos = defaultdict(list)
    controles = defaultdict(list)
    referencias = []
    pendientes = 0
    intervalos = defaultdict(list)
    for numero, fila in enumerate(filas, 2):
        quien = fila.get("quien_acierta", "").strip()
        if not quien:
            pendientes += 1
            continue
        if quien not in (*FUENTES, "ninguna"):
            raise ValueError(f"Fila {numero}: quien_acierta inválido: {quien!r}")
        presentes = fila.get("fuentes_presentes", "").split(",")
        if not fila.get("fuentes_presentes"):
            # CSV externo antiguo: un blanco es ambiguo; se consideran presentes
            # únicamente las fuentes con una celda no vacía.
            presentes = [k for k in FUENTES if fila.get(f"texto_{k}", "")]
        if quien != "ninguna" and quien not in presentes:
            raise ValueError(f"Fila {numero}: se eligió una fuente ausente")
        if quien == "ninguna":
            if not fila.get("nota", "").strip():
                raise ValueError(f"Fila {numero}: 'ninguna' requiere la lectura correcta en nota")
            referencia = (
                ""
                if fila["nota"].strip() == "[VACÍO]"
                else normalizar(fila["nota"], fragmento=True)
            )
        else:
            referencia = fila.get(f"texto_{quien}", "")
        tipo = fila.get("tipo", "desacuerdo")
        if tipo not in ("desacuerdo", "control"):
            raise ValueError(f"Fila {numero}: tipo inválido")
        pagina = (fila["documento"], int(fila["pagina"]), fila["tipo_pagina"])
        rangos = json.loads(fila.get("rangos") or "{}")
        for fuente in presentes:
            if fuente not in FUENTES:
                raise ValueError(f"Fila {numero}: fuente desconocida")
            if fuente in rangos:
                inicio, fin = rangos[fuente]
                clave = (*pagina, fuente)
                for a, b in intervalos[clave]:
                    if max(a, inicio) < min(b, fin) or (inicio == fin == a == b):
                        raise ValueError(
                            f"Fila {numero}: segmentos revisados superpuestos; regenere el CSV"
                        )
                intervalos[clave].append((inicio, fin))
            metrica = metricas(fila.get(f"texto_{fuente}", ""), referencia, normalizados=True)
            grupos[(fuente, pagina, tipo)].append(metrica)
            if tipo == "control":
                controles[fuente].append(fila.get(f"texto_{fuente}", "") != referencia)
        referencias.append(
            {
                "id": fila.get("id", str(numero)),
                "documento": pagina[0],
                "pagina": pagina[1],
                "tipo_pagina": pagina[2],
                "tipo": tipo,
                "referencia": referencia,
                "quien_acierta": quien,
            }
        )
    if pendientes and not permitir_incompleto:
        raise ValueError(
            f"Faltan {pendientes} filas por adjudicar; use --permitir-incompleto para un informe parcial"
        )
    if not referencias:
        raise ValueError("No hay segmentos adjudicados")
    # Suma de distancias por segmento: no permite que los límites se cancelen.
    # Se agrupan después por página para el bootstrap, preservando el clúster.
    campos = (
        "ediciones_caracteres",
        "caracteres_ref",
        "ediciones_palabras",
        "palabras_ref",
        "palabras_hip",
        "palabras_comunes",
    )
    por_pagina = []
    for (fuente, pagina, tipo), lista in grupos.items():
        por_pagina.append(
            {
                "fuente": fuente,
                "documento": pagina[0],
                "pagina": pagina[1],
                "tipo_pagina": pagina[2],
                "tipo": tipo,
                **{k: sum(m[k] for m in lista) for k in campos},
            }
        )
    resumen = []
    for fuente in FUENTES:
        for tipo_pagina in ("digital", "ocr", "TODAS"):
            for tipo in ("desacuerdo", "control", "TODOS"):
                elegidas = [
                    m
                    for m in por_pagina
                    if m["fuente"] == fuente
                    and (tipo_pagina == "TODAS" or m["tipo_pagina"] == tipo_pagina)
                    and (tipo == "TODOS" or m["tipo"] == tipo)
                ]
                # Una sola unidad por página, incluso al juntar ambos tipos.
                paginas = defaultdict(list)
                for m in elegidas:
                    paginas[(m["documento"], m["pagina"])].append(m)
                lista = [
                    {k: sum(m[k] for m in miembros) for k in campos}
                    for miembros in paginas.values()
                ]
                if not lista:
                    continue
                resultado = agregar(lista)
                cer = resultado["cer"]
                ic = resultado["ic95_bootstrap_paginas"]["cer"]
                resumen.append(
                    {
                        "fuente": fuente,
                        "tipo_pagina": tipo_pagina,
                        "tipo": tipo,
                        **resultado,
                        "fidelidad_1_menos_cer": 1 - cer if cer is not None else None,
                        "fidelidad_ic95": [1 - ic[1], 1 - ic[0]] if ic else None,
                    }
                )
    return {
        "alcance": "Solo segmentos revisados. Selección crítica deliberada; no extrapolar fidelidad a todo el corpus. CER puede exceder 1 y fidelidad puede ser negativa. Sin referencia no vacía, CER/WER son nulos aunque se cuentan inserciones.",
        "filas_revisadas": len(referencias),
        "filas_pendientes": pendientes,
        "referencia_verificada_segmentos": referencias,
        "resumen": resumen,
        "tasa_error_lineas_control": {
            k: {"controles": len(v), "errores": sum(v), "tasa": sum(v) / len(v)}
            for k, v in controles.items()
        },
        "controles_todas_fuentes_erradas": sum(
            r["tipo"] == "control" and r["quien_acierta"] == "ninguna" for r in referencias
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv", nargs="?", type=Path, default=BASE / "resultados" / "desacuerdos.csv"
    )
    parser.add_argument("--salida", type=Path, default=BASE / "resultados" / "error_real.json")
    parser.add_argument("--permitir-incompleto", action="store_true")
    args = parser.parse_args()
    with args.csv.open(encoding="utf-8-sig", newline="") as archivo:
        filas = list(csv.DictReader(archivo))
    try:
        resultado = evaluar(filas, args.permitir_incompleto)
    except ValueError as error:
        parser.error(str(error))
    guardar_json(args.salida, resultado)
    print(
        json.dumps(
            {
                "filas_revisadas": resultado["filas_revisadas"],
                "filas_pendientes": resultado["filas_pendientes"],
            }
        )
    )


if __name__ == "__main__":
    main()
