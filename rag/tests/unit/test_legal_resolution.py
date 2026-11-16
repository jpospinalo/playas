from __future__ import annotations

import json
from dataclasses import replace
from hashlib import sha256

import pytest
from langchain_core.documents import Document

from rag.core.legal_resolution import FragmentProvenance, ResolutionIndex

DOCKET = "13001-23-33-000-2017-01038-01"
QUERY = (
    "¿Qué resolvió en segunda instancia sobre la sentencia de agosto de 2024 en el radicado "
    + DOCKET
    + "?"
)


def _document(ident: str, text: str, section: str, radicado: str = DOCKET) -> Document:
    return Document(
        page_content=text,
        metadata={
            "id": ident,
            "chunk_id": ident,
            "source": "providencia.pdf",
            "doc_type": "jurisprudencia",
            "Corporación": "Consejo de Estado",
            "Radicado": radicado,
            "section_name": section,
        },
    )


def _provenance(documents: list[Document]) -> dict[str, FragmentProvenance]:
    return {
        doc.metadata["id"]: FragmentProvenance(
            "providencia.jsonl",
            line,
            sha256(doc.page_content.encode()).hexdigest(),
            sha256(
                json.dumps(
                    {k: v for k, v in doc.metadata.items() if k != "id"},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
        )
        for line, doc in enumerate(documents, 1)
    }


@pytest.fixture
def documents() -> list[Document]:
    return [
        _document("cabecera", "## Sentencia de segunda instancia", "Contexto del caso"),
        _document(
            "resuelve", "PRIMERO: Confirmar la sentencia del 8 de agosto de 2024.", "Decisión"
        ),
    ]


def test_cites_literal_original_document(documents: list[Document]) -> None:
    result = ResolutionIndex(documents[::-1], _provenance(documents)).resolve(QUERY)
    assert result is not None
    assert len(result.sources) == 1 and result.sources[0] is documents[1]
    assert result.passages[0].text == documents[1].page_content
    assert result.answer.endswith("[doc1]")


@pytest.mark.parametrize(
    "field,value",
    [
        ("Radicado", "13001-23-33-000-2017-01038-00"),
        ("Corporación", "Corte Constitucional"),
        ("source", "otra.pdf"),
        ("section_name", "Contexto del caso"),
        ("doc_type", "normativa"),
        ("id", "distinto"),
    ],
)
def test_rejects_metadata_changes(documents: list[Document], field: str, value: str) -> None:
    provenance = _provenance(documents)
    documents[-1].metadata[field] = value
    assert ResolutionIndex(documents, provenance).resolve(QUERY) is None


def test_rejects_changed_or_missing_decision(documents: list[Document]) -> None:
    provenance = _provenance(documents)
    documents[-1].page_content += " Se modifica el fallo."
    assert ResolutionIndex(documents, provenance).resolve(QUERY) is None
    assert ResolutionIndex(documents[:1], provenance).resolve(QUERY) is None


@pytest.mark.parametrize(
    "old,new",
    [
        ("segunda", "primera"),
        ("segunda", "única"),
        ("agosto de 2024", "septiembre de 2024"),
        ("de agosto", "del 9 de agosto"),
        ("de 2024", "de 2024 y la indemnización"),
        (DOCKET, DOCKET + " (1000)"),
        (DOCKET, "0001"),
    ],
)
def test_abstains_on_unverified_claim(documents: list[Document], old: str, new: str) -> None:
    assert (
        ResolutionIndex(documents, _provenance(documents)).resolve(QUERY.replace(old, new)) is None
    )


def test_abstains_without_verified_docket_even_if_in_body(documents: list[Document]) -> None:
    documents[0].page_content += f" Radicación: {DOCKET}."
    for doc in documents:
        del doc.metadata["Radicado"]
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is None


def test_abstains_when_source_budget_is_exceeded(documents: list[Document]) -> None:
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY, max_sources=0) is None


@pytest.mark.parametrize(
    "form", ["13-001-2333-000-2017-01038-01", DOCKET + "(AP)", DOCKET + " (AP)"]
)
def test_verified_docket_formats_resolve_without_changing_metadata(
    documents: list[Document], form: str
) -> None:
    for document in documents:
        document.metadata["Radicado"] = form
    index = ResolutionIndex(documents, _provenance(documents))
    result = index.resolve(QUERY)
    assert result is not None and result.sources[0].metadata["Radicado"] == form
    assert index.resolve(QUERY.replace(DOCKET, DOCKET + "(AP)")) is None


@pytest.mark.parametrize("suffix", ["(AC)", "(AP) (1200)", "AP"])
def test_unrecognized_metadata_suffix_does_not_identify_source(
    documents: list[Document], suffix: str
) -> None:
    for document in documents:
        document.metadata["Radicado"] = DOCKET + suffix
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is None


@pytest.mark.parametrize(
    "header,instance",
    [
        ("Sentencia de primera instancia. Se cita una sentencia apelada en otro proceso.", None),
        (
            "## Sentencia de primera instancia\n\nSe cita una sentencia apelada en otro proceso.",
            "primera",
        ),
        (
            "## Sentencia de primera instancia\n\n## Antecedentes\n\nSentencia de segunda instancia",
            "primera",
        ),
        ("## Sentencia de primera instancia\n\n## Sentencia de segunda instancia", None),
        (
            "## Sentencia de primera instancia\n\n## Salvamento de voto\n\nSentencia de segunda instancia",
            "primera",
        ),
        ("## La sentencia apelada\n\nSe decide el recurso de apelación interpuesto.", None),
        ("| SENTENCIA SEGUNDA INSTANCIA | SENTENCIA SEGUNDA INSTANCIA |", "segunda"),
        (
            "Procede esta Corporación a resolver el recurso de apelación interpuesto por la parte demandante.",
            "segunda",
        ),
        ("La sala de decisión, resuelve en primera instancia, la demanda interpuesta.", "primera"),
        ("## SENTENCIA DE ÚNICA INSTANCIA", "única"),
    ],
)
def test_only_the_rulings_own_instance_is_accepted(
    documents: list[Document], header: str, instance: str | None
) -> None:
    documents[0].page_content = header
    index = ResolutionIndex(documents, _provenance(documents))
    for value in ("primera", "segunda", "única"):
        assert (index.resolve(QUERY.replace("segunda", value)) is not None) == (value == instance)


def test_ocr_header_binds_instance_to_its_own_docket(documents: list[Document]) -> None:
    header = (
        "Radicación número:\n\nActor:\n\nMedio de control:\n\nInstancia:\n\nTema:\n\n"
        f"{DOCKET} Parte demandante\n\nParte demandada\n\nProtección de derechos colectivos\n\nPrimera"
    )
    query = QUERY.replace("segunda", "primera")
    documents[0].page_content = header
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is not None
    documents[0].page_content = header.replace(DOCKET, "13001-23-33-000-2017-01039-01")
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None


def _linked_parties_cover(docket: str) -> str:
    return (
        "Radicación número:\nActor:\nVinculados:\nMedio de control:\nInstancia:\nTema:\n"
        f"{docket}\nParte demandante\nEntidad vinculada\nOtra entidad vinculada\n"
        "Protección de los derechos e intereses colectivos\nPrimera\nAsunto costero"
    )


@pytest.mark.parametrize(
    ("variant", "supported"),
    [
        ("running_header", True),
        ("preceding_docket", False),
        ("different_suffix", False),
        ("different_cover", False),
        ("independent_source", False),
        ("foreign_legacy_cover", False),
        ("opposing_instance", False),
    ],
)
def test_linked_parties_cover_keeps_the_full_docket_and_instance(documents, variant, supported):
    short = DOCKET.replace("01038", "1038")
    cover = _linked_parties_cover(DOCKET)
    running = f"Radicación número: {short} Actor: Parte demandante"
    if variant == "preceding_docket":
        documents[0].page_content = f"{running}\n\n{cover}"
    else:
        documents[0].page_content = f"{cover}\n\n{running}"
    if variant == "different_suffix":
        documents[0].page_content = documents[0].page_content.replace(short, short[:-2] + "00")
    if variant == "different_cover":
        documents[0].page_content = (
            _linked_parties_cover(short) + "\n\n" + documents[0].page_content
        )
    if variant == "foreign_legacy_cover":
        documents[0].page_content += (
            "\n\nRadicación número:\nActor:\nMedio de control:\nInstancia:\nTema:\n"
            "13001-23-33-000-2017-09999-01 Parte demandante\nParte demandada\n"
            "Protección de derechos colectivos\nPrimera"
        )
    if variant == "opposing_instance":
        documents[0].page_content += "\n\nSentencia de segunda instancia"
    proof = _provenance(documents)
    if variant == "independent_source":
        other = _document("otra", f"Radicación número: {short}", "Contexto del caso", short)
        other.metadata["source"] = "otra.pdf"
        proof["otra"] = replace(_provenance([other])["otra"], path="otra.jsonl")
        documents = [*documents, other]
    index = ResolutionIndex(documents, proof)
    first = QUERY.replace("segunda", "primera")
    assert (index.resolve(first) is not None) == supported
    assert index.resolve(QUERY) is None
    assert index.resolve(first.replace(DOCKET, short)) is None


@pytest.mark.parametrize("radicado", ["5037", "13001-23-31-000-1994-9935-01(3100)"])
def test_short_and_historical_dockets_require_printed_identity(
    documents: list[Document], radicado: str
) -> None:
    for document in documents:
        document.metadata["Radicado"] = radicado
    query = QUERY.replace(DOCKET, radicado)
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None
    documents[0].page_content += f"\n\nRadicación número: {radicado}"
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is not None
    assert (
        ResolutionIndex(documents, _provenance(documents)).resolve(QUERY.replace(DOCKET, "3100"))
        is None
    )


def test_review_identifies_the_expediente_and_the_court(documents: list[Document]) -> None:
    for document in documents:
        document.metadata.update({"Radicado": "T-9.370.946", "Corporación": "Corte Constitucional"})
    query = QUERY.replace("segunda instancia", "sede de revisión").replace(DOCKET, "T-9370946")
    documents[0].page_content = "## CORTE CONSTITUCIONAL\n\nSala Tercera de Revisión"
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None
    documents[0].page_content += "\n\nexpediente T-9.370.946"
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is not None


def test_collision_precedes_instance_and_available_decisions(documents: list[Document]) -> None:
    other = _document(
        "otra", "Sin encabezado de instancia ni resolución.", "Contexto del caso", DOCKET + "(AP)"
    )
    other.metadata["source"] = "otra.pdf"
    proof = _provenance(documents)
    proof["otra"] = replace(_provenance([other])["otra"], path="otra.jsonl")
    assert ResolutionIndex(documents, proof).resolve(QUERY) is not None
    assert ResolutionIndex([*documents, other], proof).resolve(QUERY) is None


def test_conflicting_printed_docket_blocks_the_metadata_identity(documents: list[Document]) -> None:
    documents[0].page_content += "\n\nRadicación número: 13001-23-33-000-2017-09999-01"
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is None


def test_court_heading_after_an_ocr_excerpt_requires_the_same_docket(
    documents: list[Document],
) -> None:
    documents[0].page_content = (
        f"## 1.1. La demanda\n\nExtracto previo.\n\n## Consejo de Estado\n\n{DOCKET}\n\n"
        "Procede la Sala a decidir el recurso de apelación interpuesto.\n\n## Antecedentes"
    )
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is not None
    documents[0].page_content = documents[0].page_content.replace(DOCKET, "5037")
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is None


def _order_question(subject: str, recipient: str = "") -> str:
    return f"¿Qué ordenó en segunda instancia{recipient} sobre {subject} en el radicado {DOCKET}?"


@pytest.fixture
def phased_orders(documents: list[Document]) -> list[Document]:
    return [
        *documents,
        _document(
            "estudios",
            "SEGUNDO: ORDENAR a la Agencia Ambiental y al Municipio que, en el mes siguiente a la "
            "restitución efectiva, realicen los estudios técnicos, sin que excedan seis (6) meses.",
            "Decisión",
        ),
        _document(
            "fase",
            "Posteriormente, de forma coordinada, deberán ejecutar dichas actividades dentro de "
            "los dieciocho (18) meses siguientes al vencimiento del término anterior.\n\n"
            "Las referidas actividades son las siguientes:",
            "Decisión",
        ),
        _document(
            "obras",
            "- A. Realizar la limpieza del estuario.\n- B. Construir muros.",
            "Decisión",
        ),
        _document(
            "presupuesto",
            "Para el cumplimiento de la anterior orden, la Agencia Financiera deberá incluir "
            "las actividades de su cargo en el presupuesto para las vigencias necesarias.",
            "Decisión",
        ),
    ]


def test_consecutive_order_links_phases_and_budget(phased_orders: list[Document]) -> None:
    index = ResolutionIndex(phased_orders, _provenance(phased_orders))
    result = index.resolve(
        _order_question("la limpieza del estuario y el presupuesto para esas actividades")
    )
    assert result is not None
    assert [d.metadata["id"] for d in result.sources] == [
        "estudios",
        "fase",
        "obras",
        "presupuesto",
    ]
    assert all(p.text in p.document.page_content for p in result.passages)
    assert "dieciocho (18) meses siguientes al vencimiento del término anterior" in result.answer
    assert "seis (6) meses" in result.answer and "restitución efectiva" in result.answer
    assert "Agencia Financiera" in result.answer and "de su cargo" in result.answer
    assert "Construir muros" not in result.answer


def test_execution_keeps_own_deadline_trigger_and_recipients(phased_orders: list[Document]) -> None:
    index = ResolutionIndex(phased_orders, _provenance(phased_orders))
    claim = "la limpieza del estuario en 18 meses desde el vencimiento del término anterior"
    assert (
        index.resolve(_order_question(claim, " a la Agencia Ambiental y al Municipio")) is not None
    )
    assert index.resolve(_order_question(claim.replace("18 meses", "seis meses"))) is None
    assert (
        index.resolve(
            _order_question(
                claim.replace("el vencimiento del término anterior", "la restitución efectiva")
            )
        )
        is None
    )
    assert index.resolve(_order_question(claim, " a la Agencia Financiera")) is None


def test_a_provenance_gap_breaks_the_link_between_phase_and_list(
    phased_orders: list[Document],
) -> None:
    proof = _provenance(phased_orders)
    claim = _order_question("la limpieza del estuario en dieciocho meses")
    assert ResolutionIndex(phased_orders, proof).resolve(claim) is not None
    for ident in ("obras", "presupuesto"):
        proof[ident] = replace(proof[ident], line=proof[ident].line + 1)
    index = ResolutionIndex(phased_orders, proof)
    assert index.resolve(QUERY) is not None
    assert index.resolve(claim) is None


def test_reordering_act_and_trigger_changes_the_proposition(documents: list[Document]) -> None:
    documents[
        1
    ].page_content = "PRIMERO: ORDENAR la supervisión de los estudios antes de las obras."
    index = ResolutionIndex(documents, _provenance(documents))
    assert (
        index.resolve(_order_question("la supervisión de los estudios antes de las obras"))
        is not None
    )
    assert (
        index.resolve(_order_question("la supervisión de las obras antes de los estudios")) is None
    )


def test_suborder_retains_own_recipient_and_deadline(documents: list[Document]) -> None:
    documents.extend(
        [
            _document(
                "plan",
                "SEGUNDO: ORDENAR al Municipio que, dentro de los seis (6) meses siguientes a la ejecutoria:\n\n"
                "2.1. Formule un plan de mantenimiento.",
                "Decisión",
            ),
            _document(
                "inspeccion",
                "TERCERO: ORDENAR a la Autoridad Portuaria que, dentro de los tres (3) meses siguientes a la ejecutoria:\n\n"
                "- 3.1. Implemente un programa de inspección de los muelles.",
                "Decisión",
            ),
        ]
    )
    index = ResolutionIndex(documents, _provenance(documents))
    subject = "la inspección de los muelles en tres meses desde la ejecutoria"
    result = index.resolve(_order_question(subject, " a la Autoridad Portuaria"))
    assert result is not None and [d.metadata["id"] for d in result.sources] == ["inspeccion"]
    assert "tres (3) meses" in result.answer and "Autoridad Portuaria" in result.answer
    assert index.resolve(_order_question(subject, " al Municipio")) is None
    assert index.resolve(_order_question(subject.replace("tres meses", "seis meses"))) is None


def test_compound_order_requires_vigilance_and_committee_evidence(
    documents: list[Document],
) -> None:
    documents.extend(
        [
            _document(
                "vigilancia",
                "SEGUNDO: CONMINAR al Alcalde que ejerza la vigilancia de los sectores restituidos.",
                "Decisión",
            ),
            _document(
                "comite",
                "Para verificar el seguimiento a las acciones se ordena la integración de un "
                "COMITÉ DE VERIFICACIÓN, el cual estará integrado por: la Magistrada, quien lo "
                "presidirá, y un representante de la Defensoría.",
                "Decisión",
            ),
        ]
    )
    subject = "la vigilancia de los sectores restituidos y cómo se integra el comité de seguimiento"
    index = ResolutionIndex(documents, _provenance(documents))
    result = index.resolve(_order_question(subject))
    assert result is not None
    assert [d.metadata["id"] for d in result.sources] == ["vigilancia", "comite"]
    assert "Alcalde" in result.answer and "presidirá" in result.answer
    assert (
        index.resolve(
            _order_question(subject.replace("comité de seguimiento", "comité de contratación"))
        )
        is None
    )


def test_suborder_does_not_inherit_terms_from_an_order_it_overrides(
    documents: list[Document],
) -> None:
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que, dentro de los seis (6) meses "
        "siguientes a la ejecutoria:\n\n"
        "1.1. Ordenar al Municipio de Puerto Norte que ejecute la limpieza del canal "
        "dentro de los dos (2) meses siguientes a la ejecutoria."
    )
    index = ResolutionIndex(documents, _provenance(documents))
    assert (
        index.resolve(
            _order_question(
                "la limpieza del canal en seis meses desde la ejecutoria",
                " a la Secretaría General",
            )
        )
        is None
    )
    result = index.resolve(
        _order_question(
            "la limpieza del canal en dos meses desde la ejecutoria",
            " al Municipio de Puerto Norte",
        )
    )
    assert result is not None and "Municipio de Puerto Norte" in result.answer
    assert "dos (2) meses" in result.answer and "seis (6) meses" not in result.answer


