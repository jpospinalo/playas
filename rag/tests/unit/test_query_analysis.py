"""Pruebas de alcance, fallback y validación del analizador de consultas."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import rag.core.query_enricher as query_enricher
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
# equipo jurídico (ver PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md).

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
        "¿Qué disposiciones rigen una laguna interior no navegable dentro de "
        "una reserva forestal?"
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


# ── Revisión posterior — banco completo de 21 preguntas jurídicas ──────────
#
# Texto verbatim entregado por el equipo jurídico para esta ronda de
# revisión. No se resume, parafrasea ni sustituye por frases más simples
# (ver informe de esta ronda). Cada pregunta debe llegar a in_scope y
# alcanzar el recuperador; "válida" no implica que el corpus tenga
# evidencia suficiente para una conclusión jurídica completa.

CASO_21_01_MOTOS_PARASAILING = (
    """Vivo en un apartamento frente a la playa de El Rodadero desde hace varios años. Últimamente he notado que en la zona cercana al edificio donde vivimos están funcionando motos acuáticas y actividades de parasailing casi todo el día, especialmente en temporadas altas. Algunos vecinos consideran que estas actividades atraen turismo y ayudan a la economía del sector, pero otros creen que las motos están pasando demasiado cerca de las personas que se bañan y que eso puede generar accidentes o problemas de seguridad.
Hace unos días incluso hubo una discusión entre turistas y trabajadores de una empresa de deportes náuticos porque unos pedían que se alejaran más de la orilla y la empresa respondía que tenían autorización para operar ahí. La verdad yo no sé cómo funciona ese tema ni quién define hasta dónde pueden trabajar estas empresas. ¿DIMAR establece zonas específicas para estas actividades o las empresas pueden operar libremente en cualquier parte de la playa mientras tengan permiso?"""
)

CASO_21_02_CLUB_NAUTICO_MUELLE = (
    """Con unos socios queremos construir un pequeño club náutico con muelle flotante en una playa de Santa Marta, con capacidad para 20 embarcaciones. Ya tenemos el diseño y el capital. ¿Basta con pedir la concesión marítima directamente a la Capitanía de Puerto y esperar la aprobación, o hay pasos previos? ¿Cuánto tiempo estimado nos tomaría, y qué pasa si un vecino o la comunidad se opone al proyecto?"""
)

CASO_21_03_HOTEL_MALLA_GUARDIA = (
    """Frente a mi casa hay un hotel que tiene concesión marítima sobre la franja de playa. Desde hace un mes pusieron una malla y un guardia que no deja pasar a nadie que no sea huésped, argumentando que es 'zona restringida por seguridad del hotel'. Cuando les pregunté con qué autorización hicieron eso, me dijeron que como tienen la concesión, pueden decidir quién entra. ¿Es legal que un hotel declare por su cuenta un área restringida en la playa? ¿Y qué puedo hacer si efectivamente me están negando el paso?"""
)

CASO_21_04_ALQUILER_CARPAS_TARIMA = (
    """Mi familia vive desde hace muchos años frente a una playa y durante las vacaciones solemos alquilar carpas, mesas y sillas a los turistas para obtener ingresos adicionales. Este año queremos ampliar el negocio instalando una tarima de madera, una zona con sombrillas y un pequeño módulo desmontable donde vender bebidas. Pensamos dejar toda la infraestructura instalada durante tres meses porque desmontarla todos los días resulta muy costoso.
Un vecino nos dijo que, como las estructuras son desmontables y no vamos a construir nada en cemento, no necesitamos autorización de DIMAR.
¿Es cierto que podemos instalar toda esa infraestructura sin solicitar un permiso? En caso de necesitarlo, ¿qué condiciones establece la norma para este tipo de instalaciones temporales?"""
)

CASO_21_05_FESTIVAL_JAC = (
    """Soy presidente de una Junta de Acción Comunal de un corregimiento costero y estamos organizando un festival cultural en la playa para promover el turismo local. Esperamos la asistencia de unas 2.000 personas y habrá presentaciones musicales, venta de comidas, sonido profesional y actividades recreativas durante todo un fin de semana.
