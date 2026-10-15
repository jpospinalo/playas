"""Contratos sintéticos de normativa, sin corpus local ni servicios externos."""

from copy import deepcopy
from typing import Any

import pytest
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
_ARTICLE_METADATA: dict[str, Any] = {
    **_BASE_METADATA,
    "articulo": "1",
    "articulo_titulo": "Objeto",
    "titulo": "",
    "capitulo": "",
    "section_index": 1,
    "section_name": "Objeto",
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
    expected: list[tuple[str, dict[str, Any]]] = [
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
    expected: list[tuple[str, dict[str, Any]]] = [
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
    expected: list[tuple[str, dict[str, Any]]] = [
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


@pytest.mark.parametrize(
    ("heading", "number"),
    [
        pytest.param("Artículo 1. Objeto.", "1", id="plain"),
        pytest.param("# ARTÍCULO 3. Objeto.", "3", id="markdown-level-one"),
        pytest.param("## ARTÍCULO 3. Objeto.", "3", id="markdown"),
        pytest.param("###### ARTÍCULO 3. Objeto.", "3", id="markdown-level-six"),
        pytest.param("**Artículo 1°.** Objeto.", "1", id="bold-degree"),
        pytest.param("**Artículo 2º.** Objeto.", "2", id="bold-ordinal"),
        pytest.param("## **Artículo 3°.** Objeto.", "3", id="combined"),
        pytest.param("Artículo 5.Objeto.", "5", id="no-space-after-period"),
        pytest.param("Artículo 13º. Objeto.", "13", id="ordinal"),
        pytest.param("Artículo 14°. Objeto.", "14", id="degree-period"),
        pytest.param("Artículo 1°.- Objeto.", "1", id="degree-period-hyphen"),
    ],
)
def test_heading_formats_preserve_literal_body(heading: str, number: str) -> None:
    body = f"{heading}\nContenido de prueba."
    _assert_contract(body, [(body, {**_ARTICLE_METADATA, "articulo": number})])


@pytest.mark.parametrize(
    "heading",
    [
        pytest.param("####### ARTÍCULO 3. Objeto.", id="too-many-hashes"),
        pytest.param("> Artículo 3. Objeto.", id="blockquote"),
        pytest.param("__Artículo 3.__ Objeto.", id="unsupported-underline"),
    ],
)
def test_unsupported_markdown_wrappers_do_not_create_articles(heading: str) -> None:
    text = f"{heading}\nContenido de prueba."
    _assert_contract(text, [(text, _PREAMBLE_METADATA)])


@pytest.mark.parametrize(
    ("literal_number", "number"),
    [
        pytest.param("12", "12", id="simple"),
        pytest.param("5.2.5.12", "5.2.5.12", id="dotted"),
        pytest.param("5.2.5 .12", "5.2.5.12", id="ocr-spacing"),
        pytest.param("5.2.1A.1.1.1", "5.2.1A.1.1.1", id="middle-suffix-a"),
        pytest.param("5.2.1B.1.2.3", "5.2.1B.1.2.3", id="middle-suffix-b"),
        pytest.param("12C", "12C", id="simple-suffix"),
    ],
)
def test_article_identifiers_are_complete(literal_number: str, number: str) -> None:
    body = f"Artículo {literal_number}: Objeto.\nContenido de prueba."
    _assert_contract(body, [(body, {**_ARTICLE_METADATA, "articulo": number})])


@pytest.mark.parametrize(
    "text",
    [
        pytest.param("Artículo 5.2.1\nContenido.", id="end-of-line"),
        pytest.param("Artículo 5.2.1", id="end-of-document"),
    ],
)
def test_identifier_at_line_or_document_end_is_not_truncated(text: str) -> None:
    _assert_contract(
        text,
        [
            (
                text,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "5.2.1",
                    "articulo_titulo": "",
                    "section_name": "Artículo 5.2.1",
                },
            )
        ],
    )


def test_unsupported_identifier_is_preserved_without_partial_article() -> None:
    text = "Artículo 5.2.1AB: Objeto.\nContenido de prueba."
    _assert_contract(text, [(text, _PREAMBLE_METADATA)])


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param("Artículo 79. Texto de una norma citada.", id="punctuated-reference"),
        pytest.param(
            "artículo 9º de la Ley 810 de 2003 que dice lo siguiente.", id="ordinal-reference"
        ),
    ],
)
def test_introductory_references_remain_in_preamble(reference: str) -> None:
    preamble = f"CONSIDERANDO\nNorma citada:\n{reference}\n## DECRETA:"
    article = "Artículo 1. Objeto.\nContenido propio."
    _assert_contract(
        f"{preamble}\n{article}",
        [
            (preamble, _PREAMBLE_METADATA),
            (article, {**_ARTICLE_METADATA, "section_index": 2}),
        ],
    )


@pytest.mark.parametrize(
    "reference",
    [
        pytest.param(
            "artículo 17 del Código de Procedimiento Administrativo y de lo Contencioso\nAdministrativo.",
            id="external-code",
        ),
        pytest.param("artículo 95 del Decreto 2150 de 1995.", id="external-decree"),
        pytest.param("artículo 9º de la Ley 810 de 2003.", id="ordinal-reference-in-body"),
    ],
)
def test_wrapped_references_remain_in_containing_article(reference: str) -> None:
    body = (
        "Artículo 1. Objeto.\nSe aplica lo establecido en el\n"
        f"{reference}\nContinuación del contenido."
    )
    _assert_contract(body, [(body, _ARTICLE_METADATA)])


def test_internal_reference_does_not_deduplicate_real_article() -> None:
    first = "Artículo 2.3.1. Solicitud.\nContenido de la solicitud."
    second = (
        "Artículo 2.3.5. Estudio.\nSe verificará lo dispuesto en el\n"
        "artículo 2.3.1 del presente reglamento y se remitirá el expediente.\nTexto posterior."
    )
    _assert_contract(
        f"{first}\n{second}",
        [
            (
                first,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "2.3.1",
                    "articulo_titulo": "Solicitud",
                    "section_name": "Solicitud",
                },
            ),
            (
                second,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "2.3.5",
                    "articulo_titulo": "Estudio",
                    "section_name": "Estudio",
                    "section_index": 2,
                },
            ),
        ],
    )


