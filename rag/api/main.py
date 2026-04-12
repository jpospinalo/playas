"""FastAPI application for the RAG Playas legal jurisprudence system.

Replaces the Gradio interface with a REST API consumed by the Next.js frontend.

Run with:
    uv run uvicorn rag.api.main:app --reload --port 8080
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.documents import Document

from rag.api.schemas import QueryRequest, QueryResponse, SourceDocument
from rag.core.generator import generate_answer

app = FastAPI(
    title="RAG Playas API",
    description="Sistema de consulta de jurisprudencia española en materia de playas",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Helpers ────────────────────────────────────────────────────────────────


def _clean_answer(answer: str) -> str:
    """Remove trailing citation suffixes added by some LLM configurations."""
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


# ── Routes ─────────────────────────────────────────────────────────────────


@app.get("/api/health")
async def health() -> dict:
    """Liveness check."""
    return {"status": "ok"}


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """
    Submit a legal question and receive a RAG-generated answer with source fragments.

    The retriever performs hybrid BM25 + vector search, optionally reranked,
    before feeding the top-k documents as context to the Gemini LLM.
    """
    try:
        answer_raw, docs = generate_answer(
            question=request.question,
            k=request.k,
            k_candidates=request.k_candidates,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return QueryResponse(
        answer=_clean_answer(answer_raw),
        sources=[_doc_to_source(d) for d in docs],
    )
