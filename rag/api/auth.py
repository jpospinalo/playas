"""Dependencias de autenticación FastAPI basadas en Firebase Auth.

Tres niveles de protección:
- get_optional_user  → token opcional; retorna None si no hay token
- get_current_user   → token obligatorio; lanza 401 si no hay token válido
- require_admin      → token obligatorio + rol admin/super-admin en Firestore
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from rag.api.firebase_admin import get_db, verify_id_token

_bearer = HTTPBearer(auto_error=False)


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    """Retorna el payload decodificado del token si está presente y es válido.

    Retorna None si no hay encabezado Authorization.
    Lanza 503 si Firebase Admin no está configurado.
    Lanza 401 si el token es inválido o expirado.
    """
    if creds is None:
        return None
    try:
        return verify_id_token(creds.credentials)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido o expirado.",
        )


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
