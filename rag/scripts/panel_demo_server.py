"""Levanta la API **solo para ver el panel de administración** con la semilla.

El panel solo lee la base de datos (usuarios, conversaciones, mensajes,
calificaciones). Para no depender de ChromaDB, Ollama ni de una llave de LLM,
este lanzador apaga el calentamiento del retriever y del grafo del agente:
el inicio de sesión y todas las rutas ``/api/admin/*`` funcionan; las
preguntas al chat (``/api/query*``) no.

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
    a = p.parse_args()
    if not Path(a.db).exists():
        raise SystemExit(f"No existe {a.db}. Corra primero scripts/seed_panel_demo.py.")
    # Antes de importar rag.*: config.py lee DATABASE_URL al importarse.
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{Path(a.db).resolve()}"

    import uvicorn

    import rag.api.main as api
    import rag.core.agent as agent

    api.init_retrievers = lambda: None
    agent.build_graph = lambda *args, **kwargs: None
    uvicorn.run(api.app, host="127.0.0.1", port=a.port)


if __name__ == "__main__":
    main()
