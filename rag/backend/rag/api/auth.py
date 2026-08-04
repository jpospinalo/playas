"""Dependencias de autenticación FastAPI basadas en JWT propio.

Tres niveles de protección:
- get_optional_user  → token opcional; retorna None si no hay token
- get_current_user   → token obligatorio; lanza 401 si no hay token válido
- require_admin      → token obligatorio + rol admin/super-admin en el payload
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

_SECRET = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me-in-production")
_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "10080"))  # 7 días

_bearer = HTTPBearer(auto_error=False)


def create_access_token(user_id: str, email: str, role: str) -> str:
    """Genera un JWT firmado con los datos del usuario."""
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": datetime.now(UTC) + timedelta(minutes=_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expirado.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticación inválido.",
        ) from exc


async def get_optional_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict | None:
    """Retorna el payload del JWT si está presente y es válido.

    Si no hay token, o el token presente es inválido/expiró (p. ej. quedó
    guardado en el navegador de una sesión o despliegue anterior), se trata
    como anónimo en vez de bloquear el endpoint — la autenticación aquí es
    opcional, un token roto no debería tumbar la petición.
    """
    if creds is None:
        return None
    try:
        return _decode(creds.credentials)
    except HTTPException:
        return None


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
    """Requiere rol 'admin' o 'super-admin' en el token. Lanza 403 si no cumple."""
    role = user.get("role", "user")
    if role not in ("admin", "super-admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado.",
        )
    return user
