"""Contratos sintéticos del seccionado, sin corpus local ni servicios externos."""

from copy import deepcopy

import pytest
from langchain_core.documents import Document

from ingest.sections import _strip_accents, classify_heading, normalize_heading, split_by_sections
from ingest.sections_normativa import split_by_articles

SECTION_NAMES = (
    "Contexto del caso",
    "Desarrollo procesal",
    "Análisis del tribunal",
    "Decisión",
)


def _document(text: str) -> Document:
    return Document(
        page_content=text,
        metadata={
            "source": "sentencia_de_prueba.md",
            "title": "Prueba",
            "doc_type": "jurisprudencia",
            "summary": "Resumen heredado sin reinterpretación.",
            "keywords": ["playas", "control"],
            "control": {"values": ["sin cambios"]},
        },
    )


def _assert_contract(original: Document, sections: list[Document]) -> None:
    assert len(sections) == 4
    for index, section in enumerate(sections, 1):
        assert section is not original
        assert section.metadata["section_index"] == index
        assert section.metadata["section_name"] == SECTION_NAMES[index - 1]
        assert "section_heading" in section.metadata
        assert section.metadata == {
            **original.metadata,
            "section_index": index,
            "section_name": SECTION_NAMES[index - 1],
            "section_heading": section.metadata["section_heading"],
        }


@pytest.mark.parametrize("template", ["{}", " II. {}: ", "5.2. {}"])
@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("Antecedentes", 1),
        ("Síntesis del caso", 1),
        ("Resumen de la demanda", 1),
        ("Petitum", 1),
        ("Causa petendi", 1),
        ("Contestación de la demanda", 2),
        ("Actuación procesal", 2),
        ("Actuaciones posteriores al fallo", 2),
        ("Trámite de la acción", 2),
        ("Trámite de la segunda instancia", 2),
        ("Trámite de segunda instancia", 2),
        ("Sentencia de primera instancia", 2),
        ("Fallo de primera instancia", 2),
        ("El recurso de apelación", 2),
        ("Recurso de apelación", 2),
        ("Alegatos de conclusión", 2),
        ("Consideraciones de la sala", 3),
        ("Consideraciones del tribunal", 3),
        ("Consideraciones", 3),
        ("Conclusiones", 4),
        ("Decisión", 4),
        ("Falla", 4),
        ("Resuelve", 4),
    ],
)
def test_known_continuous_headings_keep_their_category(
    heading: str, section: int, template: str
) -> None:
    assert classify_heading(template.format(heading)) == section


@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("IIII.- DECISIÓN", 4),
        ("3.5. Conclusiones", 4),
        ("III. RESUELVE:", 4),
        ("FALLA:", 4),
        ("IVISION", None),
        ("Consideraciones y fundamentos", 3),
        ("Antecedentes expuestos en la consulta", 1),
    ],
)
def test_existing_lexical_forms_are_preserved(heading: str, section: int | None) -> None:
    assert classify_heading(heading) == section


@pytest.mark.parametrize(
    ("heading", "normalized", "section"),
    [
        ("F A L L A:", "falla", 4),
        ("F  A  L  L  A", "falla", 4),
        ("f a l l a", "falla", 4),
        ("F\tA\tL\tL\tA", "falla", 4),
        ("F\u00a0A\u00a0L\u00a0L\u00a0A:", "falla", 4),
        ("III. F A L L A", "falla", 4),
        ("I.2. F A L L A", "falla", 4),
        ("R E S U E L V E", "resuelve", 4),
        ("IV. r e s u e l v e:", "resuelve", 4),
        ("C O N S I D E R A C I O N E S", "consideraciones", 3),
        ("C O N S I D E R A C I O N E S:", "consideraciones", 3),
        ("IV. C O N S I D E R A C I O N E S", "consideraciones", 3),
        ("2. c o n s i d e r a c i o n e s", "consideraciones", 3),
        ("D E C I S I Ó N", "decision", 4),
        ("IV. D E C I S I O\u0301 N:", "decision", 4),
        ("CONSIDERACION ES Y FUNDAMENTOS", "consideraciones y fundamentos", 3),
        ("II. CONSIDERACION ES Y FUNDAMENTOS:", "consideraciones y fundamentos", 3),
        ("CONSIDERACION ES DEL TRIBUNAL", "consideraciones del tribunal", 3),
    ],
)
def test_complete_known_headings_recover_internal_spacing(
    heading: str, normalized: str, section: int
) -> None:
    assert normalize_heading(heading) == normalized
    assert classify_heading(heading) == section


