# ingest/loaders.py

from __future__ import annotations

from langchain_core.documents import Document

from .config import DOC_TYPES, layer_prefix
from .metadata_csv import get_metadata_for_file, load_metadata_csv
from .normalize import normalize_documents
from .s3_client import list_keys, read_text
from .sections import split_by_sections
from .sections_normativa import split_by_articles
from .utils import save_docs_jsonl_per_file


def _section_documents(doc: Document, doc_type: str) -> list[Document]:
    """Despacha la estrategia de seccionado según el tipo de documento."""
    if doc_type == "normativa":
        return split_by_articles(doc)
    return split_by_sections(doc)


def _load_doc_type(doc_type: str) -> list[Document]:
    """Procesa la capa BRONZE de un *doc_type* y escribe su capa SILVER.

    Flujo por tipo:
      1) Lee cada .md de bronze/<doc_type>/ en S3.
      2) Normaliza texto/metadatos e inyecta doc_type.
      3) Fusiona metadatos del CSV del tipo (opcional).
      4) Secciona con la estrategia adecuada (sentencias vs artículos).
      5) Guarda un .jsonl por archivo en silver/<doc_type>/.
    """
    bronze_prefix = layer_prefix("bronze", doc_type)
    silver_prefix = layer_prefix("silver", doc_type)

    md_keys = sorted(list_keys(bronze_prefix, suffix=".md"))
    if not md_keys:
        print(f"[{doc_type}] No se encontraron archivos .md en s3://{bronze_prefix}")
        return []

    raw_docs: list[Document] = []
    for key in md_keys:
        content = read_text(key)
        filename = key.split("/")[-1]
        raw_docs.append(Document(page_content=content, metadata={"source": filename}))

    print(f"[{doc_type}] Documentos cargados desde Markdown: {len(raw_docs)}")

    docs = normalize_documents(raw_docs)
    # normalize_metadata sólo conserva source/title; reinyectamos el doc_type.
    for doc in docs:
        doc.metadata["doc_type"] = doc_type
    print(f"[{doc_type}] Documentos normalizados: {len(docs)}")

    csv_rows = len(load_metadata_csv(doc_type))
    matched_count = 0
    for doc in docs:
        csv_meta = get_metadata_for_file(doc.metadata.get("source", ""), doc_type)
        if csv_meta:
            doc.metadata.update(csv_meta)
            doc.metadata["doc_type"] = doc_type  # el CSV no debe pisar el tipo
            matched_count += 1
            print(f"  → Metadatos CSV encontrados para: {doc.metadata.get('source', '?')}")

    sectioned_docs: list[Document] = []
    for doc in docs:
        sections = _section_documents(doc, doc_type)
        title = doc.metadata.get("title") or doc.metadata.get("source", "?")
        print(f"\n  [{title}]")
        for s in sections:
            m = s.metadata
            heading = m.get("section_heading") or m.get("articulo_titulo") or "(sin heading)"
            found = bool(s.page_content)
            status = f"{len(s.page_content):>6} chars" if found else "  vacío      "
            marker = "✓" if found else "✗"
            name = m.get("section_name", "?")
            idx = m.get("section_index", "?")
            print(f"    {marker} Sección {idx} – {name!s:<30} {heading!r:<45} {status}")
        sectioned_docs.extend(sections)

    detected = sum(1 for d in sectioned_docs if d.page_content)
    print(
        f"\n[{doc_type}] Secciones con contenido: {detected}/{len(sectioned_docs)} "
        f"({len(docs)} documentos)"
    )

    save_docs_jsonl_per_file(sectioned_docs, silver_prefix)
    print(f"[{doc_type}] Guardado en: s3://{silver_prefix}")
    print(
        f"[{doc_type}] Metadatos CSV: {matched_count}/{csv_rows} filas con archivo "
        f"({len(docs)} documentos procesados)\n"
    )

    return sectioned_docs


def load_documents() -> list[Document]:
    """Genera la capa SILVER para todos los doc_types (jurisprudencia y normativa).

    Recorre cada tipo, lee su capa bronze/<doc_type>/, secciona con la estrategia
    apropiada y escribe silver/<doc_type>/. Devuelve la lista combinada de
    secciones de todos los tipos.
    """
    all_sections: list[Document] = []
    for doc_type in DOC_TYPES:
        all_sections.extend(_load_doc_type(doc_type))
    return all_sections


def main() -> None:
    documents = load_documents()
    if not documents:
        print("No hay documentos.")
        return

    print(f"Total secciones: {len(documents)}")


if __name__ == "__main__":
    main()
