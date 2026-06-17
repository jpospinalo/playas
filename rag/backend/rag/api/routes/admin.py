"""Endpoints del panel de administración.

Solo accesibles para usuarios con rol 'admin' o 'super-admin'.

  GET  /api/admin/feedback          — lista paginada de feedback
  GET  /api/admin/message-feedback  — lista paginada de feedback de mensajes
  GET  /api/admin/users             — lista de usuarios
  POST /api/admin/users             — crea usuario
  PATCH /api/admin/users/{uid}/password — cambia contraseña
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rag.api.auth import require_admin
from rag.api.database import get_session
from rag.api.models import Feedback, MessageFeedback, User
from rag.api.schemas import (
    AdminFeedbackItem,
    AdminFeedbackResponse,
    AdminMessageFeedbackItem,
    AdminMessageFeedbackResponse,
    AdminUserItem,
    AdminUsersResponse,
    CreateUserRequest,
    MessageFeedbackRatings,
    RatingDimensions,
    RatingDimensionsFloat,
    UpdatePasswordRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.get("/feedback", response_model=AdminFeedbackResponse)
async def list_feedback(
    page: int = Query(default=1, ge=1, description="Número de página"),
    page_size: int = Query(default=20, ge=1, le=100, description="Ítems por página"),
    min_overall: int | None = Query(default=None, ge=1, le=5),
    max_overall: int | None = Query(default=None, ge=1, le=5),
    start_date: str | None = Query(default=None, description="ISO 8601 — fecha mínima"),
    end_date: str | None = Query(default=None, description="ISO 8601 — fecha máxima"),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminFeedbackResponse:
    """Lista el feedback de conversación ordenado por fecha descendente."""
    stmt = select(Feedback).order_by(Feedback.created_at.desc())

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
            stmt = stmt.where(Feedback.created_at >= dt)
        except ValueError as exc:
            raise HTTPException(422, f"start_date inválido: {start_date!r}") from exc
    if end_date:
        try:
            dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)
            stmt = stmt.where(Feedback.created_at <= dt)
        except ValueError as exc:
            raise HTTPException(422, f"end_date inválido: {end_date!r}") from exc

    docs = list((await session.execute(stmt)).scalars().all())

    if min_overall is not None:
        docs = [d for d in docs if (d.ratings or {}).get("overall", 0) >= min_overall]
    if max_overall is not None:
        docs = [d for d in docs if (d.ratings or {}).get("overall", 0) <= max_overall]

    total = len(docs)
    dims = ["tone", "length", "usability", "overall"]
    distributions: dict[str, dict[str, int]] = {
        d: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0} for d in dims
    }
    sums: dict[str, float] = {d: 0.0 for d in dims}

    for doc in docs:
        for d in dims:
            val = (doc.ratings or {}).get(d, 0)
            if 1 <= val <= 5:
                distributions[d][str(val)] += 1
                sums[d] += val

    avg_ratings = RatingDimensionsFloat(
        **{d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in dims}
    )

    start_idx = (page - 1) * page_size
    items = [
        AdminFeedbackItem(
            id=doc.id,
            userId=doc.user_id,
            userEmail=doc.user_email,
            ratings=RatingDimensions(
                tone=(doc.ratings or {}).get("tone", 0),
                length=(doc.ratings or {}).get("length", 0),
                usability=(doc.ratings or {}).get("usability", 0),
                overall=(doc.ratings or {}).get("overall", 0),
            ),
            comment=doc.comment,
            conversationId=doc.conversation_id,
            conversationTitle=doc.conversation_title,
            createdAt=doc.created_at.isoformat() if doc.created_at else "",
        )
        for doc in docs[start_idx : start_idx + page_size]
    ]

    return AdminFeedbackResponse(
        items=items,
        total=total,
        avg_ratings=avg_ratings,
        distributions=distributions,
    )


@router.get("/message-feedback", response_model=AdminMessageFeedbackResponse)
async def list_message_feedback(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    min_pertinence: int | None = Query(default=None, ge=1, le=5),
    max_pertinence: int | None = Query(default=None, ge=1, le=5),
    min_accuracy: int | None = Query(default=None, ge=1, le=5),
    max_accuracy: int | None = Query(default=None, ge=1, le=5),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminMessageFeedbackResponse:
    """Lista el feedback de mensajes ordenado por fecha descendente."""
    stmt = select(MessageFeedback).order_by(MessageFeedback.created_at.desc())

    if start_date:
        try:
            dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
            stmt = stmt.where(MessageFeedback.created_at >= dt)
        except ValueError as exc:
            raise HTTPException(422, f"start_date inválido: {start_date!r}") from exc
    if end_date:
        try:
            dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)
            stmt = stmt.where(MessageFeedback.created_at <= dt)
        except ValueError as exc:
            raise HTTPException(422, f"end_date inválido: {end_date!r}") from exc

    docs = list((await session.execute(stmt)).scalars().all())

    if min_pertinence is not None:
        docs = [d for d in docs if (d.ratings or {}).get("pertinence", 0) >= min_pertinence]
    if max_pertinence is not None:
        docs = [d for d in docs if (d.ratings or {}).get("pertinence", 0) <= max_pertinence]
    if min_accuracy is not None:
        docs = [d for d in docs if (d.ratings or {}).get("accuracy", 0) >= min_accuracy]
    if max_accuracy is not None:
        docs = [d for d in docs if (d.ratings or {}).get("accuracy", 0) <= max_accuracy]

    total = len(docs)
    msg_dims = ["pertinence", "accuracy"]
    distributions: dict[str, dict[str, int]] = {
        d: {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0} for d in msg_dims
    }
    sums: dict[str, float] = {d: 0.0 for d in msg_dims}

    for doc in docs:
        for d in msg_dims:
            val = (doc.ratings or {}).get(d, 0)
            if 1 <= val <= 5:
                distributions[d][str(val)] += 1
                sums[d] += val

    avg_ratings = {d: round(sums[d] / total, 2) if total > 0 else 0.0 for d in msg_dims}

    start_idx = (page - 1) * page_size
    items = [
        AdminMessageFeedbackItem(
            id=doc.id,
            userId=doc.user_id,
            userEmail=doc.user_email,
            conversationId=doc.conversation_id,
            messageId=doc.message_id,
            ratings=MessageFeedbackRatings(
                pertinence=(doc.ratings or {}).get("pertinence", 0),
                accuracy=(doc.ratings or {}).get("accuracy", 0),
            ),
            expectedAnswer=doc.expected_answer,
            createdAt=doc.created_at.isoformat() if doc.created_at else "",
        )
        for doc in docs[start_idx : start_idx + page_size]
    ]

    return AdminMessageFeedbackResponse(
        items=items,
        total=total,
        avg_ratings=avg_ratings,
        distributions=distributions,
    )


@router.get("/users", response_model=AdminUsersResponse)
async def list_users(
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUsersResponse:
    """Lista todos los usuarios registrados con su rol y fecha de registro."""
    users = list(
        (await session.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    )
    items = [
        AdminUserItem(
            uid=u.id,
            email=u.email,
            displayName=u.display_name,
            role=u.role,
            createdAt=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]
    return AdminUsersResponse(items=items, total=len(items))


@router.post("/users", response_model=AdminUserItem, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: CreateUserRequest,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminUserItem:
    """Crea una cuenta con rol 'user'. No envía email de verificación."""
    existing = await session.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ese email ya está registrado.",
        )
    user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        password_hash=_pwd_ctx.hash(payload.password),
        display_name=payload.displayName,
        role="user",
        created_at=datetime.now(UTC),
    )
    session.add(user)
    await session.commit()
    return AdminUserItem(
        uid=user.id,
        email=user.email,
        displayName=user.display_name,
        role=user.role,
        createdAt=user.created_at.isoformat(),
    )


@router.patch("/users/{uid}/password", status_code=status.HTTP_204_NO_CONTENT)
async def update_user_password(
    uid: str,
    payload: UpdatePasswordRequest,
    _admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Cambia la contraseña de un usuario existente."""
    user = await session.get(User, uid)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado."
        )
    user.password_hash = _pwd_ctx.hash(payload.password)
    await session.commit()
