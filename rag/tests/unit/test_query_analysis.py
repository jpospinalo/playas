"""Pruebas de alcance, fallback y validación del analizador de consultas."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.prompt_values import ChatPromptValue
from langchain_core.runnables import RunnableLambda

import rag.core.query_enricher as query_enricher
from evaluation.ground_truth import load_ground_truth_cases
from rag.core.prompts import AGENT_SYSTEM, ENRICHER_HUMAN_BODY, ENRICHER_SYSTEM
from rag.core.query_enricher import (
    EnrichedQuery,
    _apply_domain_guard,
    _fallback,
    _has_legal_signal,
    _parse_json_response,
)


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué permisos exige DIMAR para pescar desde una playa?",
        "¿Puede un hotel impedir el acceso público a una playa?",
        "¿Qué procedimiento se requiere para una concesión en terreno de bajamar?",
        "¿Qué jurisprudencia regula el turismo en una zona costera?",
        "¿Quién tiene derecho a usar las aguas marítimas cercanas a la playa?",
    ],
)
def test_scope_fallback_accepts_domain_questions(question: str) -> None:
    result = _fallback(question)
    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]


@pytest.mark.parametrize(
    "question",
    [
        "Según el REMAC 5, ¿quién aprueba los sistemas de gestión del agua de lastre "
        "y qué debe verificarse con esa aprobación?",
        "Conforme al REMAC 5, ¿qué requisitos se aplican a la gestión del agua de lastre?",
    ],
)
def test_remac_5_reference_admits_regulatory_questions(question: str) -> None:
    rejected = EnrichedQuery(
        route="out_of_scope", standalone_question=question, expanded_query=question
    )
    result = _fallback(question)
    assert result.route == "in_scope"
    assert result.doc_types == ["normativa"]
    assert _apply_domain_guard(rejected, question, "") == result


@pytest.mark.parametrize(
    "question",
    [
        "Según el REMAC 5, escribe un poema sobre los permisos para la gestión del agua de lastre.",
        "Según el REMAC 5, ¿dónde puedo comprar un equipo de gestión del agua de lastre?",
        "¿Quién aprueba las letras del grupo REMAC 5?",
        "Según el REMAC 5, ¿quién aprueba el equipo de una piscina?",
    ],
)
def test_remac_5_reference_keeps_scope_limits(question: str) -> None:
    rejected = EnrichedQuery(
        route="out_of_scope", standalone_question=question, expanded_query=question
    )
    assert _fallback(question).route != "in_scope"
    assert _apply_domain_guard(rejected, question, "") == rejected


@pytest.mark.parametrize(
    "question",
    [
        "¿Cuál es la capital de Francia?",
        "Dame una receta para cocinar pescado.",
        "Explícame cómo programar una API en Python.",
        "Recomiéndame hoteles para pasar vacaciones.",
    ],
)
def test_scope_fallback_rejects_unrelated_questions(question: str) -> None:
    assert _fallback(question).route == "out_of_scope"


def test_related_but_ambiguous_question_requests_clarification() -> None:
    result = _fallback("¿Qué permiso necesito para operar un negocio turístico?")
    assert result.route == "needs_clarification"


def test_follow_up_inherits_coastal_scope_from_history() -> None:
    result = _fallback(
        "¿Y quién tiene ese derecho?",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?\nAsistente: Respuesta previa.",
    )
    assert result.route == "in_scope"


def test_explicit_off_topic_question_does_not_inherit_old_domain_history() -> None:
    result = _fallback(
        "¿Y cuál es la capital de Francia?",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )
    assert result.route == "out_of_scope"


def test_unrelated_question_without_known_pattern_does_not_inherit_scope() -> None:
    result = _fallback(
        "Escribe un poema sobre la luna.",
        "Usuario: ¿Puede un particular cerrar el acceso a una playa?",
    )
    assert result.route == "out_of_scope"


def test_invalid_structured_output_is_not_accepted_as_enrichment() -> None:
    result = _parse_json_response(
        '{"expanded_query":"capital de Francia DIMAR","legal_concepts":["inventado"]}',
        "¿Cuál es la capital de Francia?",
    )
    assert result.route == "out_of_scope"
    assert result.expanded_query == "¿Cuál es la capital de Francia?"


def test_obvious_unrelated_question_cannot_be_forced_into_scope() -> None:
    result = _parse_json_response(
        """{
            "route": "in_scope",
            "standalone_question": "¿Cuál es la capital de Francia?",
            "expanded_query": "capital de Francia DIMAR playas",
            "doc_types": ["normativa"]
        }""",
        "¿Cuál es la capital de Francia?",
    )
    assert result.route == "out_of_scope"
    assert result.doc_types == []


def test_arbitrary_question_cannot_be_forced_into_scope_by_model() -> None:
    result = _parse_json_response(
        """{
            "route": "in_scope",
            "standalone_question": "Escribe un poema sobre la luna",
            "expanded_query": "playas poema luna",
            "doc_types": ["normativa"]
        }""",
        "Escribe un poema sobre la luna",
    )
    assert result.route == "out_of_scope"


def test_invalid_json_parse_failure_never_logs_raw_model_output(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """El log de fallo de parseo debe registrar solo metadatos (proveedor,
    clase de excepción, aviso de fallback) — nunca el texto crudo devuelto
    por el modelo, que puede repetir la pregunta, el historial o cualquier
    dato sensible. Se usa un decoy string que, si apareciera en el log,
    demostraría que el texto crudo se filtró."""
    decoy = "SECRETO-USUARIO-no-debe-aparecer-en-el-log-12345"
    malformed_json = f"esto no es JSON válido — {decoy}"

    with caplog.at_level("WARNING", logger="rag.core.query_enricher"):
        result = _parse_json_response(
            malformed_json,
            "¿Qué permisos exige DIMAR para pescar desde una playa?",
            provider_name="OpenAIProvider",
        )

    assert result.expanded_query == "¿Qué permisos exige DIMAR para pescar desde una playa?"
    assert decoy not in caplog.text
    assert malformed_json not in caplog.text
    assert "provider=OpenAIProvider" in caplog.text
    assert "exception_class=JSONDecodeError" in caplog.text
    assert "fallback_used=true" in caplog.text


def test_invalid_json_parse_failure_logs_unknown_provider_when_not_given(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING", logger="rag.core.query_enricher"):
        _parse_json_response("not json at all", "¿Puede un hotel impedir el acceso público?")

    assert "provider=unknown" in caplog.text
    assert "exception_class=JSONDecodeError" in caplog.text


def test_analysis_prompt_injects_question_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        query_enricher,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    prompt = query_enricher._build_prompt()
    messages = prompt.format_messages(
        history="Usuario: pregunta anterior sobre una playa",
        question="¿Y cuál es el plazo?",
    )
    rendered = "\n".join(str(message.content) for message in messages)
    assert "pregunta anterior sobre una playa" in rendered
    assert "¿Y cuál es el plazo?" in rendered
    assert "{history}" not in rendered
    assert "{question}" not in rendered


@pytest.mark.parametrize(
    ("async_call", "structured"),
    [
        pytest.param(False, True, id="sync-system-structured"),
        pytest.param(True, True, id="async-system-structured"),
        pytest.param(False, False, id="sync-human-json"),
        pytest.param(True, False, id="async-human-json"),
    ],
)
def test_enrichment_instructions_reach_provider_across_supported_paths(
    monkeypatch: pytest.MonkeyPatch, async_call: bool, structured: bool
) -> None:
    """Comprueba conexión y contratos con una salida fija, no obediencia del modelo."""
    question = "¿Y quién debe aprobar ese plan?"
    history = "Usuario: ¿Qué autoridad marítima aprueba la Zona de Manejo Costero (ZMC)?"
    expected = EnrichedQuery(
        route="in_scope",
        standalone_question="¿Quién debe aprobar la Zona de Manejo Costero (ZMC)?",
        expanded_query="aprobación autoridad marítima Zona de Manejo Costero ZMC",
        doc_types=["normativa"],
    )
    captured: list[ChatPromptValue] = []
    calls = {"factory": 0, "structured": 0, "sync": 0, "async": 0}

    def invoke(value: ChatPromptValue) -> EnrichedQuery | str:
        captured.append(value)
        calls["sync"] += 1
        return expected if structured else expected.model_dump_json()

    async def ainvoke(value: ChatPromptValue) -> EnrichedQuery | str:
        captured.append(value)
        calls["async"] += 1
        return expected if structured else expected.model_dump_json()

    runnable = RunnableLambda(invoke, afunc=ainvoke)

    def with_structured_output(schema: type[EnrichedQuery]):
        assert schema is EnrichedQuery
        calls["structured"] += 1
        return runnable

    def get_llm():
        calls["factory"] += 1
        return (
            SimpleNamespace(with_structured_output=with_structured_output)
            if structured
            else runnable
        )

    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(
        query_enricher,
        "get_active_provider",
        lambda: SimpleNamespace(
            supports_system_role=structured, supports_structured_output=structured
        ),
    )
    monkeypatch.setattr(query_enricher, "get_enrichment_llm", get_llm)

    result = (
        asyncio.run(query_enricher.enrich_query_async(question, history))
        if async_call
        else query_enricher.enrich_query(question, history)
    )

    assert result == expected  # El fallback no contiene esta reformulación ni estos tipos.
    assert calls == {
        "factory": 1,
        "structured": int(structured),
        "sync": int(not async_call),
        "async": int(async_call),
    }
    assert len(captured) == 1
    messages = captured[0].to_messages()
    assert [message.type for message in messages] == (
        ["system", "human"] if structured else ["human"]
    )
    rendered = "\n".join(str(message.content) for message in messages)
    assert rendered.count(ENRICHER_SYSTEM) == 1
    assert ENRICHER_SYSTEM in str(messages[0].content)
    human_body = str(messages[-1].content)
    assert f"<conversation_history>\n{history}\n</conversation_history>" in human_body
    assert f"<question>\n{question}\n</question>" in human_body


def test_prompts_do_not_assign_an_atlas_identity() -> None:
    assert "ATLAS" not in AGENT_SYSTEM
    assert "ATLAS" not in ENRICHER_SYSTEM
    assert "ATLAS" not in ENRICHER_HUMAN_BODY


def test_enriched_query_normalizes_doc_types_and_word_limit() -> None:
    result = EnrichedQuery(
        route="in_scope",
        standalone_question="¿Qué norma aplica a una playa?",
        expanded_query=" ".join(f"término{index}" for index in range(60)),
        doc_types=["normativa", "normativa"],
    )
    assert len(result.expanded_query.split()) == 45
    assert result.doc_types == ["normativa"]


# ── Plan de corrección — enrutamiento de consultas jurídicas costeras ───────
#
# Regresión para los falsos negativos y falsos positivos confirmados por el
# equipo jurídico durante una iteración de corrección ya cerrada (el plan y
# el informe correspondientes ya no están en el repo — ver el historial de
# git si hace falta el detalle original).

CASO_PESCADOR = (
    "Soy pescador artesanal y vivo con mi familia de lo que gano en el mar. "
    "Hace varios meses una embarcación quedó abandonada cerca del lugar donde "
    "trabajo. Cada vez hay más combustible y residuos en el agua, y tengo "
    "miedo de que la contaminación afecte la zona donde pesco. Ya he "
    "presentado quejas, pero nadie me da una solución. No tengo dinero para "
    "pagar un abogado. ¿Qué puedo hacer para que la autoridad actúe y retire "
    "la embarcación antes de que el problema empeore?"
)

CASO_KAYAK = (
    "Tengo una empresa que organiza competencias de kayak en El Rodadero "
    "(Santa Marta). Presenté la solicitud para realizar un campeonato "
    "internacional dentro de dos semanas, pero la respuesta de la autoridad "
    "todavía no ha llegado. Los patrocinadores ya hicieron publicidad y "
    "muchos deportistas vienen desde otras ciudades, por lo que estoy "
    "pensando en realizar el evento mientras recibo la respuesta. ¿Puedo "
    "iniciar la actividad mientras deciden mi solicitud o debo esperar la "
    "autorización?"
)


@pytest.mark.parametrize(
    "question",
    [
        CASO_PESCADOR,
        CASO_KAYAK,
        "¿Quién debe retirar una nave abandonada que contamina el mar?",
        "¿Puedo programar una competencia turística en una playa si la autoridad no responde?",
        "¿Se puede cocinar y vender pescado en una playa sin permiso?",
        "¿Qué haces si un hotel cierra el acceso público a una playa?",
        "¿Puedo practicar surf en El Rodadero?",
        "¿Quién autoriza deportes náuticos en Santa Marta?",
        "¿La contaminación de una bahía vulnera derechos colectivos?",
    ],
)
def test_scope_fallback_accepts_confirmed_false_negatives(question: str) -> None:
    """Los dos casos completos del equipo jurídico y los siete falsos
    negativos adicionales deben ser in_scope y seleccionar al menos un tipo
    documental — el defecto ocurría antes de llegar a recuperación."""
    result = _fallback(question)
    assert result.route == "in_scope"
    assert result.doc_types


@pytest.mark.parametrize(
    "question",
    [
        "Escribe un poema sobre una playa.",
        "Genera una imagen de una playa al atardecer.",
        "Recomiéndame hoteles cerca de una playa.",
        "¿Dónde puedo comprar un kayak barato?",
        "¿Cómo entrenar para una competencia de kayak?",
    ],
)
def test_scope_fallback_rejects_confirmed_false_positives(question: str) -> None:
    """La sola presencia de playa/mar/kayak o un lugar costero no debe forzar
    in_scope cuando la intención es creativa, comercial o recreativa."""
    result = _fallback(question)
    assert result.route == "out_of_scope"
    assert result.doc_types == []


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué puedes hacer?",
        "¿Cómo funcionas?",
        "¿Cuáles son tus capacidades?",
    ],
)
def test_short_meta_questions_about_the_assistant_are_conversation(question: str) -> None:
    assert _fallback(question).route == "conversation"


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué haces si un hotel cierra el acceso público a una playa?",
        "¿Cómo ayudas a exigir que una autoridad retire una embarcación?",
    ],
)
def test_legal_question_phrased_like_a_meta_question_is_not_conversation(question: str) -> None:
    """'¿Qué haces...?' / '¿Cómo ayudas...?' no deben clasificarse como
    conversation solo por su forma cuando en realidad plantean un supuesto
    jurídico costero completo."""
    result = _fallback(question)
    assert result.route != "conversation"
    assert result.route == "in_scope"


@pytest.mark.parametrize("question", [CASO_PESCADOR, CASO_KAYAK])
def test_domain_guard_does_not_veto_a_model_in_scope_for_confirmed_cases(
    question: str,
) -> None:
    """Si el modelo de enriquecimiento ya clasifica los casos A/B como
    in_scope, _apply_domain_guard() no debe vetarlo (y ahora tampoco debería
    hacer falta corregirlo, porque la heurística coincide)."""
    from rag.core.query_enricher import _apply_domain_guard

    llm_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query="consulta jurídica costera de prueba",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(llm_result, question, "")
    assert guarded.route == "in_scope"


@pytest.mark.parametrize(
    "question",
    [
        "Escribe un poema sobre una playa.",
        "Genera una imagen de una playa al atardecer.",
        "Recomiéndame hoteles cerca de una playa.",
    ],
)
def test_domain_guard_keeps_creative_or_commercial_out_of_scope_despite_playa(
    question: str,
) -> None:
    """Aun si el modelo ya responde out_of_scope, la heurística no debe
    convertir en in_scope una intención creativa o comercial por la sola
    presencia de 'playa'."""
    from rag.core.query_enricher import _apply_domain_guard

    llm_result = EnrichedQuery(
        route="out_of_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=[],
    )
    guarded = _apply_domain_guard(llm_result, question, "")
    assert guarded.route == "out_of_scope"


def test_domain_guard_does_not_flip_model_in_scope_when_heuristic_is_silent() -> None:
    """La mera ausencia de coincidencias heurísticas (ni señal costera ni
    jurídica reconocida, y ninguna señal explícitamente ajena) no debe
    convertir un in_scope semántico del modelo en out_of_scope — la
    heurística solo corrige errores evidentes, no sustituye el análisis del
    modelo cuando simplemente no tiene una opinión."""
    from rag.core.query_enricher import _apply_domain_guard

    question = (
        "¿Qué disposiciones rigen una laguna interior no navegable dentro de una reserva forestal?"
    )
    llm_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query="disposiciones laguna interior reserva forestal régimen",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(llm_result, question, "")
    assert guarded.route == "in_scope"
    assert guarded.expanded_query == llm_result.expanded_query


def test_previously_passing_domain_questions_still_pass() -> None:
    """Regresión explícita: el comportamiento que ya funcionaba antes de esta
    corrección debe seguir intacto."""
    for question in [
        "¿Qué permisos exige DIMAR para pescar desde una playa?",
        "¿Puede un hotel impedir el acceso público a una playa?",
        "¿Qué procedimiento se requiere para una concesión en terreno de bajamar?",
        "¿Qué jurisprudencia regula el turismo en una zona costera?",
        "¿Quién tiene derecho a usar las aguas marítimas cercanas a la playa?",
    ]:
        assert _fallback(question).route == "in_scope", question

    for question in [
        "¿Cuál es la capital de Francia?",
        "Dame una receta para cocinar pescado.",
        "Explícame cómo programar una API en Python.",
        "Recomiéndame hoteles para pasar vacaciones.",
    ]:
        assert _fallback(question).route == "out_of_scope", question


# ── Banco jurídico completo — fuente única: legal-ground-truth-v0.1 ────────
#
# Las 21 preguntas provienen del dataset versionado
# (evaluation/data/legal-ground-truth-v0.1.json), cargado y validado por
# evaluation/ground_truth.py — la misma fuente que usa la evaluación
# offline/online en evaluation/. No hay copias hardcodeadas del texto aquí:
# una pregunta debe llegar a in_scope y alcanzar el recuperador; "válida"
# no implica que el corpus tenga evidencia suficiente para una conclusión
# jurídica completa.

BANCO_21_PREGUNTAS = [(case["id"], case["pregunta"]) for case in load_ground_truth_cases()]


@pytest.mark.parametrize(
    ("caso_id", "question"),
    BANCO_21_PREGUNTAS,
    ids=[caso_id for caso_id, _ in BANCO_21_PREGUNTAS],
)
def test_banco_21_preguntas_juridicas_llegan_a_in_scope(caso_id: str, question: str) -> None:
    """Revisión posterior con el banco completo de 21 preguntas jurídicas:
    las 21 deben clasificarse in_scope, seleccionar al menos un tipo
    documental y no quedar atrapadas en conversation ni needs_clarification
    — es decir, deben poder llegar al recuperador. No se exige que el
    corpus tenga evidencia suficiente para una conclusión jurídica completa,
    solo que la ruta de clasificación no las rechace."""
    result = _fallback(question)
    assert result.route == "in_scope", f"{caso_id}: {question!r}"
    assert result.doc_types, f"{caso_id}: sin doc_types"
    assert result.route not in ("conversation", "needs_clarification"), caso_id
    # La pregunta original completa se preserva verbatim (no se resume ni se
    # pierde texto en el fallback determinista).
    assert result.standalone_question == question.strip(), caso_id


@pytest.mark.parametrize(
    ("caso_id", "question"),
    BANCO_21_PREGUNTAS,
    ids=[caso_id for caso_id, _ in BANCO_21_PREGUNTAS],
)
def test_banco_21_preguntas_domain_guard_no_las_convierte_a_out_of_scope(
    caso_id: str, question: str
) -> None:
    """Si el modelo de enriquecimiento ya clasifica alguna de las 21
    preguntas como in_scope, _apply_domain_guard() no debe convertirla en
    out_of_scope ni en ninguna otra ruta distinta de in_scope."""
    llm_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query="consulta jurídica costera de prueba",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(llm_result, question, "")
    assert guarded.route == "in_scope", caso_id


@pytest.mark.parametrize(
    ("legal_question", "recreational_or_commercial_question"),
    [
        (
            "¿El permiso de un hotel es suficiente para instalar una tarima y una "
            "carpa para una boda en la playa, o necesito otra autorización?",
            "Quiero organizar una boda soñada, ¿qué colores de flores combinan mejor?",
        ),
        (
            "¿Qué autorización necesito para dejar instaladas las graderías de un "
            "campeonato de fútbol playa después de que termine el torneo?",
            "¿Cuál fue el resultado del partido de fútbol de ayer?",
        ),
        (
            "¿Es legal que un hotel con concesión marítima restrinja el acceso "
            "público a la playa con una malla y un guardia?",
            "Recomiéndame hoteles buenos para ir de vacaciones a la playa.",
        ),
        (
            "¿Puedo iniciar una competencia de kayak mientras espero la "
            "autorización de la autoridad marítima?",
            "¿Dónde puedo aprender a usar un kayak este fin de semana?",
        ),
        (
            "¿Pueden sancionarme por vender comida en la playa sin permiso si es "
            "mi único sustento familiar?",
            "Dame una receta fácil para cocinar pescado al horno.",
        ),
        (
            "Compré un lote frente al mar y construí un restaurante sobre la "
            "arena, ¿eso significa que soy dueño de la playa?",
            "¿Cuáles son los precios de los inmuebles turísticos frente al mar?",
        ),
    ],
    ids=[
        "boda_playa_vs_boda_sin_contexto_costero",
        "campeonato_futbol_playa_vs_resultado_futbol",
        "hotel_restringe_acceso_vs_recomendacion_hotel",
        "competencia_kayak_vs_aprender_kayak",
        "venta_comida_playa_vs_receta_cocina",
        "propiedad_lote_playa_vs_precios_inmuebles",
    ],
)
def test_seis_pares_control_falsos_positivos_intencion_legal_vs_recreativa(
    legal_question: str, recreational_or_commercial_question: str
) -> None:
    """Sección 5 de la revisión posterior: mismo dominio superficial (boda,
    fútbol, hotel, kayak, comida, inmueble frente al mar), pero solo el
    miembro con intención jurídica/reguladora costera debe ser in_scope; la
    versión puramente recreativa o comercial sin ese contexto debe seguir
    out_of_scope."""
    legal_result = _fallback(legal_question)
    assert legal_result.route == "in_scope", legal_question
    assert legal_result.doc_types

    other_result = _fallback(recreational_or_commercial_question)
    assert other_result.route == "out_of_scope", recreational_or_commercial_question
    assert other_result.doc_types == []


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué autoridad regula las motos acuáticas que operan cerca de una zona de baño?",
        "¿Se necesita permiso para ofrecer parasailing a los turistas en una bahía?",
        "¿Qué requisitos exige la autoridad marítima para instalar un muelle flotante?",
        "¿Qué normativa protege el desarrollo turístico costero frente a comunidades étnicas?",
    ],
)
def test_scope_fallback_accepts_additional_concept_signals(question: str) -> None:
    """Protección de regresión para las señales agregadas a _COASTAL_RE en
    esta revisión (motos acuáticas, parasailing, muelle flotante y el
    adjetivo 'costero/a' sin depender de la palabra 'costa'), verificadas
    mediante combinaciones de contexto marítimo e intención jurídica —no
    mediante una lista de las 21 preguntas exactas ni de lugares."""
    result = _fallback(question)
    assert result.route == "in_scope", question
    assert result.doc_types


# ── Corrección posterior mínima (defectos #1 a #5) ──────────────────────────
#
# No revierte el trabajo de las rondas anteriores: reutiliza las mismas
# familias de señales (_COASTAL_RE, _LEGAL_RE, _OFF_TOPIC_RE, _CAPABILITIES_RE)
# y solo agrega las particiones/ajustes mínimos necesarios para los cinco
# defectos confirmados.


@pytest.mark.parametrize(
    "question",
    [
        "Escribe un poema sobre los permisos que exige DIMAR para pescar en la playa.",
        "Genera una imagen de un hotel que restringe el acceso público a una playa "
        "citando la normativa correspondiente.",
        "Ayúdame a programar una aplicación que consulte la normativa de permisos "
        "de playas de DIMAR.",
        "Escríbeme el código Python para automatizar la solicitud de una concesión marítima.",
    ],
)
def test_scope_fallback_rejects_unambiguous_off_topic_even_with_legal_coastal_terms(
    question: str,
) -> None:
    """Defecto #1: generar imágenes, escribir poemas o programar software
    deben seguir out_of_scope aunque la consulta mencione playas, mar,
    normativa, permisos o DIMAR — esas intenciones nunca deben convertirse
    en in_scope por la sola presencia de términos jurídicos costeros."""
    result = _fallback(question)
    assert result.route == "out_of_scope", question
    assert result.doc_types == []


@pytest.mark.parametrize(
    "question",
    [
        "Escribe un poema sobre los permisos que exige DIMAR para pescar en la playa.",
        "Genera una imagen de un hotel que restringe el acceso público a una playa "
        "citando la normativa correspondiente.",
    ],
)
def test_domain_guard_does_not_let_model_force_in_scope_for_unambiguous_off_topic(
    question: str,
) -> None:
    """Defecto #1 (parte de _apply_domain_guard): si el modelo se equivoca y
    devuelve in_scope para una intención inequívocamente ajena, el guard
    debe corregirlo a out_of_scope."""
    llm_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query="consulta jurídica costera de prueba",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(llm_result, question, "")
    assert guarded.route == "out_of_scope", question


@pytest.mark.parametrize(
    "question",
    [
        "Escribe un poema sobre los permisos que exige DIMAR para pescar en la playa.",
        "Genera una imagen de un hotel que restringe el acceso público a una playa "
        "citando la normativa correspondiente.",
    ],
)
def test_domain_guard_does_not_flip_a_correct_model_out_of_scope_to_in_scope(
    question: str,
) -> None:
    """Defecto #1: si el modelo ya acierta con out_of_scope para una
    intención inequívocamente ajena, el guard no debe convertirlo en
    in_scope."""
    llm_result = EnrichedQuery(
        route="out_of_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=[],
    )
    guarded = _apply_domain_guard(llm_result, question, "")
    assert guarded.route == "out_of_scope", question


def test_follow_up_after_coastal_history_reevaluates_legal_intent() -> None:
    """Defecto #2: al heredar contexto costero desde el historial, la señal
    jurídica debe volver a evaluarse con ese contexto ya incorporado. Antes
    de esta corrección, `legal` quedaba calculado con `coastal=False` y un
    modal de posibilidad como "puedo realizar el evento..." no llegaba a
    contar, dejando la pregunta en needs_clarification en vez de in_scope."""
    result = _fallback(
        "¿Y puedo realizar el evento mientras deciden?",
        "Usuario: Quiero organizar un evento en una playa, ¿qué debo tramitar?\n"
        "Asistente: Respuesta previa.",
    )
    assert result.route == "in_scope"
    assert result.doc_types


@pytest.mark.parametrize(
    "question",
    [
        "norma",
        "normas",
        "la normatividad vigente",
        "normativa aplicable",
    ],
)
def test_legal_regex_still_matches_norma_family(question: str) -> None:
    """Defecto #3, control positivo: 'norma', 'normas', 'normatividad' y
    'normativa' deben seguir contando como señal jurídica."""
    assert _has_legal_signal(question, coastal=True)


@pytest.mark.parametrize(
    "question",
    [
        "Hoy me siento normal.",
        "Normalmente llego temprano a la oficina.",
    ],
)
def test_legal_regex_does_not_match_normal_or_normalmente(question: str) -> None:
    """Defecto #3: 'normal' y 'normalmente' ya no deben contar como señal
    jurídica solo por compartir el prefijo 'norma'."""
    assert not _has_legal_signal(question, coastal=True)


@pytest.mark.parametrize(
    "question",
    [
        "¿Qué autorización necesito para remar en kayak en el lago del club deportivo?",
        "¿Puedo instalar un muelle privado en la represa del municipio sin permiso?",
        "¿Qué normativa regula una nave que navega por el río sin autorización?",
        "¿Se puede operar una moto acuática dentro de la piscina del hotel sin permiso?",
        "¿Qué normativa regula el lanzamiento de una nave espacial sin autorización?",
    ],
)
def test_scope_fallback_does_not_force_in_scope_for_inland_or_unrelated_context(
    question: str,
) -> None:
    """Defecto #4: nave, kayak, moto acuática y muelle no deben contar como
    contexto costero cuando la propia consulta indica un entorno interior o
    ajeno (lago, represa, río, piscina, nave espacial), aunque la consulta
    también tenga señal jurídica explícita (autorización/permiso/normativa)."""
    result = _fallback(question)
    assert result.route != "in_scope", question


@pytest.mark.parametrize(
    "question",
    [
        "¿Cómo ayudas?",
        "¿Cómo me ayudas?",
    ],
)
def test_short_how_do_you_help_questions_are_conversation(question: str) -> None:
    """Defecto #5: las meta-preguntas breves '¿Cómo ayudas?' y '¿Cómo me
    ayudas?' deben volver a clasificarse como conversation."""
    assert _fallback(question).route == "conversation"


