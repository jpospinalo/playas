"""Endpoint para generación de títulos de conversaciones con IA."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from rag.api.auth import get_current_user
from rag.api.firebase_admin import get_db
from rag.core.llm_factory import get_provider

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

_TITLE_PROMPT = (
    "Genera un título conciso (máximo 8 palabras) para una consulta jurídica "
    "sobre playas y dominio público marítimo-terrestre colombiano. "
    "El título debe resumir la esencia de la consulta. "
    "Responde solo con el título, sin comillas ni puntuación final.\n\n"
    "Consulta: {message}"
)


class GenerateTitleRequest(BaseModel):
    first_message: str
    conversation_id: str


class GenerateTitleResponse(BaseModel):
    title: str


@router.post("/generate-title", response_model=GenerateTitleResponse)
async def generate_title(
    request: GenerateTitleRequest,
    user: dict = Depends(get_current_user),
) -> GenerateTitleResponse:
    """Genera un título corto para una conversación y lo actualiza en Firestore."""
    provider = get_provider()
    llm = provider.create_llm(temperature=0.3, use_case="title-generation")

    prompt = _TITLE_PROMPT.format(message=request.first_message[:400])
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        title = str(response.content).strip().strip('"').strip("'")[:60]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generando el título: {exc}",
        ) from exc

    db = get_db()
    try:
        await db.collection("conversations").document(request.conversation_id).update(
            {"title": title}
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error actualizando Firestore: {exc}",
        ) from exc

    return GenerateTitleResponse(title=title)
