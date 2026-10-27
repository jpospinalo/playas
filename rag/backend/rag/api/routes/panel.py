"""Panel de administración: cifras de uso y calidad. Solo lectura.

Solo accesibles para usuarios con rol 'admin' o 'super-admin' (mismo
``require_admin`` que ``routes/admin.py``). Ninguna ruta escribe en la base.

  GET /api/admin/panel/resumen                 — cifras, serie, temas, normas, playas, personas, brechas
  GET /api/admin/panel/preguntas               — preguntas del periodo, paginadas y filtrables
  GET /api/admin/panel/preguntas.csv           — las mismas preguntas en CSV (UTF-8 con BOM)
  GET /api/admin/panel/conversaciones/{id}     — detalle de una conversación (lectura)
  GET /api/admin/panel/encuestas               — encuestas de satisfacción al final de la conversación

Las clasificaciones (tema, playa, resultado, normas) salen de
``rag/api/panel_metricas.py``: reglas sobre el texto guardado, sin IA.
El cálculo se hace en Python sobre las filas del periodo (cientos o pocos
miles de mensajes); así es idéntico en SQLite y PostgreSQL.
"""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api import ejercicio as ej
from rag.api import panel_metricas as pm
from rag.api.auth import require_admin
from rag.api.database import get_session
from rag.api.models import (
    Conversation,
    ExerciseProfile,
    Feedback,
    Message,
    MessageFeedback,
    User,
)
from rag.api.schemas import (
    PanelBrecha,
    PanelCifras,
    PanelConteo,
    PanelConversacionResponse,
    PanelEncuestaItem,
    PanelEncuestasResponse,
    PanelFuente,
    PanelMensaje,
    PanelNorma,
    PanelPeriodo,
    PanelPersonas,
    PanelPreguntaItem,
    PanelPreguntasResponse,
    PanelPunto,
    PanelResumenResponse,
    PanelTema,
)

router = APIRouter(prefix="/api/admin/panel", tags=["admin-panel"])

# Cuenta marcador que crea `scripts/seed_panel_demo.py`: si existe, el panel
# avisa "datos de demostración". No se crea ni se toca desde aquí.
DEMO_EMAIL = "demo-seed@atlas.local"

_TOP_NORMAS = 10
_TOP_BRECHAS = 50

DiasQuery = Query(default=30, ge=0, le=3660, description="Últimos N días (0 = todo)")
TemaQuery = Query(default=None, description="Id de tema (entrar, pescar, …, otros)")
ParticipanteQuery = Query(default=None, max_length=20, description="Número de participante (P001…)")
TipoPlayaQuery = Query(default=None, ge=1, le=5, description="Tipo de usuario de playa (1-5)")
ResultadoFiltro = Literal[
    "con_fuente",
    "sin_respuesta_segura",
    "no_le_sirvio",
    "fuera_de_tema",
    "pide_aclarar",
    # Para la página de opiniones (PQ-38): solo las calificadas.
    "calificadas",
    "le_sirvio",
    "con_esperaba",
]


@dataclass
class _Fila:
    """Una pregunta (mensaje `user`) con su respuesta y su calificación."""

    id: str
    conversation_id: str
    user_id: str
    texto: str
    fecha: datetime
    tema: str
    playa: str
    resultado: str = pm.SIN_RESPUESTA
    normas: list[tuple[str, str | None]] = field(default_factory=list)
    respuesta_id: str | None = None
    calificacion: str | None = None
    esperaba: str | None = None

    @property
    def es_brecha(self) -> bool:
        """Sin respuesta segura, o respondida con norma y calificada "no me
        sirvió". Una pregunta fuera de tema mal calificada no es una brecha
        de contenido."""
        return self.resultado in pm.BRECHAS or (
            self.resultado == pm.CON_FUENTE and self.calificacion == pm.NO_UTIL
        )