@pytest.mark.parametrize(
    ("heading", "number", "epigraphe"),
    [
        pytest.param(
            "Artículo 3. Del ámbito de aplicación.",
            "3",
            "Del ámbito de aplicación",
            id="del-period",
        ),
        pytest.param(
            "Artículo 3 Del ámbito de aplicación.", "3", "Del ámbito de aplicación", id="del-space"
        ),
        pytest.param(
            "Artículo 4 De los derechos de uso.", "4", "De los derechos de uso", id="de-los-space"
        ),
        pytest.param(
            "Articulo 3 Del ámbito de aplicación.", "3", "Del ámbito de aplicación", id="no-accent"
        ),
        pytest.param(
            "Artículo 3. Del Código aplicable.",
            "3",
            "Del Código aplicable",
            id="del-code-period",
        ),
    ],
)
def test_de_del_epigraphs_are_valid_headings(heading: str, number: str, epigraphe: str) -> None:
    body = f"{heading}\nTexto propio; se menciona el artículo 17 de otra norma inline."
    _assert_contract(
        body,
        [
            (
                body,
                {
                    **_ARTICLE_METADATA,
                    "articulo": number,
                    "articulo_titulo": epigraphe,
                    "section_name": epigraphe,
                },
            )
        ],
    )


def test_extract_without_enacting_marker_keeps_articles() -> None:
    first = "Artículo 33. Reglas.\nExtracto preparado."
    second = "Artículo 93. Condiciones.\nTexto propio."
    _assert_contract(
        f"{first}\n{second}",
        [
            (
                first,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "33",
                    "articulo_titulo": "Reglas",
                    "section_name": "Reglas",
                },
            ),
            (
                second,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "93",
                    "articulo_titulo": "Condiciones",
                    "section_name": "Condiciones",
                    "section_index": 2,
                },
            ),
        ],
    )