La Alcaldía nos informó que apoya el evento y nos expedirá el permiso correspondiente. Sin embargo, algunas personas nos dicen que, por realizarse en la playa, debemos hacer un trámite adicional ante otra entidad.
¿Con la autorización de la Alcaldía es suficiente para realizar el evento o debemos solicitar algún otro permiso? En caso de necesitarlo, ¿qué documentos debemos presentar?"""
)

CASO_21_06_PESCADOR_TAGANGA = (
    """Soy pescador artesanal en Playa Taganga, Santa Marta. Desde hace veinte años trabajo en esta playa: allí dejo mi bote y vendo el pescado que capturo. Hace poco me enteré de que una empresa quiere hacer un proyecto turístico en la zona y que podría empezar a utilizar parte de la playa donde normalmente trabajo. Me preocupa que, por el proyecto, ya no pueda seguir realizando mi actividad como antes. ¿Qué puedo hacer para conocer qué se va a construir y para expresar mi preocupación ante las autoridades?"""
)

CASO_21_07_VENDEDORA_PLAYA_CRISTAL = (
    """Yo vivo en una vereda y cada temporada de vacaciones viajo hasta Playa Cristal para vender jugos y las artesanías que hago con mis hijos. Con lo que gano allí compro la comida de la casa y pago parte de los estudios de mis hijos. Llevo un puesto pequeño que puedo recoger al final del día y solo trabajo durante la temporada en la que llegan más turistas. Pero me preocupa que un día llegue una autoridad y me diga que no puedo seguir vendiendo o que me pongan una multa. Yo no sé si estoy haciendo algo ilegal ni qué tendría que hacer para poder seguir trabajando tranquila. ¿Qué puedo hacer?"""
)

CASO_21_08_RESIDENTE_CLUB_PLAYA = (
    """Vivo desde niño en El Rodadero, Santa Marta, y siempre he ido a esa playa con mi familia. Hace poco escuché que una empresa quiere poner un club de playa y que algunas partes podrían quedar solo para las personas que paguen o sean clientes del lugar. A mí me preocupa que los habitantes de siempre ya no podamos disfrutar la playa como antes. ¿Qué puedo hacer para saber si eso se puede hacer y qué puedo hacer si de verdad empiezan a impedirle a la gente entrar?"""
)

CASO_21_09_COMUNIDAD_INDIGENA_GUAJIRA = (
    """Pertenezco a una comunidad indígena que vive cerca de una playa en La Guajira. Desde hace muchos años usamos ese lugar para nuestros rituales y otras actividades de nuestra comunidad. Ahora nos enteramos de que quieren hacer un proyecto turístico allí y nos preocupa que eso cambie la forma en la que usamos el lugar o que ya no podamos entrar como antes. Nosotros no sabemos bien qué puede hacer la comunidad en una situación así ni si tienen que escucharnos antes de tomar una decisión. ¿Qué podemos hacer?"""
)

CASO_21_10_PROYECTO_TURISTICO_PLAYA_BLANCA = (
    """Soy joven y quiero montar un proyecto turístico en Playa Blanca, Cartagena. La idea es poner baños, duchas, algunos kioscos y espacios para que los visitantes puedan estar más cómodos. He preguntado un poco y me han dicho que para hacer algo así necesito pedir permiso, pero no entiendo muy bien qué debo tramitar ni qué responsabilidades tendría después. También me preocupa que el proyecto termine afectando la playa o a las personas que ya trabajan y viven de ella. ¿Qué debería tener en cuenta antes de empezar?"""
)

CASO_21_11_BODA_EN_LA_PLAYA = (
    """Tengo una empresa de eventos en Cartagena y un cliente me contrató para realizar una boda sobre la playa. Debemos instalar una tarima, una pista de baile, una carpa, iluminación y mobiliario que permanecerá instalado durante dos días.
Es la primera vez que organizo un evento en una playa y no sé si basta con el permiso del hotel donde se realizará la ceremonia.
¿El permiso del hotel es suficiente para instalar toda esa infraestructura o debo tramitar otra autorización?"""
)

CASO_21_12_CAMPEONATO_FUTBOL_PLAYA = (
    """Cada año organizamos un campeonato de fútbol playa en Cartagena y normalmente desmontamos toda la infraestructura al terminar. Este año queremos dejar instaladas las graderías y las carpas durante un mes porque tendremos varios torneos consecutivos.
Algunos organizadores dicen que no hay problema porque todo fue autorizado al inicio del campeonato.
¿Podemos dejar instalada la infraestructura hasta el siguiente torneo o existe alguna obligación cuando termine el permiso?"""
)

CASO_21_13_HOTEL_BOCAGRANDE_ENTREGA_AREA = (
    """Soy propietario de un hotel en Bocagrande (Cartagena). Hace unos meses obtuve un permiso para realizar un evento privado en la playa frente al hotel. El evento terminó sin inconvenientes, pero la Capitanía de Puerto me notificó que debía asistir a una diligencia de entrega del área.
Considero que esa diligencia no es necesaria porque la playa quedó limpia y no hubo daños.
¿Estoy obligado a hacer la entrega formal del área o basta con haber terminado el evento y retirar la infraestructura?"""
)

# Nota: no es CASO_KAYAK (fase anterior) — el texto de esta ronda difiere en
# un salto de línea entre "...todavía no ha llegado." y "Los patrocinadores
# ...". Se transcribe aparte para respetar la fidelidad verbatim exigida en
# esta revisión, sin duplicar innecesariamente el caso previo.
CASO_21_14_COMPETENCIA_KAYAK = (
    """Tengo una empresa que organiza competencias de kayak en El Rodadero (Santa Marta). Presenté la solicitud para realizar un campeonato internacional dentro de dos semanas, pero la respuesta de la autoridad todavía no ha llegado.
