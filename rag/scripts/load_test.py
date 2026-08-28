"""Prueba de carga: N usuarios concurrentes contra ``/api/query/stream``.

Apunta al endpoint SSE (el que realmente usa el frontend) en vez del
endpoint JSON no-streaming, para reflejar el tráfico real de usuarios.

**Sin URL por defecto.** ``--url`` es obligatorio: este script ya no trae
hardcodeada la URL del ALB de producción. Apuntar a un host que no sea local
(``localhost`` / ``127.0.0.1`` / ``0.0.0.0`` / ``::1``) requiere además
``--allow-remote`` y, en una terminal interactiva, escribir el host exacto
como confirmación (igual que ``utils/chroma_clear.py``); en ejecución no
interactiva contra un host remoto se cancela sin preguntar, porque no hay
forma de confirmar con seguridad que se quiere generar tráfico real contra
ese destino.

**Credencial explícita.** ``/api/query/stream`` exige autenticación JWT
(``get_query_user`` → ``get_current_user`` en ``rag/backend/rag/api/main.py``
y ``rate_limit.py``); la versión anterior de este script nunca envió un
``Authorization`` header, así que toda petición habría fallado con 401 contra
el backend real. El token se lee de la variable de entorno
``RAG_LOAD_TEST_TOKEN`` (recomendado — no queda en el historial de la shell)
o de ``--token`` si no hay alternativa. Sin ninguno de los dos, el script se
detiene con un mensaje claro en vez de reportar en silencio una tanda de
errores 401; ``--allow-unauthenticated`` permite continuar sin token para
casos excepcionales (p. ej. un backend de prueba sin auth habilitada).

**"Primera fracción de respuesta", no "primer token".** El backend no
transmite tokens incrementales mientras el LLM genera: calcula la respuesta
completa y luego la trocea en fragmentos de 120 caracteres que emite en un
bucle sin pausas (ver ``query_stream`` en ``rag/backend/rag/api/main.py``).
Por eso el tiempo hasta el primer fragmento — antes llamado "primer token" en
este script, lo cual sugería una latencia de streaming incremental que el
backend no ofrece — es, en la práctica, casi idéntico al tiempo de respuesta
total. Se reporta aquí como ``primera_fraccion_respuesta`` para no inducir a
error. El único indicador de progreso genuinamente temprano que expone el
backend es el primer evento ``status`` (cambio de etapa del grafo LangGraph),
reportado como ``primer_evento_estado``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from collections.abc import Callable
from urllib.parse import urlparse

import httpx

PREGUNTAS = [
    "¿Qué dice el Consejo de Estado sobre el dominio público marítimo-terrestre?",
    "¿Cuáles son los requisitos para obtener una concesión de playa en Colombia?",
    "¿Cómo se define la línea de más alta marea en la normativa colombiana?",
    "¿Qué sanciones existen por construir en zona de playa sin permiso?",
    "¿Quién administra las playas en Colombia y bajo qué marco normativo?",
]

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _describe_error(e: Exception) -> str:
    """repr en vez de str: las excepciones de timeout de httpx no traen mensaje."""
    return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def _is_local(url: str) -> bool:
    return (urlparse(url).hostname or "") in _LOCAL_HOSTS


def confirm_remote_target(
    url: str,
    *,
    allow_remote: bool,
    interactive: bool,
    read_input: Callable[[str], str] = input,
) -> bool:
    """Autoriza generar tráfico real contra un host que no es local.

    Un host local siempre se autoriza (uso de desarrollo habitual). Para
    cualquier otro host: se cancela sin preguntar si falta ``--allow-remote``
    o si la ejecución no es interactiva (sin terminal disponible para
    confirmar con seguridad); si ambas condiciones se cumplen, exige escribir
    el host exacto como confirmación.
    """
    if _is_local(url):
        return True

    host = urlparse(url).hostname or url

    if not allow_remote:
        print(
            f"'{host}' no es un host local y falta --allow-remote. "
            "Operación cancelada para evitar generar tráfico de carga contra "
            "un destino remoto (posiblemente producción) sin intención explícita."
        )
        return False

    if not interactive:
        print(
            "Ejecución no interactiva contra un host remoto: no es posible "
            "confirmar con seguridad. Operación cancelada."
        )
        return False

    respuesta = read_input(
        f"\nEsto enviará tráfico de carga real a '{host}'. Escribe el host exacto para confirmar: "
    ).strip()
    if respuesta != host:
        print("La confirmación no coincide con el host. Operación cancelada.")
        return False
    return True


def _resolve_token(cli_token: str | None, *, allow_unauthenticated: bool) -> str | None:
    token = cli_token or os.getenv("RAG_LOAD_TEST_TOKEN") or None
    if token:
        return token
    if allow_unauthenticated:
        print(
            "Sin token (--allow-unauthenticated): las peticiones se enviarán "
            "sin Authorization. Si el backend exige autenticación, se espera "
            "que todas fallen con 401."
        )
        return None
    print(
        "Falta credencial: define RAG_LOAD_TEST_TOKEN (recomendado) o pasa "
        "--token. El endpoint /api/query/stream exige autenticación JWT; sin "
        "un token válido, toda petición fallará con 401. Usa "
        "--allow-unauthenticated si de verdad quieres probar ese caso."
    )
    return None


def _percentiles(values: list[float]) -> dict[str, float]:
    """p50/p95/p99. Con un único valor, los tres percentiles son ese valor."""
    if not values:
        return {}
    if len(values) == 1:
        return {"p50": values[0], "p95": values[0], "p99": values[0]}
    ordenados = sorted(values)
    cuantiles = statistics.quantiles(ordenados, n=100, method="inclusive")
    return {"p50": cuantiles[49], "p95": cuantiles[94], "p99": cuantiles[98]}


async def usuario(
    n: int, client: httpx.AsyncClient, timeout: float, stream_url: str, token: str | None
) -> dict:
    pregunta = PREGUNTAS[n % len(PREGUNTAS)]
    inicio = time.perf_counter()
    primer_evento_estado: float | None = None
    primera_fraccion_respuesta: float | None = None
    completo = False
    error: str | None = None
    status: int | None = None

    headers = {"Authorization": f"Bearer {token}"} if token else {}

    try:
        async with client.stream(
            "POST",
            stream_url,
            json={"question": pregunta, "k": 4},
            headers=headers,
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
                    payload = line[len("data: ") :]
                    if payload == "[DONE]":
                        completo = True
                        break
                    if '"type": "status"' in payload and primer_evento_estado is None:
                        primer_evento_estado = ahora - inicio
                    if primera_fraccion_respuesta is None and '"type": "token"' in payload:
                        primera_fraccion_respuesta = ahora - inicio
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
        f"(1er evento status: {primer_evento_estado or 0:.1f}s, "
        f"1ra fracción resp.: {primera_fraccion_respuesta or 0:.1f}s)"
    )

    return {
        "usuario": n + 1,
        "status": status,
        "completo": completo,
        "elapsed": elapsed,
        "primer_evento_estado": primer_evento_estado,
        "primera_fraccion_respuesta": primera_fraccion_respuesta,
        "error": error,
    }


def _print_stats(nombre: str, valores: list[float]) -> None:
    if not valores:
        return
    p = _percentiles(valores)
    print(
        f"{nombre} — min: {min(valores):.1f}s | avg: {statistics.mean(valores):.1f}s | "
        f"p50: {p['p50']:.1f}s | p95: {p['p95']:.1f}s | p99: {p['p99']:.1f}s | "
        f"max: {max(valores):.1f}s"
    )


async def main(
    n_usuarios: int,
    timeout: float,
    stream_url: str,
    token: str | None,
) -> int:
    rate_limit_mode = os.getenv("RAG_RATE_LIMIT_MODE", "off")

    print(f"Destino: {stream_url}")
    print(f"Usuarios concurrentes: {n_usuarios}")
    print(f"Timeout por usuario: {timeout:.0f}s")
    print(f"Autenticado: {'sí' if token else 'no'}")
    print(
        "RAG_RATE_LIMIT_MODE (entorno local de este script — puede no "
        f"reflejar la configuración real del servidor remoto): {rate_limit_mode}"
    )
    print("-" * 50)

    inicio_total = time.perf_counter()
    async with httpx.AsyncClient() as client:
        resultados = await asyncio.gather(
            *[usuario(i, client, timeout, stream_url, token) for i in range(n_usuarios)]
        )
    total = time.perf_counter() - inicio_total

    exitosos = [r for r in resultados if r["completo"]]
    tiempos = [r["elapsed"] for r in exitosos]
    fracciones = [
        r["primera_fraccion_respuesta"] for r in exitosos if r["primera_fraccion_respuesta"]
    ]

    print("-" * 50)
    print(f"Completado en {total:.1f}s")
    print(f"Exitosos: {len(exitosos)}/{n_usuarios}")
    _print_stats("Tiempo total respuesta", tiempos)
    _print_stats(
        "Tiempo a 1ra fracción de respuesta (≈ latencia total, no streaming real)", fracciones
    )

    fallidos = [r for r in resultados if not r["completo"]]
    if fallidos:
        print("Fallidos:")
        for r in fallidos:
            print(f"  Usuario {r['usuario']}: {r['error'] or 'sin [DONE] antes del timeout'}")

    return 0 if not fallidos else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL base del backend (p. ej. http://localhost:8080). Sin valor por defecto.",
    )
    parser.add_argument("-u", "--users", type=int, default=5, help="usuarios concurrentes")
    parser.add_argument(
        "-t", "--timeout", type=float, default=120, help="timeout por usuario (segundos)"
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Token JWT (Bearer). Preferir la variable de entorno RAG_LOAD_TEST_TOKEN.",
    )
    parser.add_argument(
        "--allow-unauthenticated",
        action="store_true",
        help="Permite continuar sin token pese a que el endpoint exige autenticación.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permite apuntar a un host que no es local (requiere confirmación exacta).",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    stream_url = f"{args.url.rstrip('/')}/api/query/stream"

    if not confirm_remote_target(
        args.url, allow_remote=args.allow_remote, interactive=sys.stdin.isatty()
    ):
        return 1

    token = _resolve_token(args.token, allow_unauthenticated=args.allow_unauthenticated)
    if token is None and not args.allow_unauthenticated:
        return 1

    return asyncio.run(main(args.users, args.timeout, stream_url, token))


if __name__ == "__main__":
    sys.exit(run_cli())
