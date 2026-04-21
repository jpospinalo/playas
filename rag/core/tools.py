# rag/core/tools.py
"""Tools LangGraph del agente RAG.

La tool `retrieve` envuelve el HybridEnsembleRetriever (BM25 + vector, RRF)
y devuelve un Command que actualiza simultáneamente:
  - `sources`: lista de Document para la respuesta del endpoint.
  - `messages`: ToolMessage con el bloque de contexto formateado que ve el LLM.
"""

from __future__ import annotations

from typing import Annotated

from langchain_core.documents import Document
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from .retriever import get_ensemble_retriever

# ---------------------------------------------------------------------------
# Formateo del contexto (movido desde generator.py)
# ---------------------------------------------------------------------------


def build_context_block(docs: list[Document]) -> str:
    """Convierte una lista de documentos en un bloque de contexto legible.

    Incluye metadatos de atribución (corporación, magistrado, tema, sección
    y resumen) para que el LLM pueda citar correctamente las fuentes.
    """
    bloques: list[str] = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        source = meta.get("source", "desconocido")
        chunk_id = meta.get("chunk_id", meta.get("id", f"doc_{i}"))

        # Chroma puede almacenar la clave con distintas variantes de encoding
        corporacion = (
            meta.get("Corporación") or meta.get("CorporaciÃ³n") or meta.get("Corporacion", "")
        )
        magistrado = meta.get("Magistrado ponente", "")
        tema = meta.get("Tema principal", "")
        section = meta.get("section_name", "")
        summary = meta.get("summary", "")

        header = f"[doc{i} | source={source} | chunk_id={chunk_id}]"
        meta_lines: list[str] = []
        if corporacion:
            meta_lines.append(f"Corporación: {corporacion}")
        if magistrado:
            meta_lines.append(f"Magistrado ponente: {magistrado}")
        if tema:
            meta_lines.append(f"Tema principal: {tema}")
        if section:
            meta_lines.append(f"Sección: {section}")
        if summary:
            meta_lines.append(f"Resumen: {summary}")

        parts = [header]
        if meta_lines:
            parts.append("\n".join(meta_lines))
        parts.append(d.page_content)
        bloques.append("\n".join(parts))

    return "\n\n".join(bloques)


# ---------------------------------------------------------------------------
# Tool de recuperación
# ---------------------------------------------------------------------------


@tool
def retrieve(
    query: str,
    k: int = 8,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """Busca jurisprudencia colombiana relevante usando recuperación híbrida BM25 + vector.

    Parámetros:
        query: Consulta de búsqueda. Usa la consulta enriquecida disponible en el contexto.
        k: Número de fragmentos a recuperar (por defecto 8).

    Devuelve fragmentos de sentencias del Consejo de Estado y Tribunales
    Administrativos colombianos sobre playas, zonas costeras y dominio público.
    Cita cada fragmento con el marcador [docN] que aparece en el contenido.
    """
    docs = get_ensemble_retriever(k=k).invoke(query)
    context = build_context_block(docs)
    return Command(
        update={
            "sources": docs,
            "messages": [ToolMessage(content=context, tool_call_id=tool_call_id)],
        }
    )


ALL_TOOLS = [retrieve]
