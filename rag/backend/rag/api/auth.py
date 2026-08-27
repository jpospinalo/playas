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

import rag.api.database as database
from rag.api.models import User
from rag.config import JWT_ALGORITHM as _ALGORITHM
from rag.config import JWT_EXPIRE_MINUTES as _EXPIRE_MINUTES

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)


def _secret() -> str:
    value = os.getenv("JWT_SECRET_KEY", "").strip()
    if not value or value == "dev-secret-change-me-in-production":
        raise RuntimeError("JWT_SECRET_KEY debe configurarse con un valor seguro.")
    return value


def create_access_token(user_id: str, email: str, role: str) -> str:
    """Genera un JWT firmado con los datos del usuario."""
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGORITHM)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            _secret(),
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "email", "role", "iat", "exp"]},
        )
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
    """Retorna el payload del JWT si está presente y es válido; None si no hay token."""
    if creds is None:
        return None
    return _decode(creds.credentials)


async def get_current_user(
    user: dict | None = Depends(get_optional_user),
) -> dict:
    """Requiere autenticación y refresca identidad/rol desde la base de datos."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Se requiere autenticación para este endpoint.",
        )
    async with database.async_session_factory() as session:
        db_user = await session.get(User, user["sub"])
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario no encontrado.",
        )
    return {
        **user,
        "email": db_user.email,
        "display_name": db_user.display_name,
        "role": db_user.role,
    }


async def require_admin(
    user: dict = Depends(get_current_user),
) -> dict:
    """Requiere un rol administrativo vigente en la base de datos."""
    role = user["role"]
    if role not in ("admin", "super-admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado.",
        )
    return {**user, "role": role}