def test_long_legal_question_starting_like_how_do_you_help_is_not_conversation() -> None:
    """Defecto #5, control negativo: un supuesto jurídico extenso que
    empieza igual ('¿Cómo ayudas a exigir...?') no debe clasificarse como
    conversation solo por compartir el arranque con la meta-pregunta breve."""
    result = _fallback("¿Cómo ayudas a exigir que una autoridad retire una embarcación?")
    assert result.route != "conversation"
    assert result.route == "in_scope"


def test_cooking_and_selling_on_a_beach_without_permit_stays_in_scope() -> None:
    """Regresión: 'cocinar y vender en una playa sin permiso' debe seguir
    in_scope — 'cocinar' es una señal ajena blanda que cede ante la
    combinación costera+jurídica, a diferencia de las intenciones
    inequívocamente ajenas del defecto #1."""
    result = _fallback("¿Se puede cocinar y vender pescado en una playa sin permiso?")
    assert result.route == "in_scope"
    assert result.doc_types


# ── Corrección general del clasificador de alcance ──────────────────────────
#
# Matriz general de comportamiento (no un banco de textos memorizados): cada
# caso ejercita una FAMILIA de intención/contexto con una redacción propia,
# distinta de las 21 preguntas y de las rondas anteriores, para verificar
# que la clasificación generaliza a paráfrasis nuevas en vez de depender de
# palabras específicas de ese banco.

