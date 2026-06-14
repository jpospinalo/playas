# tests/unit/test_splitter_doctype.py
"""Pruebas de chunk_id type-aware en _chunk_section (sin red ni LLM)."""

from langchain_core.documents import Document

from ingest.splitter_and_enrich import _build_splitter, _chunk_section


def test_chunk_id_normativa_usa_articulo():
    doc = Document(
        page_content="Articulo 2. Definiciones para el dominio publico maritimo-terrestre.",
        metadata={
            "source": "decreto-2324-de-1984.md",
            "doc_type": "normativa",
            "articulo": "2",
            "section_index": 3,
        },
    )
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    chunks = _chunk_section(doc, splitter)

    assert chunks
    for chunk in chunks:
        assert chunk.metadata["chunk_id"].startswith("decreto-2324-de-1984_s3_art2_c")
        # doc_type debe seguir presente en la metadata del chunk
        assert chunk.metadata["doc_type"] == "normativa"


def test_chunk_id_jurisprudencia_usa_section_index():
    doc = Document(
        page_content="Sentencia de prueba. Fundamentos juridicos para validacion.",
        metadata={
            "source": "fallo_2024.md",
            "section_index": 1,
        },
    )
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    chunks = _chunk_section(doc, splitter)

    assert chunks
    for chunk in chunks:
        assert chunk.metadata["chunk_id"].startswith("fallo_2024_s1_c")


def test_chunk_id_normativa_sin_articulo_cae_en_section_index():
    # El preámbulo de una norma (sin articulo) usa el esquema por section_index.
    doc = Document(
        page_content="Preambulo del decreto, considerandos generales.",
        metadata={
            "source": "decreto-2324-de-1984.md",
            "doc_type": "normativa",
            "section_index": 0,
        },
    )
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    chunks = _chunk_section(doc, splitter)

    assert chunks
    for chunk in chunks:
        assert chunk.metadata["chunk_id"].startswith("decreto-2324-de-1984_s0_c")


def test_chunk_id_normativa_mismo_articulo_distinta_seccion_es_unico():
    # Regresión: dos secciones que comparten el mismo número de artículo
    # (p.ej. sub-ítems "A"/"B" del art. 5.2 del REMAC) deben producir
    # chunk_ids distintos gracias al section_index en el prefijo.
    splitter = _build_splitter(chunk_size=1000, chunk_overlap=200)
    ids: set[str] = set()
    for sec in (21, 22):
        doc = Document(
            page_content=f"Contenido del subitem de la seccion {sec}.",
            metadata={
                "source": "REMAC.md",
                "doc_type": "normativa",
                "articulo": "5.2",
                "section_index": sec,
            },
        )
        for chunk in _chunk_section(doc, splitter):
            ids.add(chunk.metadata["chunk_id"])
    # 2 secciones × 1 chunk cada una = 2 ids únicos (sin colisión)
    assert len(ids) == 2
