"""Contratos sintéticos del contexto de tablas; no corpus, red, LLM ni ingesta.

Las aserciones CT_CONTEXT/CT_LAYOUT/CT_DIAGNOSTIC verifican el contexto
literal, la distribución de filas y los diagnósticos, junto con los contratos
de compatibilidad de la fragmentación.
"""

import logging
from copy import deepcopy

import pytest
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ingest.sections_normativa import split_by_articles
from ingest.splitter_and_enrich import _build_splitter, _chunk_section

HEADER = "| Clave | Valor |"
SEPARATOR = "| --- | --- |"
SIZE = 220
OVERLAP = 40


def _document(text: str, *, doc_type: str | None = "normativa", index: int = 3) -> Document:
    metadata = {
        "source": "fixture.md",
        "title": "Documento sintético",
        "section_index": index,
        "articulo": "7",
        "nested": {"literal": ["conservar", 17]},
    }
    if doc_type is not None:
        metadata["doc_type"] = doc_type
    return Document(page_content=text, metadata=metadata)


def _rows(label: str, count: int = 18) -> list[str]:
    return [f"| {label}-{i:02d} | valor-{i:02d} " + "x" * 20 + " |" for i in range(count)]


def _table(rows: list[str], header: str = HEADER, separator: str = SEPARATOR) -> str:
    return "\n".join([header, separator, *rows])


def _padding() -> str:
    return "\n".join(["Prosa de control sin tablas."] * 30)


def _assert_legacy(doc: Document, splitter: RecursiveCharacterTextSplitter) -> None:
    """Oráculo: splitter existente y expectativas de identidad del fixture."""
    before = deepcopy(doc)
    expected = splitter.split_documents([doc])
    actual = _chunk_section(doc, splitter)
    assert [d.page_content for d in actual] == [d.page_content for d in expected], (
        "CONTRACT: cambió la ruta anterior"
    )
    assert doc == before, "CONTRACT: se mutó la entrada"
    prefix = f"fixture_s{doc.metadata['section_index']}"
    if doc.metadata.get("doc_type") == "normativa":
        prefix += "_art7"
    for i, chunk in enumerate(actual):
        assert chunk.metadata == {
            **before.metadata,
            "chunk_index": i,
            "chunk_id": f"{prefix}_c{i}",
            "total_chunks_in_section": len(actual),
        }, "CONTRACT: cambió metadata o IDs de compatibilidad"


def _assert_bounds(chunks: list[Document], size: int) -> None:
    assert all(0 < len(c.page_content) <= size for c in chunks), (
        "CT_LAYOUT: fragmento vacío o fuera del presupuesto"
    )


def _assert_table_context(
    chunks: list[Document],
    rows: list[str],
    *,
    prefix: str = "",
    header: str = HEADER,
    separator: str = SEPARATOR,
) -> None:
    """Oráculo literal para fixtures conocidos, no detector productivo."""
    observed = []
    for chunk in chunks:
        lines = [line for line in chunk.page_content.splitlines() if line.startswith("|")]
        if not lines:
            continue
        assert lines[:2] == [header, separator], "CT_CONTEXT: faltan columnas o separador"
        if prefix:
            assert prefix in chunk.page_content, "CT_CONTEXT: falta el prefijo literal"
            assert chunk.page_content.index(prefix) < chunk.page_content.index(header), (
                "CT_CONTEXT: prefijo posterior a sus datos"
            )
        observed.extend(lines[2:])
    assert observed == rows, "CT_LAYOUT: filas alteradas, partidas, perdidas o duplicadas"


@pytest.mark.parametrize("doc_type", ["normativa", "jurisprudencia", None])
@pytest.mark.parametrize("text", ["", " \n\t ", "Texto sin tabla. " * 80])
def test_ct01_non_table_and_empty_inputs_keep_legacy(doc_type, text):
    _assert_legacy(_document(text, doc_type=doc_type), _build_splitter(SIZE, OVERLAP))


@pytest.mark.parametrize("doc_type", ["jurisprudencia", None])
def test_ct01_tables_outside_normativa_keep_legacy(doc_type):
    _assert_legacy(
        _document(_table(_rows("dato")), doc_type=doc_type), _build_splitter(SIZE, OVERLAP)
    )


