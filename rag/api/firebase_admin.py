"""Singleton de Firebase Admin SDK para el backend RAG.

Inicialización lazy: se activa la primera vez que se llame a verify_id_token()
o get_db(). Las credenciales se leen desde el archivo JSON indicado en
FIREBASE_SERVICE_ACCOUNT_PATH (ruta relativa a la raíz del proyecto).
"""

from __future__ import annotations

import os
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, firestore

# Raíz del proyecto (dos niveles arriba de este archivo: rag/api/ → rag/ → /)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_initialized = False
_db = None


def _initialize() -> None:
    global _initialized, _db
    if _initialized:
        return

    key_path_raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
    if not key_path_raw:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_PATH no está configurada. "
            "Agrega la ruta al archivo JSON del service account en el .env."
        )

    key_path = Path(key_path_raw)
    if not key_path.is_absolute():
        key_path = _PROJECT_ROOT / key_path

    if not key_path.exists():
        raise RuntimeError(
            f"No se encontró el archivo de credenciales de Firebase: {key_path}"
        )

    cred = credentials.Certificate(str(key_path))
    firebase_admin.initialize_app(cred)
    _db = firestore.async_client()
    _initialized = True


def get_db():
    """Retorna el cliente Firestore async. Inicializa Firebase si es necesario."""
    _initialize()
    return _db


def verify_id_token(token: str) -> dict:
    """Valida un ID token de Firebase Auth y retorna el payload decodificado."""
    _initialize()
    return firebase_auth.verify_id_token(token)