# --- Matriz positiva: paráfrasis variadas de permisos, derechos,
#     autoridades, obligaciones y actividades económicas/ambientales/
#     turísticas/náuticas en playas -------------------------------------

_POSITIVE_MATRIX = [
    (
        "permiso_quiosco_playa",
        "¿Qué permiso necesito para instalar un quiosco de comidas en la playa?",
    ),
    (
        "derecho_acceso_orilla",
        "¿Tengo derecho a acceder libremente a la orilla del mar aunque haya un hotel al frente?",
    ),
    (
        "autoridad_queja_ruido",
        "¿Qué autoridad debe resolver una queja por ruido excesivo en una playa?",
    ),
    (
        "obligaciones_concesion_eventos",
        "¿Cuáles son mis obligaciones si tengo una concesión de playa para eventos?",
    ),
    (
        "prohibicion_acampar",
        "¿Está prohibido acampar en una playa sin autorización de la autoridad marítima?",
    ),
    (
        "tramite_ampliar_terraza",
        "Tengo un restaurante frente al mar y quiero ampliar la terraza hacia la "
        "arena, ¿qué debo tramitar?",
    ),
    (
        "modal_instalar_sombrillas",
        "¿Puedo instalar sombrillas y camas playeras de forma permanente sin que "
        "DIMAR me diga nada?",
    ),
    (
        "tramites_ambientales_festival",
        "Quiero organizar un festival de música en la playa, ¿qué trámites "
        "ambientales debo seguir?",
    ),
    (
        "participacion_pescadores_proyecto",
        "¿La comunidad de pescadores tiene derecho a participar en las decisiones "
        "sobre un proyecto turístico costero?",
    ),
    (
        "responsable_retirar_escombros",
        "¿Quién es responsable de retirar los escombros que deja un evento en la playa?",
    ),
    (
        "permiso_pescar_mar_breve",
        "¿Necesito permiso para pescar en el mar?",
    ),
    (
        "legalidad_cobrar_entrada_breve",
        "¿Es legal cobrar entrada a una playa pública?",
    ),
    (
        "narrativo_renovacion_permiso_sombrillas",
        "Tengo un pequeño negocio de alquiler de sombrillas en una playa turística "
        "y la alcaldía me dijo que debo renovar mi permiso cada año, pero nadie me "
        "explica qué documentos necesito ni cuánto tiempo tarda el trámite. "
        "¿Podrían orientarme sobre qué debo hacer para no perder mi punto de "
        "trabajo?",
    ),
    (
        "acuatica_ambigua_con_contexto_maritimo",
        "¿Qué autorización necesito para ofrecer paseos en kayak a los turistas "
        "que llegan en crucero a la bahía?",
    ),
]


@pytest.mark.parametrize(
    ("caso_id", "question"),
    _POSITIVE_MATRIX,
    ids=[caso_id for caso_id, _ in _POSITIVE_MATRIX],
)
def test_general_positive_matrix_reaches_in_scope(caso_id: str, question: str) -> None:
    """Matriz positiva general: paráfrasis nuevas (no las 21 preguntas) de
    permisos/derechos/autoridades/obligaciones, actividades económicas y
    ambientales en playas, preguntas breves y narrativas, y actividad
    acuática ambigua acompañada de contexto marítimo explícito. Todas deben
    generalizar a in_scope sin necesitar una condición dedicada por
    pregunta."""
    result = _fallback(question)
    assert result.route == "in_scope", f"{caso_id}: {question!r}"
    assert result.doc_types, f"{caso_id}: sin doc_types"


# --- Seguimientos variados (sección 6 de la revisión) -----------------------

_HISTORY_EVENTO_PLAYA = (
    "Usuario: Quiero organizar un evento en una playa, ¿qué debo tramitar?\n"
    "Asistente: Respuesta previa."
)

_FOLLOW_UP_MATRIX = [
    ("puedo_hacerlo_mientras_deciden", "¿Y puedo hacerlo mientras deciden?"),
    ("quien_tiene_que_autorizarlo", "¿Y quién tiene que autorizarlo?"),
    ("cuanto_tiempo_tienen_para_responder", "¿Y cuánto tiempo tienen para responder?"),
    ("tambien_aplica_a_los_pescadores", "¿También aplica a los pescadores?"),
    ("que_puedo_hacer_si_no_cumplen", "¿Qué puedo hacer si no cumplen?"),
]


@pytest.mark.parametrize(
    ("caso_id", "question"),
    _FOLLOW_UP_MATRIX,
    ids=[caso_id for caso_id, _ in _FOLLOW_UP_MATRIX],
)
def test_general_follow_up_matrix_inherits_context(caso_id: str, question: str) -> None:
    """Seguimientos variados que deben heredar el contexto costero+jurídico
    de un historial reciente sobre un evento en una playa, sin necesitar una
    condición dedicada por frase de seguimiento."""
    result = _fallback(question, _HISTORY_EVENTO_PLAYA)
    assert result.route == "in_scope", f"{caso_id}: {question!r}"
    assert result.doc_types, f"{caso_id}: sin doc_types"


# --- Matriz negativa: creación de contenido, recomendaciones/clima/
#     deportes/precios, actividad acuática en entornos interiores
#     explícitos, y consultas jurídicas genéricas sin contexto costero -----

_NEGATIVE_MATRIX = [
    (
        "crear_imagen_verbo_dibujar",
        "Dibújame una ilustración de una playa con normativa de acceso público.",
    ),
    (
        "crear_cancion_vocabulario_juridico_costero",
        "Compón una canción sobre los permisos de DIMAR para pescar en la playa.",
    ),
    (
        "programar_relacionado_con_dimar",
        "Necesito que me ayudes a desarrollar un script que descargue los datos "
        "de concesiones de DIMAR.",
    ),
    (
        "recomendacion_hotel",
        "Recomiéndame un hotel con playa privada y buena wifi.",
    ),
    (
        "clima",
        "¿Cuál es el pronóstico del tiempo para la playa este fin de semana?",
    ),
    (
        "resultado_deportivo",
        "¿Cuál fue el resultado de fútbol de ayer en la cancha de la playa?",
    ),
    (
        "precio_inmueble",
        "¿Cuáles son los precios de los inmuebles frente al mar en la playa?",
    ),
    (
        "kayak_en_lago_explicito",
        "¿Qué autorización exige el club para usar kayak en el lago los fines de semana?",
    ),
    (
        "muelle_en_embalse_explicito",
        "¿Puedo construir un muelle en un embalse municipal?",
    ),
    (
        "embarcacion_pesca_en_lago_explicito",
        "¿Necesito permiso para tener una embarcación de pesca en mi lago privado?",
    ),
    (
        "nave_espacial_explicito",
        "¿Qué normativa regula una nave espacial en fase de pruebas?",
    ),
    (
        "derecho_generico_sin_contexto_costero",
        "¿Cuáles son mis derechos como consumidor al comprar un electrodoméstico?",
    ),
    (
        "autoridad_generica_sin_contexto_costero",
        "¿Qué autoridad debo contactar para renovar mi pasaporte?",
    ),
    (
        "permiso_generico_sin_contexto_costero",
        "¿Necesito permiso para remodelar mi apartamento en la ciudad?",
    ),
]


@pytest.mark.parametrize(
    ("caso_id", "question"),
    _NEGATIVE_MATRIX,
    ids=[caso_id for caso_id, _ in _NEGATIVE_MATRIX],
)
def test_general_negative_matrix_stays_out_of_in_scope(caso_id: str, question: str) -> None:
    """Matriz negativa general: creación de contenido con verbos distintos a
    los ya cubiertos, programación relacionada superficialmente con DIMAR,
    recomendaciones/clima/deportes/precios, actividad acuática ambigua en un
    entorno interior explícito, y consultas jurídicas genéricas que solo
    contienen palabras como derecho/permiso/autoridad sin ningún contexto
    costero. Ninguna debe llegar a in_scope."""
    result = _fallback(question)
    assert result.route != "in_scope", f"{caso_id}: {question!r}"
    assert result.doc_types == [], f"{caso_id}: doc_types debería estar vacío"


