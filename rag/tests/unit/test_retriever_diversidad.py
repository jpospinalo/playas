"""La fusión limita a un fragmento por sentencia antes de recortar.

Sin tope, el top-4 se llenaba con cuatro fragmentos de la misma sentencia y
no dejaba sitio a la norma aplicable ni a otras sentencias. Los fragmentos
extra no se borran: pasan al final y solo vuelven si faltan candidatos. Las
normas no tienen tope: varios artículos de una misma norma son evidencia
distinta.
"""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag.core.retriever import HybridEnsembleRetriever


def _doc(identifier: str, *, doc_type: str, source: str) -> Document:
    return Document(
        page_content=f"contenido de {identifier}",
        metadata={"chunk_id": identifier, "doc_type": doc_type, "source": source, "title": source},
    )


class _Static(BaseRetriever):
    docs: list[Document] = Field(default_factory=list)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        del query, run_manager
        return list(self.docs)


def _ids(docs: list[Document]) -> list[str]:
    return [str(d.metadata["chunk_id"]) for d in docs]


def _ret(docs: list[Document], max_results: int = 3, **kw) -> HybridEnsembleRetriever:
    return HybridEnsembleRetriever(
        retrievers=[_Static(docs=docs)], weights=[1.0], max_results=max_results, **kw
    )


def test_un_fragmento_por_sentencia_en_el_recorte() -> None:
    docs = [
        _doc("s1a", doc_type="jurisprudencia", source="AP X VS DIMAR"),
        _doc("s1b", doc_type="jurisprudencia", source="AP X VS DIMAR"),
        _doc("s1c", doc_type="jurisprudencia", source="AP X VS DIMAR"),
        _doc("n1", doc_type="normativa", source="REMAC 5"),
        _doc("s2a", doc_type="jurisprudencia", source="CE Consulta 2005"),
    ]

    assert _ids(_ret(docs).invoke("q")) == ["s1a", "n1", "s2a"]


def test_normas_sin_tope() -> None:
    docs = [
        _doc("n1", doc_type="normativa", source="REMAC 5"),
        _doc("n2", doc_type="normativa", source="REMAC 5"),
        _doc("s1a", doc_type="jurisprudencia", source="AP X VS DIMAR"),
    ]

    assert _ids(_ret(docs).invoke("q")) == ["n1", "n2", "s1a"]


def test_fragmentos_extra_rellenan_si_faltan_candidatos() -> None:
    docs = [
        _doc("s1a", doc_type="jurisprudencia", source="AP X"),
        _doc("s1b", doc_type="jurisprudencia", source="AP X"),
        _doc("s1c", doc_type="jurisprudencia", source="AP X"),
    ]

    assert _ids(_ret(docs).invoke("q")) == ["s1a", "s1b", "s1c"]


def test_tope_desactivable() -> None:
    docs = [
        _doc("s1a", doc_type="jurisprudencia", source="AP X"),
        _doc("s1b", doc_type="jurisprudencia", source="AP X"),
        _doc("n1", doc_type="normativa", source="REMAC 5"),
    ]

    assert _ids(_ret(docs, max_results=2, fragmentos_por_sentencia=None).invoke("q")) == [
        "s1a",
        "s1b",
    ]


def test_tope_va_antes_de_la_regla_territorial() -> None:
    """Un fragmento de sentencia degradado por el tope no debe adelantar a una
    norma local de otra ciudad: esa norma queda siempre al final."""
    docs = [
        _doc("s1a", doc_type="jurisprudencia", source="AP X"),
        _doc("s1b", doc_type="jurisprudencia", source="AP X"),
        _doc("turbo", doc_type="normativa", source="Reglamento de playas de Turbo"),
    ]

    assert _ids(_ret(docs).invoke("playa en Santa Marta")) == ["s1a", "s1b", "turbo"]