@pytest.mark.parametrize(
    ("heading", "normalized", "section"),
    [
        ("I.2. Actuación procesal", "actuacion procesal", 2),
        ("I.2. Actuación procesal posterior", "actuacion procesal posterior", 2),
        ("I. II. Consideraciones", "consideraciones", 3),
        ("10. V. Consideraciones", "consideraciones", 3),
        ("IV. 1. Antecedentes", "antecedentes", 1),
        ("1.2.3. Actuación procesal", "actuacion procesal", 2),
    ],
)
def test_mixed_or_repeated_enumeration_reaches_the_existing_heading(
    heading: str, normalized: str, section: int
) -> None:
    assert normalize_heading(heading) == normalized
    assert classify_heading(heading) == section


@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("III. F A L L A:", 4),
        ("II. C O N S I D E R A C I O N E S", 3),
        ("I.2. Actuación procesal...", 2),
    ],
)
def test_recovered_headings_keep_original_heading_body_and_metadata(
    heading: str, section: int
) -> None:
    preamble = "Nota previa."
    block = f"## {heading}\nProsa íntegra.\n![costa](<assets/costa á(1).png>)"
    doc = _document(f"{preamble}\n\n{block}")
    saved = deepcopy(doc)
    sections = split_by_sections(doc)
    expected = [preamble, "", "", ""]
    expected[section - 1] = block

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == expected
    assert sections[section - 1].metadata["section_heading"] == heading
    assert doc == saved
    assert sections == split_by_sections(doc)


@pytest.mark.parametrize(
    "heading",
    [
        "Consideración es otra cosa",
        "C O S T A",
        "C O N S I D E R A C I O N E S acerca de otro asunto",
        "SÍNTESISDELCASO",
        "CON SIDERACIONESDELTRIBUNAL",
        "CAUSAPETENDI",
        "I.2. ' F A L L A:",
        "I. II. > RESUELVE",
        "IV. “C O N S I D E R A C I O N E S”",
        "La prueba contiene conclusiones y la autoridad resuelve después",
        "Puntualmente las conclusiones del estudio fueron relevantes",
        "Posición de la parte demandada",
        "El trámite de primera instancia",
        "La actuación de segunda instancia",
        "Trámite en segunda instancia",
        "b.-La oposición",
        "FUNDAMENTOS DEL RECURSO DE APELACION",
        "LA SALA CONSIDERA",
        "LA SALA RESPONDE",
        "Con fundamento en lo anterior, la Sala responde:",
    ],
)
def test_unknown_headings_and_unapproved_aliases_remain_unknown(heading: str) -> None:
    assert classify_heading(heading) is None


@pytest.mark.parametrize("prefix", ["", "IV. "])
@pytest.mark.parametrize("marker", ["'", '"', "‘", "’", "“", "”", ">"])
@pytest.mark.parametrize("title", ["FALLA:", "CONSIDERACIONES", "TRÁMITE DE LA ACCIÓN"])
def test_explicit_quote_markers_do_not_activate_sections(
    prefix: str, marker: str, title: str
) -> None:
    heading = f"{prefix}{marker} {title}"
    assert classify_heading(heading) is None


@pytest.mark.parametrize(
    "heading",
    [
        "' FALLA:",
        "'. CONCLUSIONES",
        "IV. “DECISIÓN”",
        "> CONSIDERACIONES",
        "I.2. ' F A L L A:",
        "I. II. > RESUELVE",
        "IV. “C O N S I D E R A C I O N E S”",
    ],
)
def test_quoted_blocks_are_inherited_without_losing_text(heading: str) -> None:
    first = "## Antecedentes\nHechos."
    analysis = "## Consideraciones\nAnálisis."
    quoted = f"## {heading}\nTexto citado íntegro."
    doc = _document("\n\n".join([first, analysis, quoted]))
    saved = deepcopy(doc)
    sections = split_by_sections(doc)

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == [first, "", f"{analysis}\n\n{quoted}", ""]
    assert doc == saved