# --- Pares contrastivos --------------------------------------------------
#
# Cada par cambia únicamente la intención o el contexto entre el miembro
# ajeno (columna "negative") y el miembro jurídico legítimo (columna
# "positive"). "category" distingue dos comportamientos distintos y
# correctos del guard (ver test_general_contrastive_pairs_domain_guard):
#   - "hard": el miembro negativo es una solicitud inequívocamente ajena
#     (familia #5) — el guard debe forzar out_of_scope pase lo que pase.
#   - "inland": el miembro negativo es una actividad acuática ambigua en un
#     entorno interior — la heurística no tiene certeza suficiente, así que
#     el guard debe conservar el análisis semántico del LLM tal cual (sin
#     forzar nada en ninguna dirección).

_CONTRASTIVE_PAIRS = [
    (
        "crear_imagen_playa_vs_permiso_sesion_fotografica",
        "hard",
        "Crea una imagen de una playa al atardecer con palmeras.",
        "¿Necesito permiso para realizar una sesión fotográfica comercial en una playa?",
    ),
    (
        "entrenar_kayak_vs_autorizacion_competencia_maritima",
        "hard",
        "¿Dónde puedo entrenar kayak los fines de semana?",
        "¿Necesito autorización para organizar una competencia de kayak en El Rodadero?",
    ),
    (
        "pesca_en_rio_vs_pesca_artesanal_en_playa",
        "inland",
        "¿Qué carnada es mejor para pescar en un río de montaña?",
        "¿Qué requisitos debe cumplir un pescador artesanal para faenar en una playa protegida?",
    ),
    (
        "muelle_en_represa_vs_concesion_muelle_playa",
        "inland",
        "¿Puedo instalar un muelle privado en una represa para mi finca?",
        "¿Qué trámite debo seguir para obtener la concesión de un muelle en una playa turística?",
    ),
    (
        "nave_espacial_vs_embarcacion_abandonada_en_el_mar",
        "inland",
        "¿Qué protocolo siguen las agencias espaciales para el reingreso de una nave espacial?",
        "¿Qué debe hacer un pescador si encuentra una embarcación abandonada contaminando el mar?",
    ),
    (
        "hotel_recomendado_vs_hotel_restringe_acceso_publico",
        "hard",
        "Recomiéndame un hotel bonito para las vacaciones.",
        "¿Puede un hotel con concesión de playa impedir el acceso público a la orilla del mar?",
    ),
]


@pytest.mark.parametrize(
    ("caso_id", "category", "negative_question", "positive_question"),
    _CONTRASTIVE_PAIRS,
    ids=[caso_id for caso_id, _, _, _ in _CONTRASTIVE_PAIRS],
)
def test_general_contrastive_pairs_fallback(
    caso_id: str, category: str, negative_question: str, positive_question: str
) -> None:
    """Cada par contrastivo cambia solo la intención o el contexto: el
    miembro ajeno/ambiguo nunca debe llegar a in_scope y el miembro
    jurídico legítimo siempre debe llegar a in_scope."""
    del category
    negative_result = _fallback(negative_question)
    assert negative_result.route != "in_scope", f"{caso_id} (negativo): {negative_question!r}"
    assert negative_result.doc_types == [], caso_id

    positive_result = _fallback(positive_question)
    assert positive_result.route == "in_scope", f"{caso_id} (positivo): {positive_question!r}"
    assert positive_result.doc_types, caso_id


@pytest.mark.parametrize(
    ("caso_id", "category", "negative_question", "positive_question"),
    _CONTRASTIVE_PAIRS,
    ids=[caso_id for caso_id, _, _, _ in _CONTRASTIVE_PAIRS],
)
def test_general_contrastive_pairs_domain_guard(
    caso_id: str, category: str, negative_question: str, positive_question: str
) -> None:
    """Simula que el LLM devuelve in_scope y out_of_scope para cada miembro
    del par y verifica _apply_domain_guard() en ambas direcciones.

    - Miembro positivo (cualquier categoría): el guard siempre debe
      terminar en in_scope, tanto si el modelo acertó como si se equivocó
      (la heurística tiene alta confianza y corrige el falso negativo).
    - Miembro negativo "hard" (solicitud inequívocamente ajena): el guard
      siempre debe forzar out_of_scope, incluso si el modelo dijo
      in_scope.
    - Miembro negativo "inland" (actividad acuática ambigua en entorno
      interior): la heurística no tiene certeza suficiente, así que el
      guard debe conservar el resultado del modelo tal cual, sin forzar
      nada en ninguna dirección.
    """
    for simulated_route in ("in_scope", "out_of_scope"):
        llm_result = EnrichedQuery(
            route=simulated_route,
            standalone_question=positive_question,
            expanded_query="consulta jurídica costera de prueba",
            doc_types=["normativa"] if simulated_route == "in_scope" else [],
        )
        guarded = _apply_domain_guard(llm_result, positive_question, "")
        assert guarded.route == "in_scope", f"{caso_id} positivo sim={simulated_route}"

    for simulated_route in ("in_scope", "out_of_scope"):
        llm_result = EnrichedQuery(
            route=simulated_route,
            standalone_question=negative_question,
            expanded_query="consulta de prueba",
            doc_types=["normativa"] if simulated_route == "in_scope" else [],
        )
        guarded = _apply_domain_guard(llm_result, negative_question, "")
        if category == "hard":
            assert guarded.route == "out_of_scope", (
                f"{caso_id} negativo(hard) sim={simulated_route}"
            )
        else:
            assert guarded.route == simulated_route, (
                f"{caso_id} negativo(inland) sim={simulated_route}"
            )


@pytest.mark.parametrize(
    "question",
    [
        "Según el artículo 5 del Decreto 1504 de 1998, ¿cómo se clasifican las playas "
        "marinas y las canecas para reciclar basuras dentro del espacio público?",
        "En el artículo 12 de la Ley 881 de 2006, ¿cómo se clasifican los rompeolas "
        "situados en aguas marítimas?",
        "Según la Resolución 731 de 2021, ¿cómo se define una playa artificial?",
        "En el artículo 7 del Decreto 1875 de 1979, ¿qué garantía se exige a las naves "
        "que realizan investigación sísmica?",
        "¿Qué autoridad debe adoptar el POMIUAC Insular y dentro de qué plazo?",
        "Según el artículo 2.2.4.2.3.5 del Decreto 415 de 2017, ¿quién expide la guía "
        "técnica del POMIUAC Insular y dentro de qué plazo?",
        "Conforme al Decreto 415 de 2017, ¿qué áreas incorpora el POMIUAC Insular?",
    ],
)
def test_documentary_coastal_references_admit_normative_questions(question: str) -> None:
    """La cita concreta aporta intención jurídica; el contexto aporta el ámbito.

    Las numeraciones alternativas son sintéticas: se evalúa admisión, nunca
    existencia de esas normas ni una respuesta jurídica sobre su contenido.
    """
    fallback = _fallback(question)
    assert fallback.route == "in_scope"
    assert "normativa" in fallback.doc_types

    for simulated_route in ("out_of_scope", "needs_clarification"):
        rejected = EnrichedQuery(
            route=simulated_route,
            standalone_question=question,
            expanded_query=question,
        )
        result = _apply_domain_guard(rejected, question, "")
        assert result.route == "in_scope"
        assert "normativa" in result.doc_types
        assert result.standalone_question == question


@pytest.mark.parametrize(
    ("question", "terminal"),
    [
        (
            "Según el Decreto 315 de 2016, ¿cómo se calcula el impuesto predial?",
            False,
        ),
        (
            "En la Ley 802 de 2003, ¿qué categoría corresponde a estos ingresos?",
            False,
        ),
        (
            "Según el artículo 8 del Decreto 771 de 2010, ¿qué requisitos rigen "
            "para una nave espacial?",
            False,
        ),
        (
            "En el Decreto 771 de 2010, ¿cómo se clasifica una embarcación que "
            "opera únicamente en una represa?",
            False,
        ),
        (
            "Según el Decreto 4440 de 2008, dibuja una imagen de una playa.",
            True,
        ),
        (
            "Escribe un poema sobre los permisos del POMIUAC Insular.",
            True,
        ),
    ],
)
def test_documentary_references_do_not_bypass_scope_limits(question: str, terminal: bool) -> None:
    assert _fallback(question).route != "in_scope"
    rejected = EnrichedQuery(
        route="out_of_scope", standalone_question=question, expanded_query=question
    )
    assert _apply_domain_guard(rejected, question, "").route != "in_scope"
    if terminal:
        accepted = EnrichedQuery(
            route="in_scope",
            standalone_question=question,
            expanded_query=question,
            doc_types=["normativa"],
        )
        assert _apply_domain_guard(accepted, question, "").route == "out_of_scope"


@pytest.mark.parametrize(
    "question",
    [
        "En ese plan costero, ¿cuánto tiempo tiene la entidad para terminarlo?",
        "¿Quién debe aprobar dicho plan de manejo de playas?",
    ],
)
@pytest.mark.parametrize(
    "history",
    [
        "",
        "Usuario: ¿Qué retenciones fiscales debo declarar?\nAsistente: Respuesta tributaria.",
    ],
)
def test_plan_reference_without_relevant_history_requires_clarification(
    question: str, history: str
) -> None:
    fallback = _fallback(question, history)
    assert fallback.route == "needs_clarification"
    assert fallback.doc_types == []

    invented = EnrichedQuery(
        route="in_scope",
        standalone_question="¿Cuál es el plazo para formular el POMIUAC Insular?",
        expanded_query="plazo formulación POMIUAC Insular",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(invented, question, history)
    assert guarded.route == "needs_clarification"
    assert guarded.doc_types == []
    assert guarded.standalone_question == question


def test_plan_reference_preserves_a_contextual_rewrite_supported_by_history() -> None:
    history = "Usuario: ¿Qué requisitos debe cumplir el Plan de Recuperación de la Playa Brisa?"
    question = "¿En qué plazo debe formularse ese plan?"
    rewritten = "¿En qué plazo debe formularse el Plan de Recuperación de la Playa Brisa?"
    result = EnrichedQuery(
        route="in_scope",
        standalone_question=rewritten,
        expanded_query=rewritten,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(result, question, history) == result


@pytest.mark.parametrize(
    "history",
    [
        "Usuario: ¿Qué requisitos debe cumplir el Plan de Recuperación de la Playa Brisa?",
        "Usuario: ¿Qué plazos rigen para el plan de manejo de playas y para el plan "
        "de restauración del litoral?",
    ],
)
def test_plan_reference_keeps_model_clarification_with_relevant_history(history: str) -> None:
    """No acredita resolver dos planes: impide anular una aclaración válida."""
    question = "¿En qué plazo debe ejecutarse ese plan costero?"
    result = EnrichedQuery(
        route="needs_clarification",
        standalone_question=question,
        expanded_query=question,
    )
    assert _apply_domain_guard(result, question, history) == result


@pytest.mark.parametrize(
    "question",
    [
        "¿En qué plazo debe formularse ese plan costero previsto en el artículo 12 "
        "del Decreto 881 de 2006?",
        "¿Qué autoridad debe adoptar dicho plan POMIUAC Insular?",
    ],
)
def test_plan_reference_identified_in_question_does_not_require_history(question: str) -> None:
    assert _fallback(question).route == "in_scope"
    result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(result, question, "") == result


@pytest.mark.parametrize(
    "question",
    [
        "¿Quién debe aprobar ese plan denominado «Plan de Recuperación de la Playa Brisa»?",
        '¿Qué requisitos debe cumplir dicho plan llamado "Plan de Restauración del Litoral"?',
        "¿Qué plazo tiene ese plan «Programa de Recuperación Costera»?",
    ],
)
def test_explicit_plan_name_in_question_is_not_discarded(question: str) -> None:
    result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _fallback(question).route == "in_scope"
    assert _apply_domain_guard(result, question, "") == result


def test_earlier_unrelated_turn_does_not_erase_relevant_plan_history() -> None:
    history = (
        "Usuario: Dame una receta de cocina.\nAsistente: Ese asunto es ajeno al ámbito.\n"
        "Usuario: ¿Qué requisitos debe cumplir el Plan de Recuperación de la Playa Brisa?"
    )
    question = "¿En qué plazo debe formularse ese plan?"
    rewritten = "¿En qué plazo debe formularse el Plan de Recuperación de la Playa Brisa?"
    result = EnrichedQuery(
        route="in_scope",
        standalone_question=rewritten,
        expanded_query=rewritten,
        doc_types=["normativa"],
    )
    assert _fallback(question, history).route == "in_scope"
    assert _apply_domain_guard(result, question, history) == result


@pytest.mark.parametrize(
    "question",
    [
        "¿Quién debe aprobar ese Plan de Recuperación de la Playa Brisa?",
        "¿Qué autoridad debe adoptar dicho Plan de Restauración del Litoral del Puerto Azul?",
    ],
)
def test_complete_plan_name_without_quotes_does_not_require_history(question: str) -> None:
    result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )

    assert _fallback(question).route == "in_scope"
    assert _apply_domain_guard(result, question, "") == result


@pytest.mark.parametrize(
    ("question", "ambiguous"),
    [
        (
            "Entre el plan de manejo de playas y el plan de restauración costera, "
            "¿qué plazo tiene ese plan según el Decreto 881 de 2006?",
            True,
        ),
        (
            "¿Qué plazo tiene ese Plan de Recuperación de la Playa Brisa previsto "
            "en el Decreto 881 de 2006?",
            False,
        ),
        (
            "Entre el POMIUAC Insular y el Plan de Recuperación de la Playa Brisa, "
            "sin haber elegido uno, ¿qué plazo tiene ese plan?",
            True,
        ),
        (
            "¿Qué plazo tiene ese plan POMIUAC Insular?",
            False,
        ),
        (
            "Se comparan ese plan denominado «Plan de Recuperación de la Playa Brisa» "
            "y el Plan de Restauración del Litoral del Puerto Azul. "
            "Sin elegir uno, ¿qué plazo tiene ese plan?",
            True,
        ),
        (
            "¿Qué plazo tiene ese plan denominado «Plan de Recuperación de la Playa Brisa»?",
            False,
        ),
    ],
    ids=[
        "normative-citation-ambiguous",
        "normative-citation-identified",
        "instrument-ambiguous",
        "instrument-identified",
        "explicit-name-ambiguous",
        "explicit-name-identified",
    ],
)
def test_plan_identity_signals_preserve_the_model_reference_analysis(
    question: str, ambiguous: bool
) -> None:
    """Una señal de identidad no invalida una aclaración semántica correcta."""
    result = EnrichedQuery(
        route="needs_clarification" if ambiguous else "in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=[] if ambiguous else ["normativa"],
    )

    assert _apply_domain_guard(result, question, "") == result
    if not ambiguous:
        assert _fallback(question).route == "in_scope"


@pytest.mark.parametrize(
    ("question", "expected_route"),
    [
        ("¿Quién debe aprobar ese Plan Costero?", "needs_clarification"),
        (
            "Escribe un poema sobre ese Plan de Recuperación de la Playa Brisa.",
            "out_of_scope",
        ),
    ],
)
def test_plan_name_controls_keep_missing_reference_and_off_topic_precedence(
    question: str, expected_route: str
) -> None:
    invented = EnrichedQuery(
        route="in_scope",
        standalone_question="¿Quién debe aprobar el POMIUAC Insular?",
        expanded_query="autoridad aprobación POMIUAC Insular",
        doc_types=["normativa"],
    )

    assert _fallback(question).route == expected_route
    guarded = _apply_domain_guard(invented, question, "")
    assert guarded.route == expected_route
    assert guarded.doc_types == []
    assert guarded.standalone_question == question


# L1: qualified legal purpose, independent of retrieval or factual sufficiency.
_QUALIFIED_LEGAL_N05 = (
    "En la definición del artículo 1429 del Código de Comercio incluido en el corpus, "
    "¿las actividades marítimas se reducen a navegar en el mar territorial, o abarcan "
    "también otros espacios y actividades de pesca, investigación y extracción? "
    "Precisa ese alcance."
)
_QUALIFIED_LEGAL_J01 = (
    "En la respuesta sobre manglares del concepto 1682 de 2 de noviembre de 2005, "
    "¿la investigación corresponde exclusivamente a DIMAR o cómo se reparten y "
    "coordinan las competencias?"
)
_QUALIFIED_LEGAL_QUERIES = [
    pytest.param(_QUALIFIED_LEGAL_N05, id="N05-code-article"),
    pytest.param(_QUALIFIED_LEGAL_J01, id="J01-concept-authority"),
    pytest.param(
        "Según el artículo 77 del Código Civil, ¿qué comprende el uso de playas marinas?",
        id="other-code-and-article",
    ),
    pytest.param(
        "En el artículo 305 del Código Aduanero, ¿cómo se define el transporte marítimo?",
        id="independent-code-title",
    ),
    pytest.param(
        "En el concepto 904 de 2007, ¿la investigación de manglares corresponde "
        "exclusivamente a DIMAR?",
        id="other-concept-and-authority",
    ),
    pytest.param(
        "¿Cómo se distribuyen las competencias administrativas de DIMAR en las playas?",
        id="administrative-competence",
    ),
]


@pytest.mark.parametrize("question", _QUALIFIED_LEGAL_QUERIES)
def test_qualified_legal_fallback_admits_identified_queries(question: str) -> None:
    result = _fallback(question)

    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]
    assert result.standalone_question == question
    assert result.expanded_query == query_enricher._normalize_expanded_query(question)


