# rag/core/tools.py
"""Utilidades de recuperación y formateo de contexto del agente RAG.

El grafo de core/agent.py decide la ruta y obtiene documentos mediante el
recuperador o los selectores de procedencia verificada; este módulo no realiza
búsquedas ni decide la ruta. `build_context_block` formatea esos documentos
en el contexto que ve el LLM, y `sanitize_replacement_chars` conserva
compatibilidad con entradas históricas
que contengan U+FFFD (ver data/README.md para el corpus y su representación).
`CITATION_RE` comparte la gramática de citas entre el agente y la evaluación.
"""

from __future__ import annotations

import re

from langchain_core.documents import Document

CITATION_RE = re.compile(r"\[doc(\d+)\]", re.IGNORECASE)

# ---------------------------------------------------------------------------
# Compatibilidad de texto histórico
# ---------------------------------------------------------------------------
#
# Algunas entradas históricas pueden contener U+FFFD (`�`) en metadata o
# cuerpos. Se limpia su presentación al LLM y al frontend sin modificar los
# archivos del corpus ni exigir una nueva ingesta.


def sanitize_replacement_chars(value):
    """Elimina recursivamente U+FFFD de strings y estructuras anidadas.

    Aplica sobre str, list y dict. Otros tipos pasan sin cambios. Es una
    compatibilidad de presentación; no certifica ni repara el archivo origen.
    """
    if isinstance(value, str):
        return value.replace("\ufffd", "")
    if isinstance(value, list):
        return [sanitize_replacement_chars(v) for v in value]
    if isinstance(value, dict):
        return {k: sanitize_replacement_chars(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# Formateo del contexto (movido desde generator.py)
# ---------------------------------------------------------------------------


def build_context_block(docs: list[Document], *, include_source_identifiers: bool = True) -> str:
    """Convierte una lista de documentos en un bloque de contexto legible.

    Incluye metadatos de atribución (corporación, magistrado, tema, sección
    y resumen) para que el LLM pueda citar correctamente las fuentes.
    Con identidad ya verificada, omite los nombres históricos de la cabecera.
    """
    bloques: list[str] = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        summary = sanitize_replacement_chars(meta.get("summary", ""))

        header = f"[doc{i}]"
        if include_source_identifiers:
            source = sanitize_replacement_chars(meta.get("source", "desconocido"))
            chunk_id = sanitize_replacement_chars(meta.get("chunk_id", meta.get("id", f"doc_{i}")))
            header = f"[doc{i} | source={source} | chunk_id={chunk_id}]"
        doc_type = meta.get("doc_type", "")

        if doc_type == "normativa":
            # Cabecera para normas: nombre de la norma + jerarquía (título, capítulo,
            # artículo). La identidad explícita prevalece sobre el título descriptivo.
            # No aplican corporación ni magistrado.
            norma = sanitize_replacement_chars(
                meta.get("norma") or meta.get("title") or meta.get("source", "desconocido")
            )
            titulo = sanitize_replacement_chars(meta.get("titulo", ""))
            capitulo = sanitize_replacement_chars(meta.get("capitulo", ""))
            articulo = sanitize_replacement_chars(meta.get("articulo", ""))

            meta_lines = [f"Norma: {norma}"]
            if titulo:
                meta_lines.append(f"Título: {titulo}")
            if capitulo:
                meta_lines.append(f"Capítulo: {capitulo}")
            if articulo:
                meta_lines.append(f"Artículo: {articulo}")
            if summary:
                meta_lines.append(f"Resumen auxiliar (contrastar con el cuerpo): {summary}")
        else:
            # Jurisprudencia (o tipo ausente/desconocido por compatibilidad).
            # Chroma puede almacenar la clave con distintas variantes de encoding
            corporacion = sanitize_replacement_chars(
                meta.get("Corporación") or meta.get("CorporaciÃ³n") or meta.get("Corporacion", "")
            )
            magistrado = sanitize_replacement_chars(meta.get("Magistrado ponente", ""))
            tema = sanitize_replacement_chars(meta.get("Tema principal", ""))
            section = sanitize_replacement_chars(meta.get("section_name", ""))
            section_heading = sanitize_replacement_chars(meta.get("section_heading", ""))

            meta_lines = []
            if corporacion:
                meta_lines.append(f"Corporación: {corporacion}")
            if magistrado:
                meta_lines.append(f"Magistrado ponente: {magistrado}")
            if tema:
                meta_lines.append(f"Tema principal: {tema}")
            if section:
                meta_lines.append(f"Sección: {section}")
            if section_heading:
                meta_lines.append(f"Encabezado: {section_heading}")
            if summary:
                meta_lines.append(f"Resumen auxiliar (contrastar con el cuerpo): {summary}")

        parts = [header]
        if meta_lines:
            parts.append("\n".join(meta_lines))
        parts.append("Texto del fragmento:")
        parts.append(sanitize_replacement_chars(d.page_content or ""))
        bloques.append("\n".join(parts))

    return "\n\n".join(bloques)
