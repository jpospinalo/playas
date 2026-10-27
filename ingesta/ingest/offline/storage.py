"""Escrituras atómicas sin cambios de mtime y exclusión de escritores locales."""

from __future__ import annotations

import hashlib
import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_INPUT = ContextVar("offline_input", default=None)


def guard_output(path, input_root=None):
    target = Path(path).resolve()
    source = Path(input_root or _INPUT.get()).resolve() if input_root or _INPUT.get() else None
    if source and (target.is_relative_to(source) or source.is_relative_to(target)):
        raise ValueError("Salida protegida: no escribir dentro de input/raw ni en sus ancestros")
    # Se comprueba la ruta léxica y la resuelta para cubrir enlaces y '..'.
    for candidate in (Path(path).absolute(), target):
        parts = [part.casefold() for part in candidate.parts]
        if parts[-2:] == ["data", "documents"]:
            raise ValueError("Salida protegida: raíz de capas v1/raw")
        for index in range(len(parts) - 2):
            if parts[index : index + 2] == ["data", "documents"] and parts[index + 2] in {
                "bronze",
                "silver",
                "gold",
                "raw",
            }:
                raise ValueError("Salida protegida: capas v1/raw de solo lectura")
    if target.exists() and target.is_dir():
        # Un enlace dentro de una salida ya existente puede apuntar a raw/v1.
        for directory, dirs, files in os.walk(target, followlinks=False):
            for name in dirs + files:
                entry = Path(directory) / name
                if entry.is_symlink():
                    resolved = entry.resolve()
                    if source and (
                        resolved.is_relative_to(source) or source.is_relative_to(resolved)
                    ):
                        raise ValueError("Salida protegida: enlace interno a input/raw")
    return target


@contextmanager
def input_scope(root):
    token = _INPUT.set(Path(root).resolve())
    try:
        yield
    finally:
        _INPUT.reset(token)


def atomic_bytes(path, content):
    path = guard_output(path)
    digest = hashlib.sha256(content).hexdigest()
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return digest


def _file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.digest()


@contextmanager
def atomic_stream(path):
    path = guard_output(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            yield stream
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        if not path.exists() or _file_hash(temporary) != _file_hash(path):
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def writer_lock(*directories):
    locks = []
    try:
        for directory in sorted({guard_output(p) for p in directories}):
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / ".writer.lock"
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                raise RuntimeError(f"Ya hay un escritor; comprobar el bloqueo {path}") from None
            os.close(descriptor)
            locks.append(path)
        yield
    finally:
        for path in reversed(locks):
            path.unlink(missing_ok=True)