@pytest.mark.parametrize(
    ("preamble", "continuation", "first_index", "second_index"),
    [
        pytest.param("", "resuelve sobre la prefactibilidad.", 1, 2, id="prose"),
        pytest.param("", 'Se cita "DECRETA:" dentro del cuerpo.', 1, 2, id="inline-quote"),
        pytest.param("", '"DECRETA:"', 1, 2, id="standalone-quote"),
        pytest.param("", "DECRETA:", 1, 2, id="later-single-marker"),
        pytest.param("DECRETA:", "DECRETA:", 2, 3, id="multiple-markers"),
    ],
)
def test_non_introductory_markers_do_not_reclassify_articles(
    preamble: str, continuation: str, first_index: int, second_index: int
) -> None:
    first = f"Artículo 1. Objeto.\nTexto anterior.\n{continuation}\nTexto posterior."
    second = "Artículo 2. Final.\nTexto propio."
    text = f"{preamble}\n{first}\n{second}" if preamble else f"{first}\n{second}"
    expected: list[tuple[str, dict[str, Any]]] = []
    if preamble:
        expected.append((preamble, _PREAMBLE_METADATA))
    expected.extend(
        [
            (first, {**_ARTICLE_METADATA, "section_index": first_index}),
            (
                second,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "2",
                    "articulo_titulo": "Final",
                    "section_name": "Final",
                    "section_index": second_index,
                },
            ),
        ]
    )
    _assert_contract(text, expected)


@pytest.mark.parametrize(
    ("chapter", "title"),
    [
        pytest.param("## CAPÍTULO II", "## TÍTULO II", id="markdown"),
        pytest.param("**CAPÍTULO II**", "**TÍTULO II**", id="bold"),
        pytest.param("## **CAPÍTULO II**", "## **TÍTULO II**", id="combined"),
    ],
)
def test_formatted_hierarchy_updates_and_title_resets_chapter(chapter: str, title: str) -> None:
    preamble = "TÍTULO I\nCAPÍTULO I"
    first = f"Artículo 1. Primero.\nTexto A.\n{chapter}"
    second = f"Artículo 2. Segundo.\nTexto B.\n{title}"
    third = "Artículo 3. Tercero.\nTexto C."
    _assert_contract(
        f"{preamble}\n{first}\n{second}\n{third}",
        [
            (preamble, _PREAMBLE_METADATA),
            (
                first,
                {
                    **_ARTICLE_METADATA,
                    "articulo_titulo": "Primero",
                    "section_name": "Primero",
                    "titulo": "TÍTULO I",
                    "capitulo": "CAPÍTULO I",
                    "section_index": 2,
                },
            ),
            (
                second,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "2",
                    "articulo_titulo": "Segundo",
                    "section_name": "Segundo",
                    "titulo": "TÍTULO I",
                    "capitulo": "CAPÍTULO II",
                    "section_index": 3,
                },
            ),
            (
                third,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "3",
                    "articulo_titulo": "Tercero",
                    "section_name": "Tercero",
                    "titulo": "TÍTULO II",
                    "section_index": 4,
                },
            ),
        ],
    )


def test_heading_without_numeral_does_not_invent_hierarchy() -> None:
    preamble = "## CAPÍTULO"
    article = "Artículo 1. Objeto.\nTexto propio."
    _assert_contract(
        f"{preamble}\n{article}",
        [(preamble, _PREAMBLE_METADATA), (article, {**_ARTICLE_METADATA, "section_index": 2})],
    )


