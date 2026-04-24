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
from firebase_admin import credentials
from google.cloud import firestore as gcp_firestore
from google.oauth2 import service_account as gcp_service_account

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
    try:
        firebase_admin.get_app()
    except ValueError:
        # La app no existe aún — primera inicialización real
        firebase_admin.initialize_app(cred)

    # firebase-admin 7.x eliminó async_client() — crear AsyncClient directamente
    # desde google-cloud-firestore (dependencia transitiva ya instalada).
    google_creds = gcp_service_account.Credentials.from_service_account_file(
        str(key_path),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )
    _db = gcp_firestore.AsyncClient(
        credentials=google_creds,
        project=google_creds.project_id,
    )
    _initialized = True


def get_db():
    """Retorna el cliente Firestore async. Inicializa Firebase si es necesario."""
    _initialize()
    return _db


async def verify_id_token(token: str) -> dict:
    """Valida un ID token de Firebase Auth y retorna el payload decodificado.

    Corre firebase_auth.verify_id_token (llamada bloqueante de red) en un
    thread pool para no bloquear el event loop de asyncio.
    """
    import asyncio

    _initialize()
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, firebase_auth.verify_id_token, token)
