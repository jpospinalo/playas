"""Tokenizador de BM25: normaliza mayúsculas, tildes, puntuación, plurales y
palabras vacías para que la misma palabra escrita de otra forma sea el mismo
término léxico."""

from __future__ import annotations

from rag.core.retriever import _tokenize_bm25


def test_puntuacion_mayusculas_y_tildes_producen_el_mismo_token():
    assert _tokenize_bm25("Playa,") == ["playa"]
    assert _tokenize_bm25("PLAYA") == ["playa"]
    assert _tokenize_bm25("playa") == ["playa"]


def test_las_tildes_se_eliminan():
    assert _tokenize_bm25("Dirección") == ["direccion"]


def test_las_palabras_vacias_se_descartan():
    assert _tokenize_bm25("el acceso a la playa") == ["acceso", "playa"]


def test_los_plurales_se_reducen_a_su_forma_singular():
    assert _tokenize_bm25("playas") == ["playa"]
    assert _tokenize_bm25("concesiones") == ["concesion"]


def test_las_palabras_cortas_no_se_recortan_como_plural():
    assert _tokenize_bm25("mes") == ["mes"]


def test_los_numeros_se_conservan_y_los_digitos_sueltos_se_descartan():
    assert _tokenize_bm25("2324") == ["2324"]
    # "5.3.6.2" se parte en cuatro tokens de longitud 1, que se descartan.
    assert _tokenize_bm25("5.3.6.2") == []
