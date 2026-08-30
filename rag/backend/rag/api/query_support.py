"""Helpers de soporte de `api/main.py`: transformación de resultados del
grafo hacia el contrato HTTP/SSE, y construcción de config/hidratación de
mensajes para invocarlo.

`_make_config` y `_get_initial_messages` se reexportan desde `api/main.py`
porque `tests/unit/test_conversation_hydration.py` los importa desde ahí
(`from rag.api.main import _get_initial_messages, _make_config`).
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from rag.api.schemas import QueryRequest, SourceFragment, SourceGroup
from rag.core.tools import sanitize_replacement_chars


def _clean_answer(answer: str) -> str:
    """Elimina sufijos de citación que algunos LLMs añaden al final."""
    patterns = [
        r"\s*\(fuente:[^)]+\)\s*$",
        r"\s*\((?:doc|chunk)[^)]*\)\s*$",
    ]
    for p in patterns:
        answer = re.sub(p, "", answer)
    return answer.strip()


# Campos de metadata que pertenecen al documento (no al fragmento). El resto
# de claves se considera específico del chunk y viaja en SourceFragment.metadata.
_DOC_LEVEL_META_KEYS = (
    "doc_type",
    "norma",
    "tipo_norma",
    "anio",
    "title",
    "book_title",
    "Archivo",
    "No",
    "Corporación",
    "Radicado",
    "Magistrado ponente",
    "Tema principal",
    "Partes procesales",
    "RELACIÓN PLAYAS",
    "TEMATICA",
)


def _resolve_title(meta: dict) -> str:
    """Resuelve el título legible de un documento a partir de su metadata.

    Prioridad: ``title`` → ``book_title`` → stem del ``source`` (reemplazando
    ``_`` por espacios). Devuelve ``""`` si nada está disponible.
    """
    title = meta.get("title") or meta.get("book_title") or ""
    if title:
        return title
    source_path = meta.get("source", "")
    return Path(source_path).stem.replace("_", " ") if source_path else ""


def _truncate_content(text: str) -> str:
    """Trunca contenido de fragmento a 500 caracteres (para respuesta al frontend)."""
    content = (text or "").strip().replace("\n", " ")
    if len(content) > 500:
        content = content[:500] + "..."
    return content


def _docs_to_source_groups(docs: list[Document]) -> list[SourceGroup]:
    """Agrupa los documentos recuperados por archivo de origen.

    - Conserva el orden de recuperación (el primer fragmento determina la
      posición del grupo en la lista, lo que preserva "mejor score primero").
    - Asigna a cada fragmento un `index` global 1-based que coincide con los
      marcadores `[docN]` que `tools.build_context_block` inyecta en el prompt.
    - Separa los metadatos en nivel-documento (compartidos entre fragmentos del
      mismo archivo) y nivel-fragmento (sección, summary, keywords, entities).
    """
    groups: dict[str, SourceGroup] = {}
    order: list[str] = []

    for i, doc in enumerate(docs):
        # Parche temporal: limpiar U+FFFD antes de exponer al frontend.
        # Ver docs/INGEST_ENCODING_BUG.md.
        meta = sanitize_replacement_chars(dict(doc.metadata or {}))
        source = meta.get("source", "") or f"__unknown_{i}__"

        fragment_meta = {
            k: v for k, v in meta.items() if k not in (*_DOC_LEVEL_META_KEYS, "source")
        }
        fragment = SourceFragment(
            index=i + 1,
            content=_truncate_content(sanitize_replacement_chars(doc.page_content or "")),
            metadata=fragment_meta,
        )

        if source not in groups:
            doc_meta = {k: meta[k] for k in _DOC_LEVEL_META_KEYS if k in meta}
            groups[source] = SourceGroup(
                source=meta.get("source", ""),
                title=_resolve_title(meta),
                doc_type=meta.get("doc_type"),
                metadata=doc_meta,
                fragments=[fragment],
            )
            order.append(source)
        else:
            groups[source].fragments.append(fragment)

    return [groups[s] for s in order]


def _conversation_thread_id(user_id: str, logical_id: str) -> str:
    """Clave de checkpoint del ``MemorySaver``, aislada por usuario y conversación.

    Único punto donde se arma este formato: lo usa ``_make_config`` (para
    nuevas consultas) y ``routes/conversations.py::delete_conversation``
    (para limpiar, con el mismo ``conversation_id`` como ``logical_id``, el
    checkpoint en memoria del proceso al borrar la conversación de la base
    de datos — A3.2). Mantenerlo en un solo lugar evita que ambos puntos se
    desincronicen si el formato cambia en el futuro.
    """
    return f"user:{user_id}:conversation:{logical_id}"


def _make_config(
    user_id: str,
    conversation_id: str | None,
    thread_id: str | None,
    recursion_limit: int = 10,
) -> dict:
    """Construye una clave de checkpoint aislada por usuario y conversación."""
    logical_id = conversation_id or thread_id or str(uuid.uuid4())
    tid = _conversation_thread_id(user_id, logical_id)
    return {
        "configurable": {"thread_id": tid},
        "recursion_limit": recursion_limit,
    }


def _estimate_context_tokens(messages: list) -> int:
    """Estimación rápida de tokens en el historial (~4 chars/token).

    Solo cuenta los mensajes acumulados en state (HumanMessages + AIMessages),
    no el system prompt ni los docs del turno actual, que son overhead fijo.
    """
    total_chars = 0
    for m in messages:
        content = m.content
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    total_chars += len(part)
                elif isinstance(part, dict):
                    total_chars += len(str(part.get("text", "")))
    return total_chars // 4


def _build_graph_input(request: QueryRequest, messages: list) -> dict[str, Any]:
    """Construye en un solo lugar el contrato de entrada del grafo."""
    return {
        "question": request.question,
        "standalone_question": None,
        "enriched_query": None,
        "query_route": None,
        "messages": messages,
        "sources": [],
        "doc_types": request.doc_types,
        "k": request.k,
        "k_candidates": request.k_candidates,
    }


# ── Hydration ──────────────────────────────────────────────────────────────


async def _get_initial_messages(
    graph,
    config: dict,
    conversation_id: str | None,
    question: str,
    user_id: str,
    current_message_id: str | None = None,
) -> list:
    """Devuelve los mensajes iniciales para invocar el agente.

    - Si MemorySaver tiene estado: solo añade la nueva pregunta (continuación normal).
    - Si no hay estado y hay conversation_id: carga el historial desde la base de datos
      e inyecta el contexto completo (útil tras reinicio del servidor).
    - Si no hay estado ni conversation_id: comienza conversación nueva.
    """
    if not conversation_id:
        if current_message_id:
            raise HTTPException(
                status_code=422,
                detail="current_message_id requiere conversation_id.",
            )
        return [HumanMessage(content=question)]

    from sqlalchemy import select

    from rag.api.database import async_session_factory
    from rag.api.models import Conversation, Message

    async with async_session_factory() as session:
        conversation = await session.get(Conversation, conversation_id)
        if conversation is None or conversation.user_id != user_id:
            raise HTTPException(status_code=404, detail="Conversación no encontrada.")

        if current_message_id:
            current_message = await session.get(Message, current_message_id)
            if (
                current_message is None
                or current_message.conversation_id != conversation_id
                or current_message.role != "user"
                or current_message.text.strip() != question.strip()
            ):
                raise HTTPException(
                    status_code=422,
                    detail="El mensaje actual no coincide con la conversación y la pregunta.",
                )

        state = await graph.aget_state(config)
        has_checkpoint = bool((state.values if hasattr(state, "values") else {}).get("messages"))
        if has_checkpoint:
            return [HumanMessage(content=question)]

        result = await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        msgs = result.scalars().all()

    history: list = []
    for msg in msgs:
        if msg.id == current_message_id:
            continue
        if msg.role == "user":
            history.append(HumanMessage(content=msg.text))
        else:
            history.append(AIMessage(content=msg.text))

    return history + [HumanMessage(content=question)]
