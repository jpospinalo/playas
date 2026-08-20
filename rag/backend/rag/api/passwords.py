"""Servicio único de hashing de contraseñas para login y administración."""

from __future__ import annotations

import hashlib

import bcrypt


def hash_password(password: str) -> str:
    """Pre-hashea con SHA-256 y aplica bcrypt.

    El pre-hash mantiene compatibilidad con todas las cuentas creadas por el
    flujo de login existente y evita el límite de 72 bytes de bcrypt.
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Valida hashes actuales y hashes bcrypt directos creados por el admin legado."""
    try:
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        encoded_hash = hashed.encode("utf-8")
        if bcrypt.checkpw(digest, encoded_hash):
            return True
        # Compatibilidad temporal: versiones anteriores del endpoint admin
        # aplicaban bcrypt directamente sobre la contraseña.
        return bcrypt.checkpw(password.encode("utf-8"), encoded_hash)
    except (TypeError, ValueError):
        return False
