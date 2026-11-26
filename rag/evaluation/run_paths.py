"""Rutas de resultados por corrida de evaluación.

Cada corrida (por ejemplo, otro modelo generador) escribe en archivos con una
etiqueta propia, para no sobrescribir la línea base sin etiqueta.
"""

from __future__ import annotations

import re
from pathlib import Path

_TAG_RE = re.compile(r"[a-z0-9][a-z0-9.-]*")


def tagged(path: Path, tag: str | None) -> Path:
    """``path`` con ``-<tag>`` antes de la extensión, o ``path`` si no hay
    etiqueta. Solo acepta minúsculas, dígitos, punto y guion."""
    if tag is None:
        return path
    if not _TAG_RE.fullmatch(tag):
        raise ValueError(f"Etiqueta de corrida inválida: {tag!r}")
    return path.with_name(f"{path.stem}-{tag}{path.suffix}")
