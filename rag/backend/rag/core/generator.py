"""Adaptador síncrono para invocar el grafo RAG desde los scripts de evaluación.

Existe porque ``evaluation/ragas_eval_gemma.py`` y
``evaluation/ragas_eval_ollama.py`` hacen
``from rag.core.generator import generate_answer``: sin este módulo, ese
import fallaría contra la arquitectura actual de un único grafo
determinista en ``rag.core.agent``.

Reutiliza el grafo y la extracción de respuesta de la API. Si se configura
la resolución documental, carga la misma instantánea BM25 que prepara la
API antes de compilar el grafo.

Cada llamada compila un grafo nuevo y usa un ``thread_id`` efímero propio —
sin relación con conversaciones reales ni memoria compartida entre preguntas
de evaluación distintas.
"""

from __future__ import annotations

import asyncio
import uuid

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from rag.config import LEGAL_RESOLUTION_PROVENANCE_PATH
from rag.core.agent import build_graph, extract_answer_from_state
from rag.core.retriever import get_bm25_retriever


async def _ainvoke_graph(question: str) -> tuple[str, list[Document]]:
    if LEGAL_RESOLUTION_PROVENANCE_PATH is not None:
        await asyncio.to_thread(get_bm25_retriever)
    graph = build_graph()
    config = {
        "configurable": {"thread_id": f"eval:{uuid.uuid4()}"},
        "recursion_limit": 10,
    }
    state_input = {
        "question": question,
        "standalone_question": None,
        "enriched_query": None,
        "query_route": None,
        "messages": [HumanMessage(content=question)],
        "sources": [],
    }
    final_state = await graph.ainvoke(state_input, config=config)
    answer = extract_answer_from_state(final_state)
    docs = final_state.get("sources") or []
    return answer, docs


def generate_answer(question: str) -> tuple[str, list[Document]]:
    """Ejecuta ``question`` contra el grafo real y devuelve ``(respuesta, fuentes)``.

    Bloqueante: pensado para scripts de evaluación en lote, no para código
    que ya corre dentro de un event loop (ahí se debe usar ``_ainvoke_graph``
    directamente, con ``await``).
    """
    return asyncio.run(_ainvoke_graph(question))
