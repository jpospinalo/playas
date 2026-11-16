"""Contrato público del RAG que usan otros módulos del repositorio.

La evaluación de nivel 0 (``evaluation/ragas/run_level0.py``) y los benchmarks
de la rama de ingesta importan estas funciones directamente. Si una cambia de nombre o de firma, esta prueba falla
antes de que se rompa su código.
"""

from __future__ import annotations

import inspect

from rag.core import embeddings, retriever, tools


def test_ciclo_de_vida_del_retriever_sin_argumentos():
    for nombre in ("init_retrievers", "close_retrievers"):
        funcion = getattr(retriever, nombre)
        obligatorios = [
            p
            for p in inspect.signature(funcion).parameters.values()
            if p.default is inspect.Parameter.empty
            and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        assert obligatorios == [], nombre


def test_get_ensemble_retriever_acepta_k_y_k_candidates():
    parametros = inspect.signature(retriever.get_ensemble_retriever).parameters
    assert {"k", "k_candidates"} <= set(parametros)


def test_build_context_block_se_llama_solo_con_los_documentos():
    parametros = list(inspect.signature(tools.build_context_block).parameters.values())
    assert parametros[0].name == "docs"
    assert all(p.default is not inspect.Parameter.empty for p in parametros[1:])


def test_cliente_de_embeddings_de_ollama_existe():
    assert inspect.isclass(embeddings.OllamaEmbeddingClient)
    # run_level0.py reemplaza embed_one para cachear los vectores de consulta.
    assert callable(getattr(embeddings.OllamaEmbeddingClient, "embed_one", None))
