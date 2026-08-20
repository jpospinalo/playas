"""Endpoints de conversaciones: CRUD y generación de título con IA."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import Conversation, Message
from rag.api.rate_limit import get_title_user
from rag.core.llm_factory import get_provider

router = APIRouter(prefix="/api/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)

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
    sources: list | None = Field(default=None, max_length=20)


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
    if payload.message_id:
        existing = await session.get(Message, payload.message_id)
        if existing is not None:
            if (
                existing.conversation_id == conversation_id
                and existing.role == payload.role
                and existing.text == payload.text
                and existing.sources == payload.sources
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
        sources=payload.sources,
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
    result = await session.execute(
        select(Message).where(Message.conversation_id == conversation_id)
    )
    for msg in result.scalars().all():
        await session.delete(msg)
    await session.delete(conv)
    await session.commit()


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
