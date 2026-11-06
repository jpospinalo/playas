# rag/core/territorio.py
"""Reconocimiento de territorio en las normas locales y prioridad de fusión.

El corpus mezcla normas nacionales (leyes, decretos, el REMAC) con normas
locales de Cartagena, Santa Marta y Turbo. Una pregunta sobre una ciudad —o
una pregunta general— no debe recibir como evidencia el reglamento de otra
ciudad solo porque su texto se parezca léxicamente. Este módulo centraliza el
mapa de lugares (antes duplicado en ``evaluation/metricas_sin_llm.py``) y
ofrece:

- ``plano``: minúsculas sin tildes, para comparar sin depender de la escritura.
- ``lugar_de_norma``: lugar de una norma local a partir de su metadata.
- ``lugares_mencionados``: lugares nombrados en un conjunto de textos.
- ``priorizar_territorio``: partición estable que demota —sin descartar— las
  normas locales de ciudades que la consulta no menciona.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from langchain_core.documents import Document

# Lugar → palabras que lo identifican en el título de una norma o en la
# pregunta. Solo se consideran normas locales los documentos ``normativa``.
LUGARES: dict[str, tuple[str, ...]] = {
    "cartagena": (
        "cartagena",
        "bocagrande",
        "playa blanca",
        "baru",
        "castillogrande",
        "boquilla",
    ),
    "santa marta": (
        "santa marta",
        "rodadero",
        "taganga",
        "playa cristal",
        "tayrona",
        "pozos colorados",
    ),
    "turbo": ("turbo",),
}


# Nombre legible de cada lugar, para mostrarlo al modelo en el contexto.
NOMBRES_LUGAR: dict[str, str] = {
    "cartagena": "Cartagena de Indias",
    "santa marta": "Santa Marta",
    "turbo": "Turbo (Antioquia)",
}


def describir_ambito(lugar: str) -> str:
    """Texto del ámbito de una norma local: ciudad y lugares que cubre.

    El modelo no sabe que Playa Cristal o Taganga están en Santa Marta; sin
    esto duda de si el reglamento de la ciudad aplica a la playa preguntada.
    """
    nombre = NOMBRES_LUGAR.get(lugar, lugar)
    otros = [p for p in LUGARES.get(lugar, ()) if p != lugar]
    if not otros:
        return f"{nombre} (norma local; no rige en otras ciudades)"
    return f"{nombre} (norma local; incluye {', '.join(otros)}; no rige en otras ciudades)"


def plano(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar sin depender de la escritura."""
    descompuesto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


def _nombra(texto_plano: str, palabra: str) -> bool:
    """``palabra`` aparece como palabra completa: «turbocompresor» no es Turbo."""
    return re.search(rf"(?<!\w){re.escape(palabra)}(?!\w)", texto_plano) is not None


def lugar_de_norma(metadata: Mapping[str, Any] | None) -> str | None:
    """Lugar de una norma local, o ``None`` si no es normativa local.

    Solo ``metadata["doc_type"] == "normativa"`` puede ser una norma local: la
    jurisprudencia que menciona una ciudad no lo es. Se devuelve el primer
    lugar del mapa (en su orden) cuyas palabras aparezcan en el título.
    """
    if not metadata or metadata.get("doc_type") != "normativa":
        return None
    titulo = plano(str(metadata.get("title", "")))
    for lugar, palabras in LUGARES.items():
        if any(_nombra(titulo, palabra) for palabra in palabras):
            return lugar
    return None


def lugares_mencionados(textos: Iterable[str]) -> set[str]:
    """Lugares cuyas palabras aparecen en el texto plano de ``textos`` unidos."""
    unidos = plano(" ".join(textos))
    return {
        lugar
        for lugar, palabras in LUGARES.items()
        if any(_nombra(unidos, palabra) for palabra in palabras)
    }


def priorizar_territorio(docs: Sequence[Document], consultas: Sequence[str]) -> list[Document]:
    """Demota al final las normas locales de lugares que la consulta no menciona.

    La partición es estable: se conserva el orden relativo dentro del grupo de
    documentos prioritarios y dentro del grupo demotado, y no se descarta
    ningún documento. Un reglamento local de otra ciudad (por ejemplo el de
    Turbo cuando se pregunta por Santa Marta, o cualquiera cuando la pregunta
    no nombra ninguna ciudad) no debe desplazar a las normas nacionales ni a la
    norma de la ciudad correcta: se posterga, nunca se elimina.
    """
    mencionados = lugares_mencionados(consultas)
    prioritarios: list[Document] = []
    demotados: list[Document] = []
    for doc in docs:
        lugar = lugar_de_norma(doc.metadata)
        if lugar is not None and lugar not in mencionados:
            demotados.append(doc)
        else:
            prioritarios.append(doc)
    return [*prioritarios, *demotados]
