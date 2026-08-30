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
from rag.api.passwords import (
    hash_password_async,
    needs_rehash,
    verify_password_async,
)
from rag.api.rate_limit import login_rate_limiter
from rag.config import REGISTER_ENABLED as _REGISTER_ENABLED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# C1/3.3 — hash bcrypt sintético fijo. No corresponde a ninguna contraseña ni
# secreto real: existe solo para que login() tenga SIEMPRE un hash contra el
# cual llamar a verify_password_async, incluso cuando el email no pertenece a
# ningún usuario — sin este hash, esa rama se resolvía sin bcrypt (ver más
# abajo), lo que hacía "usuario inexistente" mensurablemente más rápido que
# "usuario existente, contraseña incorrecta" y permitía enumerar cuentas por
# temporización.
#
# v1.2/C4 — literal fijo (formato actual, prefijo "v2:") en vez de calculado
# con hash_password() al importar este módulo: bcrypt.gensalt() es
# deliberadamente costoso en CPU, y antes se pagaba ese costo en CADA
# importación del módulo (cada arranque del proceso, cada recarga en tests),
# sin ningún beneficio — el valor exacto del hash sintético es irrelevante
# siempre que sea un hash bcrypt válido con el prefijo actual, así que un
# literal fijo computado una sola vez (fuera del repositorio, con el mismo
# `hash_password()`) es equivalente en comportamiento y evita ese costo
# repetido. Sigue sin ser una credencial real ni un secreto.
_DUMMY_PASSWORD_HASH = "v2:$2b$12$0uSFgX7kLzSk3JdoFp4dnul2se6ki1Tgg5ofSGIUNVZjX34AzAZw."


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


async def _opportunistically_rehash(user: User, password: str, session: AsyncSession) -> None:
    """Tras un login exitoso con un hash heredado, intenta re-hashearlo al
    formato actual (ver ``rag.api.passwords``).

    La contraseña ya fue validada contra el hash heredado antes de llegar
    aquí — ese hash heredado sigue siendo válido indefinidamente aunque esta
    actualización falle. Por eso un fallo exclusivamente en este paso
    (calcular el nuevo hash o confirmarlo en la base de datos) nunca debe
    impedir el login: se registra el fallo, se revierte solo esta
    actualización (``session.rollback()``) y se conserva el hash anterior sin
    tocar. El llamador no debe leer ningún atributo de ``user`` después de
    invocar esta función — ``session.rollback()`` expira todos los objetos
    de la sesión, y leerlos aquí en un ``AsyncSession`` dispararía una carga
    perezosa implícita no soportada fuera de un ``await`` explícito.
    """
    user_id = user.id
    try:
        user.password_hash = await hash_password_async(password)
        await session.commit()
    except Exception:
        logger.warning("opportunistic_password_rehash_failed user_id=%s", user_id, exc_info=True)
        await session.rollback()


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
    # C1/3.3 — SIEMPRE se llama a verify_password_async, exista o no el
    # usuario: contra su hash real si existe, contra el hash sintético fijo
    # de arriba si no. Eliminado el corto-circuito `user is None or not
    # await ...` que evitaba bcrypt por completo para un email inexistente —
    # esa asimetría de tiempo permitía distinguir "no existe" de "contraseña
    # incorrecta" sin necesidad de acertar ninguna contraseña. Mismo mensaje
    # y código 401 en ambos casos; ningún dato de email/contraseña/hash se
    # registra en el camino de error.
    password_hash_to_check = user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
    password_is_valid = await verify_password_async(payload.password, password_hash_to_check)
    if user is None or not password_is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo o contraseña incorrectos.",
        )

    # Se capturan los datos de identidad ANTES del intento de re-hash
    # oportunista: si ese intento falla y se revierte, el objeto ``user``
    # queda con sus atributos expirados (ver docstring de
    # ``_opportunistically_rehash``) y no debe volver a leerse.
    user_id = user.id
    user_email = user.email
    user_display_name = user.display_name
    user_role = user.role

    if needs_rehash(user.password_hash):
        await _opportunistically_rehash(user, payload.password, session)

    token = create_access_token(user_id, user_email, user_role)
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        email=user_email,
        display_name=user_display_name,
        role=user_role,
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
    password_hash = await hash_password_async(payload.password)
    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        password_hash=password_hash,
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
