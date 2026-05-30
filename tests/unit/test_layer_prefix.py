"""Pruebas de layer_prefix y constantes de tipos de documento."""

import pytest

from ingest import config as ingest_config
from rag import config as rag_config


def test_doc_types_constant():
    assert ingest_config.DOC_TYPES == ("jurisprudencia", "normativa")
    assert rag_config.DOC_TYPES == ("jurisprudencia", "normativa")


@pytest.mark.parametrize("config", [ingest_config, rag_config])
def test_layer_prefix_valido(config):
    assert config.layer_prefix("bronze", "normativa") == "data/bronze/normativa/"
    assert config.layer_prefix("gold", "jurisprudencia") == "data/gold/jurisprudencia/"


@pytest.mark.parametrize("config", [ingest_config, rag_config])
def test_layer_prefix_capa_invalida(config):
    with pytest.raises(ValueError):
        config.layer_prefix("plata", "normativa")


@pytest.mark.parametrize("config", [ingest_config, rag_config])
def test_layer_prefix_doc_type_invalido(config):
    with pytest.raises(ValueError):
        config.layer_prefix("gold", "doctrina")
