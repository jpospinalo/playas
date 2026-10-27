"""Evaluación de las preguntas del ejercicio de validación (planilla del profe).

Roles (``users.role``): ``evaluador`` (semillerista, con sede) califica;
``comite`` (o ``admin``) resuelve diferencias, fija la calificación final y
exporta. Las preguntas se muestran **anónimas**: número de participante y
tipo de usuario de playa, nunca el nombre.

  GET /api/evaluacion/catalogo                      — rúbrica, rangos, tipos y umbral (evaluadores)
  GET /api/evaluacion/bandeja                        — preguntas con su estado (evaluadores)
  GET /api/evaluacion/preguntas/{message_id}         — ficha de una pregunta (evaluadores)
  PUT /api/evaluacion/preguntas/{message_id}/mia     — guardar mi calificación (evaluador)
  PUT /api/evaluacion/preguntas/{message_id}/final   — calificación final del comité
  GET /api/evaluacion/resumen                        — avance e indicadores (evaluadores)
  GET /api/evaluacion/premios                        — los 2 premios, gratificación y participación (comité)
  PUT /api/evaluacion/premios/{nivel}/ganadora       — el comité elige la ganadora si hay empate en Cv
  GET /api/evaluacion/exportar.xlsx                  — planilla en Excel (comité)

Reglas en ``rag/api/ejercicio.py``. Sin IA.
"""

from __future__ import annotations

import dataclasses
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import auditoria, calendario
from rag.api import ejercicio as ej
from rag.api import panel_metricas as pm
from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import (
    AccountStatus,
    AwardDecision,
    Conversation,
    EvaluationComment,
    EvaluationReview,
    ExerciseProfile,
    ExerciseSetting,
    Message,
    PertinenceReview,
    PracticeAccount,
    QuestionAssignment,
    QuestionEvaluation,
    QuestionNumber,
    User,
    ValidatorProfile,
)

router = APIRouter(prefix="/api/evaluacion", tags=["evaluacion"])