@pytest.mark.parametrize(
    "heading",
    [
        "3. Decisión de instancia [16].",
        "Decisiones anteriores",
        "Fallas de la prueba",
        "Conclusiones del informe",
        "Decisión final",
        "Falla la petición de la parte por falta de sustento.",
        "Resuelve una cuestión probatoria",
        "DECISIÓN [12]",
        "RESUELVE12",
        "AntecedentesX",
        "PetitumX",
        "ConsideracionesX",
        "Trámite de la acciónX",
    ],
)
def test_generic_keywords_do_not_accept_other_words_or_decision_suffixes(heading: str) -> None:
    assert classify_heading(heading) is None


@pytest.mark.parametrize(
    ("numeral", "body", "section", "section_heading"),
    [
        ("IV.", "CONSIDERACIONES DEL TRIBUNAL\nAnálisis.", 3, "CONSIDERACIONES DEL TRIBUNAL"),
        ("IV.", "F A L L A:\nOrden.", 4, "F A L L A:"),
        ("IV.", "Falla la petición de la parte por falta de sustento.", None, ""),
        ("IV.", "> FALLA:\nTexto citado.", None, ""),
        ("...", "FALLA:\nOrden citada.", None, ""),
        ("IV.", "' FALLA:\nTexto citado.", None, ""),
        ("I.2.", "' F A L L A:\nTexto citado.", None, ""),
        ("IV.", "I. II. > RESUELVE\nTexto citado.", None, ""),
        ("IV.", "“C O N S I D E R A C I O N E S”\nTexto citado.", None, ""),
        ("I.2.", "Actuación procesal\nTrámite.", 2, "Actuación procesal"),
        ("C.", "CONTESTACION DE LA DEMANDA\nContestación.", 2, "CONTESTACION DE LA DEMANDA"),
        ("IIII.-", "DECISIÓN\nOrden.", 4, "DECISIÓN"),
        ("IV.", "Rótulo desconocido\nFALLA:\nTexto posterior.", None, ""),
        ("IV.", "\n# Línea excluida\nFALLA:\nOrden.", 4, "FALLA:"),
        ("IV.", "  # Primera línea elegible desconocida\nFALLA:", None, ""),
        ("' IV.", "FALLA:\nTexto citado.", None, ""),
    ],
)
def test_continuation_requires_an_enum_and_a_recognized_first_candidate(
    numeral: str, body: str, section: int | None, section_heading: str
) -> None:
    first = "## Antecedentes\nHechos."
    block = f"## {numeral}\n{body}"
    doc = _document(f"{first}\n\n{block}")
    saved = deepcopy(doc)
    sections = split_by_sections(doc)
    expected = [first, "", "", ""]
    if section is None:
        expected[0] = f"{first}\n\n{block.strip()}"
    else:
        expected[section - 1] = block.strip()
        assert sections[section - 1].metadata["section_heading"] == section_heading

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == expected
    assert doc == saved


@pytest.mark.parametrize(
    ("heading", "section"),
    [
        ("SÍNTESIS DEL CASO.1. ", 1),
        ("ACTUACIONES POSTERIORES AL FALLO.1. ", 2),
        ("CONSIDERACIONES DEL TRIBUNAL. ", 3),
    ],
)
def test_valid_long_prefix_headings_are_not_rejected(heading: str, section: int) -> None:
    long_heading = heading + "Prosa sintética que acompaña al título. " * 40
    block = f"## IV.\n{long_heading}\nContenido del bloque."
    doc = _document(block)
    sections = split_by_sections(doc)

    assert len(long_heading) > 1241
    assert classify_heading(long_heading) == section
    _assert_contract(doc, sections)
    assert sections[section - 1].page_content == block.strip()
    assert sections[section - 1].metadata["section_heading"] == long_heading.strip()
    assert all(not s.page_content for i, s in enumerate(sections, 1) if i != section)


@pytest.mark.parametrize("text", ["", " \t\n", "Texto sin encabezados.", "## \nFALLA:", "# Falla"])
def test_empty_or_headingless_input_keeps_four_documents(text: str) -> None:
    doc = _document(text)
    saved = deepcopy(doc)
    sections = split_by_sections(doc)

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == [text.strip(), "", "", ""]
    assert all(s.metadata["section_heading"] == "" for s in sections)
    assert doc == saved


