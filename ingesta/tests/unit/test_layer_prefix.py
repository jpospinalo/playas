"""Pruebas de layer_prefix y constantes de tipos de documento — paquete ingest."""

import pytest

from ingest import config as ingest_config


def test_doc_types_constant():
    assert ingest_config.DOC_TYPES == ("jurisprudencia", "normativa")


def test_layer_prefix_valido():
    assert ingest_config.layer_prefix("bronze", "normativa") == "data/bronze/normativa/"
    assert ingest_config.layer_prefix("gold", "jurisprudencia") == "data/gold/jurisprudencia/"


def test_layer_prefix_capa_invalida():
    with pytest.raises(ValueError):
        ingest_config.layer_prefix("plata", "normativa")


def test_layer_prefix_doc_type_invalido():
    with pytest.raises(ValueError):
        ingest_config.layer_prefix("gold", "doctrina")