Los patrocinadores ya hicieron publicidad y muchos deportistas vienen desde otras ciudades, por lo que estoy pensando en realizar el evento mientras recibo la respuesta.
¿Puedo iniciar la actividad mientras deciden mi solicitud o debo esperar la autorización?"""
)

CASO_21_15_RENOVACION_PERMISO_TEMPORAL = (
    """Hace seis meses obtuve un permiso temporal para instalar una zona de descanso con carpas y mobiliario en una playa de Santa Marta durante la temporada turística. Como el negocio ha funcionado muy bien y quiero seguir operando allí el próximo año, pensé que el permiso se renovaba automáticamente mientras continuara pagando los impuestos y mantuviera el lugar en buen estado.
¿El permiso temporal se renueva automáticamente o debo realizar algún trámite para seguir utilizando la playa?"""
)

CASO_21_16_DUENO_DEL_LOTE_RESTAURANTE = (
    """Quiero construir un restaurante sobre una zona de arena frente al mar porque compré el lote hace varios años. ¿Eso significa que también soy dueño de la playa?"""
)

CASO_21_17_LANCHA_HUNDIDA_HERENCIA = (
    """Mi papá era dueño de una lancha que se hundió hace varios años. Él falleció y nosotros no tenemos dinero para retirarla. Ahora nos dicen que podemos ser responsables por los daños ambientales. ¿La DIMAR puede retirarla primero?"""
)

CASO_21_18_VENDEDOR_PLAYA_LOS_COCOS = (
    """Trabajo vendiendo comidas y bebidas en la playa Los Cocos. Desde que comenzaron a realizar conciertos y eventos masivos, cada vez llegan más personas, pero también aumenta la basura y algunas autoridades dicen que quieren prohibir completamente las ventas durante esos eventos. Yo no tengo dinero para pagar un abogado y mi familia depende de lo que vendo. ¿Pueden simplemente sacarme de la playa o existe alguna forma de reclamar para que se proteja el ambiente sin que se elimine completamente mi fuente de trabajo?"""
)

CASO_21_19_RESIDENTE_RUIDO_LOS_COCOS = (
    """Vivo con mi hija pequeña en una casa cerca de la playa Los Cocos. En los conciertos ponen música a alto volumen durante horas, dejan basura en la arena y, en una ocasión, hubo tanta gente que me dio miedo salir de mi casa. No tengo dinero para contratar un abogado y ya presenté varias quejas, pero no me han dado una solución. ¿Qué puedo hacer para que se proteja mi derecho a vivir en un ambiente sano y para que los próximos eventos tengan medidas reales de seguridad?"""
)

# CASO_21_20 es idéntico byte a byte a CASO_PESCADOR (definido arriba); se
# reutiliza para no duplicar el mismo texto verbatim dos veces.
CASO_21_20_PESCADOR_EMBARCACION_ABANDONADA = CASO_PESCADOR

CASO_21_21_EROSION_POZOS_COLORADOS = (
    """Vivo con mis hijos en una casa cerca de Pozos Colorados y cada año el mar se acerca más a mi vivienda. Ya se ha perdido parte de la playa y tengo miedo de que mi casa termine afectada. No tengo dinero para pagar un abogado ni para contratar un estudio técnico que demuestre la erosión. He acudido a varias entidades, pero cada una me dice que la responsabilidad es de otra. ¿Qué puedo hacer para que las autoridades actúen antes de que mi vivienda y la playa desaparezcan?"""
)

BANCO_21_PREGUNTAS = [
    ("21-01_motos_parasailing", CASO_21_01_MOTOS_PARASAILING),
    ("21-02_club_nautico_muelle", CASO_21_02_CLUB_NAUTICO_MUELLE),
    ("21-03_hotel_malla_guardia", CASO_21_03_HOTEL_MALLA_GUARDIA),
    ("21-04_alquiler_carpas_tarima", CASO_21_04_ALQUILER_CARPAS_TARIMA),
    ("21-05_festival_jac", CASO_21_05_FESTIVAL_JAC),
    ("21-06_pescador_taganga", CASO_21_06_PESCADOR_TAGANGA),
    ("21-07_vendedora_playa_cristal", CASO_21_07_VENDEDORA_PLAYA_CRISTAL),
    ("21-08_residente_club_playa", CASO_21_08_RESIDENTE_CLUB_PLAYA),
    ("21-09_comunidad_indigena_guajira", CASO_21_09_COMUNIDAD_INDIGENA_GUAJIRA),
    ("21-10_proyecto_turistico_playa_blanca", CASO_21_10_PROYECTO_TURISTICO_PLAYA_BLANCA),
    ("21-11_boda_en_la_playa", CASO_21_11_BODA_EN_LA_PLAYA),
    ("21-12_campeonato_futbol_playa", CASO_21_12_CAMPEONATO_FUTBOL_PLAYA),
    ("21-13_hotel_bocagrande_entrega_area", CASO_21_13_HOTEL_BOCAGRANDE_ENTREGA_AREA),
    ("21-14_competencia_kayak", CASO_21_14_COMPETENCIA_KAYAK),
    ("21-15_renovacion_permiso_temporal", CASO_21_15_RENOVACION_PERMISO_TEMPORAL),
    ("21-16_dueno_del_lote_restaurante", CASO_21_16_DUENO_DEL_LOTE_RESTAURANTE),
    ("21-17_lancha_hundida_herencia", CASO_21_17_LANCHA_HUNDIDA_HERENCIA),
    ("21-18_vendedor_playa_los_cocos", CASO_21_18_VENDEDOR_PLAYA_LOS_COCOS),
    ("21-19_residente_ruido_los_cocos", CASO_21_19_RESIDENTE_RUIDO_LOS_COCOS),
    ("21-20_pescador_embarcacion_abandonada", CASO_21_20_PESCADOR_EMBARCACION_ABANDONADA),
    ("21-21_erosion_pozos_colorados", CASO_21_21_EROSION_POZOS_COLORADOS),
]


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
        "Escríbeme el código Python para automatizar la solicitud de una "
        "concesión marítima.",
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
    """Control de regresión explícito exigido por esta ronda: 'cocinar y
    vender en una playa sin permiso' debe seguir in_scope — 'cocinar' es una
    señal ajena blanda que cede ante la combinación costera+jurídica, a
    diferencia de las intenciones inequívocamente ajenas del defecto #1."""
    result = _fallback("¿Se puede cocinar y vender pescado en una playa sin permiso?")
    assert result.route == "in_scope"
    assert result.doc_types