@pytest.mark.parametrize(
    ("body", "epigraphe", "section_name"),
    [
        pytest.param(
            "Artículo 1. Gestión del agua de\nlastre.\nTexto del cuerpo.",
            "Gestión del agua de lastre",
            "Gestión del agua de lastre",
            id="wrapped-title",
        ),
        pytest.param(
            "Artículo 1. Son obligaciones:\n\n1. Primera obligación.\n2. Segunda obligación.",
            "",
            "Artículo 1",
            id="enumeration",
        ),
        pytest.param(
            "Artículo 1. Obligaciones\n1. Primera obligación.\n2. Segunda obligación.",
            "",
            "Artículo 1",
            id="enumeration-without-blank-or-colon",
        ),
        pytest.param("Artículo 1. Son obligaciones:", "", "Artículo 1", id="colon-without-list"),
        pytest.param(
            "Artículo 1.\nTexto del cuerpo sin título explícito.",
            "",
            "Artículo 1",
            id="bare-period",
        ),
        pytest.param(
            "Artículo 1:\nTexto del cuerpo sin título explícito.", "", "Artículo 1", id="bare-colon"
        ),
        pytest.param(
            "Artículo 1. Gestión del agua de\n\nlastre.\nTexto del cuerpo.",
            "",
            "Artículo 1",
            id="paragraph-boundary",
        ),
    ],
)
def test_epigraphs_respect_structural_boundaries(
    body: str, epigraphe: str, section_name: str
) -> None:
    _assert_contract(
        body,
        [
            (
                body,
                {
                    **_ARTICLE_METADATA,
                    "articulo_titulo": epigraphe,
                    "section_name": section_name,
                },
            )
        ],
    )


def test_tables_links_and_images_are_preserved_literally() -> None:
    body = (
        "Artículo 1. Objeto.\n"
        "| Zona | Uso |\n| --- | --- |\n| A | Pesca |\n"
        "![Plano](images/1.png)\n"
        "[Referencia](http://example.invalid/norma)\n"
        "La referencia al artículo 17 está dentro de prosa."
    )
    _assert_contract(body, [(body, _ARTICLE_METADATA)])


def test_additive_text_keeps_numbers_without_certifying_legal_identity() -> None:
    preamble = "DECRETA:"
    first = "Artículo 1. Adición.\nSe incorpora el siguiente texto:"
    inserted = "Artículo 2.2.4.3.1. Objeto.\nContenido incorporado."
    last = "Artículo 2. Vigencia.\nContenido final."
    _assert_contract(
        f"{preamble}\n{first}\n{inserted}\n{last}",
        [
            (preamble, _PREAMBLE_METADATA),
            (
                first,
                {
                    **_ARTICLE_METADATA,
                    "articulo_titulo": "Adición",
                    "section_name": "Adición",
                    "section_index": 2,
                },
            ),
            (inserted, {**_ARTICLE_METADATA, "articulo": "2.2.4.3.1", "section_index": 3}),
            (
                last,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "2",
                    "articulo_titulo": "Vigencia",
                    "section_name": "Vigencia",
                    "section_index": 4,
                },
            ),
        ],
    )


def test_quoted_article_is_preserved_without_removing_quotes() -> None:
    body = (
        "Artículo 1. Objeto.\nSe incorpora el siguiente texto:\n"
        '"Artículo 16. Texto de otra disposición".\nTexto posterior.'
    )
    _assert_contract(body, [(body, _ARTICLE_METADATA)])


def test_annex_payload_is_preserved_without_certifying_ownership() -> None:
    article = "Artículo 1. Objeto.\nTexto propio."
    payload = "PARTE 4\nANEXOS\n| Zona | Uso |\n| --- | --- |\n| A | B |"
    text = f"{article}\n{payload}"
    doc = Document(page_content=text, metadata=deepcopy(_BASE_METADATA))
    saved = deepcopy(doc)

    sections = split_by_articles(doc)

    assert "\n".join(section.page_content for section in sections) == text
    assert sections[0].metadata == _ARTICLE_METADATA
    assert [section.metadata["section_index"] for section in sections] == list(
        range(1, len(sections) + 1)
    )
    assert all(
        {key: section.metadata[key] for key in _BASE_METADATA} == _BASE_METADATA
        for section in sections
    )
    assert sections == split_by_articles(doc)
    assert doc == saved


