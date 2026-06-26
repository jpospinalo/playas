"""Endpoints de autenticación: login, registro y perfil propio."""

from __future__ import annotations

import hashlib
import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api.auth import create_access_token, get_current_user
from rag.api.database import get_session
from rag.api.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    digest = hashlib.sha256(password.encode()).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    digest = hashlib.sha256(password.encode()).digest()
    return bcrypt.checkpw(digest, hashed.encode())


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    display_name: str | None
    role: str


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Autentica con email y contraseña. Retorna JWT."""
    result = await session.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user is None or not _verify_password(payload.password, user.password_hash):
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
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este correo ya está registrado.",
        )
    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        password_hash=_hash_password(payload.password),
        display_name=payload.display_name,
        role="user",
    )
    session.add(user)
    await session.commit()
    token = create_access_token(user.id, user.email, user.role)
    return TokenResponse(
        access_token=token,
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


@router.get("/me", response_model=TokenResponse)
async def me(
    user_payload: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """Retorna los datos del usuario autenticado."""
    result = await session.execute(select(User).where(User.id == user_payload["sub"]))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    return TokenResponse(
        access_token="",
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )
