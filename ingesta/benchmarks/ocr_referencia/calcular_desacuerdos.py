"""Estima errores condicionados a los desacuerdos adjudicados; nunca error global.

Veredicto A/B = solo esa variante correcta; ambos = ambas correctas; ninguno =
ambas erróneas. Los vacíos quedan pendientes. La clave permanece separada.
"""

from __future__ import annotations

import argparse
import importlib.util
import random
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("comun", BASE / "comun.py")
c = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c)
e = c.modulo("estadistica")


def calcular(filas, clave, *, repeticiones=2000):
    ids = [f["id"] for f in filas]
    if len(ids) != len(set(ids)):
        raise ValueError("IDs duplicados en desacuerdos")
    claves = {f["id"]: f["quien_es_A"] for f in clave}
    if len(claves) != len(clave) or set(claves) != set(ids) or set(claves.values()) - {"S", "U"}:
        raise ValueError(
            "La clave no coincide exactamente con los IDs o contiene fuentes inválidas"
        )
    revisadas = []
    for fila in filas:
        veredicto = fila.get("veredicto", "").strip()
        if veredicto not in {"", "A", "B", "ambos", "ninguno"}:
            raise ValueError("Veredicto inválido: " + veredicto)
        if not veredicto:
            continue
        s_es_a = claves[fila["id"]] == "S"
        correcto_s = veredicto == "ambos" or veredicto == ("A" if s_es_a else "B")
        correcto_u = veredicto == "ambos" or veredicto == ("B" if s_es_a else "A")
        revisadas.append({**fila, "error_s": not correcto_s, "error_u": not correcto_u})

    def estimar(datos):
        n = len(datos)
        ns, nu = sum(f["error_s"] for f in datos), sum(f["error_u"] for f in datos)
        solo_s = sum(f["error_s"] and not f["error_u"] for f in datos)
        solo_u = sum(f["error_u"] and not f["error_s"] for f in datos)
        return {
            "error_S": ns / n if n else None,
            "error_U": nu / n if n else None,
            "fraccion_solo_S": solo_s / n if n else None,
            "fraccion_solo_U": solo_u / n if n else None,
            "fraccion_ambos_erroneos": sum(f["error_s"] and f["error_u"] for f in datos) / n
            if n
            else None,
            "fraccion_ambos_correctos": sum(not f["error_s"] and not f["error_u"] for f in datos)
            / n
            if n
            else None,
            "fraccion_U_entre_errores_atribuidos": nu / (ns + nu) if ns + nu else None,
            "fraccion_U_entre_errores_unilaterales": solo_u / (solo_s + solo_u)
            if solo_s + solo_u
            else None,
        }

    punto = estimar(revisadas)
    muestras = {k: [] for k in punto}
    estratos = defaultdict(list)
    for fila in revisadas:
        estratos[(fila["tipo_pagina"], fila.get("muestreo", ""))].append(fila)
    rng = random.Random(e.SEMILLA)
    if revisadas:
        for _ in range(repeticiones):
            muestra = [f for grupo in estratos.values() for f in rng.choices(grupo, k=len(grupo))]
            for k, v in estimar(muestra).items():
                muestras[k].append(v)
    return {
        "estado": "pendiente" if not revisadas else "estimado",
        "total": len(filas),
        "adjudicados": len(revisadas),
        "pendientes": len(filas) - len(revisadas),
        "veredictos": dict(Counter(f["veredicto"].strip() for f in revisadas)),
        "estimaciones": punto,
        "ic95": {k: e.ic(v) for k, v in muestras.items()},
        "semilla": e.SEMILLA,
        "repeticiones": repeticiones,
        "alcance": "Probabilidades por segmento condicionado a esta muestra estratificada de desacuerdos adjudicados; no CER/WER ni error global del corpus. Sin extrapolación a pendientes. Bootstrap dentro de tipo/prioridad; una página por segmento en la muestra generada. Ambos erróneos cuenta para ambas fuentes en fracción entre errores atribuidos.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entrada", type=Path, default=BASE / "resultados/fase3/desacuerdos.csv")
    parser.add_argument(
        "--clave", type=Path, default=BASE / "resultados/fase3/clave_desacuerdos.csv"
    )
    parser.add_argument(
        "--salida", type=Path, default=BASE / "resultados/fase3/evaluacion_desacuerdos.json"
    )
    args = parser.parse_args()
    resultado = calcular(c.csv_leer(args.entrada), c.csv_leer(args.clave))
    c.json_guardar(args.salida, resultado)
    print(
        f"Desacuerdos: {resultado['adjudicados']} adjudicados, {resultado['pendientes']} pendientes."
    )


if __name__ == "__main__":
    main()