@pytest.mark.parametrize("two_tables", [False, True])
def test_ct02_complete_small_section_keeps_legacy(two_tables):
    text = "### UNO\n\n" + _table(["| A | 1 |"])
    if two_tables:
        text += "\n\n### DOS\n\n| Sector | Medida |\n| --- | --- |\n| B | 2 |"
    assert len(text) < 1000, "FIXTURE: no es una sección pequeña"
    _assert_legacy(_document(text), _build_splitter(1000, 200))


@pytest.mark.parametrize("size,overlap", [(SIZE, OVERLAP), (1000, 200)])
def test_ct03_rows_keep_columns(size, overlap):
    rows = _rows("dato", 45)
    text = _table(rows)
    assert len(text) > size, "FIXTURE: no activa fragmentación"
    chunks = _chunk_section(_document(text), _build_splitter(size, overlap))
    _assert_bounds(chunks, size)
    _assert_table_context(chunks, rows)


@pytest.mark.parametrize("level", [1, 3, 6])
def test_ct04_continuations_keep_literal_caption_and_paragraphs(level):
    prefix = "#" * level + " MATRIZ ALFA\n\nLocalización literal de prueba.\n\nDatos generales\n\n"
    rows = _rows("alfa")
    chunks = _chunk_section(_document(prefix + _table(rows)), _build_splitter(SIZE, OVERLAP))
    _assert_bounds(chunks, SIZE)
    _assert_table_context(chunks, rows, prefix=prefix)


@pytest.mark.parametrize("same_columns", [False, True])
def test_ct05_ct06_tables_are_partitioned_with_repeated_rows(same_columns):
    prefixes = ["### MATRIZ UNO\n\n", "### MATRIZ DOS\n\n"]
    headers = [HEADER, HEADER if same_columns else "| Sector | Medida |"]
    # Repetir una fila dentro de cada matriz y entre ambas: no usar sets como oráculo.
    rows = [_rows("comun", 10), _rows("comun", 10)]
    rows[0].insert(4, rows[0][2])
    rows[1].insert(7, rows[1][2])
    text = "\n\n".join(prefixes[i] + _table(rows[i], headers[i]) for i in range(2))
    assert len(text) > SIZE, "FIXTURE: no activa la nueva ruta"
    chunks = _chunk_section(_document(text), _build_splitter(SIZE, OVERLAP))
    observed = [[], []]
    for chunk in chunks:
        lines = [line for line in chunk.page_content.splitlines() if line.startswith("|")]
        if not lines:
            continue
        owners = [i for i, prefix in enumerate(prefixes) if prefix in chunk.page_content]
        assert len(owners) == 1, "CT_CONTEXT: matriz sin identidad o con identidades cruzadas"
        owner = owners[0]
        assert lines[:2] == [headers[owner], SEPARATOR], "CT_CONTEXT: columnas equivocadas"
        observed[owner].extend(lines[2:])
    assert observed == rows, "CT_LAYOUT: cambió orden o multiplicidad entre matrices"
    _assert_bounds(chunks, SIZE)


def test_ct07_notes_and_plain_label_are_preserved():
    phrases = ["NOTA previa literal.", "Rótulo de prosa", "NOTA posterior literal."]
    rows = _rows("dato")
    text = phrases[0] + "\n\n" + phrases[1] + "\n\n" + _table(rows) + "\n\n" + phrases[2]
    chunks = _chunk_section(_document(text), _build_splitter(SIZE, OVERLAP))
    for phrase in phrases:
        assert any(phrase in c.page_content for c in chunks), "CONTRACT: se perdió prosa literal"


def test_ct07_second_table_does_not_inherit_previous_caption():
    first_prefix = "### TITULO DE LA PRIMERA\n\n"
    second_header = "| Sector | Medida |"
    second_rows = _rows("segundo")
    text = (
        first_prefix
        + _table(_rows("primero"))
        + "\n\nNota intermedia.\n\n"
        + _table(second_rows, second_header)
    )
    chunks = _chunk_section(_document(text), _build_splitter(SIZE, OVERLAP))
    touches = [chunk for chunk in chunks if any(row in chunk.page_content for row in second_rows)]
    assert touches, "CT_LAYOUT: no se conservan las filas de la segunda tabla"
    for chunk in touches:
        assert second_header in chunk.page_content, "CT_CONTEXT: faltan columnas de la segunda"
        assert first_prefix not in chunk.page_content, "CT_CONTEXT: se heredó otro rótulo"


