"""C1/3.2 — límite de concurrencia global de proceso para operaciones bcrypt.

``rag.api.passwords`` expone un único semáforo module-level
(``_password_hash_semaphore``, dimensionado por ``PASSWORD_HASH_MAX_CONCURRENT``
— ver ``rag.config``), reutilizado por ``hash_password_async`` y
``verify_password_async``: cubre automáticamente los cinco sitios de llamada
existentes (login, registro, alta de usuario admin, cambio de contraseña
admin, re-hash oportunista) sin que ninguno gestione su propia limitación.

Este archivo prueba el semáforo en sí — que ninguna ejecución concurrente
supera el límite configurado, y que sí permite hasta ese límite en paralelo
(no lo serializa de más) — reemplazándolo por uno de tamaño conocido vía
monkeypatch, ya que el semáforo real se crea una sola vez al importar el
módulo con el valor de ``PASSWORD_HASH_MAX_CONCURRENT`` vigente en ese
momento. ``hash_password`` y ``verify_password`` en sí (síncronas) no
cambian: ver ``test_passwords.py``. Ninguna contraseña de este archivo es
real.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable

import pytest

import rag.api.passwords as passwords_module
from rag.api.passwords import hash_password, hash_password_async, verify_password_async


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _install_tracked_hash_password(
    monkeypatch: pytest.MonkeyPatch, state: dict[str, int], state_lock: threading.Lock
) -> None:
    """Sustituye ``hash_password`` (síncrona, la que corre dentro de
    ``asyncio.to_thread``) por una variante que cuenta cuántas invocaciones
    están en vuelo SIMULTÁNEAMENTE, protegido por un ``threading.Lock`` real
    — el conteo se incrementa/decrementa desde hilos de un thread pool, no
    desde el event loop, así que un `int` sin lock sería una carrera real, no
    solo teórica."""
    original_hash_password = passwords_module.hash_password

    def _tracked(password: str) -> str:
        with state_lock:
            state["in_flight"] += 1
            state["max_observed"] = max(state["max_observed"], state["in_flight"])
        try:
            time.sleep(0.05)  # suficiente para que varias tareas se solapen
            return original_hash_password(password)
        finally:
            with state_lock:
                state["in_flight"] -= 1

    monkeypatch.setattr(passwords_module, "hash_password", _tracked)


@pytest.mark.anyio
async def test_concurrent_hash_operations_never_exceed_the_configured_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 2
    monkeypatch.setattr(passwords_module, "_password_hash_semaphore", asyncio.Semaphore(limit))
    state = {"in_flight": 0, "max_observed": 0}
    state_lock = threading.Lock()
    _install_tracked_hash_password(monkeypatch, state, state_lock)

    await asyncio.gather(*[hash_password_async(f"contraseña-concurrencia-{i}") for i in range(6)])

    assert state["max_observed"] <= limit, (
        f"se observaron {state['max_observed']} operaciones bcrypt simultáneas, "
        f"más que el límite configurado ({limit})"
    )


@pytest.mark.anyio
async def test_the_limit_permits_up_to_n_in_parallel_not_just_one_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirma que el semáforo no serializa de más: con margen suficiente de
    tareas concurrentes, la concurrencia observada debe LLEGAR al límite, no
    solo mantenerse por debajo de él por casualidad de scheduling."""
    limit = 3
    monkeypatch.setattr(passwords_module, "_password_hash_semaphore", asyncio.Semaphore(limit))
    state = {"in_flight": 0, "max_observed": 0}
    state_lock = threading.Lock()
    _install_tracked_hash_password(monkeypatch, state, state_lock)

    await asyncio.gather(*[hash_password_async(f"contraseña-paralela-{i}") for i in range(9)])

    assert state["max_observed"] == limit


@pytest.mark.anyio
async def test_hash_and_verify_share_the_same_semaphore_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El límite es sobre el TOTAL de operaciones bcrypt en vuelo — hash y
    verify combinados comparten un único presupuesto, no uno independiente
    cada uno."""
    limit = 2
    monkeypatch.setattr(passwords_module, "_password_hash_semaphore", asyncio.Semaphore(limit))
    state = {"in_flight": 0, "max_observed": 0}
    state_lock = threading.Lock()
    original_verify_password = passwords_module.verify_password

    def _tracked_verify(password: str, hashed: str) -> bool:
        with state_lock:
            state["in_flight"] += 1
            state["max_observed"] = max(state["max_observed"], state["in_flight"])
        try:
            time.sleep(0.05)
            return original_verify_password(password, hashed)
        finally:
            with state_lock:
                state["in_flight"] -= 1

    monkeypatch.setattr(passwords_module, "verify_password", _tracked_verify)
    _install_tracked_hash_password(monkeypatch, state, state_lock)

    precomputed_hash = hash_password("contraseña-mixta-precomputada")
    await asyncio.gather(
        *[hash_password_async(f"contraseña-mixta-{i}") for i in range(3)],
        *[
            verify_password_async("contraseña-mixta-precomputada", precomputed_hash)
            for _ in range(3)
        ],
    )

    assert state["max_observed"] <= limit


@pytest.mark.anyio
async def test_event_loop_stays_responsive_under_the_semaphore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con el semáforo real (no sustituido) y su límite por defecto, el event
    loop debe seguir atendiendo otras tareas mientras varias operaciones
    bcrypt están en vuelo — el semáforo (``asyncio.Semaphore``) es en sí un
    primitivo async no bloqueante; esto confirma que envolver
    ``asyncio.to_thread`` con él no reintroduce bloqueo del loop."""
    progress = 0
    stop = False

    async def _ticker() -> None:
        nonlocal progress
        while not stop:
            await asyncio.sleep(0)
            progress += 1

    ticker_task = asyncio.ensure_future(_ticker())
    await asyncio.gather(*[hash_password_async(f"contraseña-loop-{i}") for i in range(4)])
    stop = True
    await ticker_task

    assert progress > 0, "el event loop no avanzó ninguna otra tarea durante el hashing"


