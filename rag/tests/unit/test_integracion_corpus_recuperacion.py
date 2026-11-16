"""Convivencia de la recuperación multiconsulta con la resolución documental.

Sin radicado verificado, ``retrieve_forced_node`` recupera la pregunta original,
la autosuficiente y la enriquecida por separado y las fusiona
(``afuse_queries``). Con radicado verificado usa una consulta compuesta
(``ainvoke``) y deja que la evidencia elija los fragmentos verificados.
``build_context_block`` omite los identificadores históricos (cabecera y
radicado de la metadata) solo cuando se le pide; la llamada sin argumentos,
la que usan ingesta y la evaluación de nivel 0, no cambia.
"""

from __future__ import annotations

import pytest
from langchain_core.documents import Document

import rag.core.agent as agent_module
from rag.core.tools import build_context_block


class _FusingRetriever:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self.fused: list[list[str]] = []

    async def ainvoke(self, query: str) -> list[Document]:
        pytest.fail("sin radicado verificado no debe usarse ainvoke con una consulta compuesta")

    async def afuse_queries(self, queries: list[str]) -> list[Document]:
        self.fused.append(list(queries))
        return self.docs


@pytest.mark.anyio
async def test_sin_radicado_verificado_recupera_con_consultas_fusionadas(monkeypatch):
    docs = [Document(page_content=f"f{i}", metadata={"chunk_id": f"c{i}"}) for i in range(5)]
    retriever = _FusingRetriever(docs)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **_: retriever)
    state = {
        "question": "¿Quién otorga concesiones de playa?",
        "standalone_question": "¿Qué autoridad otorga concesiones sobre playas en Colombia?",
        "enriched_query": "concesión playa DIMAR bienes de uso público",
        "k": 2,
        "k_candidates": 8,
    }

    result = await agent_module.retrieve_forced_node(state)

    assert retriever.fused == [
        [state["question"], state["standalone_question"], state["enriched_query"]]
    ]
    assert [d.metadata["chunk_id"] for d in result["sources"]] == ["c0", "c1"]


def _sentencia() -> Document:
    return Document(
        page_content="Se ordena la restitución del bien de uso público.",
        metadata={
            "doc_type": "jurisprudencia",
            "source": "AP_historico_2011.jsonl",
            "chunk_id": "AP_historico_2011_0003",
            "Radicado": "47001-23-31-000-2011-00999-01",
        },
    )


def _norma_local() -> Document:
    return Document(
        page_content="Artículo 5. Zonificación de playas.",
        metadata={
            "doc_type": "normativa",
            "title": "Por medio del cual se reglamenta el uso de las playas de Santa Marta",
            "source": "decreto_santa_marta.jsonl",
            "chunk_id": "decreto_santa_marta_0001",
        },
    )


def test_contexto_por_defecto_conserva_identificadores_y_radicado():
    bloque = build_context_block([_sentencia()])
    assert "source=AP_historico_2011.jsonl" in bloque
    assert "chunk_id=AP_historico_2011_0003" in bloque
    assert "Radicado: 47001-23-31-000-2011-00999-01" in bloque


def test_contexto_verificado_omite_identificadores_historicos_y_conserva_ambito():
    bloque = build_context_block([_sentencia(), _norma_local()], include_source_identifiers=False)
    assert "[doc1]" in bloque and "[doc2]" in bloque
    assert "source=" not in bloque and "chunk_id=" not in bloque
    assert "2011-00999" not in bloque
    assert "Ámbito territorial:" in bloque