@pytest.mark.parametrize("question", _QUALIFIED_LEGAL_QUERIES)
@pytest.mark.parametrize("rejected_route", ["out_of_scope", "needs_clarification"])
def test_qualified_legal_guard_recovers_model_false_negative(
    question: str, rejected_route: str
) -> None:
    rejected = EnrichedQuery(
        route=rejected_route,
        standalone_question=question,
        expanded_query=question,
    )
    expected_expanded = rejected.expanded_query

    result = _apply_domain_guard(rejected, question, "")

    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]
    assert result.standalone_question == question
    assert result.expanded_query == expected_expanded
    assert rejected.route == rejected_route
    assert rejected.doc_types == []


@pytest.mark.parametrize("question", [_QUALIFIED_LEGAL_N05, _QUALIFIED_LEGAL_J01])
@pytest.mark.parametrize("mode", ["disabled", "provider_failure"])
def test_qualified_legal_async_fallback_keeps_identified_queries(
    monkeypatch: pytest.MonkeyPatch, question: str, mode: str
) -> None:
    def unavailable_provider():
        if mode == "disabled":
            pytest.fail("Disabled enrichment must not instantiate a provider")
        raise RuntimeError("Offline qualified legal provider failure")

    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", mode != "disabled")
    monkeypatch.setattr(query_enricher, "get_active_provider", unavailable_provider)
    monkeypatch.setattr(
        query_enricher,
        "get_enrichment_llm",
        lambda: pytest.fail("The fallback must not instantiate a model"),
    )

    result = asyncio.run(query_enricher.enrich_query_async(question))

    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]
    assert result.standalone_question == question
    assert result.expanded_query == query_enricher._normalize_expanded_query(question)


@pytest.mark.parametrize("question", [_QUALIFIED_LEGAL_N05, _QUALIFIED_LEGAL_J01])
@pytest.mark.parametrize("rejected_route", ["out_of_scope", "needs_clarification"])
def test_qualified_legal_async_guard_recovers_structured_false_negative(
    monkeypatch: pytest.MonkeyPatch, question: str, rejected_route: str
) -> None:
    rejected = EnrichedQuery(
        route=rejected_route,
        standalone_question=question,
        expanded_query=question,
    )

    async def analyze(_value):
        return rejected

    runnable = RunnableLambda(lambda _value: rejected, afunc=analyze)

    def structured_output(schema):
        assert schema is EnrichedQuery
        return runnable

    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", True)
    monkeypatch.setattr(
        query_enricher,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True, supports_structured_output=True),
    )
    monkeypatch.setattr(
        query_enricher,
        "get_enrichment_llm",
        lambda: SimpleNamespace(with_structured_output=structured_output),
    )

    result = asyncio.run(query_enricher.enrich_query_async(question))

    assert result.route == "in_scope"
    assert result.doc_types == ["jurisprudencia", "normativa"]
    assert result.standalone_question == question
    assert result.expanded_query == rejected.expanded_query
    assert rejected.route == rejected_route


@pytest.mark.parametrize(
    "question",
    [
        pytest.param(
            "Según el artículo 77 del Código Civil, escribe código Python "
            "para filtrar una foto de la playa.",
            id="programming-with-qualified-reference",
        ),
        pytest.param(
            "Según el concepto 904 de 2007 de DIMAR, escribe un poema sobre la playa.",
            id="poem-with-concept-and-authority",
        ),
        pytest.param("¿Cómo entrenar para una competencia de kayak?", id="sports-training"),
        pytest.param(
            "¿Cómo se reparten las competencias de kayak en una playa?",
            id="sport-competence-is-not-administrative",
        ),
        pytest.param(
            "¿Qué comprende el artículo 77 del Código Civil sobre contratos privados?",
            id="legal-reference-without-coastal-connection",
        ),
        pytest.param("¿Qué código tiene esa playa?", id="bare-code"),
        pytest.param(
            "En una playa, ¿qué comprende el artículo 77 del Código de?",
            id="code-reference-truncated-after-de",
        ),
        pytest.param(
            "En una playa, ¿qué comprende el artículo 77 del Código del?",
            id="code-reference-truncated-after-del",
        ),
        pytest.param("¿Cuál es la definición de mar?", id="bare-definition"),
        pytest.param(
            "¿Qué código comercial llevan las tablas de surf?",
            id="commercial-product-code",
        ),
    ],
)
def test_qualified_legal_controls_do_not_expand_scope(question: str) -> None:
    rejected = EnrichedQuery(
        route="out_of_scope",
        standalone_question=question,
        expanded_query=question,
    )

    assert _fallback(question).route != "in_scope"
    assert _apply_domain_guard(rejected, question, "") == rejected


@pytest.mark.parametrize(
    "question",
    [
        "En el texto del artículo 2 del Decreto 1875 de 1979, ¿por qué conducto se "
        "presenta una solicitud de vertimiento al mar, quién puede autorizarla y qué "
        "límite deben respetar su cantidad y concentración?",
        "Según el artículo 278 del Código de Recursos Naturales de 1974 recogido "
        "en el corpus, ¿el uso de playas marinas por los pescadores durante sus "
        "faenas es incondicional? Identifica las tres clases de áreas que el "
        "artículo exceptúa.",
        "En el artículo 28 del Decreto 804 de 2001 del corpus, ¿se sigue el mismo "
        "trámite para una empresa habilitada de transporte marítimo internacional "
        "y para una empresa colombiana de cabotaje que va a fletar una nave de "
        "bandera extranjera? Distingue el trámite previo en cada supuesto.",
        "Conforme al texto del artículo 141 del Decreto 2256 de 1991, ¿qué entidad "
        "matricula las embarcaciones pesqueras y expide sus patentes de navegación, "
        "y qué funciones de control marítimo le atribuye ese artículo?",
        "Según el artículo 1 del Decreto 803 de 2004 del corpus, ¿quién debe ofrecer "
        "públicamente la concesión portuaria del muelle departamental del Archipiélago "
        "y qué diferencia establece el texto entre el terreno del muelle y su zona accesoria?",
        "Según la respuesta 9 del concepto 1682 de 2005 sobre playas y bajamar, "
        "¿quién realiza la restitución física y se necesita después otro acto "
        "para que el bien vuelva al uso general?",
        "Con una autorización temporal para ocupar una playa en actividades portuarias, "
        "¿ya tengo asegurada la concesión que solicité y qué derecho me da esa "
        "autorización mientras dura, según el artículo 26 del Decreto 474 de 2015 del corpus?",
    ],
    ids=["N01", "N02", "N03", "N04", "N06", "J02", "C03"],
)
def test_qualified_legal_keeps_approved_bank_queries(question: str) -> None:
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["jurisprudencia", "normativa"],
    )

    assert _fallback(question).route != "out_of_scope"
    assert _apply_domain_guard(admitted, question, "") == admitted


@pytest.mark.parametrize(
    ("question", "expected_route"),
    [
        (
            "¿A qué despacho le corresponde dar el visto bueno a dicho plan "
            "para ordenar la franja de playa?",
            "needs_clarification",
        ),
        (
            "Escribe código Python que aplique un filtro azul a una foto de la playa.",
            "out_of_scope",
        ),
    ],
    ids=["C01", "C05"],
)
def test_qualified_legal_keeps_plan_and_programming_controls(
    question: str, expected_route: str
) -> None:
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )

    assert _fallback(question).route == expected_route
    guarded = _apply_domain_guard(admitted, question, "")
    assert guarded.route == expected_route
    assert guarded.doc_types == []
    assert guarded.standalone_question == question


def test_qualified_legal_guard_ignores_invented_coastal_expansion() -> None:
    question = "¿Qué comprende el artículo 77 del Código Civil?"
    rejected = EnrichedQuery(
        route="out_of_scope",
        standalone_question="¿Qué comprende el artículo 77 del Código Civil en una playa?",
        expanded_query="artículo 77 Código Civil competencia DIMAR playas marítimas",
    )

    assert _fallback(question).route != "in_scope"
    assert _apply_domain_guard(rejected, question, "") == rejected


