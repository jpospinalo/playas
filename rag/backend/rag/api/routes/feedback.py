"""Endpoints para registro de feedback de usuarios.

POST /api/feedback          — Feedback de conversación (multi-dimensión)
POST /api/feedback/message   — Feedback de mensaje individual (pertinencia + precisión)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api.auth import get_current_user
from rag.api.database import get_session
from rag.api.models import Conversation, Feedback, Message, MessageFeedback
from rag.api.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    MessageFeedbackRequest,
    MessageFeedbackResponse,
)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> FeedbackResponse:
    """Registra el feedback de conversación de un usuario."""
    conversation_title: str | None = None
    if request.conversation_id:
        conv = await session.get(Conversation, request.conversation_id)
        if conv is None or conv.user_id != user["sub"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversación no encontrada.",
            )
        conversation_title = conv.title

    feedback = Feedback(
        id=str(uuid.uuid4()),
        user_id=user["sub"],
        user_email=user.get("email", ""),
        ratings=request.ratings.model_dump(),
        comment=request.comment,
        conversation_id=request.conversation_id,
        conversation_title=conversation_title,
        created_at=datetime.now(UTC),
    )
    session.add(feedback)
    await session.commit()
    return FeedbackResponse(id=feedback.id)


@router.post(
    "/message", response_model=MessageFeedbackResponse, status_code=status.HTTP_201_CREATED
)
async def submit_message_feedback(
    request: MessageFeedbackRequest,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MessageFeedbackResponse:
    """Registra el feedback de un mensaje individual del agente.

    Previene duplicados: un usuario solo puede calificar cada mensaje una vez.
    """
    conv = await session.get(Conversation, request.conversation_id)
    if conv is None or conv.user_id != user["sub"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversación no encontrada.",
        )

    message = await session.get(Message, request.message_id)
    if (
        message is None
        or message.conversation_id != request.conversation_id
        or message.role != "assistant"
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mensaje no encontrado.",
        )

    dup = await session.execute(
        select(MessageFeedback).where(
            MessageFeedback.user_id == user["sub"],
            MessageFeedback.message_id == request.message_id,
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe feedback para este mensaje.",
        )

    msg_feedback = MessageFeedback(
        id=str(uuid.uuid4()),
        user_id=user["sub"],
        user_email=user.get("email", ""),
        conversation_id=request.conversation_id,
        message_id=request.message_id,
        ratings=request.ratings.model_dump(),
        expected_answer=request.expected_answer,
        created_at=datetime.now(UTC),
    )
    session.add(msg_feedback)
    await session.commit()
    return MessageFeedbackResponse(id=msg_feedback.id)
