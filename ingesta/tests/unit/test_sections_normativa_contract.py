"""Contratos sintéticos de normativa, sin corpus local ni servicios externos."""

from copy import deepcopy
from typing import Any

from langchain_core.documents import Document

from ingest.sections_normativa import split_by_articles

_BASE_METADATA = {
    "source": "norma_sintetica.md",
    "title": "Norma de prueba",
    "doc_type": "normativa",
    "control": "offline",
}
_PREAMBLE_METADATA = {
    **_BASE_METADATA,
    "articulo": None,
    "articulo_titulo": "",
    "titulo": "",
    "capitulo": "",
    "section_index": 1,
    "section_name": "Preámbulo",
}


def _assert_contract(text: str, expected: list[tuple[str, dict[str, Any]]]) -> None:
    doc = Document(page_content=text, metadata=deepcopy(_BASE_METADATA))
    saved = deepcopy(doc)

    sections = split_by_articles(doc)

    assert [(section.page_content, section.metadata) for section in sections] == expected
    assert [section.metadata["section_index"] for section in sections] == list(
        range(1, len(expected) + 1)
    )
    assert doc == saved
    assert sections == split_by_articles(doc)
    assert doc == saved


def test_more_than_ten_articles_keep_exact_order_and_metadata() -> None:
    preamble = "DECRETA\nTÍTULO I\nCAPÍTULO I"
    articles = [f"Artículo {i}. Objeto {i}.\nContenido único {i}." for i in range(1, 13)]
    expected = [
        (preamble, _PREAMBLE_METADATA),
        *[
            (
                article,
                {
                    **_BASE_METADATA,
                    "articulo": str(i),
                    "articulo_titulo": f"Objeto {i}",
                    "titulo": "TÍTULO I",
                    "capitulo": "CAPÍTULO I",
                    "section_index": i + 1,
                    "section_name": f"Objeto {i}",
                },
            )
            for i, article in enumerate(articles, 1)
        ],
    ]

    _assert_contract("\n".join([preamble, *articles]), expected)


def test_page_markers_are_removed_without_cutting_article_text() -> None:
    text = (
        "## Página 1\n"
        "DECRETA\n"
        "Artículo 1. Objeto.\n"
        "Texto anterior.\n"
        "## Página 2\n"
        "Texto posterior.\n"
        "En esta frase se menciona ## Página 99."
    )
    expected = [
        ("DECRETA", _PREAMBLE_METADATA),
        (
            "Artículo 1. Objeto.\nTexto anterior.\n\nTexto posterior.\n"
            "En esta frase se menciona ## Página 99.",
            {
                **_BASE_METADATA,
                "articulo": "1",
                "articulo_titulo": "Objeto",
                "titulo": "",
                "capitulo": "",
                "section_index": 2,
                "section_name": "Objeto",
            },
        ),
    ]

    _assert_contract(text, expected)


def test_dotted_and_repeated_article_numbers_preserve_literal_bodies() -> None:
    articles = [
        ("Artículo 5.2.5 .12: Primero.\nTexto A.", "5.2.5.12", "Primero"),
        ("Artículo 5.2.5.12: Segundo.\nTexto B.", "5.2.5.12", "Segundo"),
        ("ARTICULO 6- Tercero.\nTexto C.", "6", "Tercero"),
    ]
    expected = [
        (
            body,
            {
                **_BASE_METADATA,
                "articulo": number,
                "articulo_titulo": epigraphe,
                "titulo": "",
                "capitulo": "",
                "section_index": index,
                "section_name": epigraphe,
            },
        )
        for index, (body, number, epigraphe) in enumerate(articles, 1)
    ]

    _assert_contract("\n".join(body for body, _, _ in articles), expected)


def test_title_change_resets_chapter_and_preserves_body() -> None:
    text = (
        "TÍTULO I\n"
        "CAPÍTULO I\n"
        "Artículo 1. Primero.\n"
        "Texto A.\n"
        "CAPÍTULO II\n"
        "Artículo 2. Segundo.\n"
        "Texto B.\n"
        "TÍTULO II\n"
        "Artículo 3. Tercero.\n"
        "Texto C."
    )
    expected = [
        ("TÍTULO I\nCAPÍTULO I", _PREAMBLE_METADATA),
        (
            "Artículo 1. Primero.\nTexto A.\nCAPÍTULO II",
            {
                **_BASE_METADATA,
                "articulo": "1",
                "articulo_titulo": "Primero",
                "titulo": "TÍTULO I",
                "capitulo": "CAPÍTULO I",
                "section_index": 2,
                "section_name": "Primero",
            },
        ),
        (
            "Artículo 2. Segundo.\nTexto B.\nTÍTULO II",
            {
                **_BASE_METADATA,
                "articulo": "2",
                "articulo_titulo": "Segundo",
                "titulo": "TÍTULO I",
                "capitulo": "CAPÍTULO II",
                "section_index": 3,
                "section_name": "Segundo",
            },
        ),
        (
            "Artículo 3. Tercero.\nTexto C.",
            {
                **_BASE_METADATA,
                "articulo": "3",
                "articulo_titulo": "Tercero",
                "titulo": "TÍTULO II",
                "capitulo": "",
                "section_index": 4,
                "section_name": "Tercero",
            },
        ),
    ]

    _assert_contract(text, expected)


def test_document_without_articles_keeps_preamble() -> None:
    _assert_contract("Texto sin artículos.", [("Texto sin artículos.", _PREAMBLE_METADATA)])


def test_blank_document_returns_no_units_without_mutation() -> None:
    _assert_contract(" \n\t ", [])
