"""Tests de build_context_block: ramificación de cabecera por doc_type."""

from __future__ import annotations

from langchain_core.documents import Document

from rag.core.tools import build_context_block


def test_normativa_header_shows_norma_and_articulo_not_corporacion():
    doc = Document(
        page_content="Contenido del artículo.",
        metadata={
            "doc_type": "normativa",
            "title": "Decreto 2324 de 1984",
            "articulo": "2",
            "titulo": "TITULO I",
            "capitulo": "",
            "source": "decreto_2324.md",
            "chunk_id": "norm_1",
            "summary": "Define el dominio público marítimo.",
        },
    )

    block = build_context_block([doc])

    assert "Decreto 2324 de 1984" in block
    assert "Artículo" in block
    assert "Corporación" not in block
    assert "Magistrado" not in block


def test_jurisprudencia_header_keeps_corporacion_and_magistrado():
    doc = Document(
        page_content="Razonamiento de la Sala.",
        metadata={
            "doc_type": "jurisprudencia",
            "Corporación": "Consejo de Estado",
            "Magistrado ponente": "Juan Pérez",
            "Tema principal": "Deslinde",
            "section_name": "Argumentación jurídica",
            "source": "sentencia_1.md",
            "chunk_id": "juris_1",
            "summary": "Resumen de la sentencia.",
        },
    )

    block = build_context_block([doc])

    assert "Corporación: Consejo de Estado" in block
    assert "Magistrado ponente: Juan Pérez" in block