async def _cargar_filas(session: AsyncSession, desde: datetime | None) -> list[_Fila]:
    stmt = (
        select(
            Message.id,
            Message.conversation_id,
            Message.role,
            Message.text,
            Message.sources,
            Message.created_at,
            Conversation.user_id,
        )
        .join(Conversation, Conversation.id == Message.conversation_id)
        # role desc: a igual fecha, "user" va antes que "assistant".
        .order_by(Message.conversation_id, Message.created_at, Message.role.desc(), Message.id)
    )
    if desde is not None:
        stmt = stmt.where(Message.created_at >= desde)
    filas: list[_Fila] = []
    previa: _Fila | None = None
    for mid, cid, role, texto, sources, creado, uid in (await session.execute(stmt)).all():
        if role == "user":
            previa = _Fila(
                id=mid,
                conversation_id=cid,
                user_id=uid,
                texto=texto,
                fecha=pm.a_utc(creado),
                tema=pm.clasificar_tema(texto),
                playa=pm.detectar_playa(texto),
            )
            filas.append(previa)
        elif role == "assistant" and previa is not None and previa.conversation_id == cid:
            if previa.respuesta_id is None:
                previa.respuesta_id = mid
                previa.resultado = pm.clasificar_respuesta(texto, sources)
                previa.normas = pm.normas_citadas(sources)
                # Si ATLAS la juzgó fuera del tema de playas (o era un saludo),
                # no cuenta en un tema de playas aunque nombre un "restaurante"
                # o un "hotel" (PQ-46).
                if previa.resultado in (pm.FUERA_DE_TEMA, pm.SALUDO):
                    previa.tema = pm.TEMA_OTROS
            previa = None

    por_respuesta = {f.respuesta_id: f for f in filas if f.respuesta_id}
    ids = list(por_respuesta)
    for i in range(0, len(ids), 500):
        fb_stmt = (
            select(
                MessageFeedback.message_id, MessageFeedback.ratings, MessageFeedback.expected_answer
            )
            .where(MessageFeedback.message_id.in_(ids[i : i + 500]))
            .order_by(MessageFeedback.created_at, MessageFeedback.id)
        )
        # La más reciente gana si alguien calificó dos veces.
        for message_id, ratings, esperaba in (await session.execute(fb_stmt)).all():
            fila = por_respuesta[message_id]
            fila.calificacion = pm.calificacion(ratings)
            fila.esperaba = (esperaba or "").strip() or fila.esperaba
    return filas


async def _primeras_preguntas(session: AsyncSession) -> dict[str, datetime]:
    stmt = (
        select(Conversation.user_id, func.min(Message.created_at))
        .join(Message, Message.conversation_id == Conversation.id)
        .where(Message.role == "user")
        .group_by(Conversation.user_id)
    )
    return {uid: pm.a_utc(dt) for uid, dt in (await session.execute(stmt)).all() if dt}


async def _es_demo(session: AsyncSession) -> bool:
    stmt = select(User.id).where(User.email == DEMO_EMAIL).limit(1)
    return (await session.execute(stmt)).first() is not None


def _en(filas: list[_Fila], desde: datetime | None, hasta: datetime | None) -> list[_Fila]:
    return [
        f
        for f in filas
        if (desde is None or f.fecha >= desde) and (hasta is None or f.fecha < hasta)
    ]


def _cifras(
    filas: list[_Fila], primeras: dict[str, datetime], desde: datetime | None
) -> PanelCifras:
    respondidas = [f for f in filas if f.resultado not in (pm.SALUDO, pm.SIN_RESPUESTA)]
    calificadas = [f for f in filas if f.calificacion]
    personas = {f.user_id for f in filas}
    nuevas = {u for u in personas if desde is None or primeras.get(u, desde) >= desde}
    return PanelCifras(
        preguntas=len(filas),
        personas=len(personas),
        personas_nuevas=len(nuevas),
        respuestas=len(respondidas),
        con_fuente=sum(f.resultado == pm.CON_FUENTE for f in respondidas),
        sin_respuesta_segura=sum(f.resultado in pm.BRECHAS for f in respondidas),
        fuera_de_tema=sum(f.resultado == pm.FUERA_DE_TEMA for f in respondidas),
        pide_aclarar=sum(f.resultado == pm.PIDE_ACLARAR for f in respondidas),
        saludos=sum(f.resultado == pm.SALUDO for f in filas),
        sin_respuesta_guardada=sum(f.resultado == pm.SIN_RESPUESTA for f in filas),
        calificaciones=len(calificadas),
        le_sirvio=sum(f.calificacion == pm.UTIL for f in calificadas),
        no_le_sirvio=sum(f.calificacion == pm.NO_UTIL for f in calificadas),
    )


