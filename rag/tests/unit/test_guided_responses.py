"""Las rutas sin recuperación guían al usuario, no solo describen el ámbito.

Quien no sabe cómo preguntar no sale de una descripción de alcance. Estas
pruebas fijan lo que las cuatro respuestas sin recuperación deben ofrecerle:
los datos concretos que hacen falta para buscar en el corpus y ejemplos con la
forma de las consultas reales. También cubren la regla del guard que convierte
un rechazo en una petición de aclaración.
"""

from __future__ import annotations

import pytest

from rag.core.agent import (
    _CLARIFICATION_RESPONSE,
    _CONVERSATION_RESPONSE,
    _NO_EVIDENCE_RESPONSE,
    _OUT_OF_SCOPE_RESPONSE,
)
from rag.core.domain_scope import EnrichedQuery, _apply_domain_guard, _fallback
from rag.core.prompts import AGENT_RESPONSE_SECTIONS, AGENT_SYSTEM

LICENCIA = (
    "Mi licencia de construcción fue suspendida por una medida cautelar dentro de un "
    "proceso judicial, y antes de que se resolviera el proceso se cumplió el término de "
    "vigencia de 24 meses que tenía la licencia. Cuando finalmente se levantó la "
    "suspensión, ¿ese tiempo suspendido se descuenta del plazo de vigencia?"
)


@pytest.mark.parametrize(
    "respuesta",
    [_CONVERSATION_RESPONSE, _OUT_OF_SCOPE_RESPONSE, _CLARIFICATION_RESPONSE],
)
def test_las_respuestas_sin_evidencia_traen_un_ejemplo_concreto(respuesta: str) -> None:
    """Un ejemplo con comillas angulares es la diferencia entre describir el
    ámbito y enseñar a preguntar."""
    assert "«" in respuesta and "»" in respuesta


@pytest.mark.parametrize("respuesta", [_CLARIFICATION_RESPONSE, _NO_EVIDENCE_RESPONSE])
def test_pedir_aclaracion_nombra_los_tres_datos_que_faltan(respuesta: str) -> None:
    for dato in ("Dónde", "Qué actividad o trámite", "Quién intervino"):
        assert dato in respuesta


def test_los_ejemplos_nombran_lugares_del_corpus() -> None:
    """Un ejemplo con un lugar que el corpus no cubre entrena al usuario a
    preguntar lo que no podemos responder."""
    assert "El Rodadero" in _CONVERSATION_RESPONSE
    assert "Santa Marta" in _CONVERSATION_RESPONSE


# ── Guard: un rechazo se convierte en petición de aclaración ────────────────


def test_consulta_juridica_sin_marcador_costero_pide_aclaracion() -> None:
    """Caso 046 del ground truth: el modelo la etiquetaba fuera de ámbito y el
    usuario quedaba sin salida, aunque el corpus la cubre en contexto costero."""
    assert _fallback(LICENCIA).route == "needs_clarification"
    guarded = _apply_domain_guard(
        EnrichedQuery(
            route="out_of_scope",
            standalone_question=LICENCIA,
            expanded_query=LICENCIA,
            doc_types=[],
        ),
        LICENCIA,
        "",
    )
    assert guarded.route == "needs_clarification"
    assert guarded.doc_types == []


def test_una_peticion_inequivocamente_ajena_sigue_fuera_de_ambito() -> None:
    """La regla que protege las solicitudes ajenas precede a la degradación:
    pedir un poema sobre la playa no se convierte en una aclaración."""
    question = "Escribe un poema sobre los permisos que exige DIMAR para pescar en la playa."
    guarded = _apply_domain_guard(
        EnrichedQuery(
            route="out_of_scope",
            standalone_question=question,
            expanded_query=question,
            doc_types=[],
        ),
        question,
        "",
    )
    assert guarded.route == "out_of_scope"


# ── Prompt: el formato de respuesta no se filtra al texto ───────────────────


def test_los_titulos_de_seccion_estan_en_el_prompt() -> None:
    for titulo in AGENT_RESPONSE_SECTIONS:
        assert f"**{titulo}**" in AGENT_SYSTEM


def test_ninguna_descripcion_comparte_linea_con_su_titulo() -> None:
    """La fuga de plantilla (4 de 65 respuestas de la línea base imprimieron
    "— regla jurídica central en 2–4 oraciones con [docN]") venía de tener el
    título y su descripción en la misma línea: el modelo copiaba las dos."""
    for titulo, descripcion in AGENT_RESPONSE_SECTIONS.items():
        for linea in AGENT_SYSTEM.splitlines():
            if f"**{titulo}**" in linea:
                assert descripcion not in linea


def test_el_prompt_prohibe_reproducir_las_descripciones() -> None:
    assert "No las copies" in AGENT_SYSTEM


def test_aclaracion_no_afirma_que_falta_la_playa() -> None:
    """La aclaración salta por varios motivos (falta lugar, actividad o
    autoridad). Decir «no mencionas el vínculo con una playa» a quien escribió
    «tengo un problema con la playa» suena a que no se le leyó."""
    from rag.core.agent import _CLARIFICATION_RESPONSE

    assert "no mencionas" not in _CLARIFICATION_RESPONSE
    assert "playa" not in _CLARIFICATION_RESPONSE.split("\n\n")[0]


def test_saludo_con_problema_guia_en_vez_de_preguntar_cual_es_la_consulta() -> None:
    """«hola, tengo un problema con la playa» ya trae una consulta: responder
    «¿Cuál es tu consulta?» obliga a repetirla. Se pide el dato que falta."""
    from rag.core.agent import _CLARIFICATION_RESPONSE, _conversation_response

    assert _conversation_response("hola, tengo un problema con la playa") == (
        _CLARIFICATION_RESPONSE
    )


def test_saludo_solo_sigue_siendo_breve() -> None:
    from rag.core.agent import _conversation_response

    assert _conversation_response("Hola") == "Hola. ¿Cuál es tu consulta?"
    assert _conversation_response("buenas tardes!") == "Hola. ¿Cuál es tu consulta?"