def test_trigger_preserves_the_difference_between_previous_and_following_term(
    documents: list[Document],
) -> None:
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que realice la limpieza del canal "
        "en seis (6) meses siguientes al vencimiento del término posterior."
    )
    index = ResolutionIndex(documents, _provenance(documents))
    subject = "la limpieza del canal en seis meses desde el vencimiento del término anterior"
    assert index.resolve(_order_question(subject)) is None
    result = index.resolve(_order_question(subject.replace("anterior", "posterior")))
    assert result is not None and "vencimiento del término posterior" in result.answer


def test_reporting_frequency_does_not_qualify_cleanup(documents: list[Document]) -> None:
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que realice la limpieza del canal "
        "en seis (6) meses y presente informes cada seis (6) meses."
    )
    index = ResolutionIndex(documents, _provenance(documents))
    assert index.resolve(_order_question("la limpieza del canal cada seis meses")) is None
    result = index.resolve(_order_question("los informes cada seis meses"))
    assert result is not None and "informes cada seis (6) meses" in result.answer


def test_reporting_another_authoritys_power_does_not_transfer_it(
    documents: list[Document],
) -> None:
    documents[
        1
    ].page_content = (
        "PRIMERO: Ordenar al Municipio que informe si la autoridad marítima puede otorgar permisos."
    )
    index = ResolutionIndex(documents, _provenance(documents))
    assert index.resolve(_order_question("otorgar permisos", " al Municipio")) is None
    result = index.resolve(_order_question("informe", " al Municipio"))
    assert result is not None and "informe si la autoridad marítima puede" in result.answer