@pytest.mark.parametrize(
    ("context", "heading", "epigraphe", "chapter"),
    [
        pytest.param(
            "Texto completo.",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="code",
        ),
        pytest.param(
            "Texto completo.",
            "Artículo 3 Del Decreto 100 de 2020.",
            "Del Decreto 100 de 2020",
            "",
            id="decree",
        ),
        pytest.param(
            "Texto completo.",
            "Artículo 3 De la Ley 100 de 2020.",
            "De la Ley 100 de 2020",
            "",
            id="law",
        ),
        pytest.param(
            "Texto completo.",
            "Artículo 3 Del presente reglamento.",
            "Del presente reglamento",
            "",
            id="self",
        ),
        pytest.param(
            "Texto completo.",
            "Artículo 3. Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="punctuated",
        ),
        pytest.param(
            "La explicación anterior termina en el",
            "## Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="atx_after_open_prose",
        ),
        pytest.param(
            "La explicación anterior termina en el",
            "**Artículo 3** Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="bold_after_open_prose",
        ),
        pytest.param(
            "Texto sin punto final",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="no_sentence_end_without_signal",
        ),
        pytest.param(
            "Texto completo.\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n42",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="furniture_after_complete_prose",
        ),
        pytest.param(
            "Texto sin punto final\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n42",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="furniture_without_signal",
        ),
        pytest.param(
            "La explicación anterior termina en el\n\nINFORMACIÓN COMPLEMENTARIA",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="uppercase_label_only",
        ),
        pytest.param(
            "La explicación anterior termina en el\n\n42",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="page_number_only",
        ),
        pytest.param(
            "La explicación anterior termina en el\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n42",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="no_repeated_label",
        ),
        pytest.param(
            "La explicación anterior termina en el\n\n## CAPÍTULO II",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "CAPÍTULO II",
            id="hierarchy_not_furniture",
        ),
        pytest.param(
            "Texto completo.",
            "Artículo 3 Del ámbito de aplicación.",
            "Del ámbito de aplicación",
            "",
            id="generic_del_heading",
        ),
        pytest.param(
            "Texto completo.\n\n## Información del",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="generic_atx_context",
        ),
        pytest.param(
            "Texto completo.\n\n**Información** del",
            "Artículo 3 Del Código de Comercio.",
            "Del Código de Comercio",
            "",
            id="generic_bold_context",
        ),
    ],
)
def test_subsequent_normative_headings_keep_article_identity(
    context: str, heading: str, epigraphe: str, chapter: str
) -> None:
    first = f"Artículo 1. Objeto.\n{context}"
    second = f"{heading}\nTexto propio del artículo 3."
    _assert_contract(
        f"{first}\n\n{second}",
        [
            (first, _ARTICLE_METADATA),
            (
                second,
                {
                    **_ARTICLE_METADATA,
                    "articulo": "3",
                    "articulo_titulo": epigraphe,
                    "capitulo": chapter,
                    "section_index": 2,
                    "section_name": epigraphe,
                },
            ),
        ],
    )


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "Artículo 1. Objeto.\n"
            "Se aplica lo establecido en el literal d) del\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n42\n\n"
            "artículo 95 del Decreto 200 de 1999.\nContinuación del contenido.",
            id="furniture_reference",
        ),
        pytest.param(
            "Artículo 1. Objeto. Se aplica lo establecido en el\n"
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            id="inline_body_reference",
        ),
        pytest.param(
            "Artículo 1. Objeto. Se aplica lo establecido en el literal d) del\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n\n"
            "REGLAMENTO GENERAL\nPUBLICACIÓN NORMATIVA\n42\n\n"
            "artículo 95 del Decreto 200 de 1999.\nContinuación del contenido.",
            id="inline_body_furniture_reference",
        ),
    ],
)
def test_reference_with_page_furniture_remains_in_article(body: str) -> None:
    _assert_contract(body, [(body, _ARTICLE_METADATA)])


