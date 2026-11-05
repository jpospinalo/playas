"""Limpieza determinista del formato de la respuesta generada.

Con gemma4:e4b, 10 de 63 respuestas «etiquetaban» la sección de límites con
una línea que solo tenía citas (``[doc1][doc4]``) y alguna repetía el título
«Límites de evidencia». La limpieza no toca el contenido ni las citas que
acompañan a una frase.
"""

from rag.core.agent import _tidy_answer


def test_quita_lineas_que_solo_tienen_citas() -> None:
    answer = "**Límites de evidencia**\n[doc1][doc4]\nNo se detalla el plazo [doc1]."

    assert _tidy_answer(answer) == "**Límites de evidencia**\nNo se detalla el plazo [doc1]."


def test_conserva_citas_dentro_de_frases() -> None:
    answer = "La DIMAR es competente [doc2].\n- Requiere permiso [doc1][doc3]."

    assert _tidy_answer(answer) == answer


def test_quita_titulo_de_seccion_repetido_y_conserva_su_contenido() -> None:
    answer = "**Límites de evidencia**\nUno [doc1].\n\n**Límites de evidencia**\n- Dos.\n- Tres."

    assert _tidy_answer(answer) == "**Límites de evidencia**\nUno [doc1].\n\n- Dos.\n- Tres."


def test_no_deja_mas_de_una_linea_en_blanco_seguida() -> None:
    answer = "Uno [doc1].\n\n[doc2]\n\nDos [doc2]."

    assert _tidy_answer(answer) == "Uno [doc1].\n\nDos [doc2]."


def test_respuesta_solo_con_citas_queda_vacia_y_no_pasa_la_validacion() -> None:
    from rag.core.agent import _validate_citations

    assert not _validate_citations(_tidy_answer("[doc1]\n[doc2]"), doc_count=2)
