"""Dependencias de autenticación FastAPI basadas en Firebase Auth.

Tres niveles de protección:
- get_optional_user  → token opcional; retorna None si no hay token
- get_current_user   → token obligatorio; lanza 401 si no hay token válido
- require_admin      → token obligatorio + rol admin/super-admin en Firestore
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rag.api.firebase_admin import get_db, verify_id_token

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    """Retorna el payload decodificado del token si está presente y es válido.

    Retorna None si no hay encabezado Authorization.
    Lanza 503 si Firebase Admin no está configurado o hay error de red.
    Lanza 401 si el token es inválido o expirado.
    """
    if creds is None:
        return None
    try:
        return await verify_id_token(creds.credentials)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        exc_name = type(exc).__name__
        # TransportError / CertificateFetchError indican problema de red, no token inválido
        if "Transport" in exc_name or "Certificate" in exc_name or "Fetch" in exc_name:
            logger.error("Error de red al verificar token Firebase: %s: %s", exc_name, exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Error temporal de autenticación. Intenta de nuevo.",
            ) from exc
        logger.warning("Token Firebase inválido: %s: %s", exc_name, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido o expirado.",
        ) from exc


async def get_current_user(
    user: dict | None = Depends(get_optional_user),
) -> dict:
    """Requiere autenticación. Lanza 401 si no hay token válido."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación para este endpoint.",
        )
    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Requiere rol 'admin' o 'super-admin' en Firestore. Lanza 403 si no cumple."""
    db = get_db()
    uid = user["uid"]
    doc = await db.collection("users").document(uid).get()
    if not doc.exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado.",
        )
    role = (doc.to_dict() or {}).get("role", "user")
    if role not in ("admin", "super-admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado.",
        )
    return user
