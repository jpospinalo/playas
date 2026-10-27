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

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import ejercicio as ej
from rag.api import panel_metricas as pm
from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import (
    AwardDecision,
    Conversation,
    ExerciseProfile,
    Message,
    QuestionEvaluation,
    QuestionNumber,
    User,
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
            )
            .join(Conversation, Conversation.id == Message.conversation_id)
            .join(ExerciseProfile, ExerciseProfile.user_id == Conversation.user_id)
            .where(Message.role == "user", ExerciseProfile.codigo.is_not(None))
            .order_by(Message.created_at, Message.id)
        )
    ).all()
    # ID fijo por pregunta (PQ-56): los que no tienen número lo reciben ahora,
    # siguiendo el orden de llegada, después del último asignado.
    numeros = dict(
        (await session.execute(select(QuestionNumber.message_id, QuestionNumber.numero))).all()
    )
    siguiente = max(numeros.values(), default=0) + 1
    nuevos = False
    for mid, *_ in filas:
        if mid not in numeros:
            numeros[mid] = siguiente
            session.add(QuestionNumber(message_id=mid, numero=siguiente))
            siguiente += 1
            nuevos = True
    if nuevos:
        await session.commit()
    preguntas = [
        _Pregunta(
            numero=numeros[mid],
            message_id=mid,
            conversation_id=cid,
            codigo=codigo,
            tipo_playa=tipo,
            fecha=pm.a_utc(creado).astimezone(pm.HORA_COLOMBIA),
            texto=texto,
        )
        for mid, cid, texto, creado, codigo, tipo in filas
    ]
    por_id = {p.message_id: p for p in preguntas}
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
            )
        )
    return preguntas


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
    anterior: str | None
    siguiente: str | None


def _cal_out(c: ej.Calificacion) -> CalificacionOut:
    return CalificacionOut(
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
        "finalizadas": oficial.estado in ("final", "concordante"),
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
    indice = next((i for i, p in enumerate(preguntas) if p.message_id == message_id), None)
    if indice is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta no encontrada.")
    p = preguntas[indice]
    sede = await _sede(session, user["sub"])
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
    await _guardar(session, message_id, user["sub"], sede, payload, final=False)
    return await _ficha(session, message_id, user)


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
    if not any(x.message_id == message_id for x in preguntas):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta no encontrada.")
    await _guardar(session, message_id, user["sub"], None, payload, final=True)
    return await _ficha(session, message_id, user)


# ── Resumen, premios y Excel ─────────────────────────────────────────────────


def _oficiales(preguntas: list[_Pregunta]) -> list[ej.PreguntaOficial]:
    return [
        ej.PreguntaOficial(p.message_id, p.codigo, p.fecha, p.texto, p.oficial)
        for p in preguntas
        if p.oficial.estado == "final"
        or (p.oficial.estado == "concordante" and not ej.PREMIOS_SOLO_REVISADAS)
    ]


@router.get("/resumen")
async def resumen(
    user: dict = Depends(require_evaluacion),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Como la hoja "Resumen" de la planilla, más el avance por evaluador."""
    preguntas = await _cargar(session)
    estados = Counter(p.oficial.estado for p in preguntas)
    oficiales = _oficiales(preguntas)
    validas = [o for o in oficiales if o.oficial.valida]
    por_nivel = Counter(o.oficial.ct for o in validas)
    avance: dict[str, dict] = {}
    for p in preguntas:
        for c in p.cals:
            if c.es_final:
                continue
            fila = avance.setdefault(
                c.evaluador_id, {"evaluador": c.evaluador, "sede": c.sede, "evaluadas": 0}
            )
            fila["evaluadas"] += 1
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
        "nota": "Solo cuentan preguntas válidas con calificación final del comité o con dos "
        "calificaciones concordantes. Si en un nivel hay empate en Cv, decide el comité.",
    }


@router.get("/premios")
async def premios(
    _user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Los dos premios del documento (mejor pregunta por nivel y participación
    más constante), el puntaje acumulado para la gratificación y la
    participación por día."""
    return await _premios(session, await _cargar(session))


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
    preguntas = await _cargar(session)
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
    await session.commit()
    return await _premios(session, preguntas)


@router.get("/exportar.xlsx")
async def exportar(
    _user: dict = Depends(require_comite),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Planilla en Excel con las mismas columnas de la hoja "Evaluación", más
    "Calificaciones" (una fila por evaluador) y "Resumen"."""
    preguntas = await _cargar(session)
    hoja = [list(ej.COLUMNAS_PLANILLA)]
    for p in preguntas:
        o = p.oficial
        forma = ej.puntaje_forma(o.f1, o.f2, o.f3) if o.f1 else None
        estado = {
            "sin_evaluar": "Sin evaluar",
            "una_evaluacion": "Falta una calificación",
            "con_diferencias": "Con diferencias: pendiente del comité",
            "concordante": "Concordantes (promedio): pendiente de revisión del comité",
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
