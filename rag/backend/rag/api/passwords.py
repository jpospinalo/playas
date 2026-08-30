"""Servicio único de hashing de contraseñas para login y administración.

Formatos de ``password_hash`` reconocidos por :func:`verify_password`, en el
orden en que se intentan:

  1. **Actual** (``_CURRENT_PREFIX`` + hash bcrypt del pre-hash SHA-256):
     formato producido por :func:`hash_password` desde que existe este
     prefijo. Identificable sin ambigüedad por el prefijo — un único intento
     de verificación, sin tanteo.
  2. **Heredado, pre-hash** (hash bcrypt del pre-hash SHA-256, sin prefijo):
     lo que producía :func:`hash_password` antes de introducir el prefijo.
     Formato indistinguible de (3) por estructura — ambos son un string
     bcrypt puro (``$2b$...``) — por eso se tantea antes que (3).
  3. **Heredado, bcrypt directo** (bcrypt aplicado directamente sobre la
     contraseña, sin pre-hash SHA-256, sin prefijo): lo que producían
     versiones anteriores del endpoint admin.

Ningún hash existente deja de funcionar: el prefijo solo marca los hashes
*nuevos* (o los que se re-hashean oportunistamente tras un login exitoso con
un hash heredado — ver :func:`needs_rehash`) para que futuras verificaciones
de esos ya no necesiten tantear los tres formatos.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable

import bcrypt

from rag.config import PASSWORD_HASH_MAX_CONCURRENT

#: Prefijo que marca un hash producido por el esquema actual. No puede
#: colisionar con ningún hash bcrypt real (que siempre empieza con
#: ``$2a$``/``$2b$``/``$2y$``) ni con un hash heredado de este servicio (que
#: es directamente ese string bcrypt, sin nada antepuesto).
_CURRENT_PREFIX = "v2:"

#: Límite de concurrencia global de proceso para operaciones bcrypt (ver
#: ``PASSWORD_HASH_MAX_CONCURRENT`` en ``rag.config``). Un único semáforo de
#: módulo, reutilizado por ambas variantes async de abajo — cubre
#: automáticamente todos sus llamadores (login, registro, alta de usuario
#: admin, cambio de contraseña admin, re-hash oportunista) sin que cada uno
#: tenga que gestionar su propia limitación.
_password_hash_semaphore = asyncio.Semaphore(PASSWORD_HASH_MAX_CONCURRENT)


def hash_password(password: str) -> str:
    """Pre-hashea con SHA-256, aplica bcrypt y antepone el prefijo actual.

    El pre-hash mantiene compatibilidad con todas las cuentas creadas por el
    flujo de login existente y evita el límite de 72 bytes de bcrypt. El
    prefijo (``_CURRENT_PREFIX``) marca el resultado como formato actual,
    para que :func:`verify_password` no tenga que tantear formatos heredados
    en un hash ya conocido como actual.

    Síncrona y bloqueante (bcrypt es intencionalmente costoso en CPU). Los
    endpoints async deben usar :func:`hash_password_async` en su lugar para
    no bloquear el event loop; esta variante síncrona se mantiene para
    scripts y pruebas que no corren dentro de un loop async.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    bcrypt_hash = bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")
    return f"{_CURRENT_PREFIX}{bcrypt_hash}"


def needs_rehash(hashed: str) -> bool:
    """``True`` si *hashed* es de un formato heredado (sin el prefijo actual).

    Predicado puro, sin efectos secundarios — no re-hashea nada por sí
    mismo. Uso previsto: tras un login exitoso con un hash heredado,
    decidir si conviene re-hashear oportunistamente la contraseña ya
    validada al formato actual.
    """
    return not hashed.startswith(_CURRENT_PREFIX)


def verify_password(password: str, hashed: str) -> bool:
    """Valida los tres formatos documentados en el docstring del módulo.

    Síncrona y bloqueante, por la misma razón que :func:`hash_password`. Los
    endpoints async deben usar :func:`verify_password_async`.
    """
    try:
        if not needs_rehash(hashed):
            # Formato actual: un único intento, sin ambigüedad de formato.
            digest = hashlib.sha256(password.encode("utf-8")).digest()
            encoded_hash = hashed[len(_CURRENT_PREFIX) :].encode("utf-8")
            return bcrypt.checkpw(digest, encoded_hash)

        # Heredado (sin prefijo): mismo tanteo de siempre, en el mismo orden
        # — pre-hash primero (el caso más común), bcrypt directo como
        # compatibilidad con el admin legado.
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        encoded_hash = hashed.encode("utf-8")
        if bcrypt.checkpw(digest, encoded_hash):
            return True
        return bcrypt.checkpw(password.encode("utf-8"), encoded_hash)
    except (TypeError, ValueError):
        return False


