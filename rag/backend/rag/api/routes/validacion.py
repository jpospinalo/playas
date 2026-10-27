"""Validación de las evaluaciones (reunión del 20-oct, T2-T4 y E7).

- Validación jurídica (Ana María, Sandra): cada evaluación enviada por un
  semillerista de su sede pasa a su bandeja; marca "De acuerdo" o "No de
  acuerdo" con comentario. El desacuerdo abre una conversación con el
  semillerista, que responde y corrige; la corrección vuelve a "por validar".
- Gestión costera (Camilo): por cada pregunta, ¿es del tema de playas? "No
  pertinente" la saca de premios y gratificación.
- Admin (Juan Pablo): ve todo, no valida (D2); como comité puede fijar la
  final en diferencias (``routes/evaluacion.py``).

Los participantes siguen anónimos: solo número y tipo de usuario de playa.
Los semilleristas ven solo el hilo de su propia evaluación.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import auditoria, calendario
from rag.api import ejercicio as ej
from rag.api import panel_metricas as pm
from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import (
    EvaluationComment,
    EvaluationReview,
    ExerciseProfile,
    PertinenceReview,
    QuestionEvaluation,
    User,
    ValidatorProfile,
)
from rag.api.routes.evaluacion import _buscar, _cargar, _Pregunta

router = APIRouter(prefix="/api/evaluacion/validacion", tags=["evaluacion"])

TIPOS_VALIDACION = ("juridico", "costero")


async def _validador(session: AsyncSession, user: dict) -> tuple[str | None, str | None]:
    """(tipo de validación, sede) de la cuenta; admin = (None, None)."""
    perfil = await session.get(ValidatorProfile, user["sub"])
    ep = await session.get(ExerciseProfile, user["sub"])
    return (perfil.tipo if perfil else None), (ep.sede if ep else None)


async def require_validacion(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] not in ej.ROLES_COMITE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo el comité valida evaluaciones.")
    return user


# ── Hilo ─────────────────────────────────────────────────────────────────────


class EntradaHilo(BaseModel):
    autor: str
    tipo: str
    texto: str
    fecha: str


async def hilo(session: AsyncSession, evaluation_id: str) -> list[EntradaHilo]:
    filas = (
        await session.execute(
            select(EvaluationComment, User.display_name, User.email)
            .join(User, User.id == EvaluationComment.autor_id)
            .where(EvaluationComment.evaluation_id == evaluation_id)
            .order_by(EvaluationComment.created_at, EvaluationComment.id)
        )
    ).all()
    return [
        EntradaHilo(
            autor=(nombre or correo or "").strip(),
            tipo=c.tipo,
            texto=c.texto,
            fecha=pm.a_utc(c.created_at).isoformat(),
        )
        for c, nombre, correo in filas
    ]


def estado_validacion(
    c: ej.Calificacion, ultima: EvaluationReview | None, cambio: datetime | None
) -> str:
    """por_validar | validada | en_conversacion (desacuerdo aún sin corregir).
    Si el semillerista corrigió después del desacuerdo, vuelve a por_validar."""
    if c.validada:
        return "validada"
    if ultima is not None and not ultima.de_acuerdo:
        if cambio is None or pm.a_utc(cambio) <= pm.a_utc(ultima.created_at):
            return "en_conversacion"
    return "por_validar"


async def _ultimas(session: AsyncSession) -> dict[str, EvaluationReview]:
    ultima: dict[str, EvaluationReview] = {}
    for r in (
        await session.execute(
            select(EvaluationReview).order_by(EvaluationReview.created_at, EvaluationReview.id)
        )
    ).scalars():
        ultima[r.evaluation_id] = r
    return ultima


async def _cambios(session: AsyncSession) -> dict[str, datetime]:
    return {
        i: (u or c)
        for i, u, c in (
            await session.execute(
                select(
                    QuestionEvaluation.id,
                    QuestionEvaluation.updated_at,
                    QuestionEvaluation.created_at,
                )
            )
        ).all()
    }


# ── Bandeja del validador ────────────────────────────────────────────────────


class EvaluacionOut(BaseModel):
    id: str
    sede: str | None
    evaluador: str
    f1: int
    f2: int
    f3: int
    forma: int
    ct: str
    cv: int
    total: int
    valida: bool
    observaciones: str | None
    estado: str
    comentarios: int


class ItemValidacion(BaseModel):
    message_id: str
    numero: int
    codigo: str
    tipo_playa_nombre: str | None
    fecha: str
    pregunta: str
    pertinente: bool | None
    evaluaciones: list[EvaluacionOut]


class BandejaValidacion(BaseModel):
    tipo: str | None
    sede: str | None
    items: list[ItemValidacion]
    total: int
    page: int
    page_size: int
    conteos: dict[str, int]


ESTADOS_VALIDACION = Literal["por_validar", "en_conversacion", "validadas", "todas"]


_Fila = tuple[ej.Calificacion, str, int]  # (evaluación, estado de validación, comentarios)


async def _evaluaciones(
    session: AsyncSession, preguntas: list[_Pregunta]
) -> dict[str, list[_Fila]]:
    """Por pregunta, las evaluaciones de semilleristas con su estado."""
    ultima = await _ultimas(session)
    cambios = await _cambios(session)
    ncom: dict[str, int] = {}
    for (eid,) in (await session.execute(select(EvaluationComment.evaluation_id))).all():
        ncom[eid] = ncom.get(eid, 0) + 1
    salida: dict[str, list[_Fila]] = {}
    for p in preguntas:
        for c in p.cals:
            if c.es_final:
                continue
            est = estado_validacion(c, ultima.get(c.id), cambios.get(c.id))
            salida.setdefault(p.message_id, []).append((c, est, ncom.get(c.id, 0)))
    return salida


def _eval_out(c: ej.Calificacion, estado: str, comentarios: int = 0) -> EvaluacionOut:
    return EvaluacionOut(
        id=c.id,
        sede=c.sede,
        evaluador=c.evaluador,
        f1=c.f1,
        f2=c.f2,
        f3=c.f3,
        forma=ej.puntaje_forma(c.f1, c.f2, c.f3),
        ct=c.ct,
        cv=c.cv,
        total=c.total,
        valida=c.valida,
        observaciones=c.observaciones,
        estado=estado,
        comentarios=comentarios,
    )


@router.get("/bandeja", response_model=BandejaValidacion)
async def bandeja(
    estado: ESTADOS_VALIDACION = "por_validar",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    buscar: str | None = Query(default=None, max_length=200),
    orden: Literal["antiguas", "recientes"] = "antiguas",
    user: dict = Depends(require_validacion),
    session: AsyncSession = Depends(get_session),
) -> BandejaValidacion:
    """Jurídica: evaluaciones de su sede. Costera: preguntas (pertinencia).
    Admin: todas las evaluaciones, solo para ver."""
    tipo, sede = await _validador(session, user)
    preguntas = _buscar(await _cargar(session), buscar)
    evals = await _evaluaciones(session, preguntas)
    items: list[tuple[_Pregunta, list[_Fila], str]] = []
    for p in preguntas:
        propias = evals.get(p.message_id, [])
        if tipo == "juridico":
            propias = [f for f in propias if f[0].sede == sede]
            if not propias:
                continue
            # Estado de la fila = el de la evaluación de su sede.
            est = propias[0][1]
        elif tipo == "costero":
            if not propias:
                continue  # se revisa cuando ya hay al menos una evaluación
            est = (
                "por_validar"
                if p.pertinente is None
                else ("validadas" if p.pertinente else "en_conversacion")
            )
        else:
            if not propias:
                continue
            ests = {f[1] for f in propias}
            est = (
                "en_conversacion"
                if "en_conversacion" in ests
                else ("por_validar" if "por_validar" in ests else "validada")
            )
        items.append((p, propias, "validadas" if est == "validada" else est))
    conteos = {
        k: sum(1 for *_, e in items if e == k)
        for k in ("por_validar", "en_conversacion", "validadas")
    }
    conteos["todas"] = len(items)
    elegidos = [x for x in items if estado == "todas" or x[2] == estado]
    elegidos.sort(key=lambda x: x[0].numero, reverse=orden == "recientes")
    pagina = elegidos[(page - 1) * page_size : page * page_size]
    return BandejaValidacion(
        tipo=tipo,
        sede=sede,
        items=[
            ItemValidacion(
                message_id=p.message_id,
                numero=p.numero,
                codigo=p.codigo,
                tipo_playa_nombre=ej.TIPOS_PLAYA.get(p.tipo_playa or 0),
                fecha=p.fecha.date().isoformat(),
                pregunta=p.texto,
                pertinente=p.pertinente,
                evaluaciones=[_eval_out(*f) for f in propias],
            )
            for p, propias, _ in pagina
        ],
        total=len(elegidos),
        page=page,
        page_size=page_size,
        conteos=conteos,
    )


# ── Validación jurídica de una evaluación ────────────────────────────────────


async def _evaluacion(session: AsyncSession, evaluation_id: str) -> QuestionEvaluation:
    e = await session.get(QuestionEvaluation, evaluation_id)
    if e is None or e.es_final:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Evaluación no encontrada.")
    return e


async def _exigir_juridico(session: AsyncSession, user: dict, e: QuestionEvaluation) -> None:
    tipo, sede = await _validador(session, user)
    if tipo != "juridico":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Solo la validación jurídica marca de acuerdo o no."
        )
    if sede and e.sede != sede:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Esta evaluación es de {e.sede}; usted valida las de {sede}.",
        )


class ValidacionIn(BaseModel):
    de_acuerdo: bool
    comentario: str | None = Field(default=None, max_length=2000)


class DetalleEvaluacion(BaseModel):
    evaluacion: EvaluacionOut
    hilo: list[EntradaHilo]


async def _detalle(session: AsyncSession, evaluation_id: str) -> DetalleEvaluacion:
    e = await session.get(QuestionEvaluation, evaluation_id)
    preguntas = await _cargar(session)
    evals = await _evaluaciones(session, [p for p in preguntas if p.message_id == e.message_id])
    fila = next(x for x in evals.get(e.message_id, []) if x[0].id == evaluation_id)
    return DetalleEvaluacion(evaluacion=_eval_out(*fila), hilo=await hilo(session, evaluation_id))


@router.get("/evaluaciones/{evaluation_id}", response_model=DetalleEvaluacion)
async def ver(
    evaluation_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DetalleEvaluacion:
    """La evaluación y su conversación. La ve el comité o su autor."""
    e = await _evaluacion(session, evaluation_id)
    if user["role"] not in ej.ROLES_COMITE and e.evaluador_id != user["sub"]:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta conversación no es suya.")
    return await _detalle(session, evaluation_id)


@router.put("/evaluaciones/{evaluation_id}", response_model=DetalleEvaluacion)
async def validar(
    evaluation_id: str,
    payload: ValidacionIn,
    user: dict = Depends(require_validacion),
    session: AsyncSession = Depends(get_session),
) -> DetalleEvaluacion:
    """De acuerdo / No de acuerdo. El desacuerdo necesita un comentario: es
    lo que abre la conversación con el semillerista (T4)."""
    await calendario.exigir_plazo(session, "fin_validacion", "validar")
    e = await _evaluacion(session, evaluation_id)
    await _exigir_juridico(session, user, e)
    comentario = (payload.comentario or "").strip() or None
    if not payload.de_acuerdo and not comentario:
        raise HTTPException(422, "Si no está de acuerdo, explique por qué en el comentario.")
    ahora = datetime.now(UTC)
    session.add(
        EvaluationReview(
            evaluation_id=evaluation_id,
            validador_id=user["sub"],
            de_acuerdo=payload.de_acuerdo,
            comentario=comentario,
            created_at=ahora,
        )
    )
    session.add(
        EvaluationComment(
            evaluation_id=evaluation_id,
            autor_id=user["sub"],
            tipo="acuerdo" if payload.de_acuerdo else "desacuerdo",
            # PQ-92: el tipo ya dice "De acuerdo" / "No de acuerdo": el texto es el comentario.
            texto=comentario or "Sin comentario.",
            created_at=ahora,
        )
    )
    await session.commit()
    return await _detalle(session, evaluation_id)


class LoteIn(BaseModel):
    evaluaciones: list[str] = Field(min_length=1, max_length=200)
    # Confirmación explícita (revisor, D1): sin ella no se marca nada.
    confirmar: Literal[True]


class LoteOut(BaseModel):
    validadas: int


@router.post("/lote", response_model=LoteOut)
async def de_acuerdo_en_lote(
    payload: LoteIn,
    user: dict = Depends(require_validacion),
    session: AsyncSession = Depends(get_session),
) -> LoteOut:
    """Atajo: "De acuerdo" con varias evaluaciones de su sede a la vez."""
    await calendario.exigir_plazo(session, "fin_validacion", "validar")
    ahora = datetime.now(UTC)
    n = 0
    for eid in dict.fromkeys(payload.evaluaciones):
        e = await _evaluacion(session, eid)
        await _exigir_juridico(session, user, e)
        session.add(
            EvaluationReview(
                evaluation_id=eid, validador_id=user["sub"], de_acuerdo=True, created_at=ahora
            )
        )
        session.add(
            EvaluationComment(
                evaluation_id=eid,
                autor_id=user["sub"],
                tipo="acuerdo",
                texto="Marcada en lote.",
                created_at=ahora,
            )
        )
        n += 1
    auditoria.registrar(session, user["sub"], "validar_lote", detalle={"cantidad": n})
    await session.commit()
    return LoteOut(validadas=n)


class ComentarioIn(BaseModel):
    texto: str = Field(min_length=1, max_length=2000)


@router.post("/evaluaciones/{evaluation_id}/comentarios", response_model=DetalleEvaluacion)
async def comentar(
    evaluation_id: str,
    payload: ComentarioIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DetalleEvaluacion:
    """Mensaje en la conversación: su validador jurídico o el semillerista autor."""
    await calendario.exigir_plazo(session, "fin_validacion", "validar")
    e = await _evaluacion(session, evaluation_id)
    if e.evaluador_id != user["sub"]:
        await _exigir_juridico(session, user, e)
    session.add(
        EvaluationComment(
            evaluation_id=evaluation_id,
            autor_id=user["sub"],
            tipo="comentario",
            texto=payload.texto.strip(),
            created_at=datetime.now(UTC),
        )
    )
    await session.commit()
    return await _detalle(session, evaluation_id)


# ── Gestión costera: pertinencia de la pregunta ──────────────────────────────


class PertinenciaIn(BaseModel):
    pertinente: bool
    comentario: str | None = Field(default=None, max_length=2000)


class PertinenciaOut(BaseModel):
    message_id: str
    pertinente: bool
    comentario: str | None


@router.put("/preguntas/{message_id}/pertinencia", response_model=PertinenciaOut)
async def pertinencia(
    message_id: str,
    payload: PertinenciaIn,
    user: dict = Depends(require_validacion),
    session: AsyncSession = Depends(get_session),
) -> PertinenciaOut:
    """¿La pregunta es del tema de playas? (Camilo). "No" la saca de premios."""
    await calendario.exigir_plazo(session, "fin_validacion", "validar")
    tipo, _ = await _validador(session, user)
    if tipo != "costero":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "La pertinencia la marca la validación de gestión costera."
        )
    preguntas = await _cargar(session)
    if not any(p.message_id == message_id for p in preguntas):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pregunta no encontrada.")
    comentario = (payload.comentario or "").strip() or None
    r = await session.get(PertinenceReview, message_id)
    if r is None:
        r = PertinenceReview(message_id=message_id, validador_id=user["sub"], pertinente=True)
        session.add(r)
    r.validador_id = user["sub"]
    r.pertinente = payload.pertinente
    r.comentario = comentario
    r.updated_at = datetime.now(UTC)
    await session.commit()
    return PertinenciaOut(message_id=message_id, pertinente=r.pertinente, comentario=comentario)
