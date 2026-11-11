"""Tests de build_context_block: línea Radicado en la rama de jurisprudencia.

El prompt de fidelidad exige citar las sentencias por corporación y
radicado/expediente; por tanto el bloque de contexto debe incluir el radicado
cuando el fragmento lo trae.
"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.core.tools import build_context_block


def _doc_jurisprudencia(**metadata_extra) -> Document:
    meta = {
        "doc_type": "jurisprudencia",
        "Corporación": "Consejo de Estado",
        "Magistrado ponente": "Juan Pérez",
        "Tema principal": "Deslinde",
        "section_name": "Argumentación jurídica",
        "source": "sentencia_1.md",
        "chunk_id": "juris_1",
        "summary": "Resumen de la sentencia.",
    }
    meta.update(metadata_extra)
    return Document(page_content="Razonamiento de la Sala.", metadata=meta)


def test_radicado_se_incluye_despues_de_corporacion() -> None:
    block = build_context_block([_doc_jurisprudencia(Radicado="25000-23-24-000-2010-00001-01")])

    assert "Radicado: 25000-23-24-000-2010-00001-01" in block
    assert block.index("Corporación: Consejo de Estado") < block.index("Radicado:")


def test_radicado_ausente_no_produce_linea() -> None:
    block = build_context_block([_doc_jurisprudencia()])

    assert "Radicado" not in block


def test_radicado_vacio_o_solo_espacios_no_produce_linea() -> None:
    assert "Radicado" not in build_context_block([_doc_jurisprudencia(Radicado="")])
    assert "Radicado" not in build_context_block([_doc_jurisprudencia(Radicado="   ")])


def test_radicado_sanea_caracter_u_fffd() -> None:
    block = build_context_block([_doc_jurisprudencia(Radicado="25000-\ufffd2010-00001")])

    assert "\ufffd" not in block
    assert "Radicado: 25000-2010-00001" in block


def test_normativa_no_agrega_linea_de_radicado() -> None:
    doc = Document(
        page_content="Contenido del artículo.",
        metadata={
            "doc_type": "normativa",
            "title": "Decreto 2324 de 1984",
            "articulo": "2",
            "source": "decreto_2324.md",
            "chunk_id": "norm_1",
            "summary": "Define el dominio público marítimo.",
            "Radicado": "25000-23-24-000-2010-00001-01",
        },
    )

    block = build_context_block([doc])

    assert "Radicado" not in block
    assert (
        block == "[doc1 | source=decreto_2324.md | chunk_id=norm_1]\n"
        "Norma: Decreto 2324 de 1984\n"
        "Artículo: 2\n"
        "Resumen auxiliar (contrastar con el cuerpo): Define el dominio público marítimo.\n"
        "Texto del fragmento:\n"
        "Contenido del artículo."
    )