def _serie(filas: list[_Fila], periodo: pm.Periodo) -> tuple[str, list[PanelPunto]]:
    """Preguntas por día (periodos de hasta 14 días) o por semana de lunes a
    domingo, en hora de Colombia. Solo cuenta preguntas del periodo; una
    semana que el periodo corta por un lado queda marcada ``parcial`` con
    los días que sí cubre (``desde``/``hasta``)."""
    agrupacion: Literal["dia", "semana"] = "dia" if 0 < periodo.dias <= 14 else "semana"
    clave = pm.clave_dia if agrupacion == "dia" else pm.clave_semana
    preguntas: Counter[str] = Counter()
    brechas: Counter[str] = Counter()
    for f in filas:
        k = clave(f.fecha)
        preguntas[k] += 1
        brechas[k] += f.resultado in pm.BRECHAS
    inicio = periodo.inicio or (min(f.fecha for f in filas) if filas else periodo.fin)
    primer_dia = date.fromisoformat(pm.clave_dia(inicio))
    ultimo_dia = date.fromisoformat(pm.clave_dia(periodo.fin))
    largo = timedelta(days=1 if agrupacion == "dia" else 7)
    # Todos los días/semanas del periodo, también los que no tienen preguntas.
    puntos: list[PanelPunto] = []
    actual = date.fromisoformat(clave(inicio))
    while actual <= ultimo_dia:
        fin_bloque = actual + largo - timedelta(days=1)
        desde, hasta = max(actual, primer_dia), min(fin_bloque, ultimo_dia)
        k = actual.isoformat()
        puntos.append(
            PanelPunto(
                fecha=k,
                desde=desde.isoformat(),
                hasta=hasta.isoformat(),
                parcial=agrupacion == "semana" and (desde != actual or hasta != fin_bloque),
                preguntas=preguntas[k],
                sin_respuesta_segura=brechas[k],
            )
        )
        actual += largo
    return agrupacion, puntos


def _temas(filas: list[_Fila]) -> list[PanelTema]:
    grupos: dict[str, list[_Fila]] = defaultdict(list)
    for f in filas:
        grupos[f.tema].append(f)
    salida = [
        PanelTema(
            id=tema_id,
            titulo=pm.titulo_tema(tema_id),
            preguntas=len(fs),
            calificaciones=sum(1 for f in fs if f.calificacion),
            le_sirvio=sum(f.calificacion == pm.UTIL for f in fs),
            brechas=sum(f.es_brecha for f in fs),
        )
        for tema_id, fs in grupos.items()
    ]
    # "Otros temas" siempre al final, aunque sea grande.
    salida.sort(key=lambda t: (t.id == pm.TEMA_OTROS, -t.preguntas, t.titulo))
    return salida


def _normas(filas: list[_Fila]) -> list[PanelNorma]:
    conteo: Counter[str] = Counter()
    tipos: dict[str, str | None] = {}
    for f in filas:
        for nombre, doc_type in f.normas:
            conteo[nombre] += 1
            tipos.setdefault(nombre, doc_type)
    return [
        PanelNorma(nombre=n, doc_type=tipos[n], respuestas=c)
        for n, c in sorted(conteo.items(), key=lambda x: (-x[1], x[0]))[:_TOP_NORMAS]
    ]


def _playas(filas: list[_Fila]) -> tuple[list[PanelConteo], int]:
    conteo = Counter(f.playa for f in filas)
    sin = conteo.pop(pm.SIN_PLAYA, 0)
    return [
        PanelConteo(nombre=n, preguntas=c)
        for n, c in sorted(conteo.items(), key=lambda x: (-x[1], x[0]))
    ], sin


def _personas(cifras: PanelCifras) -> PanelPersonas:
    # Sin ranking de personas (Ley 1581, finalidad): el panel sirve para
    # mejorar ATLAS, no para seguir a alguien. Ver PQ-05.
    return PanelPersonas(
        activas=cifras.personas,
        nuevas=cifras.personas_nuevas,
        recurrentes=cifras.personas - cifras.personas_nuevas,
        preguntas_por_persona=round(cifras.preguntas / cifras.personas, 1)
        if cifras.personas
        else 0,
    )