def test_matching_date_does_not_override_a_conflicting_court(documents: list[Document]) -> None:
    documents[1].page_content = (
        "PRIMERO: Confirmar la sentencia del 8 de agosto de 2024 proferida por el "
        "Tribunal Administrativo de Córdoba."
    )
    index = ResolutionIndex(documents, _provenance(documents))
    assert index.resolve(QUERY) is not None
    subject = "agosto de 2024 dictada por el Tribunal Administrativo de Antioquia"
    assert index.resolve(QUERY.replace("agosto de 2024", subject)) is None


def test_matching_date_does_not_admit_an_added_remedy(documents: list[Document]) -> None:
    index = ResolutionIndex(documents, _provenance(documents))
    assert index.resolve(QUERY) is not None
    subject = "agosto de 2024 y ordenar una indemnización"
    assert index.resolve(QUERY.replace("agosto de 2024", subject)) is None


@pytest.mark.parametrize(
    "contradiction",
    [
        "| Radicación número: | 13001-23-33-000-2017-09999-01 |",
        "| Instancia | Primera |",
    ],
)
def test_conflicting_table_fields_deny_resolution(
    documents: list[Document], contradiction: str
) -> None:
    documents[0].page_content += f"\n\n| Radicación número: | {DOCKET} |\n| Instancia | Segunda |"
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is not None
    documents[0].page_content += "\n" + contradiction
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is None


