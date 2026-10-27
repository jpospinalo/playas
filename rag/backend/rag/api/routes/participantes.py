"""Administración de cuentas del ejercicio de validación.

Solo para 'admin' o 'super-admin' (``require_admin``):

  GET   /api/admin/participantes            — cuentas con número, tipo de playa, rol, sede y nº de preguntas
  GET   /api/admin/participantes/catalogo   — tipos de usuario de playa, roles y sedes
  POST  /api/admin/participantes/lote       — crea varias cuentas y devuelve sus claves (una sola vez)
  PATCH /api/admin/participantes/{uid}      — cambia nombre, tipo de playa, rol o sede
  POST  /api/admin/participantes/{uid}/clave — genera una clave nueva y la devuelve (una sola vez)

Los datos del ejercicio van en la tabla nueva ``exercise_profile``; ``users``
no cambia (el rol sigue en ``users.role``). Las claves se generan aquí, se
guardan con hash y solo se muestran en la respuesta para imprimirlas.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import ejercicio as ej
from rag.api.auth import require_admin
from rag.api.database import get_session
from rag.api.models import Conversation, ExerciseProfile, Message, User
from rag.api.passwords import hash_password_async
from rag.api.routes.panel import DEMO_EMAIL

router = APIRouter(prefix="/api/admin/participantes", tags=["admin-participantes"])

Rol = Literal["user", "evaluador", "comite", "admin"]
DOMINIO = "ejercicio.atlas"
_PALABRAS = (
    "arena", "bahia", "boya", "brisa", "coral", "duna", "faro", "isla", "marea",
    "muelle", "ola", "palma", "puerto", "roca", "sal", "velero",
)  # fmt: skip


def clave_nueva() -> str:
    """Clave fácil de dictar e imprimir: palabra-número-palabra (≥ 8 letras)."""
    return (
        f"{secrets.choice(_PALABRAS)}-{secrets.randbelow(9000) + 1000}-{secrets.choice(_PALABRAS)}"
    )


class PersonaNueva(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    rol: Rol = "user"
    tipo_playa: int | None = Field(default=None, ge=1, le=5)
    sede: Literal["Santa Marta", "Barranquilla"] | None = None
    codigo: str | None = Field(default=None, max_length=20, pattern=r"^[A-Za-z0-9-]+$")
    correo: str | None = Field(default=None, max_length=320)
    organizacion: str | None = Field(default=None, max_length=160)


class LoteRequest(BaseModel):
    personas: list[PersonaNueva] = Field(min_length=1, max_length=200)


class Credencial(BaseModel):
    uid: str
    nombre: str
    rol: str
    codigo: str | None
    tipo_playa: int | None
    sede: str | None
    correo: str
    clave: str


class LoteResponse(BaseModel):
    creadas: list[Credencial]


class Cuenta(BaseModel):
    uid: str
    nombre: str | None
    correo: str
    rol: str
    codigo: str | None
    tipo_playa: int | None
    tipo_playa_nombre: str | None
    sede: str | None
    organizacion: str | None = None
    preguntas: int
    creada: str


class CuentasResponse(BaseModel):
    items: list[Cuenta]
    total: int


class CambioCuenta(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=120)
    rol: Rol | None = None
    tipo_playa: int | None = Field(default=None, ge=1, le=5)
    sede: Literal["Santa Marta", "Barranquilla"] | None = None
    organizacion: str | None = Field(default=None, max_length=160)


class ClaveResponse(BaseModel):
    correo: str
    clave: str


@router.get("/catalogo")
async def catalogo(_admin: dict = Depends(require_admin)) -> dict:
    return {
        "tipos_playa": [
            {"id": k, "nombre": v, "largo": ej.TIPOS_PLAYA_LARGO[k]}
            for k, v in ej.TIPOS_PLAYA.items()
        ],
        "roles": list(ej.ROLES),
        "sedes": list(ej.SEDES),
    }


@router.get("", response_model=CuentasResponse)
async def listar(
    rol: Rol | None = None,
    tipo_playa: int | None = None,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> CuentasResponse:
    """Cuentas con sus datos del ejercicio, las de participantes primero por número."""
    preguntas = dict(
        (
            await session.execute(
                select(Conversation.user_id, func.count(Message.id))
                .join(Message, Message.conversation_id == Conversation.id)
                .where(Message.role == "user")
                .group_by(Conversation.user_id)
            )
        ).all()
    )
    filas = (
        await session.execute(
            select(User, ExerciseProfile)
            .join(ExerciseProfile, ExerciseProfile.user_id == User.id, isouter=True)
            # La cuenta marcador de la semilla de demostración no es una persona.
            .where(User.email != DEMO_EMAIL)
        )
    ).all()
    items = []
    for u, perfil in filas:
        if rol and u.role != rol:
            continue
        if tipo_playa and (not perfil or perfil.tipo_playa != tipo_playa):
            continue
        tipo = perfil.tipo_playa if perfil else None
        items.append(
            Cuenta(
                uid=u.id,
                nombre=u.display_name,
                correo=u.email,
                rol=u.role,
                codigo=perfil.codigo if perfil else None,
                tipo_playa=tipo,
                tipo_playa_nombre=ej.TIPOS_PLAYA.get(tipo) if tipo else None,
                sede=perfil.sede if perfil else None,
                organizacion=perfil.organizacion if perfil else None,
                preguntas=preguntas.get(u.id, 0),
                creada=(u.created_at or datetime.now(UTC)).isoformat(),
            )
        )
    items.sort(key=lambda c: (c.codigo is None, c.codigo or "", c.nombre or c.correo))
    return CuentasResponse(items=items, total=len(items))


async def siguiente_codigo(session: AsyncSession, usados: set[str]) -> str:
    """P001, P002…: el siguiente número libre."""
    existentes = {
        c for (c,) in (await session.execute(select(ExerciseProfile.codigo))).all() if c
    } | usados
    numeros = [int(m.group(1)) for c in existentes if (m := re.fullmatch(r"P(\d+)", c))]
    n = max(numeros, default=0) + 1
    return f"P{n:03d}"


def _correo_generado(codigo: str | None, nombre: str) -> str:
    base = (codigo or re.sub(r"[^a-z0-9]+", ".", nombre.lower()).strip(".") or "cuenta").lower()
    return f"{base}@{DOMINIO}"


@router.post("/lote", response_model=LoteResponse, status_code=status.HTTP_201_CREATED)
async def crear_lote(
    payload: LoteRequest,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> LoteResponse:
    """Crea varias cuentas a la vez. Participantes: número automático (P001…)
    si no se da y tipo de usuario de playa obligatorio. Evaluadores: sede
    obligatoria. Devuelve las claves en claro solo esta vez."""
    usados: set[str] = set()
    correos: set[str] = set()
    planes = []
    for i, p in enumerate(payload.personas, 1):
        if p.rol == "user" and p.tipo_playa is None:
            raise HTTPException(
                422, f"Fila {i}: un participante necesita su tipo de usuario de playa."
            )
        if p.rol == "evaluador" and p.sede is None:
            raise HTTPException(422, f"Fila {i}: un evaluador necesita su sede.")
        codigo = (p.codigo or "").upper() or None
        if p.rol == "user" and codigo is None:
            codigo = await siguiente_codigo(session, usados)
        if codigo:
            if codigo in usados:
                raise HTTPException(422, f"Fila {i}: el número {codigo} está repetido en la lista.")
            usados.add(codigo)
        correo = (p.correo or _correo_generado(codigo, p.nombre)).strip().lower()
        if correo in correos:
            raise HTTPException(422, f"Fila {i}: el correo {correo} está repetido en la lista.")
        correos.add(correo)
        planes.append((p, codigo, correo))

    ya = set(
        (await session.execute(select(User.email).where(func.lower(User.email).in_(correos))))
        .scalars()
        .all()
    )
    if ya:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Ya existen cuentas con: {', '.join(sorted(ya))}."
        )
    if usados:
        repetidos = set(
            (
                await session.execute(
                    select(ExerciseProfile.codigo).where(ExerciseProfile.codigo.in_(usados))
                )
            )
            .scalars()
            .all()
        )
        if repetidos:
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"Ya existen los números: {', '.join(sorted(repetidos))}."
            )

    creadas: list[Credencial] = []
    for p, codigo, correo in planes:
        clave = clave_nueva()
        uid = str(uuid.uuid4())
        session.add(
            User(
                id=uid,
                email=correo,
                password_hash=await hash_password_async(clave),
                display_name=p.nombre.strip(),
                role=p.rol,
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        session.add(
            ExerciseProfile(
                user_id=uid,
                codigo=codigo,
                tipo_playa=p.tipo_playa,
                sede=p.sede,
                organizacion=(p.organizacion or "").strip() or None,
            )
        )
        creadas.append(
            Credencial(
                uid=uid,
                nombre=p.nombre.strip(),
                rol=p.rol,
                codigo=codigo,
                tipo_playa=p.tipo_playa,
                sede=p.sede,
                correo=correo,
                clave=clave,
            )
        )
    await session.commit()
    return LoteResponse(creadas=creadas)


@router.patch("/{uid}", response_model=Cuenta)
async def cambiar(
    uid: str,
    payload: CambioCuenta,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Cuenta:
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuenta no encontrada.")
    perfil = await session.get(ExerciseProfile, uid)
    if perfil is None:
        perfil = ExerciseProfile(user_id=uid)
        session.add(perfil)
    if payload.nombre is not None:
        user.display_name = payload.nombre.strip()
    if payload.rol is not None:
        user.role = payload.rol
    if payload.tipo_playa is not None:
        perfil.tipo_playa = payload.tipo_playa
    if payload.sede is not None:
        perfil.sede = payload.sede
    if payload.organizacion is not None:
        perfil.organizacion = payload.organizacion.strip() or None
    await session.commit()
    n = (
        await session.execute(
            select(func.count(Message.id))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == uid, Message.role == "user")
        )
    ).scalar_one()
    return Cuenta(
        uid=user.id,
        nombre=user.display_name,
        correo=user.email,
        rol=user.role,
        codigo=perfil.codigo,
        tipo_playa=perfil.tipo_playa,
        tipo_playa_nombre=ej.TIPOS_PLAYA.get(perfil.tipo_playa) if perfil.tipo_playa else None,
        sede=perfil.sede,
        organizacion=perfil.organizacion,
        preguntas=n,
        creada=(user.created_at or datetime.now(UTC)).isoformat(),
    )


@router.post("/{uid}/clave", response_model=ClaveResponse)
async def clave(
    uid: str,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ClaveResponse:
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Cuenta no encontrada.")
    nueva = clave_nueva()
    user.password_hash = await hash_password_async(nueva)
    await session.commit()
    return ClaveResponse(correo=user.email, clave=nueva)