@pytest.mark.parametrize(
    ("caso_id", "question"),
    BANCO_21_PREGUNTAS,
    ids=[caso_id for caso_id, _ in BANCO_21_PREGUNTAS],
)
def test_banco_21_preguntas_siguen_in_scope_tras_la_correccion_posterior(
    caso_id: str, question: str
) -> None:
    """Control de no regresión exigido por esta ronda: las 21 preguntas
    jurídicas deben seguir in_scope después de los cinco ajustes mínimos de
    esta corrección posterior."""
    result = _fallback(question)
    assert result.route == "in_scope", f"{caso_id}: {question!r}"
    assert result.doc_types, f"{caso_id}: sin doc_types"


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
        "¿Tengo derecho a acceder libremente a la orilla del mar aunque haya un "
        "hotel al frente?",
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
        "¿Está prohibido acampar en una playa sin autorización de la autoridad "
        "marítima?",
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
        "¿Quién es responsable de retirar los escombros que deja un evento en la "
        "playa?",
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
        "¿Qué autorización exige el club para usar kayak en el lago los fines de "
        "semana?",
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
        "¿Necesito permiso para realizar una sesión fotográfica comercial en una "
        "playa?",
    ),
    (
        "entrenar_kayak_vs_autorizacion_competencia_maritima",
        "hard",
        "¿Dónde puedo entrenar kayak los fines de semana?",
        "¿Necesito autorización para organizar una competencia de kayak en El "
        "Rodadero?",
    ),
    (
        "pesca_en_rio_vs_pesca_artesanal_en_playa",
        "inland",
        "¿Qué carnada es mejor para pescar en un río de montaña?",
        "¿Qué requisitos debe cumplir un pescador artesanal para faenar en una "
        "playa protegida?",
    ),
    (
        "muelle_en_represa_vs_concesion_muelle_playa",
        "inland",
        "¿Puedo instalar un muelle privado en una represa para mi finca?",
        "¿Qué trámite debo seguir para obtener la concesión de un muelle en una "
        "playa turística?",
    ),
    (
        "nave_espacial_vs_embarcacion_abandonada_en_el_mar",
        "inland",
        "¿Qué protocolo siguen las agencias espaciales para el reingreso de una "
        "nave espacial?",
        "¿Qué debe hacer un pescador si encuentra una embarcación abandonada "
        "contaminando el mar?",
    ),
    (
        "hotel_recomendado_vs_hotel_restringe_acceso_publico",
        "hard",
        "Recomiéndame un hotel bonito para las vacaciones.",
        "¿Puede un hotel con concesión de playa impedir el acceso público a la "
        "orilla del mar?",
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
