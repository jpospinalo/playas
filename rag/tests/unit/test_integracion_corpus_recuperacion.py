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
from langchain_core.retrievers import BaseRetriever

import rag.core.agent as agent_module
from rag.core.retriever import HybridEnsembleRetriever
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


class _Fijo(BaseRetriever):
    """Sub-retriever falso: devuelve siempre la misma lista."""

    docs: list[Document]

    def _get_relevant_documents(self, query, *, run_manager=None):
        return list(self.docs)


def _frag(fuente: str, n: int) -> Document:
    return Document(
        page_content=f"{fuente} fragmento {n}",
        metadata={"doc_type": "jurisprudencia", "source": fuente, "chunk_id": f"{fuente}-{n}"},
    )


class _Evidencia:
    docket = "47001333300520100068401"
    instance = "segunda instancia"

    def __init__(self) -> None:
        self.recibidos: list[Document] = []

    def select_for_question(self, question, documents, limit):
        self.recibidos = list(documents)
        verificados = [d for d in documents if d.metadata["source"] == "verificada.pdf"]
        return verificados[:limit], None


class _Indice:
    def __init__(self, evidencia: _Evidencia) -> None:
        self.evidencia = evidencia

    def docket_evidence(self, question):
        return self.evidencia

    def resolve(self, question, *, max_sources=4):
        return None


@pytest.mark.anyio
async def test_radicado_verificado_recibe_todos_los_fragmentos_de_la_sentencia(monkeypatch):
    # BM25 trae 4 fragmentos de la sentencia verificada y luego 10 sentencias
    # ajenas. La diversificación (1 fragmento por sentencia) mandaría los
    # fragmentos 2-4 detrás de las ajenas y el recorte a k_candidates los
    # dejaría fuera: la evidencia solo vería un fragmento verificado.
    verificada = [_frag("verificada.pdf", n) for n in range(1, 5)]
    ajenas = [_frag(f"ajena-{n}.pdf", 1) for n in range(10)]
    hibrido = HybridEnsembleRetriever(
        retrievers=[_Fijo(docs=verificada + ajenas), _Fijo(docs=[])],
        weights=[0.8, 0.2],
        max_results=8,
    )
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **_: hibrido)
    evidencia = _Evidencia()
    pregunta = (
        "¿Qué resolvió en segunda instancia sobre la sentencia del 22 de septiembre "
        "de 2019 en el radicado 47001333300520100068401?"
    )
    state = {"question": pregunta, "k": 4, "k_candidates": 8}

    result = await agent_module.retrieve_forced_node(
        state, verify_docket=True, resolution_index=_Indice(evidencia)
    )

    recibidos = [d.metadata["chunk_id"] for d in evidencia.recibidos]
    assert [f"verificada.pdf-{n}" for n in range(1, 5)] == [
        c for c in recibidos if c.startswith("verificada")
    ]
    assert [d.metadata["chunk_id"] for d in result["sources"]] == [
        f"verificada.pdf-{n}" for n in range(1, 5)
    ]
    assert result["verified_docket"] == "47001333300520100068401"
    assert hibrido.fragmentos_por_sentencia == 1  # el retriever compartido no se altera


@pytest.mark.anyio
async def test_resolucion_activa_y_pregunta_sin_radicado_usa_multiconsulta(monkeypatch):
    docs = [Document(page_content=f"f{i}", metadata={"chunk_id": f"c{i}"}) for i in range(3)]
    retriever = _FusingRetriever(docs)
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", lambda **_: retriever)
    state = {
        "question": "¿Se puede instalar un kiosco en la playa de El Rodadero?",
        "standalone_question": "¿Qué permisos exige un kiosco en El Rodadero?",
        "enriched_query": "kiosco playa El Rodadero permiso DIMAR",
        "k": 2,
        "k_candidates": 8,
    }

    result = await agent_module.retrieve_forced_node(
        state, verify_docket=True, resolution_index=None
    )

    assert retriever.fused == [
        [state["question"], state["standalone_question"], state["enriched_query"]]
    ]
    assert [d.metadata["chunk_id"] for d in result["sources"]] == ["c0", "c1"]
    assert result["verified_docket"] is None
    assert result["verified_instance"] is None
    assert result["documentary_answer"] is None