# ---------------------------------------------------------------------------
# v1.2/C1 — el cupo del semáforo sigue ocupado hasta que el trabajo en el
# hilo TERMINA de verdad, no hasta que el llamador se cancela.
#
# Antes: `async with _password_hash_semaphore: await asyncio.to_thread(...)`
# libera el semáforo en cuanto la cancelación desenrolla el `async with` —
# pero el hilo ya lanzado por `to_thread` sigue corriendo (no se puede
# cancelar un hilo en curso). Una segunda solicitud puede entonces ocupar el
# cupo liberado mientras el trabajo cancelado todavía consume CPU real,
# superando el límite configurado de operaciones bcrypt simultáneas.
#
# Estas pruebas usan únicamente eventos (``asyncio.Event``/``threading.Event``)
# para sincronizar — cero ``sleep`` de coordinación: cada paso avanza solo
# cuando el paso anterior señaliza explícitamente que ocurrió.
# ---------------------------------------------------------------------------


def _controlled_sync_op(
    loop: asyncio.AbstractEventLoop,
    entered: asyncio.Event,
    release: threading.Event,
    *,
    raise_error: bool = False,
) -> Callable[[str], str]:
    """Función síncrona (la que corre dentro de ``asyncio.to_thread``) que se
    detiene deterministamente hasta que el test la libera. Señaliza que
    "entró" mediante ``loop.call_soon_threadsafe`` — se ejecuta en el hilo del
    thread pool, así que tocar un ``asyncio.Event`` directamente desde ahí no
    sería seguro sin pasar por el loop."""

    def _op(password: str) -> str:
        loop.call_soon_threadsafe(entered.set)
        release.wait(timeout=5)
        if raise_error:
            raise RuntimeError("fallo simulado tras la cancelación del llamador")
        return f"resultado-{password}"

    return _op


@pytest.mark.anyio
async def test_cancelling_the_caller_keeps_the_slot_held_until_the_background_work_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(passwords_module, "_password_hash_semaphore", asyncio.Semaphore(1))

    first_entered = asyncio.Event()
    first_release = threading.Event()
    second_entered = asyncio.Event()
    second_release = threading.Event()

    def _dispatch(password: str) -> str:
        if password == "first":
            return _controlled_sync_op(loop, first_entered, first_release)(password)
        return _controlled_sync_op(loop, second_entered, second_release)(password)

    monkeypatch.setattr(passwords_module, "hash_password", _dispatch)

    # 3) Primera operación: iniciar y confirmar que realmente entró al hilo.
    first_task = asyncio.ensure_future(hash_password_async("first"))
    await first_entered.wait()

    # 4) Cancelar al llamador y esperarlo — la cancelación debe completarse
    #    (8: visible para el llamador) SIN que el hilo de "first" haya
    #    terminado todavía (sigue bloqueado en `first_release`).
    first_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first_task

    # 5) Iniciar una segunda operación ANTES de liberar la primera.
    second_task = asyncio.ensure_future(hash_password_async("second"))

    # 6) Con el límite en 1 y el trabajo de "first" aún en curso, "second" no
    #    debe poder entrar al hilo todavía. Con la implementación corregida
    #    esto nunca ocurre dentro de esta ventana — no es una apuesta por una
    #    coincidencia de scheduling, es una propiedad garantizada mientras
    #    `first_release` siga sin activarse.
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(second_entered.wait(), timeout=0.3)
    assert not second_task.done()
    assert passwords_module._password_hash_semaphore.locked()

    # 7) Liberar la primera, dejar que la segunda progrese y termine, y
    #    confirmar que el semáforo recuperó su capacidad.
    first_release.set()
    await second_entered.wait()
    second_release.set()
    result = await second_task

    assert result == "resultado-second"
    assert not passwords_module._password_hash_semaphore.locked()


@pytest.mark.anyio
async def test_a_cancelled_callers_background_exception_is_not_leaked_as_unretrieved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si el trabajo de un llamador ya cancelado termina en excepción, esa
    excepción debe quedar recuperada internamente — de lo contrario asyncio
    reporta "Task exception was never retrieved" (vía el manejador de
    excepciones del loop) para una Task que nadie más está observando."""
    import gc

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(passwords_module, "_password_hash_semaphore", asyncio.Semaphore(1))

    entered = asyncio.Event()
    release = threading.Event()
    monkeypatch.setattr(
        passwords_module,
        "hash_password",
        _controlled_sync_op(loop, entered, release, raise_error=True),
    )

    unhandled: list[dict] = []
    previous_handler = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: unhandled.append(context))
    try:
        task = asyncio.ensure_future(hash_password_async("contraseña-cancelada-con-fallo"))
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        del task
        gc.collect()

        release.set()
        # Recorre el semáforo hasta que el callback de finalización de la
        # Task interna corrió (lo señaliza liberando el cupo) — un evento
        # real, no un tiempo fijo: el bucle solo cede el control del loop
        # (`sleep(0)`) para permitir que ese callback, ya encolado, se
        # ejecute; no espera una duración arbitraria para "que coincida".
        for _ in range(1000):
            if not passwords_module._password_hash_semaphore.locked():
                break
            await asyncio.sleep(0)
        assert not passwords_module._password_hash_semaphore.locked()
        gc.collect()
    finally:
        loop.set_exception_handler(previous_handler)

    assert unhandled == [], f"excepción de fondo no recuperada: {unhandled}"