@pytest.mark.parametrize(
    "header",
    [
        "Radicación: {number} Demandantes: Parte A",
        "| Radicado | Instancia |\n| --- | --- |\n| {number} | Segunda |",
        "| Radicado | Instancia |\n| --- | --- |\n| {number} | Primera |",
    ],
)
def test_inconsistent_identity_in_flat_or_column_headers(
    documents: list[Document], header: str
) -> None:
    title = documents[0].page_content + "\n\n"
    documents[0].page_content = title + header.format(number=DOCKET).replace(
        "| Primera |", "| Segunda |"
    )
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is not None
    printed = DOCKET if "| Primera |" in header else "13001-23-33-000-2017-09999-01"
    documents[0].page_content = title + header.format(number=printed)
    assert ResolutionIndex(documents, _provenance(documents)).resolve(QUERY) is None


def test_printed_auxiliary_reference_cannot_contradict_verified_metadata(
    documents: list[Document],
) -> None:
    identity = DOCKET + " (63.554)"
    for document in documents:
        document.metadata["Radicado"] = identity
    documents[0].page_content += f"\n\nRadicación número: {identity}"
    query = QUERY.replace(DOCKET, identity)
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is not None
    documents[0].page_content = documents[0].page_content.replace("63.554", "63.555")
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None