# L2: clarify only a necessary missing datum or an unidentified singular decision.
_NECESSARY_CLARIFICATION_C02 = (
    "En el trámite de reversión de una autorización temporal sobre una playa me "
    "requirieron reparar daños. Según el artículo 28 del Decreto 474 de 2015 del "
    "corpus, ¿qué día exacto vence mi plazo si no tengo la fecha de ese requerimiento?"
)
_NECESSARY_CLARIFICATION_C04 = (
    "Sobre aquella acción popular contra DIMAR relacionada con el uso de una playa, "
    "¿qué orden impartió el juez en primera instancia y en qué plazo?"
)
_NECESSARY_CLARIFICATION_QUERIES = [
    pytest.param(_NECESSARY_CLARIFICATION_C02, id="C02-missing-start-date"),
    pytest.param(_NECESSARY_CLARIFICATION_C04, id="C04-unidentified-judicial-reference"),
    pytest.param(
        "¿Qué día vence mi plazo para reparar daños en la playa? Desconozco la "
        "fecha de notificación del requerimiento.",
        id="missing-notification-date",
    ),
    pytest.param(
        "Tengo un requerimiento para reparar daños en una playa. No sé la fecha "
        "del requerimiento. ¿Cuál es la fecha exacta de vencimiento?",
        id="missing-request-date-paraphrase",
    ),
    pytest.param(
        "En ese fallo sobre una playa, ¿qué ordenó el juez y en qué plazo?",
        id="unidentified-fallo-and-term",
    ),
    pytest.param(
        "Respecto de aquella sentencia sobre el litoral, ¿qué ordenó el Tribunal "
        "y qué plazo concedió?",
        id="unidentified-sentence-and-term",
    ),
]


@pytest.mark.parametrize("question", _NECESSARY_CLARIFICATION_QUERIES)
def test_necessary_clarification_fallback_precedes_domain_admission(question: str) -> None:
    result = _fallback(question)

    assert result.route == "needs_clarification"
    assert result.doc_types == []
    assert result.standalone_question == question
    assert result.expanded_query == query_enricher._normalize_expanded_query(question)


@pytest.mark.parametrize("question", [_NECESSARY_CLARIFICATION_C02, _NECESSARY_CLARIFICATION_C04])
@pytest.mark.parametrize("model_route", ["in_scope", "needs_clarification"])
def test_necessary_clarification_guard_is_not_overridden_by_domain_signals(
    question: str, model_route: str
) -> None:
    analysis = EnrichedQuery(
        route=model_route,
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa", "jurisprudencia"] if model_route == "in_scope" else [],
    )

    guarded = _apply_domain_guard(analysis, question, "")

    assert guarded.route == "needs_clarification"
    assert guarded.doc_types == []
    assert guarded.standalone_question == question
    assert guarded.expanded_query == query_enricher._normalize_expanded_query(question)
    assert analysis.route == model_route


@pytest.mark.parametrize(
    "question",
    [
        pytest.param(
            "Según el artículo 28 del Decreto 474 de 2015, ¿qué plazo se prevé "
            "para reparar daños en una playa?",
            id="abstract-legal-term",
        ),
        pytest.param(
            "Recibí el requerimiento de reparación de daños en la playa el 4 de "
            "febrero de 2025. ¿Qué día exacto vence el plazo?",
            id="request-date-already-provided",
        ),
        pytest.param(
            "En aquella sentencia de segunda instancia sobre una playa, radicado "
            "47001233100020110842502, ¿qué ordenó el juez y en qué plazo?",
            id="judicial-reference-with-complete-docket",
        ),
        pytest.param(
            "En aquella sentencia de Flury Valencia de 9 de julio de 2009 sobre "
            "una construcción en la costa, ¿qué ordenó la Sala?",
            id="judicial-reference-with-name-and-date",
        ),
        pytest.param(
            "¿Qué órdenes suelen impartir los jueces en acciones populares sobre "
            "el uso público de las playas?",
            id="general-jurisprudence-not-a-singular-decision",
        ),
        pytest.param(
            "Según aquella norma que regula las playas, ¿qué obligaciones "
            "existen para los concesionarios?",
            id="demonstrative-is-not-a-judicial-reference",
        ),
        pytest.param(
            "Recibí el requerimiento de reparación de daños en la playa el 4 de "
            "febrero de 2025. No tengo la fecha de la fotografía de la playa. "
            "¿Qué día exacto vence mi plazo?",
            id="different-missing-date-is-not-the-start-date",
        ),
        pytest.param(_QUALIFIED_LEGAL_J01, id="J01-identified-concept-keeps-L1-admission"),
    ],
)
def test_necessary_clarification_does_not_ask_for_sufficient_or_irrelevant_data(
    question: str,
) -> None:
    analysis = EnrichedQuery(
        route="needs_clarification",
        standalone_question=question,
        expanded_query=question,
    )

    assert _fallback(question).route == "in_scope"
    guarded = _apply_domain_guard(analysis, question, "")
    assert guarded.route == "in_scope"
    assert guarded.doc_types
    assert guarded.standalone_question == question


@pytest.mark.parametrize(
    ("question", "history", "expected_route"),
    [
        pytest.param(
            "Sobre aquella acción popular contra DIMAR relacionada con el uso de "
            "una playa, ¿qué orden impartió el juez en segunda instancia y en qué plazo?",
            "Usuario: Revisemos la sentencia de segunda instancia de Gabriel Carrero, "
            "radicado 47001233100020110842502.",
            "in_scope",
            id="one-judicial-identity-in-history",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C04,
            "Usuario: Revisemos los fallos radicados 47001233100020110842502 "
            "y 47001233300020160027000, relacionados con playas.",
            "needs_clarification",
            id="two-judicial-identities-in-history",
        ),
        pytest.param(
            "En aquella sentencia de segunda instancia sobre una playa, radicado "
            "47001233100020110842502, ¿qué ordenó el juez y en qué plazo?",
            "Usuario: Revisemos los fallos radicados 47001233100020110842502 "
            "y 47001233300020160027000, relacionados con playas.",
            "in_scope",
            id="current-complete-reference-resolves-two-history-cases",
        ),
        pytest.param(
            "En aquella sentencia de Flury Valencia de 9 de julio de 2009 sobre "
            "una construcción en la costa, ¿qué ordenó la Sala?",
            "Usuario: Revisemos los fallos radicados 47001233100020110842502 "
            "y 47001233300020160027000, relacionados con playas.",
            "in_scope",
            id="current-name-and-date-are-not-erased-by-history",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C02,
            "Usuario: La fotografía de la playa fue tomada el 4 de febrero de 2025.",
            "needs_clarification",
            id="unrelated-history-date-does-not-supply-the-start",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C02,
            "Usuario: No sé si la notificación del requerimiento de reparación "
            "fue el 4 o el 7 de febrero de 2025.",
            "needs_clarification",
            id="uncertain-history-date-does-not-supply-the-start",
        ),
    ],
)
def test_necessary_clarification_uses_only_resolved_relevant_history(
    question: str, history: str, expected_route: str
) -> None:
    analysis = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["jurisprudencia", "normativa"],
    )

    fallback = _fallback(question, history)
    guarded = _apply_domain_guard(analysis, question, history)
    assert fallback.route == expected_route
    assert guarded.route == expected_route
    if expected_route == "needs_clarification":
        assert fallback.doc_types == guarded.doc_types == []
    else:
        assert fallback.doc_types and guarded.doc_types
    assert guarded.standalone_question == question


@pytest.mark.parametrize("question", [_NECESSARY_CLARIFICATION_C02, _NECESSARY_CLARIFICATION_C04])
@pytest.mark.parametrize("mode", ["disabled", "provider_failure"])
def test_necessary_clarification_async_fallback_keeps_the_missing_data_contract(
    monkeypatch: pytest.MonkeyPatch, question: str, mode: str
) -> None:
    def unavailable_provider():
        if mode == "disabled":
            pytest.fail("Disabled enrichment must not instantiate a provider")
        raise RuntimeError("Offline necessary clarification provider failure")

    monkeypatch.setattr(query_enricher, "ENRICHMENT_ENABLED", mode != "disabled")
    monkeypatch.setattr(query_enricher, "get_active_provider", unavailable_provider)
    monkeypatch.setattr(
        query_enricher,
        "get_enrichment_llm",
        lambda: pytest.fail("The fallback must not instantiate a model"),
    )

    result = asyncio.run(query_enricher.enrich_query_async(question))

    assert result.route == "needs_clarification"
    assert result.doc_types == []
    assert result.standalone_question == question
    assert result.expanded_query == query_enricher._normalize_expanded_query(question)


@pytest.mark.parametrize(
    ("question", "expected_route"),
    [
        pytest.param(
            "Sobre aquella acción popular de una playa, escribe código Python "
            "para calcular el día exacto de vencimiento aunque no tengo la fecha "
            "del requerimiento.",
            "out_of_scope",
            id="programming-precedes-a-missing-start-date",
        ),
        pytest.param("¿Qué puedes hacer?", "conversation", id="meta-precedes-clarification"),
    ],
)
def test_necessary_clarification_keeps_off_topic_and_meta_precedence(
    question: str, expected_route: str
) -> None:
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )

    assert _fallback(question).route == expected_route
    guarded = _apply_domain_guard(admitted, question, "")
    assert guarded.route == expected_route
    assert guarded.doc_types == []


@pytest.mark.parametrize(
    ("question", "history", "expected_reason"),
    [
        pytest.param(
            "En la autorización temporal de la playa, ¿qué día se firmó el permiso? "
            "No tengo la fecha del requerimiento.",
            "",
            None,
            id="signature-day-is-not-a-deadline",
        ),
        pytest.param(
            "¿Qué día aprobaron el plazo de la concesión en una playa? "
            "No tengo la fecha del requerimiento.",
            "",
            None,
            id="approval-day-is-not-deadline-even-with-plazo",
        ),
        pytest.param(
            "En aquella sentencia de apelación del 10 de junio de 2020 sobre una playa, "
            "¿qué ordenó la Sala y en qué plazo?",
            "",
            "judicial_reference",
            id="appeal-description-and-date-do-not-identify-the-parties",
        ),
        pytest.param(
            "En aquella sentencia de apelación de Flury Valencia del 9 de julio de 2009 "
            "sobre una playa, ¿qué ordenó la Sala y en qué plazo?",
            "",
            None,
            id="appeal-description-with-parties-and-date-supplies-reference",
        ),
        pytest.param(
            "Recibí el requerimiento de reparación de daños en la playa el 4 de febrero "
            "de 2025. No tengo la fecha de notificación de la resolución de archivo. "
            "¿Qué día vence el plazo para reparar los daños?",
            "",
            None,
            id="unrelated-notification-is-not-the-deadline-start",
        ),
        pytest.param(
            "En aquella sentencia de primera instancia del 9 de julio de 2009 sobre "
            "una playa, ¿qué ordenó el juez y en qué plazo?",
            "",
            "judicial_reference",
            id="instance-and-date-alone-do-not-identify-current-case",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C04,
            "Usuario: Revisemos aquella sentencia de primera instancia del 9 de julio de 2009.",
            "judicial_reference",
            id="instance-and-date-alone-do-not-identify-history-case",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C04.replace("primera instancia", "segunda instancia"),
            "Usuario: Revisemos la sentencia de Flury Valencia de 9 de julio de 2009, "
            "radicado 23001233100019981029001.",
            None,
            id="history-name-date-and-adjacent-docket-identify-one-case",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C04,
            "Usuario: Revisemos la sentencia de Flury Valencia de 9 de julio de 2009, "
            "radicado 23001233100019981029001, y la sentencia de Inversiones E y D "
            "de 9 de noviembre de 2022, radicado 47001233300020160027000.",
            "judicial_reference",
            id="two-named-history-cases-remain-ambiguous",
        ),
        pytest.param(
            "Entre aquella sentencia de Flury Valencia de 9 de julio de 2009, radicado "
            "23001233100019981029001, y aquel fallo de Inversiones E y D de 9 de noviembre "
            "de 2022, radicado 47001233300020160027000, sin elegir uno, ¿qué ordenó "
            "el juez sobre la playa y en qué plazo?",
            "",
            "judicial_reference",
            id="two-current-cases-do-not-supply-a-unique-referent",
        ),
        pytest.param(
            "En aquella sentencia sobre una playa, radicado 23001-23-31-000-1998-10290-01 "
            "(23001233100019981029001), ¿qué ordenó la Sala y en qué plazo?",
            "",
            None,
            id="current-docket-with-and-without-hyphens-is-one-reference",
        ),
        pytest.param(
            _NECESSARY_CLARIFICATION_C04.replace("primera instancia", "segunda instancia"),
            "Usuario: Revisemos el radicado 23001-23-31-000-1998-10290-01 "
            "(23001233100019981029001), sobre una playa.",
            None,
            id="history-docket-with-and-without-hyphens-is-one-reference",
        ),
        pytest.param(
            "En aquella sentencia de Flury Valencia de 9 de julio de 2009, radicado "
            "23001233100019981029001, ¿qué ordenó la Sala sobre la construcción "
            "en la costa y en qué plazo?",
            "",
            None,
            id="current-name-date-and-adjacent-docket-identify-one-case",
        ),
    ],
)
def test_necessary_clarification_identifier_and_date_boundaries(
    question: str, history: str, expected_reason: str | None
) -> None:
    from rag.core.domain_scope import clarification_reason

    assert clarification_reason(question, history) == expected_reason
    expected_route = "needs_clarification" if expected_reason is not None else "in_scope"
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["jurisprudencia", "normativa"],
    )

    fallback = _fallback(question, history)
    guarded = _apply_domain_guard(admitted, question, history)
    assert fallback.route == guarded.route == expected_route
    if expected_reason is not None:
        assert fallback.doc_types == guarded.doc_types == []
    else:
        assert fallback.doc_types and guarded.doc_types
    assert guarded.standalone_question == question


