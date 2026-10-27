"""Calendario del ejercicio de validación (reunión del 20-oct, T5).

Fechas por defecto dichas por Camilo (23:05): prueba la semana antes; presencial
del 2 al 13 nov; consultas en línea hasta el 20 nov ("2 semanas desde el día
que fueron por primera vez"); semilleristas evalúan hasta el 27 nov;
profesores validan hasta el 4 dic; premios el 11 dic. El admin las cambia en
Evaluación → Calendario; se guardan en ``exercise_setting``.

La ventana del participante (14 días desde su primer día, tope 20 nov) solo
se muestra: no se bloquea el chat (es código del equipo y participar después
es opcional). Los días son configurables: falta confirmarlos con Camilo
("2 semanas" a las 23:05, "una semana más" a las 40:22).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import auditoria
from rag.api import ejercicio as ej
from rag.api import panel_metricas as pm
from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import Conversation, ExerciseSetting, Message

# clave → (fecha por defecto, texto)
FECHAS: dict[str, tuple[str, str]] = {
    "prueba_inicio": ("2026-10-26", "Prueba con cuentas de práctica"),
    "inicio": ("2026-11-02", "Inicio del ejercicio (sesiones presenciales)"),
    "fin_presencial": ("2026-11-13", "Última sesión presencial (cierra la inscripción)"),
    "fin_participacion": ("2026-11-20", "Último día para que los participantes pregunten"),
    "fin_evaluacion": ("2026-11-27", "Último día para que los semilleristas evalúen"),
    "fin_validacion": ("2026-12-04", "Último día para que el comité valide"),
    "premios": ("2026-12-11", "Entrega de premios"),
}
DIAS_PARTICIPANTE = 14


async def leer(session: AsyncSession) -> tuple[dict[str, date], int]:
    filas = dict(
        (
            await session.execute(
                select(ExerciseSetting.clave, ExerciseSetting.valor).where(
                    ExerciseSetting.clave.in_([*FECHAS, "dias_participante"])
                )
            )
        ).all()
    )
    fechas = {k: date.fromisoformat(filas.get(k, d)) for k, (d, _) in FECHAS.items()}
    dias = int(filas.get("dias_participante", DIAS_PARTICIPANTE))
    return fechas, dias


_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)  # fmt: skip


def dia_largo(d: date) -> str:
    """ "27 de noviembre", como el resto del panel (PQ-74)."""
    return f"{d.day} de {_MESES[d.month - 1]}"


def hoy() -> date:
    return datetime.now(pm.HORA_COLOMBIA).date()


async def cerrado(session: AsyncSession) -> bool:
    """E6: el admin cerró el ejercicio; todo queda en solo lectura."""
    s = await session.get(ExerciseSetting, "ejercicio_cerrado")
    return s is not None and s.valor == "si"


async def exigir_plazo(session: AsyncSession, clave: str, que: str) -> None:
    """409 si el ejercicio está cerrado o ya pasó el día límite (incluido el
    día mismo, hora de Colombia)."""
    if await cerrado(session):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "El ejercicio está cerrado: los resultados quedaron congelados.",
        )
    fechas, _ = await leer(session)
    limite = fechas[clave]
    if hoy() > limite:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"El plazo para {que} terminó el {dia_largo(limite)}. Si hace falta, el "
            "administrador puede ampliarlo en el calendario.",
        )


router = APIRouter(tags=["evaluacion"])


class FechaOut(BaseModel):
    clave: str
    texto: str
    fecha: str


class CalendarioOut(BaseModel):
    fechas: list[FechaOut]
    dias_participante: int
    hoy: str
    # Para quien consulta: su fecha límite y cuántos días le quedan.
    mi_limite: str | None
    mi_limite_texto: str | None
    dias_restantes: int | None
    cerrado: bool = False


@router.get("/api/evaluacion/calendario", response_model=CalendarioOut)
async def ver(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CalendarioOut:
    if user["role"] not in ej.ROLES_EVALUACION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su cuenta no participa en la evaluación.")
    fechas, dias = await leer(session)
    clave = "fin_evaluacion" if user["role"] == "evaluador" else "fin_validacion"
    limite = fechas[clave]
    return CalendarioOut(
        fechas=[
            FechaOut(clave=k, texto=t, fecha=fechas[k].isoformat()) for k, (_, t) in FECHAS.items()
        ],
        dias_participante=dias,
        hoy=hoy().isoformat(),
        mi_limite=limite.isoformat(),
        mi_limite_texto=FECHAS[clave][1],
        dias_restantes=(limite - hoy()).days,
        cerrado=await cerrado(session),
    )


class CalendarioIn(BaseModel):
    fechas: dict[str, date] = Field(default_factory=dict)
    dias_participante: int | None = Field(default=None, ge=1, le=60)


@router.put("/api/evaluacion/calendario", response_model=CalendarioOut)
async def cambiar(
    payload: CalendarioIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CalendarioOut:
    """Solo el administrador cambia las fechas (por ejemplo, para ampliar un plazo)."""
    if user["role"] not in ("admin", "super-admin"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo el administrador cambia el calendario."
        )
    desconocidas = set(payload.fechas) - set(FECHAS)
    if desconocidas:
        raise HTTPException(422, f"Fechas desconocidas: {', '.join(sorted(desconocidas))}.")
    actuales, dias = await leer(session)
    nuevas = {**actuales, **payload.fechas}
    orden = list(FECHAS)
    for a, b in zip(orden, orden[1:], strict=False):
        if nuevas[a] > nuevas[b]:
            raise HTTPException(
                422, f"“{FECHAS[a][1]}” no puede quedar después de “{FECHAS[b][1]}”."
            )
    cambios: dict[str, list[str]] = {}
    ahora = datetime.now(UTC)
    valores = {k: v.isoformat() for k, v in payload.fechas.items()}
    if payload.dias_participante is not None:
        valores["dias_participante"] = str(payload.dias_participante)
    for clave, valor in valores.items():
        s = await session.get(ExerciseSetting, clave)
        antes = s.valor if s else (FECHAS[clave][0] if clave in FECHAS else str(dias))
        if antes == valor:
            continue
        if s is None:
            s = ExerciseSetting(clave=clave, valor=valor)
            session.add(s)
        s.valor = valor
        s.updated_by = user["sub"]
        s.updated_at = ahora
        cambios[clave] = [antes, valor]
    if cambios:
        auditoria.registrar(
            session, user["sub"], "cambiar_calendario", detalle={"cambios": cambios}
        )
    await session.commit()
    return await ver(user, session)


class VentanaOut(BaseModel):
    primer_dia: str | None
    ultimo_dia: str
    dias_restantes: int


@router.get("/api/ejercicio/ventana", response_model=VentanaOut)
async def ventana(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> VentanaOut:
    """Hasta cuándo puede seguir preguntando este participante: su primer día
    más los días configurados, sin pasar del cierre de la participación."""
    fechas, dias = await leer(session)
    primero = (
        await session.execute(
            select(func.min(Message.created_at))
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user["sub"], Message.role == "user")
        )
    ).scalar_one_or_none()
    inicio = pm.a_utc(primero).astimezone(pm.HORA_COLOMBIA).date() if primero else hoy()
    ultimo = min(inicio + timedelta(days=dias - 1), fechas["fin_participacion"])
    return VentanaOut(
        primer_dia=inicio.isoformat() if primero else None,
        ultimo_dia=ultimo.isoformat(),
        dias_restantes=(ultimo - hoy()).days,
    )


class CierreIn(BaseModel):
    cerrar: bool
    confirmar: Literal[True]


class CierreOut(BaseModel):
    cerrado: bool


@router.post("/api/evaluacion/cierre", response_model=CierreOut)
async def cerrar(
    payload: CierreIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CierreOut:
    """E6: al terminar la validación, el admin cierra el ejercicio: nadie
    califica, valida ni elige ganadoras; el Excel sigue disponible. Se puede
    reabrir."""
    if user["role"] not in ("admin", "super-admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador cierra el ejercicio.")
    s = await session.get(ExerciseSetting, "ejercicio_cerrado")
    if s is None:
        s = ExerciseSetting(clave="ejercicio_cerrado", valor="no")
        session.add(s)
    s.valor = "si" if payload.cerrar else "no"
    s.updated_by = user["sub"]
    s.updated_at = datetime.now(UTC)
    auditoria.registrar(
        session, user["sub"], "cerrar_ejercicio" if payload.cerrar else "reabrir_ejercicio"
    )
    await session.commit()
    return CierreOut(cerrado=payload.cerrar)