def test_ct08_table_unit_fits_exactly_inside_budget():
    row = "| dato | " + "x" * 45 + " |"
    table = _table([row])
    size = len(table)
    text = table + "\n\n" + _padding()
    assert len(text) > size, "FIXTURE: no distingue sección y unidad"
    chunks = _chunk_section(_document(text), _build_splitter(size, 0))
    _assert_bounds(chunks, size)
    _assert_table_context(chunks, [row])


def test_ct08_one_character_over_table_budget_keeps_legacy():
    table = _table(["| dato | " + "x" * 45 + " |"])
    _assert_legacy(_document(table + "\n\n" + _padding()), _build_splitter(len(table) - 1, 0))


def _rejected_candidate(kind: str) -> str:
    short = ["| A | uno |", "| B | dos |"]
    if kind == "long-row":
        table = _table([short[0], "| larga | " + "x" * 600 + " |", short[1]])
    elif kind == "long-header":
        table = _table(short, "| Clave | " + "x" * 400 + " |")
    elif kind == "long-prefix":
        table = "### " + "x" * 400 + "\n\n" + _table(short)
    elif kind == "columns":
        table = _table([*short, "| C | tres | extra |"])
    elif kind == "missing-bar":
        table = _table([*short, "| C | tres"])
    elif kind == "indented-row":
        table = _table([*short, "  | C | tres |"])
    elif kind == "empty":
        table = HEADER + "\n" + SEPARATOR
    elif kind == "escaped-bar":
        table = _table([*short, r"| C | tres\|cuatro |"])
    elif kind == "inline-code":
        table = _table([*short, "| C | `tres` |"])
    elif kind == "adjacent":
        table = _table(short) + "\n| Sector | Medida |\n" + SEPARATOR + "\n| Z | otro |"
    elif kind == "separator-in-data":
        table = _table([short[0], SEPARATOR, short[1]])
    else:
        raise AssertionError("FIXTURE: caso de rechazo desconocido")
    return table + "\n\n" + _padding()


@pytest.mark.parametrize(
    "kind",
    [
        "long-row",
        "long-header",
        "long-prefix",
        "columns",
        "missing-bar",
        "indented-row",
        "empty",
        "escaped-bar",
        "inline-code",
        "adjacent",
        "separator-in-data",
    ],
)
def test_ct09_ct10_ct11_rejected_sections_keep_legacy(kind):
    text = _rejected_candidate(kind)
    assert len(text) > SIZE, "FIXTURE: sección de rechazo insuficiente"
    _assert_legacy(_document(text), _build_splitter(SIZE, OVERLAP))


@pytest.mark.parametrize("kind", ["long-row", "adjacent"])
def test_ct09_ct11_rejection_emits_one_bounded_warning(kind, caplog):
    doc = _document(_rejected_candidate(kind))
    with caplog.at_level(logging.WARNING, logger="ingest.splitter_and_enrich"):
        _chunk_section(doc, _build_splitter(SIZE, OVERLAP))
    records = [
        record
        for record in caplog.records
        if record.name == "ingest.splitter_and_enrich" and record.levelno >= logging.WARNING
    ]
    assert len(records) == 1, "CT_DIAGNOSTIC: falta el único aviso de rechazo"
    message = records[0].getMessage()
    assert "fixture.md" in message and "3" in message, "CT_DIAGNOSTIC: falta fuente/sección"
    assert doc.page_content not in message, "CT_DIAGNOSTIC: el log contiene el texto completo"


@pytest.mark.parametrize(
    "form", ["backticks", "tildes", "unclosed", "indented", "blockquote", "list", "one-space"]
)
def test_ct12_ct13_table_like_blocks_outside_grammar_keep_legacy(form):
    table = _table(_rows("codigo"))
    if form == "backticks":
        text = "`" * 4 + "text\n" + table + "\n" + "`" * 4
    elif form == "tildes":
        text = "~~~~text\n" + table + "\n~~~~"
    elif form == "unclosed":
        text = "`" * 4 + "text\n" + table + "\n```\n" + _padding()
    elif form == "indented":
        text = "\n".join("    " + line for line in table.splitlines())
    elif form == "blockquote":
        text = "\n".join("> " + line for line in table.splitlines())
    elif form == "list":
        text = "- Ejemplo\n" + "\n".join("  " + line for line in table.splitlines())
    else:
        text = "\n".join(" " + line for line in table.splitlines())
    _assert_legacy(_document(text), _build_splitter(SIZE, OVERLAP))


def test_ct13_pipe_prose_and_inline_code_keep_legacy():
    text = "Expresión A | B. Código `A | B` sin tabla.\n" * 30
    _assert_legacy(_document(text), _build_splitter(SIZE, OVERLAP))


