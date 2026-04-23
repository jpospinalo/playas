"""FastAPI application para el sistema RAG de jurisprudencia de playas.

Expone tres endpoints sobre el agente LangGraph:
  GET  /api/health          — liveness check
  POST /api/query           — respuesta completa (JSON)
  POST /api/query/stream    — streaming SSE con tokens del LLM

Run with:
    uv run uvicorn rag.api.main:app --reload --port 8080
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage

from rag.api.auth import get_optional_user
from rag.api.routes.conversations import router as conversations_router
from rag.api.schemas import QueryRequest, QueryResponse, SourceDocument
from rag.config import CONTEXT_LIMIT_TOKENS
from rag.core.retriever import init_retrievers

# ── Singleton del grafo ─────────────────────────────────────────────────────

_graph: Any = None


def get_graph() -> Any:
    if _graph is None:
        raise RuntimeError("El grafo no ha sido compilado. Verifica el lifespan de la app.")
    return _graph


# ── Lifespan ───────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-calienta los componentes costosos al arrancar:
    - Conexión HTTP a Chroma (singleton)
    - Índice BM25 completo (construido una sola vez desde el corpus de Chroma)
    - Vectorstore LangChain-Chroma (singleton)
    - Grafo LangGraph compilado (singleton con MemorySaver)
    """
    import asyncio

    from rag.core.agent import build_graph

    global _graph
    await asyncio.to_thread(init_retrievers)
    _graph = build_graph()
    yield


# ── App ────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="RAG Playas API",
    description="Sistema de consulta de jurisprudencia española en materia de playas",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations_router)


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_answer(answer: str) -> str:
    """Elimina sufijos de citación que algunos LLMs añaden al final."""
    patterns = [
        r"\s*\(fuente:[^)]+\)\s*$",
        r"\s*\((?:doc|chunk)[^)]*\)\s*$",
    ]
    for p in patterns:
        answer = re.sub(p, "", answer)
    return answer.strip()


def _doc_to_source(doc: Document) -> SourceDocument:
    meta = doc.metadata or {}
    content = (doc.page_content or "").strip().replace("\n", " ")
    if len(content) > 500:
        content = content[:500] + "..."

    title = meta.get("title") or meta.get("book_title") or ""
    if not title:
        source_path = meta.get("source", "")
        title = Path(source_path).stem.replace("_", " ") if source_path else ""

    return SourceDocument(
        content=content,
        source=meta.get("source", ""),
        title=title,
        metadata={k: v for k, v in meta.items() if k not in ("source",)},
    )


def _make_config(thread_id: str | None, recursion_limit: int = 10) -> dict:
    """Construye el config de LangGraph con thread_id y recursion_limit."""
    tid = thread_id or str(uuid.uuid4())
    return {
        "configurable": {"thread_id": tid},
        "recursion_limit": recursion_limit,
    }