def test_verified_incomplete_source_still_blocks_a_known_docket_collision(
    documents: list[Document],
) -> None:
    competing = [
        _document(
            "otra-cabecera",
            f"Sentencia de segunda instancia\n\nRadicación número: {DOCKET}",
            "Contexto del caso",
        ),
        _document(
            "otra-decisión", "PRIMERO: Revocar la sentencia del 8 de agosto de 2024.", "Decisión"
        ),
    ]
    for doc in competing:
        doc.metadata["source"] = "otra.pdf"
    proof = _provenance(documents)
    proof.update(
        {
            ident: replace(value, path="otra.jsonl")
            for ident, value in _provenance(competing).items()
        }
    )
    assert ResolutionIndex(documents, proof).resolve(QUERY) is not None
    assert ResolutionIndex([*documents, *competing], proof).resolve(QUERY) is None
    assert ResolutionIndex([*documents, competing[0]], proof).resolve(QUERY) is None


@pytest.mark.parametrize(
    "second_action",
    [
        "y construya una planta de filtración dentro de seis (6) meses.",
        "y, dentro de seis (6) meses, construya una planta de filtración.",
    ],
)
def test_deadline_on_a_coordinated_action_does_not_qualify_the_other(
    documents: list[Document],
    second_action: str,
) -> None:
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que realice la limpieza del canal "
        + second_action
    )
    index = ResolutionIndex(documents, _provenance(documents))
    assert index.resolve(_order_question("la limpieza del canal en seis meses")) is None
    assert index.resolve(_order_question("la planta de filtración en seis meses")) is not None


@pytest.mark.parametrize(
    "qualifier", ["", "contados a partir de la ejecutoria, ", "previa aprobación técnica, "]
)
def test_suborder_recognizes_its_own_recipient_after_the_time_intro(
    documents: list[Document],
    qualifier: str,
) -> None:
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que prepare el plan:\n\n"
        f"1.1. Dentro de dos meses, {qualifier}el Municipio de Puerto Norte deberá ejecutar la limpieza del canal."
    )
    index = ResolutionIndex(documents, _provenance(documents))
    subject = "la limpieza del canal en dos meses"
    assert index.resolve(_order_question(subject, " a la Secretaría General")) is None
    valid = index.resolve(_order_question(subject, " al Municipio de Puerto Norte"))
    assert valid is not None and "Municipio de Puerto Norte" in valid.answer
    assert "Secretaría General" not in valid.answer


