"""El recuperador híbrido debe respetar el k final."""

from __future__ import annotations

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag.core.retriever import HybridEnsembleRetriever


class _StaticRetriever(BaseRetriever):
    docs: list[Document]

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
    ) -> list[Document]:
        del query, run_manager
        return self.docs


def _doc(identifier: str) -> Document:
    return Document(page_content=identifier, metadata={"chunk_id": identifier})


def test_hybrid_fusion_truncates_union_to_final_k() -> None:
    retriever = HybridEnsembleRetriever(
        retrievers=[
            _StaticRetriever(docs=[_doc("a"), _doc("b"), _doc("c")]),
            _StaticRetriever(docs=[_doc("d"), _doc("e"), _doc("f")]),
        ],
        weights=[0.5, 0.5],
        max_results=2,
    )
    assert len(retriever.invoke("consulta")) == 2