def _extract_answer_from_state(state: dict) -> str:
    """Extrae el contenido del último AIMessage del state."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


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


# ── Hydration ──────────────────────────────────────────────────────────────


async def _get_initial_messages(
    graph,
    config: dict,
    conversation_id: str | None,
    question: str,
) -> list:
    """Devuelve los mensajes iniciales para invocar el agente.

    - Si MemorySaver tiene estado: solo añade la nueva pregunta (continuación normal).
    - Si no hay estado y hay conversation_id: carga el historial desde Firestore e
      inyecta el contexto completo (útil tras reinicio del servidor).
    - Si no hay estado ni conversation_id: comienza conversación nueva.
    """
    state = await graph.aget_state(config)
    has_checkpoint = bool(
        (state.values if hasattr(state, "values") else {}).get("messages")
    )

    if has_checkpoint:
        return [HumanMessage(content=question)]

    if not conversation_id:
        return [HumanMessage(content=question)]

    # Cargar historial desde Firestore via Admin SDK
    from rag.api.firebase_admin import get_db

    db = get_db()
    messages_ref = (
        db.collection("conversations")
        .document(conversation_id)
        .collection("messages")
        .order_by("createdAt")
    )

    history: list = []
    async for doc in messages_ref.stream():
        data = doc.to_dict() or {}
        if data.get("role") == "user":
            history.append(HumanMessage(content=data.get("text", "")))
        else:
            history.append(AIMessage(content=data.get("text", "")))

    return history + [HumanMessage(content=question)]


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
async def query(
    request: QueryRequest,
    _user: dict | None = Depends(get_optional_user),
) -> QueryResponse:
    """Consulta jurídica completa (respuesta JSON).

    Ejecuta el agente LangGraph hasta completar el ciclo enrich → retrieve → generate.
    Soporta memoria multi-turno si se proporciona `thread_id`.
    """
    graph = get_graph()
    config = _make_config(request.thread_id)

    try:
        initial_messages = await _get_initial_messages(
            graph, config, request.conversation_id, request.question
        )
        final_state = await graph.ainvoke(
            {
                "question": request.question,
                "messages": initial_messages,
                "sources": [],
            },
            config=config,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    answer_raw = _extract_answer_from_state(final_state)
    if not answer_raw:
        answer_raw = "No se encontraron fragmentos relevantes en la base de conocimiento."

    sources = final_state.get("sources") or []
    enriched_query = final_state.get("enriched_query")
    context_tokens = _estimate_context_tokens(final_state.get("messages", []))

    return QueryResponse(
        answer=_clean_answer(answer_raw),
        sources=[_doc_to_source(d) for d in sources],
        enriched_query=enriched_query,
        context_tokens=context_tokens,
        context_limit=CONTEXT_LIMIT_TOKENS,
    )


@app.post("/api/query/stream")
async def query_stream(
    request: QueryRequest,
    _user: dict | None = Depends(get_optional_user),
):
    """Streaming SSE: emite tokens del LLM en tiempo real.

    Formato de eventos SSE:
      data: {"type": "token",   "content": "<fragmento>"}
      data: {"type": "sources", "sources": [...], "enriched_query": "..."}
      data: [DONE]

    Los tokens del nodo `agent` se emiten en tiempo real. Al finalizar se envía
    un evento con los documentos fuente y la consulta enriquecida.
    """
    graph = get_graph()
    config = _make_config(request.thread_id)
    initial_messages = await _get_initial_messages(
        graph, config, request.conversation_id, request.question
    )

    async def event_generator():
        try:
            # Multi-stream: combinamos los tokens del LLM ("messages") con los
            # eventos custom de progreso ("custom") que emiten los nodos vía
            # get_stream_writer. Cada chunk viene como (mode, payload).
            async for mode, payload in graph.astream(
                {
                    "question": request.question,
                    "messages": initial_messages,
                    "sources": [],
                },
                config=config,
                stream_mode=["messages", "custom"],
            ):
                if mode == "messages":
                    chunk, metadata = payload
                    # Solo emitir tokens del nodo "agent" o "generate" (no
                    # enriquecimiento ni ToolMessages)
                    node = metadata.get("langgraph_node", "")
                    if node in ("agent", "generate") and isinstance(chunk, AIMessage):
                        if isinstance(chunk.content, str) and chunk.content:
                            event = json.dumps({"type": "token", "content": chunk.content})
                            yield f"data: {event}\n\n"
                elif mode == "custom":
                    # Eventos de estado emitidos por los nodos
                    if isinstance(payload, dict) and payload.get("type") == "status":
                        event = json.dumps(payload)
                        yield f"data: {event}\n\n"

            # Recuperar el state final para sources y enriched_query
            final_state = await graph.aget_state(config)
            values = final_state.values if hasattr(final_state, "values") else {}

            sources_raw = values.get("sources") or []
            enriched_query = values.get("enriched_query")
            context_tokens = _estimate_context_tokens(values.get("messages", []))

            sources_payload = [_doc_to_source(d).model_dump() for d in sources_raw]
            event = json.dumps(
                {
                    "type": "sources",
                    "sources": sources_payload,
                    "enriched_query": enriched_query,
                    "context_tokens": context_tokens,
                    "context_limit": CONTEXT_LIMIT_TOKENS,
                }
            )
            yield f"data: {event}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as exc:
            event = json.dumps({"type": "error", "detail": str(exc)})
            yield f"data: {event}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
