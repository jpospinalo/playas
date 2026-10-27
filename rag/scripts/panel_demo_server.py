"""Levanta la API **solo para ver el panel de administración** con la semilla.

El panel solo lee la base de datos (usuarios, conversaciones, mensajes,
calificaciones). Para no depender de ChromaDB, Ollama ni de una llave de LLM,
este lanzador apaga el calentamiento del retriever y del grafo del agente:
el inicio de sesión y todas las rutas ``/api/admin/*`` funcionan. Las
preguntas al chat (``/api/query/stream``) reciben una **respuesta de
demostración** por el mismo stream (dice que es de demostración y trae 1-2
fuentes de la semilla), para poder mostrar el flujo completo del
participante sin RAG; el front la guarda como cualquier respuesta.

Escucha solo en 127.0.0.1. No es para producción.

Uso (desde ``rag/``):
    uv run python scripts/seed_panel_demo.py --db data/panel-demo.db --reset
    JWT_SECRET_KEY=<un valor largo cualquiera> uv run python scripts/panel_demo_server.py --port 8280
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--db", default="data/panel-demo.db", help="Archivo SQLite de la semilla")
    p.add_argument("--port", type=int, default=8280)
    p.add_argument(
        "--front",
        default="http://localhost:3280,http://127.0.0.1:3280",
        help="Orígenes del front local permitidos por CORS (separados por coma)",
    )
    a = p.parse_args()
    if not Path(a.db).exists():
        raise SystemExit(f"No existe {a.db}. Corra primero scripts/seed_panel_demo.py.")
    # Antes de importar rag.*: config.py lee DATABASE_URL al importarse.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(a.db).resolve()}"

    import uvicorn
    from fastapi.middleware.cors import CORSMiddleware

    import rag.api.main as api
    import rag.core.agent as agent

    api.init_retrievers = lambda: None
    agent.build_graph = lambda *args, **kwargs: None
    # main.py solo permite http://localhost:3000; el front de la demo corre en otro puerto.
    api.app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in a.front.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _respuesta_de_demostracion(api)
    uvicorn.run(api.app, host="127.0.0.1", port=a.port)


def _respuesta_de_demostracion(api) -> None:
    """Reemplaza ``POST /api/query/stream`` por una respuesta fija con el
    mismo formato SSE (status → token → sources → [DONE])."""
    import asyncio
    import hashlib
    import json

    from fastapi import Depends
    from fastapi.responses import StreamingResponse
    from fastapi.routing import APIRoute
    from sqlalchemy import select

    from rag.api import panel_metricas as pm
    from rag.api.database import async_session_factory
    from rag.api.models import Message
    from rag.api.rate_limit import get_query_user
    from rag.api.schemas import QueryRequest

    async def demo_stream(request: QueryRequest, user: dict = Depends(get_query_user)):
        async with async_session_factory() as s:
            todas = [
                f
                for (f,) in (
                    await s.execute(
                        select(Message.sources)
                        .where(Message.role == "assistant", Message.sources.is_not(None))
                        .limit(200)
                    )
                ).all()
                if f
            ]
        n = int(hashlib.sha256(request.question.encode()).hexdigest(), 16)
        # PQ-89: títulos largos del corpus cortados en palabra completa con "…".
        fuentes = [
            {**g, "title": pm._legible(g.get("title", ""))}
            for g in (todas[n % len(todas)] if todas else [])[:2]
        ]
        nombres = "; ".join(g.get("title", "") for g in fuentes) or "las normas de la semilla"
        texto = (
            "**Respuesta de demostración.** En esta presentación ATLAS no está conectado a su "
            "base de normas y sentencias, así que muestra una respuesta de ejemplo. En el "
            "ejercicio real, aquí aparece la respuesta a su pregunta, con las normas que la "
            f"respaldan. Fuentes de ejemplo: {nombres}."
        )

        async def eventos():
            for etapa, msg in (
                ("enriching", "Entendiendo su pregunta…"),
                ("retrieving", "Buscando en las normas…"),
                ("generating", "Escribiendo la respuesta…"),
            ):
                yield f"data: {json.dumps({'type': 'status', 'stage': etapa, 'message': msg})}\n\n"
                await asyncio.sleep(0.4)
            for i in range(0, len(texto), 120):
                yield f"data: {json.dumps({'type': 'token', 'content': texto[i : i + 120]})}\n\n"
            fin = {
                "type": "sources",
                "sources": fuentes,
                "enriched_query": request.question,
                "query_route": "in_scope",
                "context_tokens": 0,
                "context_limit": 0,
            }
            yield f"data: {json.dumps(fin)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(eventos(), media_type="text/event-stream")

    # Con ``from __future__ import annotations`` las anotaciones son texto y
    # FastAPI no ve los tipos importados aquí adentro: se dan los reales.
    demo_stream.__annotations__ = {"request": QueryRequest, "user": dict}
    api.app.router.routes.insert(
        0, APIRoute("/api/query/stream", demo_stream, methods=["POST"], name="demo_stream")
    )


if __name__ == "__main__":
    main()
