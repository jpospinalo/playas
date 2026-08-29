"""T4.3 — regresión: `rag.core.retriever` no debe volver a exponer `demo()`.

`demo()` (con su bloque `if __name__ == "__main__":`) no tenía ningún
llamador real: no la importaba ningún módulo de `api/`, `core/` ni
`evaluation/`, ningún test la ejercitaba, y no estaba documentada en
`docs/SCRIPTS.md`, el `Makefile` ni `CLAUDE.md`/`docs/ARCHITECTURE.md` como
una herramienta de línea de comandos mantenida — solo era alcanzable
ejecutando `python retriever.py` directamente, algo que ningún flujo del
repo hace. Se eliminó en T4.3 por ser código muerto demostrable.

`OllamaReranker` se conserva deliberadamente (no se prueba aquí su
ausencia): a diferencia de `demo()`, está documentado como reranker
opcional en CLAUDE.md/docs/ARCHITECTURE.md (infraestructura Terraform que
aprovisiona un modelo de Ollama para ese propósito) — su no-uso en el flujo
principal es intencional, no un descuido, así que no se demuestra "código
muerto" en el mismo sentido y queda fuera de esta limpieza.
"""

from __future__ import annotations

from rag.core import retriever as retriever_module


def test_retriever_module_no_longer_exposes_a_demo_cli_helper() -> None:
    assert not hasattr(retriever_module, "demo")


def test_ollama_reranker_is_deliberately_kept_as_optional_utility() -> None:
    """No es una prueba de comportamiento — solo deja constancia de que la
    clase sigue existiendo por decisión explícita, no por descuido."""
    assert hasattr(retriever_module, "OllamaReranker")


# ---------------------------------------------------------------------------
# C10 — regresión: `balance_by_doc_type()` también se retiró por ser código
# muerto demostrable. A diferencia de `demo()` (T4.3), ni siquiera un test la
# ejercitaba desde el flujo real: su ÚNICO consumidor en todo el repo era
# tests/unit/test_retriever_balance.py, un archivo dedicado exclusivamente a
# probarla — ningún módulo de api/, core/ o evaluation/ la importaba. Se
# elimina la función junto con ese archivo de pruebas (que dejó de tener
# sujeto).
# ---------------------------------------------------------------------------


def test_retriever_module_no_longer_exposes_balance_by_doc_type() -> None:
    assert not hasattr(retriever_module, "balance_by_doc_type")