@pytest.mark.parametrize(
    "local_mandate",
    [
        "Se ordena al Municipio de Puerto Norte que ejecute la limpieza del canal dentro de dos (2) meses.",
        "Dentro de dos meses, el Municipio de Puerto Norte estará a cargo de la limpieza del canal.",
    ],
)
def test_other_express_local_mandates_keep_their_own_recipient(
    documents: list[Document],
    local_mandate: str,
) -> None:
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que prepare el plan:\n\n1.1. " + local_mandate
    )
    index = ResolutionIndex(documents, _provenance(documents))
    subject = "la limpieza del canal en dos meses"
    assert index.resolve(_order_question(subject, " a la Secretaría General")) is None
    result = index.resolve(_order_question(subject, " al Municipio de Puerto Norte"))
    assert result is not None and local_mandate in result.answer
    assert "Secretaría General" not in result.answer


@pytest.mark.parametrize(
    "local_mandates",
    [
        "Se ordena la limpieza del canal. Se ordena al Municipio de Puerto Norte que informe.",
        "Se ordena al Municipio de Puerto Norte que informe. Se ordena la limpieza del canal.",
        "El Municipio de Puerto Norte deberá informar. La CAR deberá ejecutar la limpieza del canal.",
        "El Municipio de Puerto Norte deberá informar; la CAR deberá ejecutar la limpieza del canal.",
        "El Municipio de Puerto Norte deberá informar y la CAR deberá ejecutar la limpieza del canal.",
        "El Municipio de Puerto Norte deberá informar. CAR deberá ejecutar la limpieza del canal.",
        "El Municipio de Puerto Norte deberá informar. Ecopetrol deberá ejecutar la limpieza del canal.",
        "El Municipio de Puerto Norte deberá informar. Clemente deberá ejecutar la limpieza del canal.",
        (
            "El Municipio de Puerto Norte deberá informar; "
            "Aguas de Cartagena deberá ejecutar la limpieza del canal."
        ),
        (
            "El Municipio de Puerto Norte deberá informar; "
            "Aguas de Cartagena S.A. E.S.P. deberá ejecutar la limpieza del canal."
        ),
        (
            "El Municipio de Puerto Norte deberá informar; "
            "Aguas de Cartagena S. A. E. S. P. deberá ejecutar la limpieza del canal."
        ),
        (
            "El Municipio de Puerto Norte deberá informar; "
            "Aguas de Cartagena, S.A. E.S.P., deberá ejecutar la limpieza del canal."
        ),
        (
            "El Municipio de Puerto Norte deberá informar; "
            "Aguas de Cartagena s.a. e.s.p. deberá ejecutar la limpieza del canal."
        ),
        (
            "El Municipio de Puerto Norte deberá informar; la CAR, en coordinación con el Distrito, "
            "deberá ejecutar la limpieza del canal."
        ),
    ],
)
def test_local_recipient_does_not_extend_to_a_separate_mandate(
    documents: list[Document], local_mandates: str
) -> None:
    heading = "PRIMERO: Ordenar a la Secretaría General que prepare el plan:\n\n1.1. "
    query = _order_question("la limpieza del canal", " al Municipio de Puerto Norte")
    documents[1].page_content = heading + local_mandates
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None
    local_mandate = (
        "Se ordena al Municipio de Puerto Norte que deberá ejecutar la limpieza del canal."
    )
    documents[1].page_content = heading + local_mandate
    result = ResolutionIndex(documents, _provenance(documents)).resolve(query)
    assert result is not None and local_mandate in result.answer


@pytest.mark.parametrize("connector", ["Luego", "Posteriormente"])
def test_temporal_continuation_keeps_its_local_recipient(
    documents: list[Document], connector: str
) -> None:
    order = (
        "1.1. El Municipio de Puerto Norte deberá informar. "
        f"{connector} deberá ejecutar la limpieza del canal."
    )
    documents[1].page_content = (
        "PRIMERO: Ordenar a la Secretaría General que prepare el plan:\n\n" + order
    )
    query = _order_question("la limpieza del canal", " al Municipio de Puerto Norte")
    result = ResolutionIndex(documents, _provenance(documents)).resolve(query)
    assert result is not None and order in result.answer


@pytest.mark.parametrize(
    "site", ["los sedimentos de la bahía", "los sedimentos del río y los sedimentos de la bahía"]
)
def test_analysis_cannot_inherit_a_location_when_its_samples_have_another_origin(
    documents: list[Document], site: str
) -> None:
    documents[1].page_content = (
        "QUINTO: Ordenar a la Autoridad Ambiental CAR que cumpla las siguientes medidas:\n\n"
        f"5.1. Establezca un programa de monitoreo de {site}.\n\n"
        "5.2. Realice análisis semestrales de coliformes fecales."
    )
    question = _order_question(
        "los análisis de coliformes fecales en los sedimentos de la bahía", " a CAR"
    )
    assert ResolutionIndex(documents, _provenance(documents)).resolve(question) is not None
    documents[1].page_content = (
        documents[1].page_content.removesuffix(".")
        + " de muestras provenientes únicamente del río vecino."
    )
    assert ResolutionIndex(documents, _provenance(documents)).resolve(question) is None