def test_blocks_keep_preamble_multiplicity_order_and_first_heading() -> None:
    preamble = "  Preámbulo íntegro.  "
    repeated = "## Etiqueta desconocida\nMismo bloque repetido."
    blocks = [
        (1, "## Antecedentes\nHechos iniciales."),
        (1, "## Rótulo no previsto\nDetalle desconocido."),
        (3, "## II. Consideraciones\nPrimer análisis."),
        (3, repeated),
        (4, "## Falla:\nOrden completa."),
        (3, "## Consideraciones del tribunal\nSegundo análisis."),
        (3, repeated),
        (1, "## Antecedentes\nHechos posteriores."),
    ]
    text = preamble + "\n\n" + "\n\n".join(block for _, block in blocks)
    doc = _document(text)
    saved = deepcopy(doc)
    sections = split_by_sections(doc)
    expected = []
    for category in range(1, 5):
        parts = [preamble.strip()] if category == 1 else []
        parts.extend(block for section, block in blocks if section == category)
        expected.append("\n\n".join(parts))

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == expected
    assert sections[2].page_content.count(repeated) == 2
    assert [s.metadata["section_heading"] for s in sections] == [
        "Antecedentes",
        "",
        "II. Consideraciones",
        "Falla:",
    ]
    assert doc == saved
    assert sections == split_by_sections(doc)


@pytest.mark.parametrize(
    "image",
    [
        "![plano](assets/mapa.png)",
        "![plano](assets/mapa con espacios.png)",
        "![plano](assets/mapa%20costero.png)",
        "![plano](assets/mapa(1).png)",
        "![plano](<assets/mapa costero.png>)",
        "![plano](../fuente/assets/costa_á.png)",
    ],
)
def test_image_destinations_and_body_unicode_are_literal(image: str) -> None:
    first = f"## Antecedentes\nProsa: acción, Ñ, % y paréntesis (originales).\n{image}"
    second = "## Falla\nOrden sin cambios."
    doc = _document(f"{first}\n\n{second}")
    saved = deepcopy(doc)
    sections = split_by_sections(doc)

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == [first, "", "", second]
    assert doc == saved


def test_unknown_headings_inherit_context_without_becoming_section_heading() -> None:
    text = "Preámbulo.\n\n## Rótulo desconocido\nContenido.\n\n## Otro rótulo\nOtro contenido."
    doc = _document(text)
    sections = split_by_sections(doc)

    _assert_contract(doc, sections)
    assert [s.page_content for s in sections] == [text, "", "", ""]
    assert all(s.metadata["section_heading"] == "" for s in sections)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", ""),
        ("ÁÉÍÓÚ ü Ñ", "AEIOU u N"),
        ("CONSIDERACIO\u0301NES", "CONSIDERACIONES"),
        ("SÍNTESIS DEL CASO", "SINTESIS DEL CASO"),
    ],
)
def test_shared_accent_helper_keeps_its_existing_behavior(text: str, expected: str) -> None:
    assert _strip_accents(text) == expected


def test_normativa_keeps_the_captured_synthetic_article_contract() -> None:
    text = (
        "Preámbulo de prueba.\nDECRETA\nTÍTULO I\nCAPÍTULO I\nArtículo 1. Objeto.\n"
        "Contenido primero.\nArtículo 2. Definiciones.\nContenido segundo."
    )
    metadata = {"source": "fixture.md", "doc_type": "normativa", "title": "Prueba"}
    doc = Document(page_content=text, metadata=metadata)
    saved = deepcopy(doc)
    units = split_by_articles(doc)
    expected = [
        (
            "Preámbulo de prueba.\nDECRETA\nTÍTULO I\nCAPÍTULO I",
            {
                **metadata,
                "articulo": None,
                "articulo_titulo": "",
                "titulo": "",
                "capitulo": "",
                "section_index": 1,
                "section_name": "Preámbulo",
            },
        ),
        (
            "Artículo 1. Objeto.\nContenido primero.",
            {
                **metadata,
                "articulo": "1",
                "articulo_titulo": "Objeto",
                "titulo": "TÍTULO I",
                "capitulo": "CAPÍTULO I",
                "section_index": 2,
                "section_name": "Objeto",
            },
        ),
        (
            "Artículo 2. Definiciones.\nContenido segundo.",
            {
                **metadata,
                "articulo": "2",
                "articulo_titulo": "Definiciones",
                "titulo": "TÍTULO I",
                "capitulo": "CAPÍTULO I",
                "section_index": 3,
                "section_name": "Definiciones",
            },
        ),
    ]

    assert [(u.page_content, u.metadata) for u in units] == expected
    assert doc == saved
    assert units == split_by_articles(doc)
