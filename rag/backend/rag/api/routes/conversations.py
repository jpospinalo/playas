"""Endpoints de conversaciones: CRUD y generación de título con IA."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import Conversation, Message
from rag.api.query_support import _conversation_thread_id
from rag.api.rate_limit import get_title_user
from rag.api.schemas import SourceGroup
from rag.core.llm_factory import get_provider

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

# A3.4 — límite de tamaño serializado de `sources` al persistir un mensaje.
#
# Medido sobre el caso realista más grande de hoy: k=8 fragmentos (tope
# actual de `QueryRequest.k`), en el peor caso cada uno en su propio
# `SourceGroup` (sin agrupar por archivo fuente), con `content` recortado a
# 500 caracteres (ver `SourceFragment` en `api/schemas.py`) más metadata
# típica por fragmento (Corporación, Radicado, Magistrado, Tema — o para
# normativa: norma/titulo/capitulo/articulo). Eso serializa en la práctica a
# ~10-15 KB. El valor de abajo deja un margen amplio (~7-10x ese máximo
# observado) para no rechazar payloads legítimos con algo más de metadata,
# sin permitir que una fila JSON crezca sin límite.
_MAX_SOURCES_SERIALIZED_CHARS = 100_000

_TITLE_PROMPT = (
    "Genera un título conciso (máximo 8 palabras) para una consulta jurídica o normativa "
    "sobre playas, zonas costeras, pesca, turismo, usos, derechos o procedimientos relacionados. "
    "El título debe resumir la esencia de la consulta. "
    "Responde solo con el título, sin comillas ni puntuación final.\n\n"
    "Consulta: {message}"
)


class GenerateTitleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_message: str = Field(min_length=1, max_length=4000)
    conversation_id: str = Field(min_length=1, max_length=64)


class GenerateTitleResponse(BaseModel):
    title: str


class ConversationOut(BaseModel):
    id: str
    title: str | None
    thread_id: str
    created_at: str
    updated_at: str
    message_count: int


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    thread_id: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=120)


class MessageOut(BaseModel):
    id: str
    role: str
    text: str
    sources: list | None
    created_at: str


class AddMessageRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message_id: str | None = Field(default=None, min_length=1, max_length=64)
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=50_000)
    sources: list[SourceGroup] | None = Field(default=None, max_length=20)

    @field_validator("sources")
    @classmethod
    def _limit_serialized_size(cls, value: list[SourceGroup] | None) -> list[SourceGroup] | None:
        """A3.4 — rechaza payloads de `sources` excesivos (ver
        `_MAX_SOURCES_SERIALIZED_CHARS` arriba para la medición y el margen
        elegido). No trunca: un payload que exceda el límite se rechaza
        entero con 422, nunca se recorta en silencio."""
        if value is None:
            return value
        serialized_chars = sum(len(group.model_dump_json()) for group in value)
        if serialized_chars > _MAX_SOURCES_SERIALIZED_CHARS:
            raise ValueError(
                "sources excede el tamaño máximo permitido "
                f"({serialized_chars} > {_MAX_SOURCES_SERIALIZED_CHARS} caracteres serializados)."
            )
        return value


class UpdateConversationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=120)


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    """Lista las conversaciones del usuario autenticado, más recientes primero."""
    result = await session.execute(
        select(Conversation)
        .where(Conversation.user_id == user["sub"])
        .order_by(Conversation.updated_at.desc())
    )
    convs = result.scalars().all()
    return [
        ConversationOut(
            id=c.id,
            title=c.title,
            thread_id=c.thread_id,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
            message_count=c.message_count,
        )
        for c in convs
    ]


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: CreateConversationRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    """Crea una nueva conversación para el usuario autenticado."""
    now = datetime.now(UTC)
    conv = Conversation(
        id=str(uuid.uuid4()),
        user_id=user["sub"],
        thread_id=payload.thread_id,
        title=payload.title,
        created_at=now,
        updated_at=now,
        message_count=0,
    )
    session.add(conv)
    await session.commit()
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        thread_id=conv.thread_id,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=conv.message_count,
    )


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MessageOut]:
    """Retorna los mensajes de una conversación, en orden cronológico."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    msgs = result.scalars().all()
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            text=m.text,
            sources=m.sources,
            created_at=m.created_at.isoformat(),
        )
        for m in msgs
    ]


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_message(
    conversation_id: str,
    payload: AddMessageRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageOut:
    """Agrega un mensaje a una conversación y actualiza su contador."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )
    # A3.4 — `payload.sources` son instancias de `SourceGroup` (Pydantic), no
    # el JSON plano que espera la columna `Message.sources`: se convierten
    # explícitamente con `model_dump()` antes de comparar o persistir. Nunca
    # se envían instancias Pydantic directamente a la columna JSON.
    sources_payload = (
        [group.model_dump() for group in payload.sources] if payload.sources is not None else None
    )
    if payload.message_id:
        existing = await session.get(Message, payload.message_id)
        if existing is not None:
            if (
                existing.conversation_id == conversation_id
                and existing.role == payload.role
                and existing.text == payload.text
                and existing.sources == sources_payload
            ):
                return MessageOut(
                    id=existing.id,
                    role=existing.role,
                    text=existing.text,
                    sources=existing.sources,
                    created_at=existing.created_at.isoformat(),
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="El identificador del mensaje ya está en uso.",
            )
    now = datetime.now(UTC)
    msg = Message(
        id=payload.message_id or str(uuid.uuid4()),
        conversation_id=conversation_id,
        role=payload.role,
        text=payload.text,
        sources=sources_payload,
        created_at=now,
    )
    conv.message_count = (conv.message_count or 0) + 1
    conv.updated_at = now
    session.add(msg)
    await session.commit()
    return MessageOut(
        id=msg.id,
        role=msg.role,
        text=msg.text,
        sources=msg.sources,
        created_at=msg.created_at.isoformat(),
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str,
    payload: UpdateConversationRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    """Actualiza el título de una conversación."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )
    if payload.title is not None:
        conv.title = payload.title
    conv.updated_at = datetime.now(UTC)
    await session.commit()
    return ConversationOut(
        id=conv.id,
        title=conv.title,
        thread_id=conv.thread_id,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=conv.message_count,
    )


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Elimina una conversación y todos sus mensajes."""
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )
    # C4 — capturado ANTES de borrar la fila: es el identificador histórico
    # de checkpoint (ver _cleanup_checkpoint_after_delete más abajo), no
    # accesible una vez que `conv` se borra y expira de la sesión.
    legacy_thread_id = conv.thread_id
    result = await session.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    for msg in result.scalars().all():
        await session.delete(msg)
    await session.delete(conv)
    await session.commit()

    # C4 — el grafo se lee de `request.app.state.graph` (poblado por el
    # lifespan corregido en C3, siempre el mismo objeto que el singleton
    # `_graph` de `api/main.py`) en vez de importar `get_graph` desde
    # `api/main.py`: ese import diferido existía solo para evitar el ciclo
    # de importación con `api/main.py` (que importa este router), y
    # `Request` — inyectado estándar de FastAPI, excluido automáticamente
    # del schema de OpenAPI — logra lo mismo sin ningún import cruzado ni
    # registro global nuevo. `Request` es un parámetro obligatorio de este
    # endpoint (v1.2/C3): toda invocación real de FastAPI siempre lo inyecta,
    # así que `getattr(..., "graph", None)` solo cubre la ausencia del
    # atributo `graph` en sí (p. ej. arranque en curso, antes de que el
    # lifespan lo asigne) — no la ausencia del propio `request`. Las pruebas
    # que invocan esta función directamente deben construir un `Request`
    # válido (con o sin `app.state.graph`, según el escenario a probar).
    graph = getattr(request.app.state, "graph", None)
    await _cleanup_checkpoint_after_delete(graph, user["sub"], conversation_id, legacy_thread_id)


async def _cleanup_checkpoint_after_delete(
    graph: Any | None,
    user_id: str,
    conversation_id: str,
    legacy_thread_id: str,
) -> None:
    """Borra, si existen, los checkpoints en memoria (``MemorySaver``) de la
    conversación recién eliminada (A3.2, ampliado por C4).

    Sin esto, el checkpoint del proceso queda huérfano indefinidamente tras
    borrar la conversación de la base de datos: ninguna solicitud futura
    puede volver a alcanzarlo (su ``conversation_id`` ya no existe), pero
    tampoco se libera hasta que el proceso se reinicia.

    C4 — dos identificadores pueden apuntar a checkpoints DISTINTOS de la
    misma conversación lógica: ``_conversation_thread_id(user_id,
    conversation_id)`` (la clave que usa cualquier consulta hecha después de
    que la fila ``Conversation`` ya existiera) y ``_conversation_thread_id(
    user_id, legacy_thread_id)`` (la clave que pudieron haber usado sus
    primeros turnos, antes de que esa fila existiera — ver ``_make_config``
    en ``query_support.py``: prioriza ``conversation_id`` sobre
    ``thread_id``, pero cae a este último si el primero no vino en la
    request). Si ambos coinciden, el ``set`` de abajo los deduplica y se
    borra una sola vez. Cada clave se intenta de forma INDEPENDIENTE: que
    una falle no debe impedir el intento de la otra.

    Es una limpieza en el mismo espíritu que el re-hash oportunista de A2:
    la operación primaria (borrar la conversación) ya se confirmó antes de
    llegar aquí, así que ningún fallo de esta función — grafo no disponible,
    checkpointer sin ese método, lo que sea — debe convertir ese borrado ya
    exitoso en un error para el cliente; por eso este método nunca lanza.

    v1.2/C2 — el `except` de abajo NO usa `exc_info=True`: un checkpointer de
    terceros puede incluir en su mensaje de excepción (o en el traceback)
    valores internos sensibles, como el propio `thread_id` que se le pasó.
    Registrar esa excepción completa filtraría ese identificador (y
    potencialmente contenido de negocio) al log. Se conserva únicamente el
    nombre de la clase de la excepción (`error_type`) como señal operativa
    mínima — suficiente para diagnosticar el tipo de fallo sin exponer nada
    de su contenido.
    """
    if graph is None:
        logger.warning("checkpoint_cleanup_skipped_graph_unavailable_after_conversation_delete")
        return

    thread_ids = {
        _conversation_thread_id(user_id, conversation_id),
        _conversation_thread_id(user_id, legacy_thread_id),
    }
    for thread_id in thread_ids:
        try:
            await graph.checkpointer.adelete_thread(thread_id)
        except Exception as exc:
            logger.warning(
                "checkpoint_cleanup_failed_after_conversation_delete error_type=%s",
                type(exc).__name__,
            )


@router.post("/generate-title", response_model=GenerateTitleResponse)
async def generate_title(
    request: GenerateTitleRequest,
    user: dict = Depends(get_title_user),
    session: AsyncSession = Depends(get_session),
) -> GenerateTitleResponse:
    """Genera un título corto con IA y lo guarda en la conversación."""
    conv = await session.get(Conversation, request.conversation_id)
    if conv is None or conv.user_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )

    provider = get_provider()
    llm = provider.create_llm(temperature=0.3, use_case="title-generation")

    prompt = _TITLE_PROMPT.format(message=request.first_message[:400])
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        title = str(response.content).strip().strip('"').strip("'")[:60]
        if not title:
            title = request.first_message[:60]
    except Exception as exc:
        logger.exception("Error generando el título de la conversación")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible generar el título.",
        ) from exc

    conv.title = title
    await session.commit()

    return GenerateTitleResponse(title=title)
