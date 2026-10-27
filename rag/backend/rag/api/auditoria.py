"""Registro de auditoría de las acciones de administración y del comité
(CHECKLIST-FINAL c7, OWASP Logging): quién hizo qué, a quién y cuándo.

Solo se escribe; nunca guarda claves ni tokens. Lo leen los administradores
en ``GET /api/admin/auditoria``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import panel_metricas as pm
from rag.api.auth import require_admin
from rag.api.database import get_session
from rag.api.models import AdminAudit, ExerciseProfile, User

# Texto que se muestra para cada acción.
ACCIONES = {
    "crear_cuentas": "Creó cuentas",
    "cambiar_cuenta": "Cambió una cuenta",
    "desactivar_cuenta": "Desactivó una cuenta",
    "activar_cuenta": "Reactivó una cuenta",
    "nueva_clave": "Generó una clave nueva",
    "calificacion_final": "Fijó la calificación final",
    "validar_concordantes": "Validó concordantes en lote",
    "validar_lote": "Marcó de acuerdo varias evaluaciones",
    "elegir_ganadora": "Eligió la ganadora de un nivel",
    "reasignar_pendientes": "Reasignó preguntas pendientes",
    "archivar_practica": "Archivó la práctica",
    "cambiar_calendario": "Cambió el calendario",
    "cerrar_ejercicio": "Cerró el ejercicio",
    "reabrir_ejercicio": "Reabrió el ejercicio",
    "desarchivar_practica": "Volvió a mostrar la práctica",
    "marcar_practica": "Marcó una cuenta como de práctica",
    "desmarcar_practica": "Quitó la marca de práctica",
}


def registrar(
    session: AsyncSession,
    actor_id: str,
    accion: str,
    objetivo_id: str | None = None,
    detalle: dict | None = None,
) -> None:
    """Agrega la entrada a la sesión; la guarda el ``commit`` de quien llama."""
    session.add(
        AdminAudit(
            actor_id=actor_id,
            accion=accion,
            objetivo_id=objetivo_id,
            detalle=detalle or {},
            created_at=datetime.now(UTC),
        )
    )


router = APIRouter(prefix="/api/admin/auditoria", tags=["admin"])


class EntradaAuditoria(BaseModel):
    fecha: str
    quien: str
    accion: str
    texto: str
    objetivo: str | None
    detalle: dict


class AuditoriaResponse(BaseModel):
    items: list[EntradaAuditoria]
    total: int


@router.get("", response_model=AuditoriaResponse)
async def listar(
    limite: int = Query(default=200, ge=1, le=1000),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AuditoriaResponse:
    """Las acciones más recientes primero."""
    filas = (
        await session.execute(
            select(AdminAudit).order_by(AdminAudit.created_at.desc(), AdminAudit.id.desc())
        )
    ).scalars()
    filas = list(filas)
    ids = {f.actor_id for f in filas} | {f.objetivo_id for f in filas if f.objetivo_id}
    nombres = {
        u.id: (u.display_name or u.email)
        for u in (await session.execute(select(User).where(User.id.in_(ids)))).scalars()
    }
    codigos = dict(
        (
            await session.execute(
                select(ExerciseProfile.user_id, ExerciseProfile.codigo).where(
                    ExerciseProfile.user_id.in_(ids)
                )
            )
        ).all()
    )

    def _objetivo(uid: str | None) -> str | None:
        if not uid:
            return None
        nombre = nombres.get(uid)
        codigo = codigos.get(uid)
        if codigo and nombre:
            return f"{codigo} ({nombre})"
        return codigo or nombre or uid

    return AuditoriaResponse(
        items=[
            EntradaAuditoria(
                # SQLite guarda sin zona: se marca UTC para que el front lo pase a Colombia (PQ-71).
                fecha=pm.a_utc(f.created_at or datetime.now(UTC)).isoformat(),
                quien=nombres.get(f.actor_id, f.actor_id),
                accion=f.accion,
                texto=ACCIONES.get(f.accion, f.accion),
                objetivo=_objetivo(f.objetivo_id),
                detalle=f.detalle or {},
            )
            for f in filas[:limite]
        ],
        total=len(filas),
    )
