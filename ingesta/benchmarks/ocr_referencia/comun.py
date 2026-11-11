"""Utilidades locales. Escritura limitada al benchmark, excepto entrada/."""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import os
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent


def modulo(nombre):
    spec = importlib.util.spec_from_file_location(nombre, BASE / (nombre + ".py"))
    resultado = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resultado)
    return resultado


def destino(ruta):
    ruta = Path(ruta).resolve()
    if not ruta.is_relative_to(BASE) or ruta.is_relative_to(BASE / "entrada"):
        raise ValueError("Escritura fuera del benchmark o dentro de entrada")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    return ruta


def json_guardar(ruta, datos):
    destino(ruta).write_text(
        json.dumps(datos, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


def csv_leer(ruta):
    # Los faltantes críticos de documentos largos superan el límite por defecto
    # de 128 KiB; límite explícito y finito, sin evaluar contenido de las celdas.
    csv.field_size_limit(64 * 1024 * 1024)
    with Path(ruta).open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def csv_guardar(ruta, filas, campos=None):
    filas = list(filas)
    campos = campos or list(dict.fromkeys(k for f in filas for k in f))
    ruta = destino(ruta)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=ruta.parent,
            prefix=f".{ruta.name}.",
            suffix=".tmp",
            delete=False,
        ) as f:
            temporal = Path(f.name)
            w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
            w.writeheader()
            for fila in filas:
                w.writerow(
                    {
                        k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                        for k, v in fila.items()
                    }
                )
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, ruta)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)


def huella(ruta):
    return hashlib.sha256(Path(ruta).read_bytes()).hexdigest()