@pytest.mark.parametrize(
    "question",
    [
        "ola, puedo aser esto en la playa?",
        "¿Puedo hacer eso en una playa?",
    ],
    ids=["PR01-typos", "independent-missing-activity"],
)
def test_coastal_access_missing_activity_overrides_terminal_model_route(question: str) -> None:
    model_result = EnrichedQuery(
        route="conversation", standalone_question=question, expanded_query=question
    )
    guarded = _apply_domain_guard(model_result, question, "")
    assert guarded.route == "needs_clarification"
    assert guarded.doc_types == []


@pytest.mark.parametrize(
    "question",
    [
        "me pueden cobrar por entra a la playa??",
        "¿Pueden cobrarme por pasar a una playa pública?",
    ],
    ids=["PR08-typos", "independent-public-entry"],
)
def test_coastal_access_entry_payment_is_admitted_without_municipality(question: str) -> None:
    rejected = EnrichedQuery(
        route="needs_clarification", standalone_question=question, expanded_query=question
    )
    assert _fallback(question).route == "in_scope"
    guarded = _apply_domain_guard(rejected, question, "")
    assert guarded.route == "in_scope"
    assert set(guarded.doc_types) == {"normativa", "jurisprudencia"}


def test_coastal_access_concrete_obstruction_asks_for_place_before_search() -> None:
    question = "hola, un hotel puso una cerca y no deja pasar a la playa"
    eager = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query="Un hotel impide el acceso a una playa. ¿Qué norma o permiso lo regula?",
        doc_types=["normativa"],
    )
    guarded = _apply_domain_guard(eager, question, "")
    assert guarded.route == "needs_clarification"
    assert guarded.doc_types == []


@pytest.mark.parametrize(
    "place", ["El Rodadero, Santa Marta", "Coveñas", "el rodadero, santa marta", "coveñas"]
)
def test_coastal_access_place_reply_completes_a_specific_previous_case(place: str) -> None:
    question = f"Es en {place}."
    history = (
        "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio o playa ocurre el bloqueo del hotel?"
    )
    rejected = EnrichedQuery(
        route="needs_clarification", standalone_question=question, expanded_query=question
    )
    guarded = _apply_domain_guard(rejected, question, history)
    assert guarded.route == "in_scope"
    assert guarded.doc_types


