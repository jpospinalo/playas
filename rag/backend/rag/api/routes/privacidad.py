"""Aviso de privacidad y autorización de tratamiento de datos (Ley 1581 de
2012 y Decreto 1377 de 2013, CHECKLIST-FINAL c8): se muestra en el primer
ingreso y la autorización queda guardada con su fecha y la versión del texto,
como prueba.

El texto es un borrador para el ejercicio de validación: el responsable y el
correo de contacto se configuran con ``PRIVACIDAD_RESPONSABLE`` y
``PRIVACIDAD_CORREO``, y el equipo jurídico debe revisarlo antes de usarlo.
PQ-110 (decisión de Juan): para revocar la autorización se da un correo, no un
botón; si el correo no está configurado no se muestra ningún texto de relleno.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import panel_metricas as pm
from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import PrivacyConsent

# Cambiar la versión cuando cambie el texto: se vuelve a pedir la autorización.
VERSION = "2026-10-27b"
RESPONSABLE = os.getenv("PRIVACIDAD_RESPONSABLE", "el equipo del proyecto ATLAS")
CORREO = os.getenv("PRIVACIDAD_CORREO", "").strip() or None

PARRAFOS = [
    f"Responsable del tratamiento: {RESPONSABLE}.",
    "Finalidad: validar el funcionamiento del agente jurídico ATLAS durante el ejercicio "
    "de validación, calificar las preguntas y calcular la participación y la gratificación.",
    "Datos que se tratan: su nombre, el correo y la clave asignados, su número de "
    "participante, su tipo de usuario de playa y, si la dio, su organización; las preguntas "
    "que haga y las respuestas de ATLAS; y sus respuestas a la encuesta de percepción.",
    "Los evaluadores ven solo su número de participante y su tipo de usuario, no su nombre. "
    "Los resultados se usan en informes del ejercicio sin identificarle.",
    "Sus derechos (Ley 1581 de 2012, art. 8): conocer, actualizar y rectificar sus datos, "
    "pedir prueba de esta autorización, ser informado del uso de sus datos, presentar quejas "
    "ante la Superintendencia de Industria y Comercio, revocar la autorización y pedir que se "
    "supriman sus datos.",
    "Responder sobre datos sensibles es voluntario: no escriba en sus preguntas datos de "
    "salud, origen, creencias u otros datos sensibles.",
]


router = APIRouter(prefix="/api/privacidad", tags=["privacidad"])


class PrivacidadResponse(BaseModel):
    version: str
    parrafos: list[str]
    # PQ-110: correo para revocar la autorización o ejercer los derechos (None si no está configurado).
    correo: str | None = None
    aceptada: bool
    fecha: str | None


class AutorizacionIn(BaseModel):
    acepto: Literal[True]


async def _estado(session: AsyncSession, user_id: str) -> PrivacidadResponse:
    c = await session.get(PrivacyConsent, user_id)
    vigente = c is not None and c.version == VERSION
    return PrivacidadResponse(
        version=VERSION,
        parrafos=PARRAFOS,
        correo=CORREO,
        aceptada=vigente,
        fecha=pm.a_utc(c.aceptada_at).isoformat() if vigente and c and c.aceptada_at else None,
    )


@router.get("", response_model=PrivacidadResponse)
async def ver(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PrivacidadResponse:
    """El aviso y si esta cuenta ya autorizó la versión vigente."""
    return await _estado(session, user["sub"])


@router.post("", response_model=PrivacidadResponse)
async def autorizar(
    _payload: AutorizacionIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PrivacidadResponse:
    """Guarda la autorización (fecha y versión del texto) como prueba."""
    c = await session.get(PrivacyConsent, user["sub"])
    ahora = datetime.now(UTC)
    if c is None:
        session.add(PrivacyConsent(user_id=user["sub"], version=VERSION, aceptada_at=ahora))
    else:
        c.version = VERSION
        c.aceptada_at = ahora
    await session.commit()
    return await _estado(session, user["sub"])
