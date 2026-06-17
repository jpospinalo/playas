"""Singleton de Firebase Admin SDK para el backend RAG.

Inicialización lazy: se activa la primera vez que se llame a verify_id_token()
o get_db(). Las credenciales del service account se obtienen, en orden de
prioridad:

1. Variables de entorno individuales (FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY,
   FIREBASE_CLIENT_EMAIL, …). Recomendado para despliegues como Railway, donde
   se configuran directamente en el panel sin subir ningún archivo.
2. Archivo JSON indicado en FIREBASE_SERVICE_ACCOUNT_PATH (ruta relativa a la
   raíz del proyecto o absoluta). Cómodo para desarrollo local.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from google.cloud import firestore as gcp_firestore
from google.oauth2 import service_account as gcp_service_account

# Raíz del proyecto (rag/backend/rag/api/ → rag/backend/rag/ → rag/backend/ → rag/ → /)
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

_initialized = False
_db = None


def _service_account_from_env() -> dict | None:
    """Reconstruye el dict del service account desde variables de entorno.

    Devuelve None si faltan las claves mínimas (FIREBASE_PROJECT_ID,
    FIREBASE_PRIVATE_KEY, FIREBASE_CLIENT_EMAIL), para permitir el fallback al
    archivo JSON.
    """
    project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip()
    private_key = os.getenv("FIREBASE_PRIVATE_KEY", "")
    client_email = os.getenv("FIREBASE_CLIENT_EMAIL", "").strip()

    if not (project_id and private_key.strip() and client_email):
        return None

    # En .env / Railway la clave privada se guarda en una sola línea con
    # secuencias "\n" literales; las restauramos a saltos de línea reales.
    # Si ya viene con saltos reales, replace() no la altera.
    private_key = private_key.replace("\\n", "\n")

    return {
        "type": os.getenv("FIREBASE_TYPE", "service_account"),
        "project_id": project_id,
        "private_key_id": os.getenv("FIREBASE_PRIVATE_KEY_ID", "").strip(),
        "private_key": private_key,
        "client_email": client_email,
        "client_id": os.getenv("FIREBASE_CLIENT_ID", "").strip(),
        "auth_uri": os.getenv(
            "FIREBASE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"
        ),
        "token_uri": os.getenv(
            "FIREBASE_TOKEN_URI", "https://oauth2.googleapis.com/token"
        ),
        "auth_provider_x509_cert_url": os.getenv(
            "FIREBASE_AUTH_PROVIDER_X509_CERT_URL",
            "https://www.googleapis.com/oauth2/v1/certs",
        ),
        "client_x509_cert_url": os.getenv("FIREBASE_CLIENT_X509_CERT_URL", "").strip(),
        "universe_domain": os.getenv("FIREBASE_UNIVERSE_DOMAIN", "googleapis.com"),
    }


def _service_account_from_file() -> dict | None:
    """Carga el dict del service account desde el JSON en FIREBASE_SERVICE_ACCOUNT_PATH.

    Devuelve None si la variable no está definida.
    """
    key_path_raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH", "").strip()
    if not key_path_raw:
        return None

    key_path = Path(key_path_raw)
    if not key_path.is_absolute():
        key_path = _PROJECT_ROOT / key_path

    if not key_path.exists():
        raise RuntimeError(f"No se encontró el archivo de credenciales de Firebase: {key_path}")

    with key_path.open(encoding="utf-8") as fh:
        return json.load(fh)


def _load_service_account_info() -> dict:
    info = _service_account_from_env() or _service_account_from_file()
    if info is None:
        raise RuntimeError(
            "Faltan las credenciales de Firebase. Define las variables de entorno "
            "FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY y FIREBASE_CLIENT_EMAIL "
            "(recomendado para despliegues), o bien FIREBASE_SERVICE_ACCOUNT_PATH "
            "apuntando al JSON del service account."
        )
    return info


def _initialize() -> None:
    global _initialized, _db
    if _initialized:
        return

    info = _load_service_account_info()

    cred = credentials.Certificate(info)
    try:
        firebase_admin.get_app()
    except ValueError:
        # La app no existe aún — primera inicialización real
        firebase_admin.initialize_app(cred)

    # firebase-admin 7.x eliminó async_client() — crear AsyncClient directamente
    # desde google-cloud-firestore (dependencia transitiva ya instalada).
    google_creds = gcp_service_account.Credentials.from_service_account_info(
        info,
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
    from functools import partial

    fn = partial(firebase_auth.verify_id_token, token, clock_skew_seconds=10)
    return await loop.run_in_executor(None, fn)


async def create_user_async(
    email: str,
    password: str,
    display_name: str | None = None,
):
    """Crea un usuario en Firebase Auth. Retorna el UserRecord."""
    import asyncio
    from functools import partial

    _initialize()
    loop = asyncio.get_event_loop()
    fn = partial(
        firebase_auth.create_user,
        email=email,
        password=password,
        display_name=display_name,
    )
    return await loop.run_in_executor(None, fn)


async def update_user_password_async(uid: str, password: str):
    """Cambia la contraseña de un usuario existente."""
    import asyncio
    from functools import partial

    _initialize()
    loop = asyncio.get_event_loop()
    fn = partial(firebase_auth.update_user, uid, password=password)
    return await loop.run_in_executor(None, fn)
