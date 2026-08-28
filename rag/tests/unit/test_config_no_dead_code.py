"""C10 — regresión: `rag.config` no debe volver a exponer constantes sin
ningún consumidor real.

Verificado por búsqueda global en todo el repo (backend/, tests/,
evaluation/, scripts/, utils/, docs/, .env.example) inmediatamente antes de
retirarlas:

- ``QUERY_ENRICHMENT_HYDE`` — ningún módulo la importaba ni la leía; la
  generación de un fragmento hipotético de sentencia (HyDE) nunca se
  conectó al paso de enriquecimiento real (``query_enricher.py``), que solo
  usa ``QUERY_ENRICHMENT_ENABLED`` (esa sí con consumidor real: se importa
  en ``core/query_enricher.py`` como ``ENRICHMENT_ENABLED``, y se conserva
  sin cambios).
- ``DEFAULT_K`` / ``DEFAULT_K_CANDIDATES`` — sin ningún consumidor: el `k`/
  `k_candidates` que realmente se usan en el flujo de retrieval vienen del
  `QueryRequest` de la API (con sus propios defaults en `schemas.py`) y de
  los defaults inline de `agent.py::retrieve_forced_node`
  (``state.get("k", 4)`` / ``state.get("k_candidates", 8)``), nunca de estas
  constantes de `config.py`.

No se retira `QUERY_ENRICHMENT_ENABLED`, ni ningún nombre relacionado con
BM25/vector/RRF/`k`/`k_candidates` reales del retriever — solo estas tres
constantes demostrablemente sin conexión a ningún caller.
"""

from __future__ import annotations

import rag.config as config_module


def test_config_no_longer_exposes_query_enrichment_hyde() -> None:
    assert not hasattr(config_module, "QUERY_ENRICHMENT_HYDE")


def test_config_no_longer_exposes_default_k() -> None:
    assert not hasattr(config_module, "DEFAULT_K")


def test_config_no_longer_exposes_default_k_candidates() -> None:
    assert not hasattr(config_module, "DEFAULT_K_CANDIDATES")


def test_config_still_exposes_query_enrichment_enabled() -> None:
    """No es una prueba de comportamiento — solo deja constancia de que esta
    constante SÍ tiene un consumidor real (query_enricher.py) y se conserva
    intacta: la limpieza de C10 no debe arrastrarla por error."""
    assert hasattr(config_module, "QUERY_ENRICHMENT_ENABLED")
