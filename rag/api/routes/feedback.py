"""Endpoint para registro de feedback de usuarios."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from rag.api.auth import get_current_user
from rag.api.firebase_admin import get_db
from rag.api.schemas import FeedbackRequest, FeedbackResponse

router = APIRouter(prefix="/api/feedback", tags=["feedback"])


@router.post("", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    request: FeedbackRequest,
    user: dict = Depends(get_current_user),
) -> FeedbackResponse:
    """Registra el feedback de un usuario en Firestore.

    Requiere autenticación. Valida que el rating esté en rango 1-5.
    Si se proporciona conversation_id, incluye el título de la conversación
    como snapshot para el panel de administración.
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
        "rating": request.rating,
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


def _server_timestamp():
    """Retorna el centinela SERVER_TIMESTAMP de Firestore."""
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    return SERVER_TIMESTAMP
