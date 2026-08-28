"""C7 — rag.core.generator no debe depender de rag.api.main.

`rag.core.generator` es un adaptador pensado explícitamente para uso
OFFLINE (los scripts de evaluación en ``evaluation/``, según su propio
docstring: "no forma parte de la ruta de servicio"). Sin embargo importaba
``_extract_answer_from_state`` directamente desde ``rag.api.main`` — el
módulo de la API real, que a su vez importa FastAPI, todos los routers
(auth, conversations, feedback, admin), la base de datos async y el
middleware CORS.

Eso invierte la dependencia que el propio módulo describe: una herramienta
de `core/` pensada para correr sin servidor terminaba forzando la carga
completa de la capa HTTP solo para reutilizar una función pura de
extracción de texto. La solución (C7) es mover esa función a
``rag.core.agent`` (pública y tipada) y que tanto ``api.main`` como
``core.generator`` la importen desde ahí — sin duplicar la lógica.

Esta prueba reproduce el síntoma real en un subproceso limpio: importar
`rag.core.generator` en aislamiento no debe dejar `rag.api.main` (ni
`fastapi`) en `sys.modules`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2] / "backend"

_CODE = (
    "import sys\n"
    "import rag.core.generator\n"
    "print('rag.api.main' in sys.modules)\n"
    "print('fastapi' in sys.modules)\n"
)


def test_importing_generator_does_not_load_the_api_layer() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _CODE],
        cwd=str(_BACKEND_DIR),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    api_main_loaded, fastapi_loaded = result.stdout.strip().splitlines()
    assert api_main_loaded == "False", "importar rag.core.generator cargó rag.api.main"
    assert fastapi_loaded == "False", "importar rag.core.generator cargó fastapi"


def test_extract_answer_from_state_is_public_on_core_agent() -> None:
    """La función movida debe quedar disponible, pública y tipada, en
    `rag.core.agent` — el mismo lugar del que ahora la importan tanto
    `api.main` como `core.generator`, para no duplicar la lógica."""
    from langchain_core.messages import AIMessage, HumanMessage

    from rag.core.agent import extract_answer_from_state

    state = {
        "messages": [
            HumanMessage(content="¿Puede un hotel privatizar el acceso a una playa?"),
            AIMessage(content="No, el acceso a las playas es público [doc1]."),
        ]
    }
    assert extract_answer_from_state(state) == "No, el acceso a las playas es público [doc1]."
    assert extract_answer_from_state({"messages": []}) == ""
