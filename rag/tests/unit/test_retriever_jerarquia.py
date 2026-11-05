"""Jerarquía normativa en la fusión: la norma aplicable va antes que la
jurisprudencia y, si falta, ocupa un cupo reservado del top-k."""

from __future__ import annotations

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag.core.prompts import AGENT_SYSTEM
from rag.core.retriever import HybridEnsembleRetriever


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _doc(identifier: str, *, doc_type: str, title: str = "") -> Document:
    return Document(
        page_content=f"contenido de {identifier}",
        metadata={"chunk_id": identifier, "doc_type": doc_type, "title": title or identifier},
    )


def _ids(docs: list[Document]) -> list[str]:
    return [str(d.metadata["chunk_id"]) for d in docs]


class _StaticRetriever(BaseRetriever):
    docs: list[Document] = Field(default_factory=list)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        del query, run_manager
        return list(self.docs)


def _retriever(docs: list[Document], **kwargs) -> HybridEnsembleRetriever:
    return HybridEnsembleRetriever(
        retrievers=[_StaticRetriever(docs=docs), _StaticRetriever(docs=docs)],
        weights=[0.8, 0.2],
        **kwargs,
    )


def test_norma_va_antes_que_la_jurisprudencia_sin_cambiar_la_seleccion():
    docs = [
        _doc("s1", doc_type="jurisprudencia"),
        _doc("s2", doc_type="jurisprudencia"),
        _doc("remac", doc_type="normativa", title="Reglamento Maritimo Colombiano REMAC"),
        _doc("s3", doc_type="jurisprudencia"),
    ]
    out = _retriever(docs, max_results=3, cupos_normativa=0).invoke("playa")
    assert _ids(out) == ["remac", "s1", "s2"]


def test_cupo_reservado_trae_la_norma_y_saca_la_jurisprudencia_peor_ubicada():
    docs = [
        _doc("s1", doc_type="jurisprudencia"),
        _doc("s2", doc_type="jurisprudencia"),
        _doc("s3", doc_type="jurisprudencia"),
        _doc("decreto", doc_type="normativa", title="Decreto 2324 de 1984"),
    ]
    out = _retriever(docs, max_results=3, cupos_normativa=1).invoke("playa")
    assert _ids(out) == ["decreto", "s1", "s2"]


def test_sin_normas_candidatas_no_cambia_nada():
    docs = [_doc(f"s{i}", doc_type="jurisprudencia") for i in range(1, 5)]
    out = _retriever(docs, max_results=3, cupos_normativa=1).invoke("playa")
    assert _ids(out) == ["s1", "s2", "s3"]


def test_norma_local_de_otra_ciudad_no_ocupa_el_cupo_ni_sube():
    docs = [
        _doc("s1", doc_type="jurisprudencia"),
        _doc("s2", doc_type="jurisprudencia"),
        _doc("turbo", doc_type="normativa", title="Acuerdo de Turbo"),
    ]
    out = _retriever(docs, max_results=2, cupos_normativa=1).invoke("playas de Santa Marta")
    assert _ids(out) == ["s1", "s2"]


def test_norma_local_de_la_ciudad_preguntada_si_cuenta():
    docs = [
        _doc("s1", doc_type="jurisprudencia"),
        _doc("s2", doc_type="jurisprudencia"),
        _doc("rodadero", doc_type="normativa", title="Reglamento de El Rodadero"),
    ]
    out = _retriever(docs, max_results=2, cupos_normativa=1).invoke("playas de Santa Marta")
    assert _ids(out) == ["rodadero", "s1"]


def test_desactivada_conserva_el_orden_de_fusion():
    docs = [
        _doc("s1", doc_type="jurisprudencia"),
        _doc("remac", doc_type="normativa", title="REMAC"),
    ]
    out = _retriever(docs, max_results=2, normativa_primero=False).invoke("playa")
    assert _ids(out) == ["s1", "remac"]


@pytest.mark.anyio
async def test_ruta_multiconsulta_aplica_la_misma_jerarquia():
    docs = [
        _doc("s1", doc_type="jurisprudencia"),
        _doc("s2", doc_type="jurisprudencia"),
        _doc("remac", doc_type="normativa", title="REMAC"),
    ]
    out = await _retriever(docs, max_results=2, cupos_normativa=1).afuse_queries(
        ["playa", "uso de playas"]
    )
    assert _ids(out) == ["remac", "s1"]


def test_prompt_pide_la_norma_antes_que_la_jurisprudencia():
    assert "Jerarquía de fuentes" in AGENT_SYSTEM
    assert "sin afirmar jerarquías" not in AGENT_SYSTEM
