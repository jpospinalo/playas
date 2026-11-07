"""Contratos sintéticos del contexto y su atribución documental."""

from __future__ import annotations

from copy import deepcopy

import pytest
from langchain_core.documents import Document

from rag.core.tools import build_context_block


def test_normativa_header_shows_norma_and_articulo_not_corporacion() -> None:
    doc = Document(
        page_content="Contenido del artículo.",
        metadata={
            "doc_type": "normativa",
            "title": "Decreto 2324 de 1984",
            "articulo": "2",
            "titulo": "TITULO I",
            "capitulo": "CAPÍTULO II",
            "source": "decreto_2324.md",
            "chunk_id": "norm_1",
            "summary": "Define el dominio público marítimo.",
        },
    )

    block = build_context_block([doc])

    assert block.startswith("[doc1 | source=decreto_2324.md | chunk_id=norm_1]\n")
    assert "Norma: Decreto 2324 de 1984" in block
    assert "Título: TITULO I" in block
    assert "Capítulo: CAPÍTULO II" in block
    assert "Artículo: 2" in block
    assert "Corporación" not in block
    assert "Magistrado" not in block
    assert (
        "Resumen auxiliar (contrastar con el cuerpo): Define el dominio público marítimo." in block
    )
    assert block.endswith("Texto del fragmento:\n" + doc.page_content)


def test_jurisprudencia_header_keeps_corporacion_and_magistrado() -> None:
    doc = Document(
        page_content="Razonamiento de la Sala.",
        metadata={
            "doc_type": "jurisprudencia",
            "Corporación": "Consejo de Estado",
            "Magistrado ponente": "Juan Pérez",
            "Tema principal": "Deslinde",
            "section_name": "Argumentación jurídica",
            "section_heading": "CONSIDERACIONES DE LA SALA",
            "source": "sentencia_1.md",
            "chunk_id": "juris_1",
            "summary": "Resumen de la sentencia.",
        },
    )

    block = build_context_block([doc])

    assert "Corporación: Consejo de Estado" in block
    assert "Magistrado ponente: Juan Pérez" in block
    assert "Tema principal: Deslinde" in block
    assert "Sección: Argumentación jurídica" in block
    assert "Encabezado: CONSIDERACIONES DE LA SALA" in block
    assert "Resumen auxiliar (contrastar con el cuerpo): Resumen de la sentencia." in block
    assert block.endswith("Texto del fragmento:\n" + doc.page_content)


@pytest.mark.parametrize("doc_type", ["normativa", "jurisprudencia"])
def test_missing_optional_metadata_keeps_fallbacks_and_body(doc_type: str) -> None:
    doc = Document(page_content="Texto breve conservado.", metadata={"doc_type": doc_type})

    block = build_context_block([doc])

    assert block.startswith("[doc1 | source=desconocido | chunk_id=doc_1]\n")
    for label in ("Resumen auxiliar", "Encabezado:", "Sección:", "Artículo:"):
        assert label not in block
    if doc_type == "normativa":
        assert "Norma: desconocido" in block
    assert block.endswith("Texto del fragmento:\n" + doc.page_content)


@pytest.mark.parametrize("doc_type", [None, "desconocido"])
def test_legacy_document_type_keeps_jurisprudencia_and_id_fallback(doc_type: str | None) -> None:
    metadata = {
        "source": "sentencia_legacy.md",
        "id": "legacy_id",
        "Corporacion": "Consejo de Estado",
        "Magistrado ponente": "Ponente de prueba",
    }
    if doc_type is not None:
        metadata["doc_type"] = doc_type
    doc = Document(page_content="Cuerpo de la sentencia anterior.", metadata=metadata)

    block = build_context_block([doc])

    assert block.startswith("[doc1 | source=sentencia_legacy.md | chunk_id=legacy_id]\n")
    assert "Corporación: Consejo de Estado" in block
    assert "Magistrado ponente: Ponente de prueba" in block
    assert block.endswith("Texto del fragmento:\n" + doc.page_content)


