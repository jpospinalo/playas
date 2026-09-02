# tests/unit/test_ragas_import_isolation.py
"""Pruebas de importación en subprocesos aislados para ``evaluation/``.

Estas son las únicas pruebas de la suite que arrancan un intérprete
Python nuevo e independiente, precisamente para poder observar
``sys.modules`` de un proceso limpio sin ningún doble ni monkeypatch --
algo que no se puede verificar de forma fiable dentro del propio proceso
de pytest, donde otras pruebas ya insertaron (y luego retiraron) un
``ragas`` falso en ``sys.modules``.

Verifican tres cosas, cada una con una sola prueba (no una por cada
función del módulo):

1. Con el pin de ``langchain-community==0.3.31`` (grupo ``dev`` de
   ``pyproject.toml``; ver el comentario junto a ese pin) el paquete real
   ``ragas`` importa correctamente -- sin construir ningún cliente ni
   ejecutar ninguna métrica -- con la versión exacta que ``uv.lock`` deja
   resuelta (``0.4.3`` hoy; ``pyproject.toml`` solo declara ``ragas>=0.4``,
   el piso mínimo, no esa versión exacta).
2. Cargar ``evaluation.ground_truth`` (el cargador mínimo del dataset,
   pensado para no depender de nada más -- ver su propio docstring) nunca
   importa ``ragas`` ni el backend/API del RAG.
3. Invocar cualquiera de los dos adaptadores con ``--validate-only``
   nunca importa ``ragas``, incluso sin ninguna variable de entorno
   obligatoria definida (las tres se fuerzan vacías explícitamente para
   que la prueba no dependa del contenido real de ``.env`` en esta
   máquina).

El resto de las pruebas de ``evaluation/`` (``test_ragas_common.py``) no
necesita subprocesos: corren en el mismo proceso que pytest, con
``generate_answer`` y ``ragas`` sustituidos por dobles rápidos.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

RAG_ROOT = Path(__file__).resolve().parent.parent.parent


def _run_python(
    code: str, *, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=RAG_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        env=env if env is not None else dict(os.environ),
    )


def test_ragas_imports_successfully_in_a_clean_subprocess_with_the_pinned_lock() -> None:
    result = _run_python("import ragas\nimport ragas.metrics\nprint(ragas.__version__)\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "0.4.3"


def test_importing_ground_truth_never_loads_ragas_or_the_rag_backend_api() -> None:
    result = _run_python(
        "import sys\n"
        "import evaluation.ground_truth\n"
        "assert 'ragas' not in sys.modules, 'evaluation.ground_truth importo ragas'\n"
        "assert 'rag.api.main' not in sys.modules, "
        "'evaluation.ground_truth importo el API del backend'\n"
        "print('OK')\n"
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "OK"


def test_validate_only_never_imports_ragas_even_without_required_env_vars() -> None:
    # Las tres variables se fuerzan vacías explícitamente (en vez de
    # borrarlas) para que la prueba no dependa de lo que .env defina de
    # verdad en esta máquina -- normalize_required_env() trata una cadena
    # vacía exactamente igual que una variable ausente.
    env = dict(os.environ)
    env.update(
        {
            "GOOGLE_API_KEY2": "",
            "OLLAMA_EVAL_BASE_URL": "",
            "OLLAMA_EVAL_MODEL": "",
        }
    )

    for module_name in ("evaluation.ragas_eval_gemma", "evaluation.ragas_eval_ollama"):
        result = _run_python(
            "import sys\n"
            "sys.argv = ['x', '--validate-only']\n"
            f"import {module_name} as m\n"
            "code = m.main()\n"
            "assert 'ragas' not in sys.modules, 'validate-only importo ragas'\n"
            "print('EXIT', code)\n",
            env=env,
        )
        assert result.returncode == 0, f"{module_name}: {result.stderr}"
        assert result.stdout.strip().splitlines()[-1] == "EXIT 1", f"{module_name}: {result.stdout}"