@pytest.mark.parametrize(
    "scope",
    [
        "Establezca un programa de monitoreo en los sedimentos del río, con exclusión de los sedimentos de la bahía.",
        "Establezca un programa de monitoreo en los sedimentos del río. No incluya los sedimentos de la bahía.",
    ],
)
def test_analysis_preserves_an_explicit_exclusion_in_the_monitoring_order(
    documents: list[Document],
    scope: str,
) -> None:
    documents[1].page_content = (
        "QUINTO: Ordenar a la Autoridad Ambiental CAR que cumpla las siguientes medidas:\n\n"
        f"5.1. {scope}\n\n5.2. Realice análisis semestrales de coliformes fecales."
    )
    question = _order_question(
        "los análisis de coliformes fecales en los sedimentos de la bahía", " a CAR"
    )
    assert ResolutionIndex(documents, _provenance(documents)).resolve(question) is None


@pytest.mark.parametrize(
    "monitoring,target",
    [
        ("en los sedimentos ubicados fuera del estuario", "los sedimentos del estuario"),
        (
            "de los sedimentos del río y evalúe la eventual inclusión de los sedimentos de la bahía",
            "los sedimentos de la bahía",
        ),
        (
            "de los sedimentos del río antes de su desembocadura en la bahía",
            "los sedimentos de la bahía",
        ),
        (
            "de los sedimentos del río para determinar si es viable incluir los sedimentos de la bahía",
            "los sedimentos de la bahía",
        ),
        (
            "en los sedimentos de la bahía si el Municipio autoriza su inclusión",
            "los sedimentos de la bahía",
        ),
        (
            "de los sedimentos en el área de influencia del emisario de la bahía",
            "los sedimentos de la bahía",
        ),
        (
            "de los sedimentos en el área de influencia del colector de Taganga",
            "los sedimentos de Taganga",
        ),
    ],
)
def test_monitoring_requires_affirmative_support_for_the_requested_site(
    documents: list[Document],
    monitoring: str,
    target: str,
) -> None:
    body = (
        "QUINTO: Ordenar a la Autoridad Ambiental CAR que cumpla las siguientes medidas:\n\n"
        "5.1. Establezca un programa de monitoreo {scope}.\n\n"
        "5.2. Realice análisis semestrales de coliformes fecales."
    )
    query = _order_question(f"los análisis de coliformes fecales en {target}", " a CAR")
    documents[1].page_content = body.format(scope=monitoring)
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None
    documents[1].page_content = body.format(scope=f"en {target}")
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is not None


@pytest.mark.parametrize(
    "unrelated",
    [
        ".\n\n1.1. El Municipio contratará asesores externos, quienes deberán informar cada seis meses sobre los pagos.",
        ".\n\nDÉCIMO: Establézcase una mesa de conciliación integrada por funcionarios, quienes deberán informar cada seis meses.",
        " y el Municipio contratará asesores externos, quienes deberán informar cada seis meses.",
        " y el Municipio debe contratar asesores externos, quienes deberán informar cada seis meses.",
        " y autorícese la contratación de asesores externos, quienes deberán informar cada seis meses.",
        " y el Municipio queda autorizado para contratar asesores externos, quienes deberán informar cada seis meses.",
        " y CAR queda autorizada para contratar asesores externos, quienes deberán informar cada seis meses.",
        (
            " y CAR queda autorizada de manera excepcional para contratar asesores externos, "
            "quienes deberán informar cada seis meses."
        ),
        " y CAR podrá contratar asesores externos, quienes deberán informar cada seis meses.",
        " y CAR designa dos asesores externos, quienes deberán informar cada seis meses.",
        " Y CAR DESIGNA DOS ASESORES EXTERNOS, quienes deberán informar cada seis meses.",
        " Y CAR HA DESIGNADO DOS ASESORES EXTERNOS, quienes deberán informar cada seis meses.",
        (
            "; POR CONDUCTO DE LA CAR SE HAN DESIGNADO DOS ASESORES EXTERNOS, "
            "quienes deberán informar cada seis meses."
        ),
        (
            ", POR EL FUNCIONARIO QUE HA DESIGNADO EL MINISTERIO "
            "Y CAR HA DESIGNADO DOS ASESORES EXTERNOS, quienes deberán informar cada seis meses."
        ),
        ", POR LA CAR QUE HA DESIGNADO DOS ASESORES EXTERNOS, quienes deberán informar cada seis meses.",
        ", por la CAR que ha designado asesores, quienes deberán informar cada seis meses.",
        ", por la CAR que ha designado los asesores, quienes deberán informar cada seis meses.",
        ", POR LA CAR QUE HA DESIGNADO LOS ASESORES EXTERNOS, quienes deberán informar cada seis meses.",
        (
            ", por las autoridades que han designado la empresa, "
            "quienes deberán informar cada seis meses."
        ),
        (
            "; por conducto de la CAR se designan dos asesores externos, "
            "quienes deberán informar cada seis meses."
        ),
        (
            " y por conducto de la CAR se designan dos asesores externos, "
            "quienes deberán informar cada seis meses."
        ),
        (
            "; POR CONDUCTO DE LA CAR SE DESIGNAN DOS ASESORES EXTERNOS, "
            "quienes deberán informar cada seis meses."
        ),
    ],
)
def test_committee_does_not_inherit_reporting_from_another_mandate(
    documents: list[Document], unrelated: str
) -> None:
    first = "NOVENO: Confórmese el comité de verificación. Estará integrado por dos magistrados"
    query = _order_question(
        "la integración del comité de verificación y sus informes cada seis meses"
    )
    documents[1].page_content = first + unrelated
    assert ResolutionIndex(documents, _provenance(documents)).resolve(query) is None
    documents[1].page_content = (
        first + ", quienes deberán informar cada seis meses sobre el cumplimiento."
    )
    result = ResolutionIndex(documents, _provenance(documents)).resolve(query)
    assert result is not None and "dos magistrados" in result.answer