@pytest.mark.parametrize("form", ["backticks", "tildes", "indented"])
def test_ct12_real_table_after_code_keeps_its_own_context(form):
    code = _table(["| falso | literal |"]) + "\n### TITULO FALSO\n"
    if form == "backticks":
        # El cierre más corto y de otra familia no cierran la cerca de cuatro.
        code = "`" * 4 + "text\n" + code + "`" * 3 + "\n~~~~\n" + "`" * 4
    elif form == "tildes":
        code = "~~~~text\n" + code + "~~~\n" + "`" * 4 + "\n~~~~"
    else:
        code = "\n".join("    " + line for line in code.splitlines())
    prefix = "### MATRIZ REAL\n\n"
    rows = _rows("real")
    text = code + "\n\n" + prefix + _table(rows)
    chunks = _chunk_section(_document(text), _build_splitter(SIZE, OVERLAP))
    selected = [c for c in chunks if any(row in c.page_content for row in rows)]
    _assert_table_context(selected, rows, prefix=prefix)
    assert all("TITULO FALSO" not in c.page_content for c in selected), (
        "CT_CONTEXT: se atribuyó un rótulo de código"
    )
    _assert_bounds(chunks, SIZE)


@pytest.mark.parametrize("newline", ["\n", "\r\n"], ids=["LF", "CRLF"])
def test_ct14_unicode_empty_cells_and_literal_values_keep_context(newline):
    rows = [
        f"| zona-{i:02d} | 1,25 %  Á  A\u0301  <br> W |" if i % 2 else f"| zona-{i:02d} |  |"
        for i in range(20)
    ]
    text = _table(rows).replace("\n", newline)
    chunks = _chunk_section(_document(text), _build_splitter(SIZE, OVERLAP))
    _assert_table_context(chunks, rows)
    _assert_bounds(chunks, SIZE)


def test_ct15_metadata_ids_and_inputs_are_preserved_deterministically():
    doc = _document(_table(_rows("dato")))
    before = deepcopy(doc)
    splitter = _build_splitter(SIZE, OVERLAP)
    first = _chunk_section(doc, splitter)
    assert first == _chunk_section(doc, splitter), "CONTRACT: salida no determinista"
    assert doc == before, "CONTRACT: se mutó entrada o metadata anidada"
    for i, chunk in enumerate(first):
        assert chunk.metadata == {
            **before.metadata,
            "chunk_index": i,
            "chunk_id": f"fixture_s3_art7_c{i}",
            "total_chunks_in_section": len(first),
        }, "CONTRACT: metadata o IDs inesperados"
    other = _chunk_section(_document(doc.page_content, index=4), splitter)
    assert not (
        {c.metadata["chunk_id"] for c in first} & {c.metadata["chunk_id"] for c in other}
    ), "CONTRACT: IDs cruzados entre secciones"


def test_ct16_parser_sections_feed_chunks_without_changing_parser_contract():
    text = (
        "Consideraciones de prueba.\n\nDECRETA\n\nArtículo 1. Objeto.\n"
        + _table(_rows("dato"))
        + "\n\nArtículo 2. Cierre.\nFin."
    )
    original = _document(text)
    before = deepcopy(original)
    sections = split_by_articles(original)
    frozen = deepcopy(sections)
    assert [s.metadata["articulo"] for s in sections] == [None, "1", "2"], (
        "CONTRACT: límites del parser inesperados"
    )
    all_ids = []
    for section in sections:
        chunks = _chunk_section(section, _build_splitter(SIZE, OVERLAP))
        for i, chunk in enumerate(chunks):
            assert all(chunk.metadata[k] == v for k, v in section.metadata.items()), (
                "CONTRACT: cambió la metadata del parser"
            )
            assert chunk.metadata["chunk_index"] == i
            assert chunk.metadata["total_chunks_in_section"] == len(chunks)
            all_ids.append(chunk.metadata["chunk_id"])
    assert len(all_ids) == len(set(all_ids)), "CONTRACT: colisión de IDs"
    assert original == before and sections == frozen, "CONTRACT: se mutó el seccionado"


def test_ct17_non_character_measure_keeps_legacy():
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=30,
        chunk_overlap=5,
        length_function=lambda value: len(value.split()),
        separators=["\n\n", "\n", ".", " ", ""],
    )
    _assert_legacy(_document(_table(_rows("dato"))), splitter)
