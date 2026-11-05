"""La fusión del retriever híbrido demota normas locales de otra ciudad antes
de recortar a ``max_results``, para reemplazarlas por el siguiente candidato."""

from __future__ import annotations

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag.core.retriever import HybridEnsembleRetriever


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _doc(identifier: str, *, doc_type: str, title: str) -> Document:
    return Document(
        page_content=f"contenido de {identifier}",
        metadata={"chunk_id": identifier, "doc_type": doc_type, "title": title},
    )


def _ids(docs: list[Document]) -> list[str]:
    return [str(d.metadata["chunk_id"]) for d in docs]


class _StaticRetriever(BaseRetriever):
    """Devuelve siempre la misma lista, sin importar la consulta."""

    docs: list[Document] = Field(default_factory=list)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del query, run_manager
        return list(self.docs)


def _retriever(docs: list[Document], **kwargs) -> HybridEnsembleRetriever:
    # Aísla la prioridad territorial: la jerarquía normativa tiene sus propios tests.
    kwargs.setdefault("normativa_primero", False)
    return HybridEnsembleRetriever(
        retrievers=[_StaticRetriever(docs=docs), _StaticRetriever(docs=docs)],
        weights=[0.8, 0.2],
        max_results=2,
        **kwargs,
    )


def _documentos() -> list[Document]:
    return [
        _doc("turbo", doc_type="normativa", title="Acuerdo de Turbo"),
        _doc("nacional", doc_type="normativa", title="Reglamento Maritimo Colombiano REMAC"),
        _doc("santa", doc_type="normativa", title="Reglamento de El Rodadero"),
    ]


def test_la_norma_de_otra_ciudad_se_demota_y_entra_el_siguiente_candidato():
    resultado = _retriever(_documentos()).invoke("¿Qué puedo hacer en Santa Marta?")

    assert _ids(resultado) == ["nacional", "santa"]


def test_sin_prioridad_territorial_el_orden_no_cambia():
    resultado = _retriever(_documentos(), priorizar_territorio=False).invoke(
        "¿Qué puedo hacer en Santa Marta?"
    )

    assert _ids(resultado) == ["turbo", "nacional"]


@pytest.mark.anyio
async def test_afuse_queries_usa_todas_las_consultas_para_el_territorio():
    """Un lugar mencionado solo en la segunda consulta conserva su norma:
    sin mirar esa consulta, la norma local quedaría demotada."""
    docs = [
        _doc("turbo", doc_type="normativa", title="Acuerdo de Turbo"),
        _doc("santa", doc_type="normativa", title="Reglamento de El Rodadero"),
        _doc("nacional", doc_type="normativa", title="Reglamento Maritimo Colombiano REMAC"),
    ]
    retriever = _retriever(docs)

    resultado = await retriever.afuse_queries(
        ["una pregunta general", "evento en Taganga (Santa Marta)"]
    )

    assert _ids(resultado) == ["santa", "nacional"]
    assert "turbo" not in _ids(resultado)
