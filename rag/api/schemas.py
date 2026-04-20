"""Pydantic models for the RAG API request and response payloads."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Consulta jurídica en lenguaje natural")
    k: int = Field(default=4, ge=1, le=8, description="Número de fragmentos para el contexto")
    k_candidates: int = Field(
        default=8, ge=4, le=20, description="Candidatos iniciales del retriever"
    )
    thread_id: str | None = Field(
        default=None,
        description=(
            "Identificador de hilo de conversación. Si se proporciona, el agente mantiene "
            "el historial de mensajes entre requests (memoria multi-turno). "
            "Si es None, cada request es independiente."
        ),
    )


class SourceDocument(BaseModel):
    content: str = Field(..., description="Contenido del fragmento (recortado a 500 caracteres)")
    source: str = Field(default="", description="Nombre del documento fuente")
    title: str = Field(default="", description="Título legible del documento")
    metadata: dict = Field(default_factory=dict, description="Metadatos adicionales del fragmento")


class QueryResponse(BaseModel):
    answer: str = Field(..., description="Respuesta generada por el modelo")
    sources: list[SourceDocument] = Field(
        default_factory=list, description="Fragmentos recuperados utilizados como contexto"
    )
    enriched_query: str | None = Field(
        default=None,
        description=(
            "Consulta expandida usada internamente para la recuperación de documentos. "
            "Útil para depuración y evaluación del enriquecimiento."
        ),
    )
