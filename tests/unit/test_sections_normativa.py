"""Tests de ``split_by_articles`` sobre archivos reales de normativa."""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.documents import Document

from ingest.sections_normativa import split_by_articles

# raíz del repo: tests/unit/ -> tests/ -> raíz
_REPO_ROOT = Path(__file__).resolve().parents[2]
_NORMATIVA_DIR = _REPO_ROOT / "archivos-normativa"

DECRETO = "decreto-2324-de-1984.md"
REMAC = "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103).md"


def _load(name: str) -> Document:
    path = _NORMATIVA_DIR / name
    text = path.read_text(encoding="utf-8")
    return Document(page_content=text, metadata={"source": name})


@pytest.fixture(scope="module")
def decreto_units() -> list[Document]:
    return split_by_articles(_load(DECRETO))


@pytest.fixture(scope="module")
def remac_units() -> list[Document]:
    return split_by_articles(_load(REMAC))


@pytest.mark.parametrize("name", [DECRETO, REMAC])
def test_files_exist(name: str) -> None:
    assert (_NORMATIVA_DIR / name).is_file(), f"falta el archivo {name}"


def _article_units(units: list[Document]) -> list[Document]:
    return [u for u in units if u.metadata["section_name"] != "Preámbulo"]


def test_decreto_detecta_muchos_articulos(decreto_units: list[Document]) -> None:
    arts = _article_units(decreto_units)
    assert len(arts) > 10


def test_remac_detecta_muchos_articulos(remac_units: list[Document]) -> None:
    arts = _article_units(remac_units)
    assert len(arts) > 10


@pytest.mark.parametrize("fixture", ["decreto_units", "remac_units"])
def test_sin_marcador_pagina(fixture: str, request: pytest.FixtureRequest) -> None:
    units: list[Document] = request.getfixturevalue(fixture)
    for u in units:
        assert "## Página" not in u.page_content


@pytest.mark.parametrize("fixture", ["decreto_units", "remac_units"])
def test_doc_type_y_section_index_consecutivos(
    fixture: str, request: pytest.FixtureRequest
) -> None:
    units: list[Document] = request.getfixturevalue(fixture)
    for u in _article_units(units):
        assert u.metadata["doc_type"] == "normativa"
    indices = [u.metadata["section_index"] for u in units]
    assert indices == list(range(1, len(units) + 1))


@pytest.mark.parametrize("fixture", ["decreto_units", "remac_units"])
def test_al_menos_un_titulo(fixture: str, request: pytest.FixtureRequest) -> None:
    units: list[Document] = request.getfixturevalue(fixture)
    assert any(u.metadata.get("titulo") for u in _article_units(units))


def test_decreto_preambulo_primero(decreto_units: list[Document]) -> None:
    first = decreto_units[0]
    assert first.metadata["section_name"] == "Preámbulo"
    assert "DECRETA" in first.page_content