@pytest.mark.parametrize(
    ("first_body", "separator", "reference_body", "expected_reintegrate", "first_title"),
    [
        pytest.param(
            "Artículo 1. Referencia del",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia del",
            id="single_line_epigraph_del",
        ),
        pytest.param(
            "Artículo 1. Referencia\ndel",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia del",
            id="wrapped_epigraph_del",
        ),
        pytest.param(
            "Artículo 1. Referencia\ndel.",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia del",
            id="wrapped_epigraph_closed_del",
        ),
        pytest.param(
            "Artículo 1.\nSe aplica lo establecido del",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            True,
            "",
            id="body_after_bare_heading_del",
        ),
        pytest.param(
            "Artículo 1. Referencia en el",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia en el",
            id="single_line_epigraph_en_el",
        ),
        pytest.param(
            "Artículo 1. Referencia\nen el",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia en el",
            id="wrapped_epigraph_en_el",
        ),
        pytest.param(
            "Artículo 1. Referencia\nen el.",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia en el",
            id="wrapped_epigraph_closed_en_el",
        ),
        pytest.param(
            "Artículo 1.\nSe aplica lo establecido en el",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            True,
            "",
            id="body_after_bare_heading_en_el",
        ),
        pytest.param(
            "Artículo 1. Referencia\ndel\n\nAVISO TÉCNICO\nPUBLICACIÓN GENERAL\n\nAVISO TÉCNICO\nPUBLICACIÓN GENERAL\n63",
            "\n\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "",
            id="wrapped_epigraph_del_furniture",
        ),
        pytest.param(
            "Artículo 1. Referencia\nen el\n\nAVISO TÉCNICO\nPUBLICACIÓN GENERAL\n\nAVISO TÉCNICO\nPUBLICACIÓN GENERAL\n63",
            "\n\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "",
            id="wrapped_epigraph_en_el_furniture",
        ),
        pytest.param(
            "Artículo 1. Referencia\nmarítima. Se aplica lo establecido en el",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            True,
            "Referencia marítima",
            id="wrapped_closed_title_inline_body",
        ),
        pytest.param(
            "Artículo 1. Referencia\nmarítima.\nSe aplica lo establecido en el literal d) del\n\nAVISO TÉCNICO\nPUBLICACIÓN GENERAL\n\nAVISO TÉCNICO\nPUBLICACIÓN GENERAL\n63",
            "\n\n",
            "artículo 95 del Decreto 200 de 1999.\nContinuación del contenido.",
            True,
            "Referencia marítima",
            id="wrapped_closed_title_later_body_furniture",
        ),
        pytest.param(
            "## Artículo 1. Referencia\nmarítima. Se aplica lo establecido en el",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            True,
            "Referencia marítima",
            id="atx_wrapped_closed_title_inline_body",
        ),
        pytest.param(
            "**Artículo 1.** Referencia\nmarítima. Se aplica lo establecido en el",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            True,
            "Referencia marítima",
            id="bold_wrapped_closed_title_inline_body",
        ),
        pytest.param(
            "Artículo 1. Referencia marítima. **Descripción** del",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia marítima",
            id="single_line_formatted_body_bold",
        ),
        pytest.param(
            "Artículo 1. Referencia\nmarítima. **Descripción** del",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia marítima",
            id="wrapped_title_formatted_body_bold",
        ),
        pytest.param(
            "Artículo 1. Referencia marítima. ## Descripción del",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia marítima",
            id="single_line_formatted_body_atx",
        ),
        pytest.param(
            "Artículo 1. Referencia\nmarítima. ## Descripción del",
            "\n",
            "artículo 17 del Código de Comercio.\nContinuación del contenido.",
            False,
            "Referencia marítima",
            id="wrapped_title_formatted_body_atx",
        ),
    ],
)
def test_epigraph_context_keeps_reference_boundaries(
    first_body: str,
    separator: str,
    reference_body: str,
    expected_reintegrate: bool,
    first_title: str,
) -> None:
    text = first_body + separator + reference_body
    first_metadata: dict[str, Any] = {
        **_BASE_METADATA,
        "articulo": "1",
        "articulo_titulo": first_title,
        "titulo": "",
        "capitulo": "",
        "section_index": 1,
        "section_name": first_title or "Artículo 1",
    }
    expected: list[tuple[str, dict[str, Any]]] = [
        (text if expected_reintegrate else first_body, first_metadata),
    ]
    if not expected_reintegrate:
        expected.append(
            (
                reference_body,
                {
                    **_BASE_METADATA,
                    "articulo": "17",
                    "articulo_titulo": "del Código de Comercio",
                    "titulo": "",
                    "capitulo": "",
                    "section_index": 2,
                    "section_name": "del Código de Comercio",
                },
            )
        )
    _assert_contract(text, expected)