async def require_evaluacion(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ej.ROLES_EVALUACION:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Su cuenta no participa en la evaluación.")
    return user


async def require_comite(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ej.ROLES_COMITE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el comité puede hacer esto.")
    return user


# ── Carga ────────────────────────────────────────────────────────────────────


@dataclass
class _Pregunta:
    numero: int  # "ID pregunta" de la planilla, en orden de llegada
    message_id: str
    conversation_id: str
    codigo: str
    tipo_playa: int | None
    fecha: datetime  # hora de Colombia
    texto: str
    cals: list[ej.Calificacion] = field(default_factory=list)
    # Semillerista asignado en cada sede (T1): {"Santa Marta": user_id, ...}.
    asignados: dict[str, str] = field(default_factory=dict)
    # Gestión costera (T3, E7): None = sin revisar; False = no es del tema.
    pertinente: bool | None = None
    # T7: pregunta de una cuenta de práctica (no cuenta para nada).
    practica: bool = False

    @property
    def oficial(self) -> ej.Oficial:
        return ej.calificacion_oficial(self.cals)


async def _cargar(session: AsyncSession) -> list[_Pregunta]:
    """Preguntas de participantes (cuentas con número) con sus calificaciones."""
    filas = (
        await session.execute(
            select(
                Message.id,
                Message.conversation_id,
                Message.text,
                Message.created_at,
                ExerciseProfile.codigo,
                ExerciseProfile.tipo_playa,
                Conversation.user_id,
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(ExerciseProfile, ExerciseProfile.user_id == Conversation.user_id)
            .where(Message.role == "user", ExerciseProfile.codigo.is_not(None))
            .order_by(Message.created_at, Message.id)
        )
    ).all()
    practica = await cuentas_practica(session)
    if await practica_archivada(session):
        # T7: después de archivar, la práctica desaparece de todas las vistas.
        filas = [f for f in filas if f[-1] not in practica]
    numeros = await _numerar(session, [f[0] for f in filas])
    de_practica = {f[0] for f in filas if f[-1] in practica}
    asignados = await _asignar(session, [f[0] for f in filas], de_practica)
    preguntas = [
        _Pregunta(
            numero=numeros[mid],
            message_id=mid,
            conversation_id=cid,
            codigo=codigo,
            tipo_playa=tipo,
            fecha=pm.a_utc(creado).astimezone(pm.HORA_COLOMBIA),
            texto=texto,
            asignados=asignados.get(mid, {}),
            practica=uid in practica,
        )
        for mid, cid, texto, creado, codigo, tipo, uid in filas
    ]
    por_id = {p.message_id: p for p in preguntas}
    for mid, pertinente in (
        await session.execute(select(PertinenceReview.message_id, PertinenceReview.pertinente))
    ).all():
        if mid in por_id:
            por_id[mid].pertinente = pertinente
    # Última validación jurídica de cada evaluación (T2), con quién la hizo.
    ultima: dict[str, EvaluationReview] = {}
    validador: dict[str, str] = {}
    for r, vnombre, vcorreo in (
        await session.execute(
            select(EvaluationReview, User.display_name, User.email)
            .join(User, User.id == EvaluationReview.validador_id)
            .order_by(EvaluationReview.created_at, EvaluationReview.id)
        )
    ).all():
        ultima[r.evaluation_id] = r
        dia = pm.a_utc(r.created_at).astimezone(pm.HORA_COLOMBIA).strftime("%Y-%m-%d")
        validador[r.evaluation_id] = f"{(vnombre or vcorreo or '').strip()} ({dia})"
    evals = (
        await session.execute(
            select(QuestionEvaluation, User.display_name, User.email)
            .join(User, User.id == QuestionEvaluation.evaluador_id)
            .order_by(QuestionEvaluation.created_at, QuestionEvaluation.id)
        )
    ).all()
    for e, nombre, correo in evals:
        p = por_id.get(e.message_id)
        if p is None:
            continue
        p.cals.append(
            ej.Calificacion(
                evaluador_id=e.evaluador_id,
                evaluador=(nombre or correo or "").strip(),
                sede=e.sede,
                f1=e.f1,
                f2=e.f2,
                f3=e.f3,
                ct=e.ct,
                cv=e.cv,
                total=e.total,
                valida=e.valida,
                observaciones=e.observaciones,
                es_final=e.es_final,
                fecha=pm.a_utc(e.updated_at or e.created_at)
                .astimezone(pm.HORA_COLOMBIA)
                .strftime("%Y-%m-%d")
                if (e.updated_at or e.created_at)
                else "",
                id=e.id,
                validada=_vigente(ultima.get(e.id), e),
                validada_por=validador.get(e.id, ""),
            )
        )
    return preguntas


def _vigente(r: EvaluationReview | None, e: QuestionEvaluation) -> bool:
    """De acuerdo y posterior a la última corrección del semillerista."""
    if r is None or not r.de_acuerdo:
        return False
    cambio = e.updated_at or e.created_at
    return cambio is None or pm.a_utc(r.created_at) >= pm.a_utc(cambio)


async def _numerar(
    session: AsyncSession, message_ids: list[str], _reintento: bool = False
) -> dict[str, int]:
    """ID fijo por pregunta (PQ-56): las que no tienen número lo reciben ahora,
    en orden de llegada, después del último asignado. Si otra solicitud
    numeró al mismo tiempo (número único), se usa lo que quedó guardado."""
    numeros = dict(
        (await session.execute(select(QuestionNumber.message_id, QuestionNumber.numero))).all()
    )
    siguiente = max(numeros.values(), default=0) + 1
    nuevos = False
    for mid in message_ids:
        if mid not in numeros:
            numeros[mid] = siguiente
            session.add(QuestionNumber(message_id=mid, numero=siguiente))
            siguiente += 1
            nuevos = True
    if nuevos:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if _reintento:
                raise
            return await _numerar(session, message_ids, _reintento=True)
    return numeros


async def cuentas_practica(session: AsyncSession) -> set[str]:
    return set((await session.execute(select(PracticeAccount.user_id))).scalars().all())


async def practica_archivada(session: AsyncSession) -> bool:
    s = await session.get(ExerciseSetting, "practica_archivada")
    return s is not None and s.valor == "si"


def reales(preguntas: list[_Pregunta]) -> list[_Pregunta]:
    """Sin las preguntas de práctica: lo que cuenta para resumen, premios y Excel."""
    return [p for p in preguntas if not p.practica]


async def _asignar(
    session: AsyncSession,
    message_ids: list[str],
    de_practica: set[str] | None = None,
    _reintento: bool = False,
) -> dict[str, dict[str, str]]:
    """Asigna las preguntas que aún no tienen semillerista en cada sede (T1).

    En orden de llegada, a quien menos asignadas tenga en su sede; si empatan,
    al azar con una semilla fija por pregunta (siempre da lo mismo). Solo
    cuentan los evaluadores con sede y cuenta activa. Se llama al leer
    cualquier pantalla de evaluación, así que una pregunta nueva queda
    asignada en cuanto alguien entra.
    """
    actuales: dict[str, dict[str, str]] = {}
    for mid, sede, ev in (
        await session.execute(
            select(
                QuestionAssignment.message_id,
                QuestionAssignment.sede,
                QuestionAssignment.evaluador_id,
            )
        )
    ).all():
        actuales.setdefault(mid, {})[sede] = ev
    inactivas = set(
        (
            await session.execute(
                select(AccountStatus.user_id).where(AccountStatus.activa.is_(False))
            )
        )
        .scalars()
        .all()
    )
    por_sede: dict[str, list[str]] = {s: [] for s in ej.SEDES}
    for uid, sede in (
        await session.execute(
            select(User.id, ExerciseProfile.sede)
            .join(ExerciseProfile, ExerciseProfile.user_id == User.id)
            .where(User.role == "evaluador", ExerciseProfile.sede.is_not(None))
            .order_by(User.id)
        )
    ).all():
        if uid not in inactivas and sede in por_sede:
            por_sede[sede].append(uid)
    # E5: los semilleristas de práctica solo reciben preguntas de práctica.
    evaluadores_practica = await cuentas_practica(session)
    de_practica = de_practica or set()
    carga = {uid: 0 for uids in por_sede.values() for uid in uids}
    for porsede in actuales.values():
        for ev in porsede.values():
            if ev in carga:
                carga[ev] += 1
    # Si alguien de esa sede ya la calificó (datos de antes de la asignación),
    # se le asigna a esa persona: así nadie recibe una pregunta ya evaluada.
    previas: dict[tuple[str, str], str] = {}
    for mid, sede, ev in (
        await session.execute(
            select(
                QuestionEvaluation.message_id,
                QuestionEvaluation.sede,
                QuestionEvaluation.evaluador_id,
            ).where(QuestionEvaluation.es_final.is_(False), QuestionEvaluation.sede.is_not(None))
        )
    ).all():
        previas.setdefault((mid, sede), ev)
    ahora = datetime.now(UTC)
    nuevos = False
    for mid in message_ids:
        ya = actuales.setdefault(mid, {})
        for sede, uids in por_sede.items():
            if sede in ya:
                continue
            previa = previas.get((mid, sede))
            if previa is not None:
                ya[sede] = previa
                carga[previa] = carga.get(previa, 0) + 1
                session.add(
                    QuestionAssignment(
                        message_id=mid, sede=sede, evaluador_id=previa, created_at=ahora
                    )
                )
                nuevos = True
                continue
            if mid not in de_practica:
                uids = [u for u in uids if u not in evaluadores_practica]
            if not uids:
                continue
            menor = min(carga[u] for u in uids)
            candidatos = [u for u in uids if carga[u] == menor]
            elegido = random.Random(f"{mid}|{sede}").choice(candidatos)
            ya[sede] = elegido
            carga[elegido] += 1
            session.add(
                QuestionAssignment(
                    message_id=mid, sede=sede, evaluador_id=elegido, created_at=ahora
                )
            )
            nuevos = True
    if nuevos:
        try:
            await session.commit()
        except IntegrityError:
            # Otra solicitud asignó las mismas preguntas al mismo tiempo (la
            # clave pregunta+sede es única): se descarta lo propio y se usa
            # lo que quedó guardado.
            await session.rollback()
            if _reintento:
                raise
            return await _asignar(session, message_ids, de_practica, _reintento=True)
    return actuales


async def reasignar_pendientes(
    session: AsyncSession, evaluador_id: str, actor_id: str
) -> dict[str, int]:
    """E1: las asignadas de ``evaluador_id`` que aún no evaluó pasan a otro
    semillerista activo de su misma sede (al de menos carga). Lo llama
    Cuentas al desactivar una cuenta y el admin desde Evaluación. No hace
    commit: lo hace quien llama. Devuelve {"reasignadas": n, "sin_destino": m}."""
    filas = (
        await session.execute(
            select(QuestionAssignment).where(QuestionAssignment.evaluador_id == evaluador_id)
        )
    ).scalars()
    filas = list(filas)
    if not filas:
        return {"reasignadas": 0, "sin_destino": 0}
    evaluadas = {
        mid
        for (mid,) in (
            await session.execute(
                select(QuestionEvaluation.message_id).where(
                    QuestionEvaluation.evaluador_id == evaluador_id
                )
            )
        ).all()
    }
    con_final = {
        mid
        for (mid,) in (
            await session.execute(
                select(QuestionEvaluation.message_id).where(QuestionEvaluation.es_final.is_(True))
            )
        ).all()
    }
    pendientes = [
        a for a in filas if a.message_id not in evaluadas and a.message_id not in con_final
    ]
    inactivas = set(
        (
            await session.execute(
                select(AccountStatus.user_id).where(AccountStatus.activa.is_(False))
            )
        )
        .scalars()
        .all()
    ) | {evaluador_id}
    carga: dict[str, int] = {}
    destinos: dict[str, list[str]] = {}
    for uid, sede in (
        await session.execute(
            select(User.id, ExerciseProfile.sede)
            .join(ExerciseProfile, ExerciseProfile.user_id == User.id)
            .where(User.role == "evaluador", ExerciseProfile.sede.is_not(None))
            .order_by(User.id)
        )
    ).all():
        if uid not in inactivas:
            destinos.setdefault(sede, []).append(uid)
            carga[uid] = 0
    for (ev,) in (await session.execute(select(QuestionAssignment.evaluador_id))).all():
        if ev in carga:
            carga[ev] += 1
    n = sin = 0
    for a in pendientes:
        candidatos = destinos.get(a.sede, [])
        if not candidatos:
            sin += 1
            continue
        menor = min(carga[u] for u in candidatos)
        elegido = random.Random(f"{a.message_id}|{a.sede}|re").choice(
            [u for u in candidatos if carga[u] == menor]
        )
        a.reasignada_de = evaluador_id
        a.evaluador_id = elegido
        carga[elegido] += 1
        n += 1
    if n:
        auditoria.registrar(
            session,
            actor_id,
            "reasignar_pendientes",
            evaluador_id,
            {"cantidad": n, "sin_destino": sin},
        )
    return {"reasignadas": n, "sin_destino": sin}


async def _sede(session: AsyncSession, user_id: str) -> str | None:
    perfil = await session.get(ExerciseProfile, user_id)
    return perfil.sede if perfil else None


# ── Esquemas ─────────────────────────────────────────────────────────────────


class CalificacionIn(BaseModel):
    f1: int = Field(ge=1, le=3)
    f2: int = Field(ge=1, le=3)
    f3: int = Field(ge=1, le=3)
    ct: Literal["S", "I", "A"]
    cv: int = Field(ge=3, le=12)
    valida: bool = True
    observaciones: str | None = Field(default=None, max_length=2000)


class CalificacionOut(BaseModel):
    id: str = ""
    evaluador: str
    sede: str | None
    f1: int
    f2: int
    f3: int
    forma: int
    ct: str
    cv: int
    total: int
    valida: bool
    observaciones: str | None
    es_final: bool


class OficialOut(BaseModel):
    estado: str
    f1: int | None = None
    f2: int | None = None
    f3: int | None = None
    ct: str | None = None
    cv: int | None = None
    total: int | None = None
    valida: bool | None = None


class BandejaItem(BaseModel):
    message_id: str
    numero: int
    codigo: str
    tipo_playa: int | None
    tipo_playa_nombre: str | None
    fecha: str
    hora: str
    pregunta: str
    evaluaciones: int
    evaluada_por_mi: bool
    estado: str
    oficial: OficialOut
    practica: bool = False


class BandejaResponse(BaseModel):
    items: list[BandejaItem]
    total: int
    page: int
    page_size: int
    conteos: dict[str, int]


class FichaResponse(BaseModel):
    message_id: str
    numero: int
    codigo: str
    tipo_playa: int | None
    tipo_playa_nombre: str | None
    fecha: str
    hora: str
    pregunta: str
    respuesta: str | None
    estado: str
    mia: CalificacionOut | None
    otras: list[CalificacionOut] | None = Field(
        default=None, description="Solo el comité ve las de los demás"
    )
    final: CalificacionOut | None
    oficial: OficialOut
    puede_evaluar: bool
    motivo_no_puede: str | None
    es_comite: bool
    practica: bool = False
    anterior: str | None
    siguiente: str | None


def _cal_out(c: ej.Calificacion) -> CalificacionOut:
    return CalificacionOut(
        id=c.id,
        evaluador=c.evaluador,
        sede=c.sede,
        f1=c.f1,
        f2=c.f2,
        f3=c.f3,
        forma=ej.puntaje_forma(c.f1, c.f2, c.f3),
        ct=c.ct,
        cv=c.cv,
        total=c.total,
        valida=c.valida,
        observaciones=c.observaciones,
        es_final=c.es_final,
    )


def _oficial_out(o: ej.Oficial) -> OficialOut:
    return OficialOut(
        estado=o.estado, f1=o.f1, f2=o.f2, f3=o.f3, ct=o.ct, cv=o.cv, total=o.total, valida=o.valida
    )


def _puede_evaluar(p: _Pregunta, user_id: str, rol: str, sede: str | None) -> str | None:
    """Motivo por el que este evaluador no puede calificar, o ``None``."""
    if rol != "evaluador":
        return "Su cuenta es del comité: use la calificación final."
    if sede is None:
        return "Su cuenta no tiene sede. Pida al administrador que la asigne."
    asignado = p.asignados.get(sede)
    if asignado is not None and asignado != user_id:
        return "Esta pregunta está asignada a otro semillerista de su sede."
    if any(c.es_final for c in p.cals):
        return "El comité ya fijó la calificación final de esta pregunta."
    propias = [c for c in p.cals if not c.es_final and c.evaluador_id == user_id]
    if propias:
        return None  # puede corregir la suya
    if any(c.sede == sede for c in p.cals if not c.es_final):
        return f"Ya la calificó otro evaluador de {sede}."
    if len([c for c in p.cals if not c.es_final]) >= 2:
        return "Ya tiene las dos calificaciones."
    return None


ESTADOS_FILTRO = Literal[
    "pendientes", "mias", "con_diferencias", "por_validar", "finalizadas", "todas"
]


class ReasignarIn(BaseModel):
    evaluador_id: str
    confirmar: Literal[True]


@router.post("/reasignar")
async def reasignar(
    payload: ReasignarIn,
    user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    """E1: el admin o el comité pasan las pendientes de un semillerista (que
    no ha podido evaluar) a los demás de su sede."""
    ev = await session.get(User, payload.evaluador_id)
    if ev is None or ev.role != "evaluador":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Semillerista no encontrado.")
    r = await reasignar_pendientes(session, payload.evaluador_id, user["sub"])
    await session.commit()
    return r


class PracticaOut(BaseModel):
    cuentas: int
    preguntas: int
    archivada: bool


@router.get("/practica", response_model=PracticaOut)
async def estado_practica(
    _user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> PracticaOut:
    """T7: cuántas cuentas y preguntas de práctica hay y si ya se archivó."""
    cuentas = await cuentas_practica(session)
    preguntas = [p for p in await _cargar(session) if p.practica]
    return PracticaOut(
        cuentas=len(cuentas), preguntas=len(preguntas), archivada=await practica_archivada(session)
    )


class ArchivarIn(BaseModel):
    archivar: bool
    confirmar: Literal[True]


@router.post("/practica/archivar", response_model=PracticaOut)
async def archivar_practica(
    payload: ArchivarIn,
    user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> PracticaOut:
    """T7: antes del 2 nov, el admin archiva la práctica (sale de todas las
    vistas; nada se borra). Se puede deshacer."""
    if user["role"] not in ("admin", "super-admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el administrador archiva la práctica.")
    s = await session.get(ExerciseSetting, "practica_archivada")
    if s is None:
        s = ExerciseSetting(clave="practica_archivada", valor="no")
        session.add(s)
    s.valor = "si" if payload.archivar else "no"
    s.updated_by = user["sub"]
    s.updated_at = datetime.now(UTC)
    auditoria.registrar(
        session, user["sub"], "archivar_practica" if payload.archivar else "desarchivar_practica"
    )
    await session.commit()
    return await estado_practica(user, session)


@router.get("/catalogo")
async def catalogo(_user: dict = Depends(require_evaluacion)) -> dict:
    return {
        "forma": ej.RUBRICA_FORMA,
        "fondo": ej.RUBRICA_FONDO,
        "rangos": {k: list(v) for k, v in ej.RANGOS_CV.items()},
        "tipos_playa": ej.TIPOS_PLAYA,
        "umbral_diferencia": ej.UMBRAL_DIFERENCIA,
    }


def _estado_para_mi(p: _Pregunta, user_id: str, rol: str, sede: str | None) -> dict[str, bool]:
    oficial = p.oficial
    mia = any(c.evaluador_id == user_id and not c.es_final for c in p.cals)
    if rol == "evaluador":
        pendiente = _puede_evaluar(p, user_id, rol, sede) is None and not mia
    else:
        pendiente = oficial.estado == "con_diferencias"
    return {
        "pendientes": pendiente,
        "mias": mia,
        "con_diferencias": oficial.estado == "con_diferencias",
        # Concordantes: tienen valor (promedio) pero falta que el comité las revise.
        "por_validar": oficial.estado == "concordante",
        "finalizadas": oficial.estado in ("final", "validada")
        or (oficial.estado == "concordante" and not ej.PREMIOS_SOLO_REVISADAS),
        "todas": True,
    }


@router.get("/bandeja", response_model=BandejaResponse)
async def bandeja(
    estado: ESTADOS_FILTRO = "pendientes",
    tipo_playa: int | None = Query(default=None, ge=1, le=5),
    ct: Literal["S", "I", "A"] | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(require_evaluacion),
    session: AsyncSession = Depends(get_session),
) -> BandejaResponse:
    """Preguntas anónimas con su estado. "pendientes" para un evaluador son
    las que puede calificar (ninguno de su sede lo hizo); para el comité, las
    que tienen diferencias sin resolver."""
    sede = await _sede(session, user["sub"])
    preguntas = await _cargar(session)
    if user["role"] == "evaluador":
        # T1: cada semillerista ve solo las preguntas que le asignaron.
        preguntas = [p for p in preguntas if p.asignados.get(sede or "") == user["sub"]]
    if tipo_playa:
        preguntas = [p for p in preguntas if p.tipo_playa == tipo_playa]
    if ct:
        preguntas = [p for p in preguntas if p.oficial.ct == ct]
    marcas = {p.message_id: _estado_para_mi(p, user["sub"], user["role"], sede) for p in preguntas}
    conteos = {k: sum(m[k] for m in marcas.values()) for k in ESTADOS_FILTRO.__args__}  # type: ignore[attr-defined]
    elegidas = [p for p in preguntas if marcas[p.message_id][estado]]
    # Pendientes: las más antiguas primero (orden de llegada); el resto, recientes primero.
    elegidas.sort(key=lambda p: p.numero, reverse=estado != "pendientes")
    pagina = elegidas[(page - 1) * page_size : page * page_size]
    return BandejaResponse(
        items=[
            BandejaItem(
                message_id=p.message_id,
                numero=p.numero,
                codigo=p.codigo,
                tipo_playa=p.tipo_playa,
                tipo_playa_nombre=ej.TIPOS_PLAYA.get(p.tipo_playa or 0),
                fecha=p.fecha.date().isoformat(),
                hora=p.fecha.strftime("%H:%M"),
                pregunta=p.texto,
                evaluaciones=len([c for c in p.cals if not c.es_final]),
                evaluada_por_mi=marcas[p.message_id]["mias"],
                estado=p.oficial.estado,
                oficial=_oficial_out(p.oficial),
                practica=p.practica,
            )
            for p in pagina
        ],
        total=len(elegidas),
        page=page,
        page_size=page_size,
        conteos=conteos,
    )


async def _respuesta(session: AsyncSession, p: _Pregunta) -> str | None:
    """La primera respuesta de ATLAS después de la pregunta, en su conversación."""
    filas = (
        await session.execute(
            select(Message.text, Message.created_at)
            .where(Message.conversation_id == p.conversation_id, Message.role == "assistant")
            .order_by(Message.created_at, Message.id)
        )
    ).all()
    for texto, creado in filas:
        if pm.a_utc(creado) >= p.fecha:
            return texto
    return filas[-1][0] if filas else None


async def _ficha(session: AsyncSession, message_id: str, user: dict) -> FichaResponse:
    preguntas = await _cargar(session)
    sede = await _sede(session, user["sub"])
    if user["role"] == "evaluador":
        existe = any(p.message_id == message_id for p in preguntas)
        preguntas = [p for p in preguntas if p.asignados.get(sede or "") == user["sub"]]
        if existe and not any(p.message_id == message_id for p in preguntas):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Esta pregunta no está asignada a usted."
            )
    indice = next((i for i, p in enumerate(preguntas) if p.message_id == message_id), None)
    if indice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta no encontrada.")
    p = preguntas[indice]
    es_comite = user["role"] in ej.ROLES_COMITE
    mia = next((c for c in p.cals if c.evaluador_id == user["sub"] and not c.es_final), None)
    final = next((c for c in reversed(p.cals) if c.es_final), None)
    motivo = _puede_evaluar(p, user["sub"], user["role"], sede)
    return FichaResponse(
        message_id=p.message_id,
        numero=p.numero,
        codigo=p.codigo,
        tipo_playa=p.tipo_playa,
        tipo_playa_nombre=ej.TIPOS_PLAYA.get(p.tipo_playa or 0),
        fecha=p.fecha.date().isoformat(),
        hora=p.fecha.strftime("%H:%M"),
        pregunta=p.texto,
        respuesta=await _respuesta(session, p),
        estado=p.oficial.estado,
        mia=_cal_out(mia) if mia else None,
        otras=[_cal_out(c) for c in p.cals if not c.es_final] if es_comite else None,
        final=_cal_out(final) if final else None,
        oficial=_oficial_out(p.oficial),
        puede_evaluar=motivo is None,
        motivo_no_puede=motivo,
        es_comite=es_comite,
        practica=p.practica,
        anterior=preguntas[indice - 1].message_id if indice > 0 else None,
        siguiente=preguntas[indice + 1].message_id if indice + 1 < len(preguntas) else None,
    )


@router.get("/preguntas/{message_id}", response_model=FichaResponse)
async def ficha(
    message_id: str,
    user: dict = Depends(require_evaluacion),
    session: AsyncSession = Depends(get_session),
) -> FichaResponse:
    return await _ficha(session, message_id, user)


def _validar(payload: CalificacionIn) -> None:
    error = ej.validar_calificacion(payload.f1, payload.f2, payload.f3, payload.ct, payload.cv)
    if error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, error)


async def _guardar(
    session: AsyncSession,
    message_id: str,
    user_id: str,
    sede: str | None,
    payload: CalificacionIn,
    final: bool,
) -> None:
    existente = (
        await session.execute(
            select(QuestionEvaluation).where(
                QuestionEvaluation.message_id == message_id,
                QuestionEvaluation.evaluador_id == user_id,
                QuestionEvaluation.es_final.is_(final),
            )
        )
    ).scalar_one_or_none()
    ahora = datetime.now(UTC)
    valores = {
        "f1": payload.f1,
        "f2": payload.f2,
        "f3": payload.f3,
        "ct": payload.ct,
        "cv": payload.cv,
        "total": ej.puntaje_total(payload.f1, payload.f2, payload.f3, payload.cv),
        "valida": payload.valida,
        "observaciones": (payload.observaciones or "").strip() or None,
        "sede": sede,
        "updated_at": ahora,
    }
    if existente is None:
        session.add(
            QuestionEvaluation(
                message_id=message_id,
                evaluador_id=user_id,
                es_final=final,
                created_at=ahora,
                **valores,
            )
        )
    else:
        for k, v in valores.items():
            setattr(existente, k, v)
    await session.commit()


@router.put("/preguntas/{message_id}/mia", response_model=FichaResponse)
async def guardar_mia(
    message_id: str,
    payload: CalificacionIn,
    user: dict = Depends(require_evaluacion),
    session: AsyncSession = Depends(get_session),
) -> FichaResponse:
    """Guarda (o corrige) la calificación de este evaluador."""
    _validar(payload)
    preguntas = await _cargar(session)
    p = next((x for x in preguntas if x.message_id == message_id), None)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta no encontrada.")
    sede = await _sede(session, user["sub"])
    motivo = _puede_evaluar(p, user["sub"], user["role"], sede)
    if motivo:
        raise HTTPException(status.HTTP_409_CONFLICT, motivo)
    antes = next((c for c in p.cals if c.evaluador_id == user["sub"] and not c.es_final), None)
    # T5: evaluar hasta el cierre de la evaluación; corregir lo ya evaluado
    # (por una conversación con la validadora) hasta el cierre de la validación.
    if antes is None:
        await calendario.exigir_plazo(session, "fin_evaluacion", "evaluar")
    else:
        await calendario.exigir_plazo(session, "fin_validacion", "corregir")
    await _guardar(session, message_id, user["sub"], sede, payload, final=False)
    if antes is not None:
        cambios = _diferencias(antes, payload)
        if cambios:
            session.add(
                EvaluationComment(
                    evaluation_id=antes.id,
                    autor_id=user["sub"],
                    tipo="correccion",
                    texto="Corrigió: " + "; ".join(cambios),
                    created_at=datetime.now(UTC),
                )
            )
            await session.commit()
    return await _ficha(session, message_id, user)


def _diferencias(antes: ej.Calificacion, nueva: CalificacionIn) -> list[str]:
    """Qué cambió en una corrección, en texto ("Cv 5 → 8")."""
    total = ej.puntaje_total(nueva.f1, nueva.f2, nueva.f3, nueva.cv)
    pares = [
        ("F1", antes.f1, nueva.f1),
        ("F2", antes.f2, nueva.f2),
        ("F3", antes.f3, nueva.f3),
        ("Ct", antes.ct, nueva.ct),
        ("Cv", antes.cv, nueva.cv),
        ("total", antes.total, total),
        ("válida", "sí" if antes.valida else "no", "sí" if nueva.valida else "no"),
    ]
    cambios = [f"{n} {a} → {d}" for n, a, d in pares if a != d]
    if (antes.observaciones or "") != ((nueva.observaciones or "").strip()):
        cambios.append("observaciones")
    return cambios


@router.put("/preguntas/{message_id}/final", response_model=FichaResponse)
async def guardar_final(
    message_id: str,
    payload: CalificacionIn,
    user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> FichaResponse:
    """Calificación final del comité ("Revisó"); reemplaza a las de los evaluadores."""
    _validar(payload)
    preguntas = await _cargar(session)
    p = next((x for x in preguntas if x.message_id == message_id), None)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta no encontrada.")
    await calendario.exigir_plazo(session, "fin_validacion", "validar")
    auditoria.registrar(
        session,
        user["sub"],
        "calificacion_final",
        detalle={"id_pregunta": p.numero, "ct": payload.ct, "cv": payload.cv},
    )
    await _guardar(session, message_id, user["sub"], None, payload, final=True)
    return await _ficha(session, message_id, user)


# ── Resumen, premios y Excel ─────────────────────────────────────────────────


def _oficiales(preguntas: list[_Pregunta]) -> list[ej.PreguntaOficial]:
    return [
        ej.PreguntaOficial(
            p.message_id,
            p.codigo,
            p.fecha,
            p.texto,
            dataclasses.replace(p.oficial, valida=False) if p.pertinente is False else p.oficial,
        )
        for p in preguntas
        if p.oficial.estado in ("final", "validada")
        or (p.oficial.estado == "concordante" and not ej.PREMIOS_SOLO_REVISADAS)
    ]


@router.get("/resumen")
async def resumen(
    user: dict = Depends(require_evaluacion),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Como la hoja "Resumen" de la planilla, más el avance por evaluador."""
    preguntas = reales(await _cargar(session))
    estados = Counter(p.oficial.estado for p in preguntas)
    oficiales = _oficiales(preguntas)
    validas = [o for o in oficiales if o.oficial.valida]
    por_nivel = Counter(o.oficial.ct for o in validas)
    # T6: avance de cada semillerista frente a su plazo (asignadas, hechas,
    # pendientes y cuántas al día le faltan para llegar).
    fechas, _ = await calendario.leer(session)
    dias_eval = max(1, (fechas["fin_evaluacion"] - calendario.hoy()).days + 1)
    dias_val = max(1, (fechas["fin_validacion"] - calendario.hoy()).days + 1)
    nombres = dict(
        (
            await session.execute(
                select(User.id, func.coalesce(User.display_name, User.email)).where(
                    User.role.in_(("evaluador", "comite"))
                )
            )
        ).all()
    )
    avance: dict[str, dict] = {}

    def _fila(uid: str, sede: str | None) -> dict:
        return avance.setdefault(
            uid,
            {
                "evaluador": nombres.get(uid, uid),
                "sede": sede,
                "asignadas": 0,
                "evaluadas": 0,
                "pendientes": 0,
            },
        )

    for p in preguntas:
        for sede, uid in p.asignados.items():
            _fila(uid, sede)["asignadas"] += 1
        hechas = {c.evaluador_id for c in p.cals if not c.es_final}
        for c in p.cals:
            if not c.es_final:
                _fila(c.evaluador_id, c.sede)["evaluadas"] += 1
        final = any(c.es_final for c in p.cals)
        for sede, uid in p.asignados.items():
            if uid not in hechas and not final:
                _fila(uid, sede)["pendientes"] += 1
    for f in avance.values():
        f["por_dia"] = round(f["pendientes"] / dias_eval, 1)
    # Validadoras jurídicas: evaluaciones de su sede por validar.
    validadoras = []
    for uid, sede in (
        await session.execute(
            select(ValidatorProfile.user_id, ExerciseProfile.sede)
            .join(ExerciseProfile, ExerciseProfile.user_id == ValidatorProfile.user_id)
            .where(ValidatorProfile.tipo == "juridico")
        )
    ).all():
        suyas = [c for p in preguntas for c in p.cals if not c.es_final and c.sede == sede]
        pendientes = sum(not c.validada for c in suyas)
        validadoras.append(
            {
                "validador": nombres.get(uid, uid),
                "sede": sede,
                "evaluaciones": len(suyas),
                "validadas": len(suyas) - pendientes,
                "pendientes": pendientes,
                "por_dia": round(pendientes / dias_val, 1),
            }
        )
    por_tipo: dict[int, int] = defaultdict(int)
    for p in preguntas:
        por_tipo[p.tipo_playa or 0] += 1
    return {
        "preguntas_registradas": len(preguntas),
        "evaluadas": len(oficiales),
        "estados": {e: estados.get(e, 0) for e in ej.ESTADOS},
        "no_validas": len(oficiales) - len(validas),
        "por_nivel": {ct: por_nivel.get(ct, 0) for ct in ej.RANGOS_CV},
        "promedio_total": round(sum(o.oficial.total or 0 for o in validas) / len(validas), 1)
        if validas
        else 0,
        "por_tipo_playa": [
            {"tipo": t, "nombre": ej.TIPOS_PLAYA[t], "preguntas": por_tipo.get(t, 0)}
            for t in ej.TIPOS_PLAYA
        ],
        "avance_evaluadores": sorted(
            avance.values(), key=lambda f: (f["sede"] or "", -f["evaluadas"], f["evaluador"])
        ),
        "avance_validadores": sorted(validadoras, key=lambda f: f["sede"] or ""),
        # E2: acuerdo entre las dos sedes en las preguntas con ambas evaluaciones.
        "concordancia": ej.concordancia(
            [
                (sm, bq)
                for p in preguntas
                for sm in [c for c in p.cals if not c.es_final and c.sede == "Santa Marta"][:1]
                for bq in [c for c in p.cals if not c.es_final and c.sede == "Barranquilla"][:1]
            ]
        ),
        "cerrado": await calendario.cerrado(session),
        "fin_evaluacion": fechas["fin_evaluacion"].isoformat(),
        "fin_validacion": fechas["fin_validacion"].isoformat(),
        "umbral_diferencia": ej.UMBRAL_DIFERENCIA,
        "solo_revisadas": ej.PREMIOS_SOLO_REVISADAS,
    }


async def _elegidas(session: AsyncSession) -> dict[str, str]:
    filas = (await session.execute(select(AwardDecision.nivel, AwardDecision.message_id))).all()
    return dict(filas)


def _participacion(preguntas: list[_Pregunta]) -> list[dict]:
    """Participación por día de cada participante (no es asistencia física):
    días con preguntas y, de ellos, días con preguntas válidas."""
    por: dict[str, list[_Pregunta]] = defaultdict(list)
    for p in preguntas:
        por[p.codigo].append(p)
    filas = []
    for codigo, ps in por.items():
        validas = [p for p in ps if p.oficial.valida and p.oficial.total is not None]
        filas.append(
            {
                "codigo": codigo,
                "tipo_playa": ps[0].tipo_playa,
                "preguntas": len(ps),
                "dias": sorted({p.fecha.date().isoformat() for p in ps}),
                "preguntas_validas": len(validas),
                "dias_validos": len({p.fecha.date() for p in validas}),
                "puntaje": sum(p.oficial.total or 0 for p in validas),
            }
        )
    filas.sort(key=lambda f: f["codigo"])
    return filas


async def _premios(session: AsyncSession, preguntas: list[_Pregunta]) -> dict:
    oficiales = _oficiales(preguntas)
    ranking = ej.ranking_participantes(oficiales)
    return {
        "mejor_pregunta": ej.mejores_por_nivel(oficiales, await _elegidas(session)),
        "participacion_constante": ranking[:10],
        "gratificacion": sorted(ranking, key=lambda f: (-f["puntaje"], f["codigo"])),
        "participacion_por_dia": _participacion(preguntas),
        # Concordantes que aún no cuentan porque el comité no las ha validado.
        # Evaluaciones de semilleristas que esperan la validación jurídica (T2).
        "por_validar": sum(
            1 for p in preguntas for c in p.cals if not c.es_final and not c.validada
        ),
        "solo_revisadas": ej.PREMIOS_SOLO_REVISADAS,
        "nota": (
            "Solo cuentan preguntas válidas validadas por el comité."
            if ej.PREMIOS_SOLO_REVISADAS
            else "Solo cuentan preguntas válidas con calificación final del comité o con dos "
            "calificaciones concordantes."
        )
        + " Si en un nivel hay empate en Cv, decide el comité.",
    }


@router.get("/premios")
async def premios(
    _user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Los dos premios del documento (mejor pregunta por nivel y participación
    más constante), el puntaje acumulado para la gratificación y la
    participación por día."""
    return await _premios(session, reales(await _cargar(session)))


class GanadoraIn(BaseModel):
    message_id: str


@router.put("/premios/{nivel}/ganadora")
async def elegir_ganadora(
    nivel: Literal["S", "I", "A"],
    payload: GanadoraIn,
    user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Con empate en Cv, el comité elige la mejor pregunta del nivel."""
    await calendario.exigir_plazo(session, "premios", "elegir la ganadora")
    preguntas = reales(await _cargar(session))
    actual = ej.mejores_por_nivel(_oficiales(preguntas))[nivel]
    if not actual["decide_comite"]:
        raise HTTPException(status.HTTP_409_CONFLICT, "En este nivel no hay empate que decidir.")
    if payload.message_id not in {f["message_id"] for f in actual["empatadas"]}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Esa pregunta no está entre las empatadas."
        )
    decision = await session.get(AwardDecision, nivel)
    if decision is None:
        session.add(
            AwardDecision(nivel=nivel, message_id=payload.message_id, decidido_por=user["sub"])
        )
    else:
        decision.message_id = payload.message_id
        decision.decidido_por = user["sub"]
        decision.created_at = datetime.now(UTC)
    numero = next((x.numero for x in preguntas if x.message_id == payload.message_id), None)
    auditoria.registrar(
        session, user["sub"], "elegir_ganadora", detalle={"nivel": nivel, "id_pregunta": numero}
    )
    await session.commit()
    return await _premios(session, preguntas)


@router.get("/exportar.xlsx")
async def exportar(
    _user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Planilla en Excel con las mismas columnas de la hoja "Evaluación", más
    "Calificaciones" (una fila por evaluador) y "Resumen"."""
    preguntas = reales(await _cargar(session))
    hoja = [list(ej.COLUMNAS_PLANILLA)]
    for p in preguntas:
        o = p.oficial
        forma = ej.puntaje_forma(o.f1, o.f2, o.f3) if o.f1 else None
        estado = {
            "sin_evaluar": "Sin evaluar",
            "una_evaluacion": "Falta una calificación",
            "con_diferencias": "Con diferencias: pendiente del comité",
            "concordante": "Concordantes: falta la validación jurídica",
            "validada": "Validada (promedio de las dos evaluaciones)",
            "final": "Revisada por el comité",
        }[o.estado]
        obs = "; ".join(
            x for x in (estado, "No válida" if o.valida is False else "", o.observaciones) if x
        )
        hoja.append(
            [
                p.numero,
                p.codigo,
                p.fecha.date().isoformat(),
                p.fecha.strftime("%H:%M"),
                f"Tipo {p.tipo_playa}. {ej.TIPOS_PLAYA[p.tipo_playa]}" if p.tipo_playa else "",
                ej.celda_segura(p.texto),
                o.f1,
                o.f2,
                o.f3,
                forma,
                ej.CT_PLANILLA.get(o.ct or "", ""),
                o.cv,
                o.total,
                ej.celda_segura(obs),
                o.evaluo,
                o.reviso,
            ]
        )
    individuales = [
        [
            "ID pregunta",
            "ID Usuario",
            "Evaluador",
            "Sede",
            "F1",
            "F2",
            "F3",
            "Puntaje de forma",
            "Ct",
            "Cv",
            "Puntaje Total",
            "Válida",
            "Final del comité",
            "Observaciones",
        ]
    ]
    for p in preguntas:
        for c in p.cals:
            individuales.append(
                [
                    p.numero,
                    p.codigo,
                    c.evaluador,
                    c.sede or "",
                    c.f1,
                    c.f2,
                    c.f3,
                    ej.puntaje_forma(c.f1, c.f2, c.f3),
                    ej.CT_PLANILLA[c.ct],
                    c.cv,
                    c.total,
                    c.valida,
                    c.es_final,
                    ej.celda_segura(c.observaciones or ""),
                ]
            )
    validas = [p for p in preguntas if p.oficial.total is not None and p.oficial.valida]
    resumen_hoja = [
        ["Indicador", "Resultado"],
        ["Preguntas registradas", len(preguntas)],
        ["Casos sencillos", sum(p.oficial.ct == "S" for p in validas)],
        ["Casos intermedios", sum(p.oficial.ct == "I" for p in validas)],
        ["Casos avanzados", sum(p.oficial.ct == "A" for p in validas)],
        [
            "Promedio puntaje total",
            round(sum(p.oficial.total or 0 for p in validas) / len(validas), 2) if validas else 0,
        ],
        [
            "Con diferencias pendientes del comité",
            sum(p.oficial.estado == "con_diferencias" for p in preguntas),
        ],
        [],
        # PQ-64: la planilla original usa COUNT/COUNTIF; aquí son cifras fijas.
        [
            "Cifras calculadas al exportar (no se actualizan si se editan filas): "
            + datetime.now(pm.HORA_COLOMBIA).strftime("%Y-%m-%d %H:%M")
            + " (hora de Colombia)"
        ],
    ]
    datos = await _premios(session, preguntas)
    premios_hoja: list[list[object]] = [["Mejor pregunta del ejercicio (mayor Cv por nivel)"]]
    premios_hoja.append(["Nivel", "ID Usuario", "Cv", "Pregunta", "Estado"])
    for ct, nivel in datos["mejor_pregunta"].items():
        g = nivel["ganadora"]
        if g:
            premios_hoja.append(
                [ej.CT_PLANILLA[ct], g["codigo"], g["cv"], ej.celda_segura(g["texto"]), "Ganadora"]
            )
        elif nivel["decide_comite"]:
            for f in nivel["empatadas"]:
                premios_hoja.append(
                    [
                        ej.CT_PLANILLA[ct],
                        f["codigo"],
                        f["cv"],
                        ej.celda_segura(f["texto"]),
                        "Empate: decide el comité",
                    ]
                )
        else:
            premios_hoja.append([ej.CT_PLANILLA[ct], "", "", "Sin preguntas válidas", ""])
    premios_hoja += [[], ["Participación más constante"]]
    premios_hoja.append(
        [
            "Puesto",
            "ID Usuario",
            "Días con preguntas válidas",
            "Preguntas válidas",
            "Puntaje acumulado",
        ]
    )
    for i, f in enumerate(datos["participacion_constante"], 1):
        premios_hoja.append([i, f["codigo"], f["dias"], f["preguntas_validas"], f["puntaje"]])
    premios_hoja += [[], ["Participación por día (no es asistencia física)"]]
    premios_hoja.append(
        ["ID Usuario", "Tipo de Usuario de Playa", "Preguntas", "Días con preguntas", "Fechas"]
    )
    for f in datos["participacion_por_dia"]:
        premios_hoja.append(
            [
                f["codigo"],
                f"Tipo {f['tipo_playa']}. {ej.TIPOS_PLAYA[f['tipo_playa']]}"
                if f["tipo_playa"]
                else "",
                f["preguntas"],
                len(f["dias"]),
                ", ".join(f["dias"]),
            ]
        )
    # PDF p. 5: "para cada interacción se registrará el número del
    # participante, la pregunta realizada, la categoría asignada, los puntos
    # obtenidos y el puntaje acumulado" (B15). Solo preguntas válidas con
    # calificación oficial, en orden de llegada por participante.
    numero_de = {p.message_id: p.numero for p in preguntas}
    interacciones: list[list[object]] = [
        [
            "ID Usuario",
            "ID pregunta",
            "Fecha",
            "Pregunta formulada",
            "Categoría (Ct)",
            "Puntos (Puntaje Total)",
            "Puntaje acumulado",
            "Estado",
        ]
    ]
    acumulado: dict[str, int] = {}
    for o in sorted(
        (o for o in _oficiales(preguntas) if o.oficial.valida),
        key=lambda o: (o.codigo, o.fecha),
    ):
        acumulado[o.codigo] = acumulado.get(o.codigo, 0) + (o.oficial.total or 0)
        interacciones.append(
            [
                o.codigo,
                numero_de[o.message_id],
                o.fecha.astimezone(pm.HORA_COLOMBIA).strftime("%Y-%m-%d %H:%M"),
                ej.celda_segura(o.texto),
                ej.CT_PLANILLA[o.oficial.ct] if o.oficial.ct else "",
                o.oficial.total,
                acumulado[o.codigo],
                "Revisada por el comité"
                if o.oficial.estado == "final"
                else "Concordantes (promedio): pendiente de revisión del comité",
            ]
        )
    contenido = ej.libro_xlsx(
        [
            ("Evaluación", hoja, ej.ANCHOS_PLANILLA, ej.controles_planilla(len(hoja))),
            ("Calificaciones", individuales, [12, 12, 28, 14, 6, 6, 6, 16, 16, 6, 14, 8, 16, 40]),
            ("Resumen", resumen_hoja, [40, 14]),
            ("Premios y participación", premios_hoja, [26, 14, 24, 60, 26]),
            ("Puntaje por interacción", interacciones, [12, 12, 18, 70, 16, 14, 16, 34]),
        ]
    )
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="planilla-evaluacion-atlas.xlsx"'},
    )
