"""El enriquecedor añade términos jurídicos sin borrar los del usuario.

Con un modelo local (gemma4:e4b) la consulta reescrita reemplazaba «tarima»,
«sombrillas» o «permiso temporal» por «ocupación de bienes de uso público» y
la recuperación caía (hit@4 de producción 0.707 frente a 0.724 sin
enriquecer). Con estas reglas subió a 0.776.
"""

from rag.core.prompts import ENRICHER_HUMAN_BODY


def test_terminos_juridicos_se_anaden_no_reemplazan() -> None:
    assert "se añaden, nunca reemplazan" in ENRICHER_HUMAN_BODY
    assert "mismas palabras del usuario" in ENRICHER_HUMAN_BODY


def test_lugar_costero_nombrado_no_es_aclaracion() -> None:
    assert "esa relación ya existe" in ENRICHER_HUMAN_BODY
