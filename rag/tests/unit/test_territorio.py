"""Prioridad territorial: reconocer normas locales y no dejar que una norma de
otra ciudad desplace a las normas nacionales o a la de la ciudad consultada."""

from __future__ import annotations

from collections import Counter

from langchain_core.documents import Document

from rag.core.territorio import (
    LUGARES,
    lugar_de_norma,
    lugares_mencionados,
    plano,
    priorizar_territorio,
)

CARTAGENA = (
    "Por medio del cual se expiden las normas bases para la reglamentación de las "
    "actividades en las playas urbanas y rurales en el Distrito de Cartagena de Indias"
)
REMAC = "Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103)"


def _doc(identifier: str, *, doc_type: str, title: str) -> Document:
    return Document(
        page_content=f"contenido de {identifier}",
        metadata={"chunk_id": identifier, "doc_type": doc_type, "title": title},
    )


def _ids(docs: list[Document]) -> list[str]:
    return [str(d.metadata["chunk_id"]) for d in docs]


# ── plano ────────────────────────────────────────────────────────────────────


def test_plano_pasa_a_minusculas_y_quita_tildes():
    assert plano("CARTAGENA de Indias") == "cartagena de indias"
    assert plano("Dirección") == "direccion"
    assert plano("Playas y Bahía") == "playas y bahia"


# ── lugar_de_norma ───────────────────────────────────────────────────────────


def test_normativa_de_cartagena_es_norma_local_de_cartagena():
    assert lugar_de_norma({"doc_type": "normativa", "title": CARTAGENA}) == "cartagena"


def test_el_rodadero_se_reconoce_como_santa_marta():
    metadata = {
        "doc_type": "normativa",
        "title": "Reglamento del Balneario Turístico El Rodadero",
    }
    assert lugar_de_norma(metadata) == "santa marta"


def test_normativa_de_turbo_se_reconoce_como_turbo():
    assert lugar_de_norma({"doc_type": "normativa", "title": "Acuerdo de Turbo"}) == "turbo"


def test_jurisprudencia_nunca_es_norma_local():
    assert (
        lugar_de_norma({"doc_type": "jurisprudencia", "title": "AP X VS Distrito de Cartagena"})
        is None
    )


def test_norma_nacional_no_es_norma_local():
    assert lugar_de_norma({"doc_type": "normativa", "title": REMAC}) is None


def test_metadata_nula_no_tiene_lugar():
    assert lugar_de_norma(None) is None


# ── lugares_mencionados ──────────────────────────────────────────────────────


def test_lugares_mencionados_reconoce_las_palabras_de_cada_lugar():
    assert lugares_mencionados(["Quiero un evento en Taganga"]) == {"santa marta"}
    assert lugares_mencionados(["playa de Bocagrande y Turbo"]) == {"cartagena", "turbo"}
    assert lugares_mencionados(["una pregunta general"]) == set()


# ── priorizar_territorio ─────────────────────────────────────────────────────


def test_norma_local_de_otra_ciudad_se_demota_al_final_sin_alterar_el_orden():
    turbo_1 = _doc("turbo-1", doc_type="normativa", title="Acuerdo de Turbo")
    santa = _doc("santa", doc_type="normativa", title="Reglamento de El Rodadero")
    nacional = _doc("nacional", doc_type="normativa", title=REMAC)
    turbo_2 = _doc("turbo-2", doc_type="normativa", title="Decreto de Turbo")

    resultado = priorizar_territorio(
        [turbo_1, santa, nacional, turbo_2], ["¿Qué puedo hacer en Santa Marta?"]
    )

    assert _ids(resultado) == ["santa", "nacional", "turbo-1", "turbo-2"]


def test_la_norma_del_lugar_mencionado_conserva_su_posicion():
    santa = _doc("santa", doc_type="normativa", title="Reglamento de El Rodadero")
    nacional = _doc("nacional", doc_type="normativa", title=REMAC)

    resultado = priorizar_territorio([santa, nacional], ["evento en Taganga"])

    assert _ids(resultado) == ["santa", "nacional"]


def test_sin_lugares_en_la_consulta_todas_las_normas_locales_van_al_final():
    cartagena = _doc("cartagena", doc_type="normativa", title=CARTAGENA)
    nacional = _doc("nacional", doc_type="normativa", title=REMAC)
    santa = _doc("santa", doc_type="normativa", title="Reglamento de El Rodadero")
    jurisprudencia = _doc(
        "jurisprudencia", doc_type="jurisprudencia", title="AP X VS Distrito de Cartagena"
    )

    resultado = priorizar_territorio(
        [cartagena, nacional, santa, jurisprudencia], ["una pregunta general"]
    )

    assert _ids(resultado) == ["nacional", "jurisprudencia", "cartagena", "santa"]


def test_no_se_descarta_ningun_documento():
    docs = [
        _doc("cartagena", doc_type="normativa", title=CARTAGENA),
        _doc("nacional", doc_type="normativa", title=REMAC),
        _doc("turbo", doc_type="normativa", title="Acuerdo de Turbo"),
        _doc("santa", doc_type="normativa", title="Reglamento de El Rodadero"),
    ]

    resultado = priorizar_territorio(docs, ["Santa Marta"])

    assert Counter(_ids(resultado)) == Counter(_ids(docs))
    assert LUGARES["turbo"] == ("turbo",)
