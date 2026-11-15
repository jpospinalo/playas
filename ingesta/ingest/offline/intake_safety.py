"""Destinos, identidad y clasificación determinista de entradas no confiables."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from ..legal_metadata import identidad_normativa
from .extract import sha256_file
from .layers import canonical, key
from .storage import atomic_bytes

DESTINOS = Path(__file__).resolve().parents[2] / "config" / "intake_destinos.yaml"
PROTEGIDAS = {"v1", "atlas_v1", "rag_playas", "rag_playas_magdalena"}


class ConfiguracionInvalida(ValueError):
    """La configuración no autoriza este destino o estos límites."""


def _kernel_windows():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    for nombre, argumentos, resultado in (
        ("OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        ("CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
        ("GetExitCodeProcess", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        ("CreateJobObjectW", [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        (
            "SetInformationJobObject",
            [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD],
            wintypes.BOOL,
        ),
        ("AssignProcessToJobObject", [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
    ):
        funcion = getattr(kernel, nombre)
        funcion.argtypes, funcion.restype = argumentos, resultado
    return kernel


def pid_vivo(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("PID de worker inválido")
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = _kernel_windows()
        proceso = kernel.OpenProcess(0x1000, False, pid)  # Consulta limitada.
        if not proceso:
            if ctypes.get_last_error() == 87:  # ERROR_INVALID_PARAMETER: PID inexistente.
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            codigo = wintypes.DWORD()
            if not kernel.GetExitCodeProcess(proceso, ctypes.byref(codigo)):
                raise ctypes.WinError(ctypes.get_last_error())
            return codigo.value == 259  # STILL_ACTIVE.
        finally:
            kernel.CloseHandle(proceso)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def comprobar_worker(estado):
    registro = Path(estado) / "intake_worker.json"
    if registro.exists():
        pid = json.loads(registro.read_text(encoding="utf-8"))["pid"]
        if pid_vivo(pid):
            raise RuntimeError(
                f"El worker previo (PID {pid}) sigue vivo; el intake no escribirá. "
                "Espere a que termine antes de reiniciar."
            )


@contextmanager
def _job_windows():
    """El cierre del único handle del padre mata al worker y sus descendientes."""
    import ctypes
    from ctypes import wintypes

    class LimitesBasicos(ctypes.Structure):
        _fields_ = [
            ("tiempo_proceso", ctypes.c_longlong),
            ("tiempo_job", ctypes.c_longlong),
            ("flags", wintypes.DWORD),
            ("minimo", ctypes.c_size_t),
            ("maximo", ctypes.c_size_t),
            ("procesos", wintypes.DWORD),
            ("afinidad", ctypes.c_size_t),
            ("prioridad", wintypes.DWORD),
            ("planificacion", wintypes.DWORD),
        ]

    class LimitesExtendidos(ctypes.Structure):
        _fields_ = [
            ("basicos", LimitesBasicos),
            ("contadores_io", ctypes.c_ulonglong * 6),
            ("memoria_proceso", ctypes.c_size_t),
            ("memoria_job", ctypes.c_size_t),
            ("pico_proceso", ctypes.c_size_t),
            ("pico_job", ctypes.c_size_t),
        ]

    kernel = _kernel_windows()
    job = kernel.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        limites = LimitesExtendidos()
        limites.basicos.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        if not kernel.SetInformationJobObject(
            job, 9, ctypes.byref(limites), ctypes.sizeof(limites)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        def asignar(pid):
            proceso = kernel.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE.
            if not proceso:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                if not kernel.AssignProcessToJobObject(job, proceso):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                kernel.CloseHandle(proceso)

        yield asignar
    finally:
        kernel.CloseHandle(job)


@contextmanager
def worker_vinculado(comando, estado, **opciones):
    """Arranca sin permiso de escribir; registra y vincula antes de liberarlo."""
    from contextlib import ExitStack

    with ExitStack() as pila:
        asignar = None
        if os.name == "nt":
            asignar = pila.enter_context(_job_windows())
            opciones["creationflags"] = subprocess.CREATE_NO_WINDOW
        elif sys.platform.startswith("linux"):
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            padre = os.getpid()

            def al_morir_padre():
                if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:  # PR_SET_PDEATHSIG.
                    os._exit(1)
                # Cierra la carrera entre fork y prctl si el padre ya murió.
                if os.getppid() != padre:
                    os.kill(os.getpid(), signal.SIGKILL)

            opciones["preexec_fn"] = al_morir_padre
        registro = Path(estado) / "intake_worker.json"
        proceso = subprocess.Popen(
            comando,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **opciones,
        )
        try:
            if asignar:
                asignar(proceso.pid)
            atomic_bytes(registro, canonical({"pid": proceso.pid}))
            yield proceso
        finally:
            # También en timeout, Ctrl+C o error al registrar/asignar: esperar su
            # muerte antes de quitar el PID y soltar los bloqueos del intake.
            if proceso.poll() is None:
                proceso.kill()
            proceso.communicate()
            registro.unlink(missing_ok=True)


def loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def cargar_destinos(ruta=None):
    import yaml

    datos = yaml.safe_load(Path(ruta or DESTINOS).read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise ConfiguracionInvalida("Configuración de destinos inválida")
    for campo in (
        "colecciones_protegidas",
        "prefijos_permitidos",
        "hosts_chroma_permitidos",
        "hosts_protegidos",
    ):
        valores = datos.get(campo)
        if not isinstance(valores, list) or any(not isinstance(v, str) or not v for v in valores):
            raise ConfiguracionInvalida(f"Lista inválida: {campo}")
    prefijos = datos["prefijos_permitidos"]
    # Espacios de nombres propios del intake; atlas_demo_ es el del demo en el sandbox.
    espacios = ("atlas_intake_", "atlas_demo_", "bench_intake_")
    if not prefijos or any(not p.startswith(espacios) for p in prefijos):
        raise ConfiguracionInvalida("Prefijos permitidos fuera del espacio de intake")
    if not datos["hosts_chroma_permitidos"] or not all(
        loopback(h) for h in datos["hosts_chroma_permitidos"]
    ):
        raise ConfiguracionInvalida("Chroma solo permite hosts loopback")
    for campo in (
        "tamano_maximo_bytes",
        "paginas_maximas",
        "tiempo_maximo_documento_segundos",
        "memoria_maxima_mb",
        "simhash_palabras_shingle",
    ):
        valor = datos.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise ConfiguracionInvalida(f"Límite entero positivo requerido: {campo}")
    umbral = datos.get("simhash_umbral")
    if isinstance(umbral, bool) or not isinstance(umbral, int) or not 0 <= umbral <= 64:
        raise ConfiguracionInvalida("simhash_umbral debe estar entre 0 y 64")
    gancho = datos.get("gancho_notificacion")
    if gancho is not None and (not isinstance(gancho, str) or not gancho):
        raise ConfiguracionInvalida("gancho_notificacion debe ser una ruta de archivo")
    return datos


def validar_destino(coleccion, host, destinos, *, ficticios=False, port=8000):
    if not isinstance(coleccion, str) or not re.fullmatch(
        r"[a-zA-Z0-9_][a-zA-Z0-9_-]{1,490}", coleccion
    ):
        raise ConfiguracionInvalida("Nombre de colección inválido")
    # El sufijo de preparación está reservado: una colección viva «x__staging»
    # sería borrada al recrear la preparación de «x».
    if "__staging" in coleccion:
        raise ConfiguracionInvalida("Destino protegido: el sufijo __staging está reservado")
    for nombre in (coleccion, coleccion + "__staging"):
        if nombre in PROTEGIDAS | set(destinos["colecciones_protegidas"]) or not nombre.startswith(
            tuple(destinos["prefijos_permitidos"])
        ):
            raise ConfiguracionInvalida(f"Destino protegido: colección {nombre}")
    if (
        not loopback(host)
        or host not in destinos["hosts_chroma_permitidos"]
        or host in destinos["hosts_protegidos"]
        # El publicador usa siempre 127.0.0.1, incluidos los alias loopback.
        or "127.0.0.1" in destinos["hosts_protegidos"]
        or "127.0.0.1" not in destinos["hosts_chroma_permitidos"]
    ):
        raise ConfiguracionInvalida(
            f"Destino protegido: host Chroma {host}; solo loopback autorizado"
        )
    if ficticios and not coleccion.startswith("bench_"):
        raise ConfiguracionInvalida("--fake-embeddings requiere una colección bench_")
    if not 1 <= port <= 65535:
        raise ConfiguracionInvalida("Puerto Chroma inválido")


def nombre_visible(nombre, doc_id):
    """Nombre legible para los metadatos title/source; NUNCA para rutas de salida.

    Sin separadores, sin caracteres de control ni de formato (p. ej. RTL), sin
    puntos iniciales y con longitud acotada. Si no queda nada, usa el hash corto.
    El nombre solo se usa dentro de un directorio temporal privado del análisis.
    """
    base = unicodedata.normalize("NFC", str(nombre).replace("\\", "/").rsplit("/", 1)[-1])
    base = "".join(c for c in base if not unicodedata.category(c).startswith("C"))
    base = re.sub(r'[\/:*?"<>|]', " ", base)
    base = re.sub(r"\.pdf$", "", re.sub(r"\s+", " ", base).strip(), flags=re.I)
    base = base.strip(" .")[:120].encode("utf-8")[:176].decode("utf-8", errors="ignore").strip(" .")
    return (base or doc_id[:12]) + ".pdf"


def nombre_seguro(doc_id):
    """El nombre recibido nunca participa en una ruta de salida."""
    if not re.fullmatch(r"[0-9a-f]{64}", doc_id):
        raise ValueError("Identidad SHA-256 inválida")
    return doc_id + ".pdf"


def validar_raw(raiz, inbox):
    """Valida la excepción de escritura en raw sin crear ni copiar archivos."""
    raiz, inbox = Path(raiz).resolve(), Path(inbox).resolve()
    if raiz.is_relative_to(inbox) or inbox.is_relative_to(raiz):
        raise ValueError("raw-root e inbox deben ser independientes")
    partes = [p.casefold() for p in raiz.parts]
    if partes[-2:] == ["data", "documents"]:
        raise ValueError("raw-root no puede ser la raíz de capas v1")
    if any(
        partes[i : i + 3]
        in (
            ["data", "documents", "bronze"],
            ["data", "documents", "silver"],
            ["data", "documents", "gold"],
        )
        for i in range(len(partes) - 2)
    ):
        raise ValueError("raw-root no puede apuntar a capas v1")
    if len(str(raiz / nombre_seguro("0" * 64))) >= 240:
        raise ValueError("Ruta raw demasiado larga (máximo 239 caracteres)")
    return raiz


def copiar_raw(origen, raiz, doc_id, inbox):
    """Excepción acotada al raw autorizado: copia inmutable con nombre SHA-256.

    No relaja guard_output para ningún otro escritor ni permite tocar capas v1.
    """
    raiz = validar_raw(raiz, inbox)
    destino = raiz / nombre_seguro(doc_id)
    if len(str(destino)) >= 240 or destino.is_symlink():
        raise ValueError("Ruta raw insegura o demasiado larga (máximo 239 caracteres)")
    if sha256_file(origen) != doc_id:
        raise ValueError("La entrada cambió durante el procesamiento")
    if destino.exists():
        if sha256_file(destino) != doc_id:
            raise ValueError("La copia raw existente no coincide con su identidad")
        return destino
    raiz.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=raiz, prefix="intake-", suffix=".tmp", delete=False
        ) as salida:
            temporal = Path(salida.name)
            with Path(origen).open("rb") as entrada:
                for bloque in iter(lambda: entrada.read(1024 * 1024), b""):
                    salida.write(bloque)
            salida.flush()
            os.fsync(salida.fileno())
        if sha256_file(temporal) != doc_id:
            raise ValueError("La entrada cambi? durante la copia")
        os.replace(temporal, destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
    return destino


def clasificar(documento, manual=None):
    if manual:
        if manual not in {"normativa", "jurisprudencia"}:
            raise ValueError("Categoría manual inválida")
        return {"categoria": manual, "confianza": 1.0, "origen": "correccion_manual"}
    encabezado = key("\n".join(documento["raw_pages"][:2])[:12000])
    judicial = bool(
        re.search(
            r"consejo de estado|corte (?:constitucional|suprema)|tribunal (?:administrativo|superior)",
            encabezado,
        )
    )
    # Normativa solo por el encabezado propio de la norma (línea propia, SUIN o
    # Gestor Normativo). Una línea de cuerpo que empieza por «Ley 472 de 1998»
    # hacía dudosa una sentencia (prueba E2E). Sobre los 53 documentos: 39 bien,
    # 14 dudosas a revisión y 0 errores (antes 36, 17 y 0).
    texto = documento.get("original") or "\n\f\n".join(documento["raw_pages"])
    norma = identidad_normativa(texto) is not None
    clara = judicial != norma
    return {
        "categoria": "normativa" if norma and not judicial else "jurisprudencia",
        "confianza": 0.95 if clara else 0.0,
        "origen": "reglas_encabezado",
    }


def simhash_shingles(texto, palabras=3):
    tokens = re.findall(r"\w+", key(texto))
    shingles = [
        " ".join(tokens[i : i + palabras]) for i in range(max(1, len(tokens) - palabras + 1))
    ]
    pesos = [0] * 64
    for shingle, cuenta in Counter(shingles).items():
        valor = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            pesos[bit] += cuenta if valor & (1 << bit) else -cuenta
    return sum(1 << bit for bit, peso in enumerate(pesos) if peso > 0)
