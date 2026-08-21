# rag/core/tools.py
"""Utilidades de recuperación y formateo de contexto del agente RAG.

El flujo del agente (ver core/agent.py) es determinista: enrich_query →
route_after_analysis → {retrieve_forced → generate, respond_without_retrieval}.
No hay tool-calling ni ReAct — el LLM nunca decide si buscar o no. La
recuperación (retrieve_forced) se ejecuta exactamente una vez, pero solo para
consultas que enrich_query clasifica como `in_scope`; conversación
(saludos/meta-preguntas), aclaración y fuera de alcance van directo a
respond_without_retrieval y no recuperan documentos. Este módulo conserva las
funciones que ese flujo determinista reutiliza: `build_context_block`
formatea los documentos recuperados en el bloque de contexto que ve el LLM,
y `sanitize_replacement_chars` limpia caracteres U+FFFD del pipeline de
ingesta (ver docs/INGEST_ENCODING_BUG.md).
"""

from __future__ import annotations

from langchain_core.documents import Document

# ---------------------------------------------------------------------------
# Sanitización (parche temporal)
# ---------------------------------------------------------------------------
#
# El pipeline bronze → silver actualmente produce caracteres U+FFFD (`�`) en
# metadatos y contenido de chunks (ver docs/INGEST_ENCODING_BUG.md). Hasta que
# se corrija la raíz y se re-ingeste el corpus, eliminamos esos caracteres antes
# de exponer el texto al LLM y al frontend.


def sanitize_replacement_chars(value):
    """Elimina recursivamente U+FFFD de strings y estructuras anidadas.

    Aplica sobre str, list y dict. Otros tipos pasan sin cambios. Cuando el bug
    de ingestión se arregle y se re-ingeste, esta función puede eliminarse.
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


def build_context_block(docs: list[Document]) -> str:
    """Convierte una lista de documentos en un bloque de contexto legible.

    Incluye metadatos de atribución (corporación, magistrado, tema, sección
    y resumen) para que el LLM pueda citar correctamente las fuentes.
    """
    bloques: list[str] = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        source = sanitize_replacement_chars(meta.get("source", "desconocido"))
        chunk_id = sanitize_replacement_chars(meta.get("chunk_id", meta.get("id", f"doc_{i}")))
        summary = sanitize_replacement_chars(meta.get("summary", ""))

        header = f"[doc{i} | source={source} | chunk_id={chunk_id}]"
        doc_type = meta.get("doc_type", "")

        if doc_type == "normativa":
            # Cabecera para normas: nombre de la norma + jerarquía (título, capítulo,
            # artículo). No aplican corporación ni magistrado.
            norma = sanitize_replacement_chars(
                meta.get("title") or meta.get("norma") or meta.get("source", "desconocido")
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
                meta_lines.append(f"Resumen: {summary}")
        else:
            # Jurisprudencia (o tipo ausente/desconocido por compatibilidad).
            # Chroma puede almacenar la clave con distintas variantes de encoding
            corporacion = sanitize_replacement_chars(
                meta.get("Corporación") or meta.get("CorporaciÃ³n") or meta.get("Corporacion", "")
            )
            magistrado = sanitize_replacement_chars(meta.get("Magistrado ponente", ""))
            tema = sanitize_replacement_chars(meta.get("Tema principal", ""))
            section = sanitize_replacement_chars(meta.get("section_name", ""))

            meta_lines = []
            if corporacion:
                meta_lines.append(f"Corporación: {corporacion}")
            if magistrado:
                meta_lines.append(f"Magistrado ponente: {magistrado}")
            if tema:
                meta_lines.append(f"Tema principal: {tema}")
            if section:
                meta_lines.append(f"Sección: {section}")
            if summary:
                meta_lines.append(f"Resumen: {summary}")

        parts = [header]
        if meta_lines:
            parts.append("\n".join(meta_lines))
        parts.append(sanitize_replacement_chars(d.page_content or ""))
        bloques.append("\n".join(parts))

    return "\n\n".join(bloques)