def _brechas(filas: list[_Fila]) -> tuple[int, list[PanelBrecha]]:
    grupos: dict[str, list[_Fila]] = defaultdict(list)
    for f in filas:
        if f.es_brecha:
            grupos[pm.normalizar(f.texto)].append(f)
    salida: list[PanelBrecha] = []
    for fs in grupos.values():
        fs.sort(key=lambda f: f.fecha, reverse=True)
        ultima = fs[0]
        esperaba = next((f.esperaba for f in fs if f.esperaba), None)
        salida.append(
            PanelBrecha(
                pregunta=ultima.texto,
                veces=len(fs),
                tema=ultima.tema,
                tema_titulo=pm.titulo_tema(ultima.tema),
                motivo="no_le_sirvio"
                if ultima.calificacion == pm.NO_UTIL
                else "sin_respuesta_segura",
                esperaba=esperaba,
                ultima=ultima.fecha.isoformat(),
                conversation_id=ultima.conversation_id,
            )
        )
    # Más repetidas primero; con las mismas veces, la más reciente primero.
    salida.sort(key=lambda b: b.ultima, reverse=True)
    salida.sort(key=lambda b: b.veces, reverse=True)
    return sum(len(fs) for fs in grupos.values()), salida[:_TOP_BRECHAS]


async def _perfiles(session: AsyncSession) -> dict[str, tuple[str | None, int | None]]:
    """user_id → (número de participante, tipo de usuario de playa)."""
    filas = await session.execute(
        select(ExerciseProfile.user_id, ExerciseProfile.codigo, ExerciseProfile.tipo_playa)
    )
    return {uid: (codigo, tipo) for uid, codigo, tipo in filas.all()}


def _filtrar_persona(
    filas: list[_Fila],
    perfiles: dict[str, tuple[str | None, int | None]],
    participante: str | None,
    tipo_playa: int | None,
) -> list[_Fila]:
    if participante:
        buscado = participante.strip().upper()
        filas = [f for f in filas if (perfiles.get(f.user_id, (None, None))[0] or "") == buscado]
    if tipo_playa:
        filas = [f for f in filas if perfiles.get(f.user_id, (None, None))[1] == tipo_playa]
    return filas


def _filtrar_tema(filas: list[_Fila], tema: str | None) -> list[_Fila]:
    if not tema:
        return filas
    if tema != pm.TEMA_OTROS and tema not in pm.TEMAS_POR_ID:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Tema desconocido: {tema!r}")
    return [f for f in filas if f.tema == tema]


