"""Prueba de carga: N usuarios concurrentes contra /api/query/stream en ECS.

Apunta al endpoint SSE (el que realmente usa el frontend) en vez del
endpoint JSON no-streaming, para reflejar el tráfico real de usuarios.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

BASE_URL = "http://rag-playas-prod-alb-2093113268.us-east-1.elb.amazonaws.com"
STREAM_URL = f"{BASE_URL}/api/query/stream"

PREGUNTAS = [
    "¿Qué dice el Consejo de Estado sobre el dominio público marítimo-terrestre?",
    "¿Cuáles son los requisitos para obtener una concesión de playa en Colombia?",
    "¿Cómo se define la línea de más alta marea en la normativa colombiana?",
    "¿Qué sanciones existen por construir en zona de playa sin permiso?",
    "¿Quién administra las playas en Colombia y bajo qué marco normativo?",
]


def _describe_error(e: Exception) -> str:
    """repr en vez de str: las excepciones de timeout de httpx no traen mensaje."""
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


async def usuario(n: int, client: httpx.AsyncClient, timeout: float) -> dict:
    pregunta = PREGUNTAS[n % len(PREGUNTAS)]
    inicio = time.perf_counter()
    primer_evento: float | None = None
    primer_token: float | None = None
    completo = False
    error: str | None = None
    status: int | None = None

    try:
        async with client.stream(
            "POST",
            STREAM_URL,
            json={"question": pregunta, "k": 4},
            timeout=timeout,
        ) as r:
            status = r.status_code
            if status != 200:
                error = f"HTTP {status}"
            else:
                async for line in r.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    ahora = time.perf_counter()
                    if primer_evento is None:
                        primer_evento = ahora - inicio
                    payload = line[len("data: ") :]
                    if payload == "[DONE]":
                        completo = True
                        break
                    if primer_token is None and '"type": "token"' in payload:
                        primer_token = ahora - inicio
                    if '"type": "error"' in payload:
                        error = payload[:200]
                        break
    except Exception as e:
        error = _describe_error(e)

    elapsed = time.perf_counter() - inicio

    if completo:
        estado = "OK"
    elif error:
        estado = f"ERROR ({error})"
    else:
        estado = "INCOMPLETO (cortado sin [DONE] ni error)"

    print(
        f"  Usuario {n + 1}: {estado} — total {elapsed:.1f}s "
        f"(1er evento: {primer_evento or 0:.1f}s, 1er token: {primer_token or 0:.1f}s)"
    )

    return {
        "usuario": n + 1,
        "status": status,
        "completo": completo,
        "elapsed": elapsed,
        "primer_evento": primer_evento,
        "primer_token": primer_token,
        "error": error,
    }


async def main(n_usuarios: int, timeout: float) -> None:
    print(f"Destino: {STREAM_URL}")
    print(f"Usuarios concurrentes: {n_usuarios}")
    print(f"Timeout por usuario: {timeout:.0f}s")
    print("-" * 50)

    inicio_total = time.perf_counter()
    async with httpx.AsyncClient() as client:
        resultados = await asyncio.gather(
            *[usuario(i, client, timeout) for i in range(n_usuarios)]
        )
    total = time.perf_counter() - inicio_total

    exitosos = [r for r in resultados if r["completo"]]
    tiempos = [r["elapsed"] for r in exitosos]
    primeros_tokens = [r["primer_token"] for r in exitosos if r["primer_token"]]

    print("-" * 50)
    print(f"Completado en {total:.1f}s")
    print(f"Exitosos: {len(exitosos)}/{n_usuarios}")
    if tiempos:
        print(
            f"Tiempo total respuesta — min: {min(tiempos):.1f}s | "
            f"avg: {statistics.mean(tiempos):.1f}s | max: {max(tiempos):.1f}s"
        )
    if primeros_tokens:
        print(
            f"Tiempo al primer token — min: {min(primeros_tokens):.1f}s | "
            f"avg: {statistics.mean(primeros_tokens):.1f}s | "
            f"max: {max(primeros_tokens):.1f}s"
        )
    fallidos = [r for r in resultados if not r["completo"]]
    if fallidos:
        print("Fallidos:")
        for r in fallidos:
            print(f"  Usuario {r['usuario']}: {r['error'] or 'sin [DONE] antes del timeout'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-u", "--users", type=int, default=5, help="usuarios concurrentes")
    parser.add_argument(
        "-t", "--timeout", type=float, default=120, help="timeout por usuario (segundos)"
    )
    args = parser.parse_args()
    asyncio.run(main(args.users, args.timeout))
