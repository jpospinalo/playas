"""Adaptador síncrono de conveniencia para invocar el grafo RAG real desde
herramientas offline (los scripts de evaluación en ``evaluation/``).

T4.2 — restaura ``rag.core.generator.generate_answer``: los scripts
``evaluation/ragas_eval_gemma.py`` y ``evaluation/ragas_eval_ollama.py``
hacían ``from rag.core.generator import generate_answer`` contra un módulo
que ya no existía en el código actual (quedó huérfano tras la migración del
agente a un único grafo determinista en ``rag.core.agent``).

No reimplementa retrieval ni generación: invoca exactamente el mismo grafo
que sirve ``/api/query`` (``rag.core.agent.build_graph()``, sin modificarlo)
y reutiliza la misma extracción de respuesta que usa la API
(``rag.core.agent.extract_answer_from_state`` — C7: antes se importaba
desde ``rag.api.main``, lo que forzaba cargar FastAPI y toda la capa HTTP
solo por esta función pura; ahora ambos la importan desde ``core.agent``,
sin duplicar la lógica ni depender uno del otro), para no arriesgar que
ambas rutas diverjan.

Cada llamada compila un grafo nuevo y usa un ``thread_id`` efímero propio —
sin relación con conversaciones reales ni memoria compartida entre preguntas
de evaluación distintas. Solo para uso offline: no forma parte de la ruta de
servicio (ningún módulo de ``api/`` o ``core/`` importa este archivo).
"""

from __future__ import annotations

import asyncio
import uuid

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from rag.core.agent import build_graph, extract_answer_from_state


async def _ainvoke_graph(question: str) -> tuple[str, list[Document]]:
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