@pytest.mark.parametrize(
    "history",
    [
        "",
        "Asistente: Un hotel puso una cerca y no deja pasar a la playa. ¿En qué municipio ocurre?",
        (
            "Usuario: Un hotel puso una cerca en una playa y otro hotel cerró otra playa.\n"
            "Asistente: ¿Cuál de los dos casos y en qué municipio?"
        ),
    ],
    ids=["no-case", "assistant-only-facts", "two-unidentified-cases"],
)
def test_coastal_access_expansion_cannot_create_the_case_for_a_place_reply(history: str) -> None:
    question = "Es en El Rodadero, Santa Marta."
    invented = "Un hotel puso una cerca y bloqueó el acceso a la playa en El Rodadero, Santa Marta."
    model_result = EnrichedQuery(
        route="in_scope",
        standalone_question=invented,
        expanded_query=invented,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(model_result, question, history).route != "in_scope"


@pytest.mark.parametrize(
    "question",
    [
        "¿Cuánto cobra el hotel por una habitación?",
        "¿Dónde puedo comprar un almuerzo?",
        "Me cobraron por estacionar en un centro comercial, ¿es legal?",
    ],
)
def test_coastal_access_payment_words_do_not_supply_coastal_context(question: str) -> None:
    assert _fallback(question).route != "in_scope"


def test_coastal_access_service_payment_does_not_become_a_public_entry_question() -> None:
    question = "¿Qué permiso se exige para cobrar por estacionamiento junto a una playa?"
    result = _fallback(question)
    assert result.route == "in_scope"
    assert result.standalone_question == question
    assert "estacionamiento" in result.expanded_query


def test_coastal_access_unrelated_turn_does_not_complete_pending_place() -> None:
    history = (
        "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio ocurre?"
    )
    question = "¿Cuál es la mejor receta de arepas de huevo?"
    eager = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(eager, question, history).route == "out_of_scope"


def test_coastal_access_missing_source_is_not_missing_user_context() -> None:
    question = (
        "¿Qué dice la Ley 1437 de 2011 sobre la caducidad de los actos administrativos en playas?"
    )
    rejected = EnrichedQuery(
        route="needs_clarification", standalone_question=question, expanded_query=question
    )
    assert _apply_domain_guard(rejected, question, "").route == "in_scope"


@pytest.mark.parametrize("place", ["santa marta", "bahía azul"])
def test_coastal_access_initial_place_is_not_asked_again_when_lowercase(place: str) -> None:
    question = f"Un hotel puso una cerca y no deja pasar a la playa en {place}."
    rejected = EnrichedQuery(
        route="needs_clarification", standalone_question=question, expanded_query=question
    )
    assert _apply_domain_guard(rejected, question, "").route == "in_scope"


def test_coastal_access_changed_topic_does_not_complete_an_older_case() -> None:
    history = (
        "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio ocurre el bloqueo?\n"
        "Usuario: Ahora quiero saber qué permiso requiere un muelle en la playa.\n"
        "Asistente: El permiso se examina según sus condiciones."
    )
    question = "Es en Coveñas."
    eager = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(eager, question, history).route != "in_scope"


def test_coastal_access_vague_place_does_not_license_invented_location() -> None:
    history = (
        "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio ocurre el bloqueo?"
    )
    question = "Es en la playa."
    eager = EnrichedQuery(
        route="in_scope",
        standalone_question="En Santa Marta",
        expanded_query="En Santa Marta",
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(eager, question, history).route == "needs_clarification"


@pytest.mark.parametrize(
    "question",
    [
        "En el Decreto 2324 de 1984, explica los permisos de playa.",
        "En la sentencia sobre la playa, explica la competencia de DIMAR.",
    ],
)
def test_coastal_access_legal_introduction_is_not_a_location_reply(question: str) -> None:
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["jurisprudencia"],
    )
    assert _apply_domain_guard(admitted, question, "").route == "in_scope"


@pytest.mark.parametrize("ambiguous", [False, True])
def test_coastal_access_activity_antecedent_must_be_unique(ambiguous: bool) -> None:
    prior = "¿Puedo vender artesanías en la playa"
    prior += " o instalar una caseta?" if ambiguous else "?"
    history = f"Usuario: {prior}\nAsistente: Respuesta sobre esa actividad."
    question = "¿Puedo hacer esto en la playa?"
    model_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(model_result, question, history).route == (
        "needs_clarification" if ambiguous else "in_scope"
    )


def test_coastal_access_oversized_context_is_not_used_as_a_standalone_question() -> None:
    prior = "Un hotel puso una cerca y no deja pasar a la playa. " + "detalle " * 550
    history = f"Usuario: {prior}\nAsistente: ¿En qué municipio ocurre el bloqueo?"
    question = "Es en Coveñas."
    model_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    result = _apply_domain_guard(model_result, question, history)
    assert result.route == "needs_clarification" and len(result.standalone_question) <= 4000


@pytest.mark.parametrize(
    "question",
    [
        "Un hotel bloqueó el acceso a una playa. Según el artículo 166 del Decreto 2324 de 1984, ¿puede apropiarse del suelo o solo usarlo mediante permiso?",
        "Un vecino colocó una barrera e impide el paso a la playa. Explica qué derechos concede el artículo 166 del Decreto 2324 de 1984.",
    ],
)
def test_precommit_guard_general_normative_effect_does_not_require_municipality(question):
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(admitted, question, "").route == "in_scope"
    assert _fallback(question).route == "in_scope"


def test_precommit_guard_explanatory_introduction_preserves_semantic_admission():
    question = "En lenguaje sencillo, interpreta lo relativo a pescar en una playa."
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(admitted, question, "").route == "in_scope"


def test_precommit_guard_named_norm_does_not_remove_local_authority_clarification():
    question = "Un hotel bloqueó el acceso a una playa. Según el artículo 166 del Decreto 2324 de 1984, ¿ante qué autoridad debo denunciar esta cerca?"
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _apply_domain_guard(admitted, question, "").route == "needs_clarification"


@pytest.mark.parametrize(
    "question",
    [
        pytest.param(
            "Un hotel puso una cerca y no deja pasar a la playa en Coveñas, dime qué opinas.",
            id="known-place-before-request",
        ),
        pytest.param(
            "Un hotel puso una cerca y no deja pasar a la playa en Santa Marta, "
            "Magdalena, dime qué opinas.",
            id="comma-in-known-place-before-request",
        ),
        pytest.param(
            "Un hotel bloqueó el acceso a una playa. Ya inicié un trámite municipal. "
            "Según el artículo 166 del Decreto 2324 de 1984, ¿puede apropiarse "
            "del suelo o solo usarlo mediante permiso?",
            id="past-local-procedure-national-question",
        ),
        *[
            pytest.param(
                "Un hotel bloqueó el acceso a una playa. "
                f"{verb} el artículo 166 del Decreto 2324 de 1984.",
                id=f"named-national-rule-{verb.casefold()}",
            )
            for verb in ("Explica", "Resume", "Describe")
        ],
    ],
)
def test_tres_rechazos_admitted_question_survives_fallback_and_guard(question: str) -> None:
    from rag.core.domain_scope import clarification_reason

    model_result = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert clarification_reason(question) is None
    assert _fallback(question).route == "in_scope"
    guarded = _apply_domain_guard(model_result, question, "")
    assert guarded.route == "in_scope"
    assert guarded.standalone_question == guarded.expanded_query == question


@pytest.mark.parametrize(
    "local_request",
    [
        "¿qué trámite municipal debo iniciar para retirar la cerca?",
        "¿ante qué autoridad debo denunciar esta cerca?",
    ],
    ids=["requested-local-procedure", "requested-local-authority"],
)
def test_tres_rechazos_requested_local_action_retains_location_guard(local_request: str) -> None:
    from rag.core.domain_scope import clarification_reason

    question = (
        "Un hotel bloqueó el acceso a una playa. Según el artículo 166 del "
        "Decreto 2324 de 1984, " + local_request
    )
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert clarification_reason(question) == "access_location"
    assert _fallback(question).route == "needs_clarification"
    guarded = _apply_domain_guard(admitted, question, "")
    assert guarded.route == "needs_clarification" and guarded.doc_types == []


@pytest.mark.parametrize("pending_location", [False, True], ids=["no-case", "pending-case"])
@pytest.mark.parametrize("initial_route", ["out_of_scope", "needs_clarification", "in_scope"])
def test_tres_rechazos_explanatory_introduction_is_never_a_place(
    pending_location: bool,
    initial_route: str,
) -> None:
    from rag.core.domain_scope import _access_place_reply, clarification_reason

    question = "En palabras sencillas, explica si puedo pescar en la playa."
    history = (
        "Usuario: Un vecino colocó una barrera y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio ocurre el bloqueo?"
        if pending_location
        else ""
    )
    model_result = EnrichedQuery(
        route=initial_route,
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"] if initial_route == "in_scope" else [],
    )
    assert _access_place_reply(question) is None
    assert clarification_reason(question, history) is None
    guarded = _apply_domain_guard(model_result, question, history)
    assert guarded.route == "in_scope"
    assert guarded.standalone_question == guarded.expanded_query == question


def test_tres_rechazos_vague_place_does_not_resolve_pending_case() -> None:
    from rag.core.domain_scope import _access_place_reply, clarification_reason

    question = "Es en la playa."
    history = (
        "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio ocurre el bloqueo?"
    )
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _access_place_reply(question) is None
    assert clarification_reason(question, history) == "access_location"
    assert _fallback(question, history).route == "needs_clarification"
    assert _apply_domain_guard(admitted, question, history).route == "needs_clarification"


def test_tres_rechazos_comma_is_preserved_inside_actual_place_reply() -> None:
    from rag.core.domain_scope import _access_place_reply

    question = "Es en Santa Marta, Magdalena."
    history = (
        "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\n"
        "Asistente: ¿En qué municipio ocurre el bloqueo?"
    )
    rejected = EnrichedQuery(
        route="needs_clarification", standalone_question=question, expanded_query=question
    )
    assert _access_place_reply(question) == "Santa Marta, Magdalena"
    assert _fallback(question, history).route == "in_scope"
    guarded = _apply_domain_guard(rejected, question, history)
    assert guarded.route == "in_scope"
    assert "Santa Marta, Magdalena" in guarded.standalone_question
    assert "Santa Marta, Magdalena" in guarded.expanded_query


def test_tres_rechazos_past_local_procedure_in_history_is_not_a_current_request() -> None:
    question = (
        "Un hotel bloqueó el acceso a una playa. Según el artículo 166 del "
        "Decreto 2324 de 1984, ¿puede apropiarse del suelo o solo usarlo mediante permiso?"
    )
    history = (
        "Usuario: Ya inicié un trámite municipal.\nAsistente: Has indicado una actuación anterior."
    )
    admitted = EnrichedQuery(
        route="in_scope",
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"],
    )
    assert _fallback(question, history).route == "in_scope"
    guarded = _apply_domain_guard(admitted, question, history)
    assert guarded.route == "in_scope"
    assert guarded.standalone_question == guarded.expanded_query == question


def test_tres_rechazos_style_modifier_inside_case_does_not_invent_a_location():
    from rag.core.domain_scope import clarification_reason

    question = "Un hotel puso una cerca y no deja pasar a la playa. En palabras sencillas, dime qué opinas."
    assert clarification_reason(question) == "access_location"


@pytest.mark.parametrize(
    "local_query",
    [
        "Necesito conocer los requisitos municipales.",
        "¿Cómo se inicia el trámite municipal?",
        "Describe los requisitos municipales.",
    ],
)
def test_tres_rechazos_current_procedure_frames_keep_local_clarification(local_query):
    from rag.core.domain_scope import clarification_reason

    question = (
        "Un hotel bloqueó el acceso a una playa. Explica el efecto del artículo 166 del Decreto 2324 de 1984; "
        + local_query
    )
    assert clarification_reason(question) == "access_location"


def test_tres_rechazos_past_description_is_not_a_present_local_request():
    from rag.core.domain_scope import clarification_reason

    question = "Un hotel bloqueó el acceso a una playa. Ya describí los requisitos municipales. Resume el artículo 166 del Decreto 2324 de 1984."
    assert clarification_reason(question) is None


def test_tres_rechazos_reported_how_is_not_a_current_request():
    from rag.core.domain_scope import clarification_reason

    question = "Un hotel bloqueó el acceso a una playa. Ya relaté cómo se inicia el trámite municipal. Resume el artículo 166 del Decreto 2324 de 1984."
    assert clarification_reason(question) is None


@pytest.mark.parametrize(
    ("tail", "local"),
    [
        (
            "Resume el artículo 166 del Decreto 2324 de 1984 y dime qué trámite municipal debo iniciar.",
            True,
        ),
        (
            "Describe el artículo 166 del Decreto 2324 de 1984 y necesito conocer los requisitos municipales.",
            True,
        ),
        (
            "Resume el artículo 166 del Decreto 2324 de 1984 y ya describí los requisitos municipales.",
            False,
        ),
    ],
)
def test_tres_rechazos_coordinated_current_request_is_not_lost(tail, local):
    from rag.core.domain_scope import clarification_reason

    question = "Un hotel puso una cerca y bloqueó el acceso a la playa. " + tail
    assert clarification_reason(question) == ("access_location" if local else None)


@pytest.mark.parametrize(
    ("tail", "local"),
    [
        ("Quiero saber qué trámite municipal debo iniciar.", True),
        ("Dime los requisitos municipales.", True),
        ("Ya quería saber qué trámite municipal debía iniciar.", False),
        ("Ya indiqué los requisitos municipales.", False),
    ],
)
def test_tres_rechazos_direct_local_requests_and_past_reports(tail, local):
    from rag.core.domain_scope import clarification_reason

    question = (
        "Un hotel bloqueó el acceso a una playa. Resume el artículo 166 del Decreto 2324 de 1984. "
        + tail
    )
    assert clarification_reason(question) == ("access_location" if local else None)


@pytest.mark.parametrize("model_route", ["in_scope", "needs_clarification"])
@pytest.mark.parametrize(
    ("question", "local"),
    [
        (
            "Un hotel bloqueó el acceso a una playa. Explica el artículo 166 del Decreto 2324 de 1984. Quisiera saber qué trámite municipal debo iniciar.",
            True,
        ),
        (
            "Un hotel bloqueó el acceso a una playa. Ya había querido saber qué trámite municipal debía iniciar. Resume el artículo 166 del Decreto 2324 de 1984.",
            False,
        ),
    ],
    ids=["current-request", "past-report"],
)
def test_quisiera_current_request_and_past_report(question, local, model_route):
    from rag.core.domain_scope import clarification_reason

    expected = "needs_clarification" if local else "in_scope"
    analyzed = EnrichedQuery(
        route=model_route,
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"] if model_route == "in_scope" else [],
    )
    assert clarification_reason(question) == ("access_location" if local else None)
    assert _fallback(question).route == expected
    guarded = _apply_domain_guard(analyzed, question, "")
    assert guarded.route == expected
    assert guarded.standalone_question == guarded.expanded_query == question
    if local:
        assert guarded.doc_types == []
    else:
        expected_types = (
            {"normativa"} if model_route == "in_scope" else {"jurisprudencia", "normativa"}
        )
        assert set(guarded.doc_types) == expected_types


@pytest.mark.parametrize("model_route", ["in_scope", "needs_clarification"])
@pytest.mark.parametrize(
    ("question", "has_place"),
    [
        ("Un hotel puso una cerca y no deja pasar a la playa en Coveñas, ¿qué puedo hacer?", True),
        ("Un hotel puso una cerca y no deja pasar a la playa en Coveñas; ¿qué puedo hacer?", True),
        ("Un hotel puso una cerca y no deja pasar a la playa en Coveñas ¿qué puedo hacer?", True),
        (
            "Un hotel puso una cerca y no deja pasar a la playa en Santa Marta, Magdalena, ¿qué puedo hacer?",
            True,
        ),
        ("Un hotel puso una cerca y no deja pasar a la playa en Coveñas, qué puedo hacer?", True),
        ("Un hotel puso una cerca y no deja pasar a la playa, ¿qué puedo hacer?", False),
        (
            "Un hotel puso una cerca y no deja pasar a la playa. En palabras sencillas, ¿qué puedo hacer?",
            False,
        ),
        (
            "Un hotel puso una cerca y no deja pasar a la playa. En general, ¿qué puedo hacer?",
            False,
        ),
        (
            "Un hotel puso una cerca y no deja pasar a la playa. En particular, qué puedo hacer?",
            False,
        ),
        (
            "Un hotel puso una cerca y no deja pasar a la playa. En este caso, ¿qué puedo hacer?",
            False,
        ),
    ],
    ids=[
        "comma",
        "semicolon",
        "space",
        "compound",
        "no-opening-mark",
        "missing",
        "style",
        "general",
        "particular",
        "this-case",
    ],
)
def test_ubicacion_interrogativa_preserves_place_not_style(question, has_place, model_route):
    from rag.core.domain_scope import _access_place_reply, clarification_reason

    analyzed = EnrichedQuery(
        route=model_route,
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"] if model_route == "in_scope" else [],
    )
    expected = "in_scope" if has_place else "needs_clarification"
    assert clarification_reason(question) == (None if has_place else "access_location")
    assert _fallback(question).route == expected
    guarded = _apply_domain_guard(analyzed, question, "")
    assert guarded.route == expected
    assert guarded.standalone_question == guarded.expanded_query == question
    assert _access_place_reply(question) is None
    if not has_place:
        assert guarded.doc_types == []


@pytest.mark.parametrize("model_route", ["in_scope", "needs_clarification"])
@pytest.mark.parametrize(
    "question",
    [
        "Un hotel puso una cerca y no deja pasar a la playa en temporada alta, ¿qué puedo hacer?",
        "Un hotel puso una cerca y no deja pasar a la playa en temporada baja, qué puedo hacer?",
        "Un hotel puso una cerca y no deja pasar a la playa en vacaciones; ¿qué puedo hacer?",
    ],
    ids=["high-season", "low-season", "holidays"],
)
def test_ubicacion_interrogativa_temporal_modifier_is_not_a_place(question, model_route):
    from rag.core.domain_scope import clarification_reason

    analyzed = EnrichedQuery(
        route=model_route,
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"] if model_route == "in_scope" else [],
    )
    assert clarification_reason(question) == "access_location"
    assert _fallback(question).route == "needs_clarification"
    assert _apply_domain_guard(analyzed, question, "").route == "needs_clarification"


@pytest.mark.parametrize("model_route", ["in_scope", "needs_clarification"])
@pytest.mark.parametrize("reply", ["En general.", "Es en vacaciones."])
def test_ubicacion_interrogativa_non_place_reply_keeps_case_pending(reply, model_route):
    from rag.core.domain_scope import _access_place_reply, clarification_reason

    history = "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?"
    analyzed = EnrichedQuery(
        route=model_route,
        standalone_question=reply,
        expanded_query=reply,
        doc_types=["normativa"] if model_route == "in_scope" else [],
    )
    assert _access_place_reply(reply) is None
    assert clarification_reason(reply, "") is None
    assert clarification_reason(reply, history) == "access_location"
    guarded = _apply_domain_guard(analyzed, reply, history)
    assert guarded.route == "needs_clarification" and guarded.doc_types == []


@pytest.mark.parametrize("model_route", ["in_scope", "needs_clarification"])
@pytest.mark.parametrize(
    ("history", "expected_case"),
    [
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: En general.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            "Un hotel puso una cerca y no deja pasar a la playa.",
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Es en vacaciones.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            "Un hotel puso una cerca y no deja pasar a la playa.",
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: En general.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Es en vacaciones.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            "Un hotel puso una cerca y no deja pasar a la playa.",
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Resume el artículo 166 del Decreto 2324 de 1984 sobre permisos de playa.\nAsistente: La norma distingue permisos y concesiones. [doc1]",
            None,
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: En el otro caso.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            None,
        ),
        (
            "Usuario (truncado): Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Es en vacaciones.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            None,
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Es en vacaciones.\nAsistente (truncado): ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            None,
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Un vecino colocó una barrera y bloqueó el acceso a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            "Un vecino colocó una barrera y bloqueó el acceso a la playa.",
        ),
        (
            "Usuario: Un hotel puso una cerca y no deja pasar a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?\nUsuario: Dos hoteles pusieron cercas y bloquearon el acceso a la playa.\nAsistente: ¿En qué municipio o playa ocurre el bloqueo del acceso que describes?",
            None,
        ),
    ],
    ids=[
        "general",
        "holidays",
        "two-invalid",
        "new-topic",
        "other-case",
        "truncated-user",
        "truncated-assistant",
        "new-concrete-case",
        "ambiguous-cases",
    ],
)
def test_continuidad_ubicacion_preserves_only_the_active_case(history, expected_case, model_route):
    from rag.core.domain_scope import clarification_reason

    question = "Es en Coveñas."
    analyzed = EnrichedQuery(
        route=model_route,
        standalone_question=question,
        expanded_query=question,
        doc_types=["normativa"] if model_route == "in_scope" else [],
    )
    result = _apply_domain_guard(analyzed, question, history)
    if expected_case:
        assert clarification_reason(question, history) is None
        assert result.route == "in_scope"
        assert expected_case in result.standalone_question
        assert "Coveñas" in result.standalone_question
        assert result.standalone_question == result.expanded_query
        assert "vacaciones" not in result.standalone_question
        if "vecino" in expected_case:
            assert "hotel" not in result.standalone_question
    else:
        assert clarification_reason(question, history) == "activity"
        assert result.route == "needs_clarification" and result.doc_types == []


@pytest.mark.parametrize(
    "question",
    [
        pytest.param(
            "En palabras sencillas, explica si puedo pescar en la playa.",
            id="exact-question",
        ),
        pytest.param("¿Se puede pescar en el mar?", id="independent-formulation"),
    ],
)
def test_fishing_modal_scope_fallback(question: str) -> None:
    result = _fallback(question)

    assert result.route == "in_scope"
    assert result.doc_types
    assert result.standalone_question == question
    assert result.expanded_query == question


@pytest.mark.parametrize(
    ("question", "initial_route", "expected_route"),
    [
        pytest.param(
            "¿Puedo pescar en un río de montaña?",
            "out_of_scope",
            "out_of_scope",
            id="inland-out",
        ),
        pytest.param(
            "¿Puedo pescar en un río de montaña?",
            "needs_clarification",
            "needs_clarification",
            id="inland-needs",
        ),
        *[
            pytest.param(question, initial_route, "out_of_scope", id=f"{label}-{initial_route}")
            for label, question in [
                ("poem", "Escribe un poema sobre pescar en la playa."),
                ("recipe", "Dame una receta para cocinar pescado en la playa."),
            ]
            for initial_route in ["out_of_scope", "needs_clarification", "in_scope"]
        ],
    ],
)
def test_fishing_modal_scope_preserves_negative_precedence(
    question: str,
    initial_route: str,
    expected_route: str,
) -> None:
    model_result = EnrichedQuery(
        route=initial_route,
        standalone_question=question,
        expanded_query="¿Qué permisos necesito para pescar en una playa?",
        doc_types=["normativa"] if initial_route == "in_scope" else [],
    )
    assert _fallback(question).route != "in_scope"

    guarded = _apply_domain_guard(model_result, question, "")

    assert guarded.route == expected_route
    assert guarded.doc_types == []