async def _run_with_hash_semaphore[T](func: Callable[..., T], *args: object) -> T:
    """Ejecuta ``func(*args)`` en un hilo aparte, bajo ``_password_hash_semaphore``,
    de forma segura ante la cancelación del llamador (v1.2/C1).

    ``async with _password_hash_semaphore: await asyncio.to_thread(...)`` (la
    forma anterior) tiene un defecto: al cancelar la coroutine que espera
    dentro de ese bloque, ``async with`` libera el semáforo INMEDIATAMENTE
    como parte del desenrollado de la cancelación — pero el trabajo síncrono
    ya entregado a ``asyncio.to_thread`` sigue corriendo en su hilo, porque un
    hilo en curso no puede cancelarse. El resultado es que el semáforo cuenta
    coroutines en espera, no operaciones bcrypt realmente en ejecución: una
    solicitud cancelada libera su cupo antes de que el hilo termine, y una
    nueva solicitud puede ocuparlo de inmediato — superando el límite real de
    operaciones bcrypt simultáneas exactamente cuando hay cancelaciones
    (p. ej. un cliente que cierra la conexión a mitad de un login).

    La corrección: el semáforo se adquiere ANTES de programar el trabajo (1);
    el trabajo se envuelve en una ``Task`` propia (``asyncio.ensure_future``)
    en vez de esperarse directamente, para que exista independientemente de
    quien la espera (2); se libera el semáforo en un callback de finalización
    de esa ``Task`` — atado a que el trabajo TERMINE de verdad, nunca a que el
    llamador se cancele (4); ese mismo callback llama a ``Task.exception()``
    (cuando corresponde) para que asyncio no reporte "Task exception was
    never retrieved" si nadie más vuelve a esperar esa ``Task`` (7); y se
    espera esa ``Task`` mediante ``asyncio.shield``, que protege el trabajo en
    curso de la cancelación del llamador pero SÍ deja que el propio llamador
    reciba su ``CancelledError`` con normalidad (3, 6) — y, si nadie cancela
    nada, ``shield`` simplemente entrega el resultado o relanza la excepción
    real del trabajo, sin ninguna diferencia de comportamiento (5).
    """
    await _password_hash_semaphore.acquire()
    task: asyncio.Task[T] = asyncio.ensure_future(asyncio.to_thread(func, *args))

    def _release(finished_task: asyncio.Task[T]) -> None:
        _password_hash_semaphore.release()
        if not finished_task.cancelled():
            # Marca la excepción (si la hubo) como recuperada, aunque el
            # llamador original ya no esté esperando esta Task — evita el
            # log espurio de asyncio por una excepción "nunca recogida".
            finished_task.exception()

    task.add_done_callback(_release)
    return await asyncio.shield(task)


async def hash_password_async(password: str) -> str:
    """Variante async de :func:`hash_password`.

    Ejecuta el hashing bcrypt (síncrono y deliberadamente costoso en CPU) en
    un hilo aparte vía ``asyncio.to_thread``, para no bloquear el event loop
    del proceso ASGI mientras se calcula. Mismo resultado y mismo formato de
    hash que la variante síncrona — solo cambia dónde se ejecuta el trabajo.

    Limitada por ``_password_hash_semaphore`` (``PASSWORD_HASH_MAX_CONCURRENT``,
    ver ``rag.config``): a lo sumo ese número de operaciones bcrypt corren a
    la vez en todo el proceso, para no saturar sus hilos bajo carga
    concurrente alta — incluso si el llamador se cancela a mitad de camino
    (ver :func:`_run_with_hash_semaphore`).
    """
    return await _run_with_hash_semaphore(hash_password, password)


async def verify_password_async(password: str, hashed: str) -> bool:
    """Variante async de :func:`verify_password`, ver :func:`hash_password_async`.

    Comparte el mismo semáforo de concurrencia que :func:`hash_password_async`
    — el límite es sobre el total de operaciones bcrypt en vuelo (hash +
    verify combinados), no uno independiente por función.
    """
    return await _run_with_hash_semaphore(verify_password, password, hashed)
