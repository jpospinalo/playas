"""Tests de build_context_block: ámbito territorial de las normas locales.

Una norma local solo rige en su ciudad. Si el bloque de contexto no lo dice,
el modelo no puede saber que, por ejemplo, Playa Cristal está en Santa Marta
y duda de si el reglamento aplica. Las normas no locales no llevan la línea:
no se afirma un ámbito que la metadata no respalda.
"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.core.tools import build_context_block


def _norma(title: str) -> Document:
    return Document(
        page_content="ARTÍCULO 1. Texto.",
        metadata={"doc_type": "normativa", "title": title, "source": f"{title}.md"},
    )


def test_norma_local_declara_ciudad_y_lugares_que_cubre() -> None:
    block = build_context_block(
        [_norma("Por medio de la cual se reglamenta el área de playa en el Balneario El Rodadero")]
    )

    linea = next(x for x in block.splitlines() if x.startswith("Ámbito territorial:"))
    assert "Santa Marta" in linea
    assert "playa cristal" in linea.lower()
    assert block.index("Norma:") < block.index("Ámbito territorial:")


def test_norma_local_de_cartagena() -> None:
    block = build_context_block(
        [_norma("Reglamento de playas del Distrito de Cartagena de Indias")]
    )

    assert "Ámbito territorial: Cartagena" in block


def test_norma_nacional_no_lleva_ambito() -> None:
    block = build_context_block([_norma("decreto-2324-de-1984")])

    assert "Ámbito territorial" not in block


def test_jurisprudencia_no_lleva_ambito_aunque_mencione_ciudad() -> None:
    doc = Document(
        page_content="Hechos en Santa Marta.",
        metadata={"doc_type": "jurisprudencia", "title": "AP X VS Distrito de Santa Marta"},
    )

    assert "Ámbito territorial" not in build_context_block([doc])
