"""Endpoints para registro de feedback de usuarios.

POST /api/feedback          — Feedback de conversación (multi-dimensión)
POST /api/feedback/message   — Feedback de mensaje individual (pertinencia + precisión)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from rag.api.auth import get_current_user
from rag.api.firebase_admin import get_db
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
) -> FeedbackResponse:
    """Registra el feedback de conversación de un usuario en Firestore.

    Requiere autenticación. El payload incluye calificaciones por dimensión
    (tone, length, usability, overall) y un comentario opcional.
    Si se proporciona conversation_id, incluye el título de la conversación.
    """
    db = get_db()

    # Obtener título de la conversación si se proporcionó conversation_id
    conversation_title: str | None = None
    if request.conversation_id:
        try:
            conv_doc = await db.collection("conversations").document(request.conversation_id).get()
            if conv_doc.exists:
                conversation_title = (conv_doc.to_dict() or {}).get("title")
        except Exception:
            pass  # El título es un dato de enriquecimiento; si falla no se bloquea el feedback

    feedback_data = {
        "userId": user["uid"],
        "userEmail": user.get("email", ""),
        "ratings": request.ratings.model_dump(),
        "comment": request.comment,
        "conversationId": request.conversation_id,
        "conversationTitle": conversation_title,
        "createdAt": _server_timestamp(),
    }

    try:
        _timestamp, doc_ref = await db.collection("feedback").add(feedback_data)
        return FeedbackResponse(id=doc_ref.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando el feedback: {exc}",
        ) from exc


@router.post(
    "/message", response_model=MessageFeedbackResponse, status_code=status.HTTP_201_CREATED
)
async def submit_message_feedback(
    request: MessageFeedbackRequest,
    user: dict = Depends(get_current_user),
) -> MessageFeedbackResponse:
    """Registra el feedback de un mensaje individual del agente en Firestore.

    Requiere autenticación. Valida que no exista feedback previo del mismo
    usuario para el mismo mensaje (prevención de duplicados).
    """
    db = get_db()

    # Verificar duplicado: mismo usuario + mismo mensaje
    try:
        dup_query = (
            db.collection("message_feedback")
            .where("userId", "==", user["uid"])
            .where("messageId", "==", request.message_id)
            .limit(1)
        )
        dup_docs = [doc async for doc in dup_query.stream()]
        if dup_docs:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya existe feedback para este mensaje.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Si la verificación falla, permitir el insert (mejor esfuerzo)

    msg_feedback_data = {
        "userId": user["uid"],
        "userEmail": user.get("email", ""),
        "conversationId": request.conversation_id,
        "messageId": request.message_id,
        "ratings": request.ratings.model_dump(),
        "expectedAnswer": request.expected_answer,
        "createdAt": _server_timestamp(),
    }

    try:
        _timestamp, doc_ref = await db.collection("message_feedback").add(msg_feedback_data)
        return MessageFeedbackResponse(id=doc_ref.id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error guardando el feedback de mensaje: {exc}",
        ) from exc


def _server_timestamp():
    """Retorna el centinela SERVER_TIMESTAMP de Firestore."""
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    return SERVER_TIMESTAMP