@pytest.mark.parametrize(
    "member", ["los delegados de la comunidad", "dos delegados de la comunidad", "CAR"]
)
def test_committee_reports_keep_an_explicit_coordinated_member(
    documents: list[Document], member: str
) -> None:
    decision = (
        "NOVENO: Confórmese el comité de verificación. Estará integrado por dos magistrados "
        f"y {member}, quienes deberán informar cada seis meses."
    )
    documents[1].page_content = decision
    query = _order_question(
        "la integración del comité de verificación y sus informes cada seis meses"
    )
    result = ResolutionIndex(documents, _provenance(documents)).resolve(query)
    assert result is not None and decision in result.answer


@pytest.mark.parametrize(
    "members",
    [
        "por dos representantes del Ministerio de Ambiente y Desarrollo Sostenible",
        "POR DOS REPRESENTANTES DEL MINISTERIO DE AMBIENTE Y DESARROLLO SOSTENIBLE",
        "por el funcionario que el Ministerio designe",
        "por el funcionario que el Ministerio delegue",
        "por el representante que designe la CAR",
        "por el funcionario que ha designado el Ministerio",
        "POR EL FUNCIONARIO QUE HA DESIGNADO EL MINISTERIO",
        "por el funcionario que el Ministerio ha designado",
        "por el funcionario que ha designado el Ministerio, por el alcalde",
        "por el funcionario que han designado los magistrados",
        "por el funcionario que habían delegado las autoridades",
    ],
)
def test_committee_reports_keep_the_full_name_or_designation_of_a_member(
    documents: list[Document], members: str
) -> None:
    decision = (
        "NOVENO: Confórmese el comité de verificación. Estará integrado por dos magistrados, "
        f"{members}, quienes deberán informar cada seis meses."
    )
    documents[1].page_content = decision
    query = _order_question(
        "la integración del comité de verificación y sus informes cada seis meses"
    )
    result = ResolutionIndex(documents, _provenance(documents)).resolve(query)
    assert result is not None and decision in result.answer


def test_denial_excerpt_preserves_the_limitation_and_remaining_award(
    documents: list[Document],
) -> None:
    documents[1].page_content = (
        "PRIMERO: NEGAR las pretensiones de la demanda dentro del medio de control de nulidad "
        "únicamente en cuanto al cobro de los intereses; se reconoce el capital."
    )
    result = ResolutionIndex(documents, _provenance(documents)).resolve(
        _order_question("las pretensiones de la demanda")
    )
    assert result is not None
    assert "únicamente en cuanto al cobro de los intereses" in result.answer
    assert "se reconoce el capital" in result.answer


@pytest.mark.parametrize(
    "condition",
    [", en la parte relativa al cobro de intereses", " EN LA PARTE RELATIVA AL COBRO DE INTERESES"],
)
def test_collective_denial_keeps_an_explicitly_narrow_scope(
    documents: list[Document],
    condition: str,
) -> None:
    documents[1].page_content = (
        "PRIMERO: NEGAR las pretensiones de la demanda dentro del medio de control de protección "
        "de los derechos e intereses colectivos incoada por la Personería en contra de la Alcaldía"
        f"{condition}, por los argumentos expuestos en esta providencia."
    )
    result = ResolutionIndex(documents, _provenance(documents)).resolve(
        _order_question("las pretensiones de la demanda")
    )
    assert (
        result is not None and "en la parte relativa al cobro de intereses" in result.answer.lower()
    )


@pytest.mark.parametrize("field", ["body", "metadata"])
def test_document_changed_after_indexing_is_not_evidence(
    documents: list[Document], field: str
) -> None:
    index = ResolutionIndex(documents, _provenance(documents))
    assert index.resolve(QUERY) is not None
    if field == "body":
        documents[1].page_content = documents[1].page_content.replace("2024", "2025")
        query = QUERY.replace("2024", "2025")
    else:
        documents[1].metadata["Corporación"] = "Otra corporación"
        query = QUERY
    assert index.resolve(query) is None


def test_caller_cannot_raise_the_four_source_limit(documents: list[Document]) -> None:
    headings = ("PRIMERO", "SEGUNDO", "TERCERO", "CUARTO", "QUINTO")
    subjects = ("el dragado", "la limpieza", "la pasarela", "la vía", "el puente")
    docs = [documents[0]] + [
        _document(str(i), f"{heading}: Ordenar {subject}.", "Decisión")
        for i, (heading, subject) in enumerate(zip(headings, subjects, strict=True))
    ]
    index = ResolutionIndex(docs, _provenance(docs))
    assert index.resolve(_order_question(" y ".join(subjects[:4])), max_sources=6) is not None
    assert index.resolve(_order_question(" y ".join(subjects)), max_sources=6) is None