@router.get("/resumen", response_model=PanelResumenResponse)
async def resumen(
    dias: int = DiasQuery,
    tema: str | None = TemaQuery,
    participante: str | None = ParticipanteQuery,
    tipo_playa: int | None = TipoPlayaQuery,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PanelResumenResponse:
    """Cifras del periodo y del periodo anterior, con temas, normas, playas y brechas."""
    periodo = pm.calcular_periodo(dias)
    todas = _filtrar_persona(
        _filtrar_tema(await _cargar_filas(session, periodo.anterior_inicio), tema),
        await _perfiles(session),
        participante,
        tipo_playa,
    )
    primeras = await _primeras_preguntas(session)
    filas = _en(todas, periodo.inicio, None)
    cifras = _cifras(filas, primeras, periodo.inicio)
    anterior = None
    if periodo.anterior_inicio is not None:
        anterior = _cifras(
            _en(todas, periodo.anterior_inicio, periodo.inicio), primeras, periodo.anterior_inicio
        )
    agrupacion, serie = _serie(filas, periodo)
    playas, sin_playa = _playas(filas)
    brechas_total, brechas = _brechas(filas)
    return PanelResumenResponse(
        demo=await _es_demo(session),
        periodo=PanelPeriodo(
            dias=periodo.dias,
            desde=periodo.inicio.isoformat() if periodo.inicio else None,
            hasta=periodo.fin.isoformat(),
            agrupacion=agrupacion,  # type: ignore[arg-type]
        ),
        cifras=cifras,
        anterior=anterior,
        serie=serie,
        temas=_temas(filas),
        normas=_normas(filas),
        playas=playas,
        sin_playa=sin_playa,
        personas=_personas(cifras),
        brechas_total=brechas_total,
        brechas=brechas,
    )


async def _preguntas_filtradas(
    session: AsyncSession,
    dias: int,
    tema: str | None,
    resultado: ResultadoFiltro | None,
    participante: str | None = None,
    tipo_playa: int | None = None,
) -> list[_Fila]:
    periodo = pm.calcular_periodo(dias)
    filas = _filtrar_tema(await _cargar_filas(session, periodo.inicio), tema)
    filas = _filtrar_persona(filas, await _perfiles(session), participante, tipo_playa)
    if resultado == "con_fuente":
        filas = [f for f in filas if f.resultado == pm.CON_FUENTE]
    elif resultado == "sin_respuesta_segura":
        filas = [f for f in filas if f.resultado in pm.BRECHAS]
    elif resultado == "no_le_sirvio":
        filas = [f for f in filas if f.calificacion == pm.NO_UTIL]
    elif resultado == "fuera_de_tema":
        filas = [f for f in filas if f.resultado == pm.FUERA_DE_TEMA]
    elif resultado == "pide_aclarar":
        filas = [f for f in filas if f.resultado == pm.PIDE_ACLARAR]
    elif resultado == "calificadas":
        filas = [f for f in filas if f.calificacion]
    elif resultado == "le_sirvio":
        filas = [f for f in filas if f.calificacion == pm.UTIL]
    elif resultado == "con_esperaba":
        filas = [f for f in filas if f.esperaba]
    filas.sort(key=lambda f: (f.fecha, f.id), reverse=True)
    return filas


def _nombre(nombre: str | None) -> str:
    return (nombre or "").strip() or "Sin nombre"


async def _nombres(session: AsyncSession, filas: list[_Fila]) -> dict[str, str]:
    """Solo el nombre que la persona dio al registrarse: nunca el correo."""
    ids = list({f.user_id for f in filas})
    if not ids:
        return {}
    stmt = select(User.id, User.display_name).where(User.id.in_(ids))
    return {uid: _nombre(nombre) for uid, nombre in (await session.execute(stmt)).all()}


def _item(
    f: _Fila,
    nombres: dict[str, str],
    perfiles: dict[str, tuple[str | None, int | None]] | None = None,
) -> PanelPreguntaItem:
    codigo, tipo = (perfiles or {}).get(f.user_id, (None, None))
    return PanelPreguntaItem(
        participante=codigo,
        tipo_playa=tipo,
        id=f.id,
        fecha=f.fecha.isoformat(),
        pregunta=f.texto,
        tema=f.tema,
        tema_titulo=pm.titulo_tema(f.tema),
        playa=None if f.playa == pm.SIN_PLAYA else f.playa,
        resultado=f.resultado,
        fuentes=len(f.normas),
        fuentes_sentencias=sum(t == "jurisprudencia" for _, t in f.normas),
        calificacion=f.calificacion,
        esperaba=f.esperaba,
        persona=nombres.get(f.user_id, _nombre(None)),
        conversation_id=f.conversation_id,
    )


@router.get("/preguntas", response_model=PanelPreguntasResponse)
async def preguntas(
    dias: int = DiasQuery,
    tema: str | None = TemaQuery,
    resultado: ResultadoFiltro | None = Query(default=None),
    participante: str | None = ParticipanteQuery,
    tipo_playa: int | None = TipoPlayaQuery,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PanelPreguntasResponse:
    """Preguntas del periodo, de la más reciente a la más antigua."""
    filas = await _preguntas_filtradas(session, dias, tema, resultado, participante, tipo_playa)
    pagina = filas[(page - 1) * page_size : page * page_size]
    nombres = await _nombres(session, pagina)
    return PanelPreguntasResponse(
        items=[_item(f, nombres, await _perfiles(session)) for f in pagina],
        total=len(filas),
        page=page,
        page_size=page_size,
    )


_ETIQUETAS_RESULTADO = {
    pm.CON_FUENTE: "Con fuente citada",
    pm.SIN_EVIDENCIA: "Sin respuesta segura (sin evidencia)",
    pm.SIN_CITA_VALIDA: "Sin respuesta segura (citas no válidas)",
    pm.SIN_FUENTE_OTRO: "Sin respuesta segura (sin fuente)",
    pm.FUERA_DE_TEMA: "Fuera de tema",
    pm.PIDE_ACLARAR: "Pidió aclarar",
    pm.SALUDO: "Saludo",
    pm.SIN_RESPUESTA: "Sin respuesta guardada",
}
_ETIQUETAS_CALIFICACION = {pm.UTIL: "Le sirvió", pm.NO_UTIL: "No le sirvió", pm.NEUTRA: "Regular"}


def _tipo_texto(tipo: int | None) -> str:
    """Mismo texto de la planilla del ejercicio: "Tipo 2. Pescadores"."""
    return f"Tipo {tipo}. {ej.TIPOS_PLAYA[tipo]}" if tipo in ej.TIPOS_PLAYA else ""


def _celda(valor: object) -> str:
    """Evita que Excel ejecute una celda como fórmula (inyección CSV)."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@", "\t", "\r") else texto


@router.get("/preguntas.csv")
async def preguntas_csv(
    dias: int = DiasQuery,
    tema: str | None = TemaQuery,
    resultado: ResultadoFiltro | None = Query(default=None),
    participante: str | None = ParticipanteQuery,
    tipo_playa: int | None = TipoPlayaQuery,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Las preguntas del periodo con los mismos filtros, en CSV para Excel."""
    filas = await _preguntas_filtradas(session, dias, tema, resultado, participante, tipo_playa)
    nombres = await _nombres(session, filas)
    perfiles = await _perfiles(session)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(
        [
            "Fecha (hora de Colombia)",
            "Participante",
            "Tipo de usuario de playa",
            "Pregunta",
            "Tema",
            "Playa mencionada",
            "Resultado",
            "Fuentes citadas",
            "Calificación",
            "Lo que esperaba",
            "Persona",
            "Conversación",
        ]
    )
    for f in filas:
        escritor.writerow(
            [
                _celda(v)
                for v in (
                    f.fecha.astimezone(pm.HORA_COLOMBIA).strftime("%Y-%m-%d %H:%M"),
                    perfiles.get(f.user_id, (None, None))[0] or "",
                    _tipo_texto(perfiles.get(f.user_id, (None, None))[1]),
                    f.texto,
                    pm.titulo_tema(f.tema),
                    "" if f.playa == pm.SIN_PLAYA else f.playa,
                    _ETIQUETAS_RESULTADO.get(f.resultado, f.resultado),
                    "; ".join(n for n, _ in f.normas),
                    _ETIQUETAS_CALIFICACION.get(f.calificacion or "", "Sin calificar"),
                    f.esperaba,
                    nombres.get(f.user_id, _nombre(None)),
                    f.conversation_id,
                )
            ]
        )
    nombre = f"atlas-preguntas-{'todo' if dias == 0 else f'{dias}-dias'}.csv"
    return Response(
        content="﻿" + salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/conversaciones/{conversation_id}", response_model=PanelConversacionResponse)
async def conversacion(
    conversation_id: str,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PanelConversacionResponse:
    """Una conversación completa, para leer el caso desde el panel."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversación no encontrada.")
    usuario = await session.get(User, conv.user_id)
    mensajes = list(
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at, Message.role.desc(), Message.id)
            )
        )
        .scalars()
        .all()
    )
    ids = [m.id for m in mensajes if m.role == "assistant"]
    feedback: dict[str, tuple[str | None, str | None]] = {}
    if ids:
        stmt = (
            select(
                MessageFeedback.message_id, MessageFeedback.ratings, MessageFeedback.expected_answer
            )
            .where(MessageFeedback.message_id.in_(ids))
            .order_by(MessageFeedback.created_at, MessageFeedback.id)
        )
        for mid, ratings, esperaba in (await session.execute(stmt)).all():
            feedback[mid] = (pm.calificacion(ratings), (esperaba or "").strip() or None)
    return PanelConversacionResponse(
        id=conv.id,
        titulo=conv.title,
        persona=_nombre(usuario.display_name if usuario else None),
        creada=pm.a_utc(conv.created_at).isoformat(),
        mensajes=[
            PanelMensaje(
                id=m.id,
                role=m.role,
                text=m.text,
                fecha=pm.a_utc(m.created_at).isoformat(),
                resultado=pm.clasificar_respuesta(m.text, m.sources)
                if m.role == "assistant"
                else None,
                fuentes=[PanelFuente(nombre=n, doc_type=t) for n, t in pm.normas_citadas(m.sources)]
                if m.role == "assistant"
                else [],
                calificacion=feedback.get(m.id, (None, None))[0],
                esperaba=feedback.get(m.id, (None, None))[1],
            )
            for m in mensajes
        ],
    )


_DIMENSIONES = {
    "general": "overall",
    "claridad": "clarity",
    "tono": "tone",
    "largo": "length",
    "facilidad": "usability",
}


@router.get("/encuestas", response_model=PanelEncuestasResponse)
async def encuestas(
    dias: int = DiasQuery,
    filtro: Literal["buenas", "malas", "con_comentario"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> PanelEncuestasResponse:
    """Encuestas del final de la conversación (tabla `feedback`), con nombre
    de registro en vez de correo y promedios del periodo (PQ-28, PQ-37)."""
    periodo = pm.calcular_periodo(dias)
    stmt = select(Feedback, User.display_name).join(User, User.id == Feedback.user_id, isouter=True)
    if periodo.inicio is not None:
        stmt = stmt.where(Feedback.created_at >= periodo.inicio)
    filas = []
    for fb, nombre in (await session.execute(stmt)).all():
        notas = {k: (fb.ratings or {}).get(v) for k, v in _DIMENSIONES.items()}
        notas = {k: int(v) if isinstance(v, (int, float)) else None for k, v in notas.items()}
        filas.append((fb, nombre, notas))

    def _promedio(k: str) -> float:
        # Solo sobre las encuestas que traen esa nota (claridad es nueva).
        valores = [n[k] for _, _, n in filas if n[k] is not None]
        return round(sum(valores) / len(valores), 1) if valores else 0.0

    promedios = {k: _promedio(k) for k in _DIMENSIONES}
    if filtro == "buenas":
        filas = [x for x in filas if (x[2]["general"] or 0) >= 4]
    elif filtro == "malas":
        filas = [x for x in filas if (x[2]["general"] or 0) <= 2]
    elif filtro == "con_comentario":
        filas = [x for x in filas if (x[0].comment or "").strip()]
    filas.sort(key=lambda x: (pm.a_utc(x[0].created_at), x[0].id), reverse=True)
    pagina = filas[(page - 1) * page_size : page * page_size]
    return PanelEncuestasResponse(
        items=[
            PanelEncuestaItem(
                id=fb.id,
                fecha=pm.a_utc(fb.created_at).isoformat(),
                persona=_nombre(nombre),
                titulo=fb.conversation_title,
                conversation_id=fb.conversation_id,
                comentario=(fb.comment or "").strip() or None,
                general=notas["general"] or 0,
                claridad=notas["claridad"],
                tono=notas["tono"],
                largo=notas["largo"],
                facilidad=notas["facilidad"] or 0,
            )
            for fb, nombre, notas in pagina
        ],
        total=len(filas),
        page=page,
        page_size=page_size,
        promedios=promedios,
    )


@router.get("/encuestas.csv")
async def encuestas_csv(
    dias: int = DiasQuery,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Encuestas de percepción con sus comentarios, en CSV (evidencia del
    informe final: "observaciones y comentarios de los participantes", PDF p. 9)."""
    periodo = pm.calcular_periodo(dias)
    stmt = select(Feedback, User.display_name).join(User, User.id == Feedback.user_id, isouter=True)
    if periodo.inicio is not None:
        stmt = stmt.where(Feedback.created_at >= periodo.inicio)
    filas = sorted(
        (await session.execute(stmt)).all(),
        key=lambda x: (pm.a_utc(x[0].created_at), x[0].id),
    )
    perfiles = await _perfiles(session)
    salida = io.StringIO()
    escritor = csv.writer(salida)
    escritor.writerow(
        [
            "Fecha (hora de Colombia)",
            "Participante",
            "Tipo de usuario de playa",
            "Persona",
            "Claridad de las respuestas",
            "Facilidad de uso",
            "Calificación general",
            "Tono",
            "Largo",
            "Comentario",
        ]
    )
    for fb, nombre in filas:
        r = fb.ratings or {}
        codigo, tipo = perfiles.get(fb.user_id, (None, None))
        escritor.writerow(
            [
                _celda(v)
                for v in (
                    pm.a_utc(fb.created_at).astimezone(pm.HORA_COLOMBIA).strftime("%Y-%m-%d %H:%M"),
                    codigo or "",
                    _tipo_texto(tipo),
                    _nombre(nombre),
                    r.get("clarity") or "",
                    r.get("usability") or "",
                    r.get("overall") or "",
                    r.get("tone") or "",
                    r.get("length") or "",
                    fb.comment or "",
                )
            ]
        )
    nombre_archivo = f"atlas-encuestas-{'todo' if dias == 0 else f'{dias}-dias'}.csv"
    return Response(
        content="\ufeff" + salida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
