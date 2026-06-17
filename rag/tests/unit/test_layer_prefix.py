"""Pruebas de layer_prefix y constantes de tipos de documento — paquete rag."""

import pytest

from rag import config as rag_config


def test_doc_types_constant():
    assert rag_config.DOC_TYPES == ("jurisprudencia", "normativa")


def test_layer_prefix_valido():
    assert rag_config.layer_prefix("bronze", "normativa") == "data/bronze/normativa/"
    assert rag_config.layer_prefix("gold", "jurisprudencia") == "data/gold/jurisprudencia/"


def test_layer_prefix_capa_invalida():
    with pytest.raises(ValueError):
        rag_config.layer_prefix("plata", "normativa")


def test_layer_prefix_doc_type_invalido():
    with pytest.raises(ValueError):
        rag_config.layer_prefix("gold", "doctrina")