def test_multiple_documents_keep_order_numbering_and_complete_bodies() -> None:
    docs = [
        Document(
            page_content="  Primera línea.\n\nSegunda línea con espacios.  \n",
            metadata={"doc_type": "normativa", "source": "norma.md", "chunk_id": "norm_1"},
        ),
        Document(
            page_content="Segundo fragmento.\nOtra línea independiente.",
            metadata={"doc_type": "jurisprudencia", "source": "fallo.md", "chunk_id": "juris_2"},
        ),
    ]

    block = build_context_block(docs)

    first_header = "[doc1 | source=norma.md | chunk_id=norm_1]"
    second_header = "[doc2 | source=fallo.md | chunk_id=juris_2]"
    assert block.index(first_header) < block.index(second_header)
    first_block, _, second_block = block.partition(second_header)
    assert "Texto del fragmento:\n" + docs[0].page_content in first_block
    assert second_block.endswith("Texto del fragmento:\n" + docs[1].page_content)
    assert block.count("Texto del fragmento:") == 2
    for doc in docs:
        assert block.count(doc.page_content) == 1


@pytest.mark.parametrize("doc_type", ["normativa", "jurisprudencia"])
def test_context_does_not_mutate_documents_or_nested_metadata(doc_type: str) -> None:
    doc = Document(
        page_content="Cuerpo original sin cambios.",
        metadata={
            "doc_type": doc_type,
            "summary": "Resumen descriptivo.",
            "section_heading": "Encabezado original",
            "entities": [{"text": "Entidad", "details": {"aliases": ["Nombre alternativo"]}}],
        },
    )
    before = (doc.page_content, deepcopy(doc.metadata))

    build_context_block([doc])

    assert (doc.page_content, doc.metadata) == before


def test_replacement_character_sanitization_is_preserved_without_mutation() -> None:
    doc = Document(
        page_content="Pasaje\ufffd conservado.\nSegundo párrafo.",
        metadata={
            "doc_type": "jurisprudencia",
            "source": "senten\ufffdcia.md",
            "chunk_id": "juris\ufffd_1",
            "Corporación": "Consejo de \ufffdEstado",
            "section_name": "Argumenta\ufffdción",
            "section_heading": "CONSIDERA\ufffdCIONES",
            "summary": "Resume\ufffdn fiel.",
        },
    )
    before = (doc.page_content, deepcopy(doc.metadata))

    block = build_context_block([doc])

    assert "\ufffd" not in block
    assert "[doc1 | source=sentencia.md | chunk_id=juris_1]" in block
    assert "Corporación: Consejo de Estado" in block
    assert "Sección: Argumentación" in block
    assert "Encabezado: CONSIDERACIONES" in block
    assert "Resumen auxiliar (contrastar con el cuerpo): Resumen fiel." in block
    assert block.endswith("Texto del fragmento:\nPasaje conservado.\nSegundo párrafo.")
    assert (doc.page_content, doc.metadata) == before


@pytest.mark.parametrize(
    ("heading", "summary", "body"),
    [
        (
            "CONTESTACIÓN DE LA DEMANDA",
            "La sociedad presenta su posición.",
            "La sociedad sostuvo que contaba con autorización.",
        ),
        (
            "ASPECTOS POR ANALIZAR",
            "Enumera los temas que se estudiarán.",
            "Se analizarán los siguientes aspectos: delimitación y autoridades competentes.",
        ),
        (
            "RESUELVE",
            "La Sala ordena habilitar el acceso.",
            "ORDENA a la autoridad habilitar el acceso señalado en esta decisión.",
        ),
    ],
    ids=["alegacion", "indice", "decision"],
)
def test_legal_passages_remain_available_without_role_inference(
    heading: str, summary: str, body: str
) -> None:
    doc = Document(
        page_content=body,
        metadata={
            "doc_type": "jurisprudencia",
            "section_heading": heading,
            "summary": summary,
        },
    )

    block = build_context_block([doc])

    assert f"Encabezado: {heading}" in block
    assert f"Resumen auxiliar (contrastar con el cuerpo): {summary}" in block
    assert block.endswith("Texto del fragmento:\n" + body)
