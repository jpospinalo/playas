"""Endpoints de autenticación: login, registro y perfil propio."""

from __future__ import annotations

import hashlib
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api.auth import create_access_token, get_current_user
from rag.api.database import get_session
from rag.api.models import User
from rag.api.passwords import hash_password, verify_password
from rag.api.rate_limit import login_rate_limiter
from rag.config import REGISTER_ENABLED as _REGISTER_ENABLED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("El correo es obligatorio.")
        return normalized


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("El correo es obligatorio.")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str | None
    role: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    role: str


def _login_rate_limit_key(email: str, request: Request) -> str:
    """Clave del límite de login: email normalizado + IP de origen, con hash
    para no conservar direcciones IP ni correos en claro en memoria.

    request.client.host es la IP de la conexión TCP directa. No se confía en
    cabeceras como X-Forwarded-For: sin una política de proxy de confianza
    explícita, serían falsificables por el cliente y permitirían evadir el
    límite trivialmente.
    """
    raw = f"{email}:{request.client.host if request.client else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Autentica con email y contraseña. Retorna JWT."""
    await login_rate_limiter.check(_login_rate_limit_key(payload.email, request))
    result = await session.execute(select(User).where(func.lower(User.email) == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )
    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Registra un nuevo usuario con rol 'user'. Retorna JWT."""
    if not _REGISTER_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El registro público está deshabilitado.",
        )
    existing = await session.execute(select(User).where(func.lower(User.email) == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este correo ya está registrado.",
        )
    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        role="user",
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # La comprobación previa de existencia (arriba) no es atómica con este
        # commit: dos registros concurrentes con el mismo email pueden pasarla
        # ambos y competir por la restricción unique de la base de datos. Solo
        # uno gana el commit; el otro llega aquí. Se revierte y se confirma si
        # el email ya existe (carrera real, responder 409 igual que el chequeo
        # de arriba) antes de relanzar cualquier otro error de integridad.
        await session.rollback()
        existing_after_race = await session.execute(
            select(User).where(func.lower(User.email) == payload.email)
        )
        if existing_after_race.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Este correo ya está registrado.",
            ) from None
        raise
    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


@router.get("/me", response_model=UserResponse)
async def me(
    user_payload: dict = Depends(get_current_user),
) -> UserResponse:
    """Retorna los datos vigentes ya validados por la dependencia de autenticación."""
    return UserResponse(
        user_id=user_payload["sub"],
        email=user_payload["email"],
        display_name=user_payload["display_name"],
        role=user_payload["role"],
    )
