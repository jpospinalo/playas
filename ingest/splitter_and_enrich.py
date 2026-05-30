"""Pipeline unificado Silver → Gold.

Lee los documentos seccionales de data/silver/, los fragmenta con tamaño
óptimo para embeddings y los enriquece con metadatos generados por un LLM
(seleccionado según OPENAI_API_KEY → OPENROUTER_API_KEY → GOOGLE_API_KEY),
escribiendo el resultado directamente en data/gold/ sin pasar por ninguna
capa intermedia.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

from .config import DOC_TYPES, GOLD_PREFIX, SILVER_PREFIX, layer_prefix
from .llm_factory import GeminiProvider, LLMProvider, get_active_provider
from .s3_client import key_exists, list_keys
from .utils import _load_docs_jsonl_file, save_docs_jsonl_per_file

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

# ---------------------------------------------------------------------------
# Pydantic output schema
# ---------------------------------------------------------------------------


class Entity(BaseModel):
    type: str = Field(
        description="Tipo de entidad: PERSON, LOCATION, DATE u otro valor descriptivo."
    )
    text: str = Field(description="Texto exacto de la entidad en el chunk.")


class ChunkMetadata(BaseModel):
    summary: str = Field(
        description="Resumen muy breve del contenido del chunk (máx. ~40 palabras)."
    )
    keywords: list[str] = Field(
        description="Lista de 5 a 10 palabras o frases clave relevantes para búsqueda."
    )
    entities: list[Entity] = Field(
        description="Lista de entidades nombradas (personas, lugares, fechas, etc.)."
    )


# ---------------------------------------------------------------------------
# Rate limiter (sólo relevante para Gemini free-tier, 9 RPM)
# ---------------------------------------------------------------------------


@dataclass
class RateLimiter:
    max_calls: int
    period_seconds: int = 60

    def __post_init__(self) -> None:
        self._calls: deque[float] = deque()

    def wait_for_slot(self) -> None:
        now = time.time()
        while self._calls and now - self._calls[0] > self.period_seconds:
            self._calls.popleft()

        if len(self._calls) >= self.max_calls:
            wait = self.period_seconds - (now - self._calls[0]) + 0.1
            logger.info("RateLimiter: esperando %.1fs para respetar el límite...", wait)
            time.sleep(wait)
            now = time.time()
            while self._calls and now - self._calls[0] > self.period_seconds:
                self._calls.popleft()

        self._calls.append(time.time())


class _NoOpRateLimiter:
    def wait_for_slot(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Chunk enricher (agnóstico al proveedor)
# ---------------------------------------------------------------------------


_ENRICH_PROMPT = (
    "Eres un asistente para preparar datos de un sistema de Recuperación "
    "Aumentada por Generación (RAG) en español. A partir del siguiente "
    "fragmento de texto (chunk), debes generar:\n"
    "1) Un resumen muy breve (máximo ~40 palabras) que capture la idea "
    "   principal del chunk.\n"
    "2) Entre 5 y 10 palabras clave relevantes para búsqueda semántica.\n"
    "3) Una lista de entidades nombradas importantes (personas, lugares, "
    "   fechas, organizaciones u otras).\n\n"
)

_ENRICH_PROMPT_NORMATIVA = (
    "Eres un asistente para preparar datos de un sistema de Recuperación "
    "Aumentada por Generación (RAG) en español, especializado en normativa "
    "jurídica colombiana (leyes, decretos, resoluciones). A partir del "
    "siguiente fragmento normativo (chunk), debes generar:\n"
    "1) Un resumen muy breve (máximo ~40 palabras) centrado en el objeto del "
    "   artículo: qué regula, qué obligaciones, prohibiciones o definiciones "
    "   establece.\n"
    "2) Entre 5 y 10 palabras clave relevantes para búsqueda semántica "
    "   (conceptos jurídicos, definiciones y obligaciones del artículo).\n"
    "3) Una lista de entidades nombradas importantes (autoridades, lugares, "
    "   normas citadas, fechas u otras).\n\n"
)

_JSON_INSTRUCTION = (
    "Responde SOLO con un JSON válido (sin texto adicional) con esta forma exacta:\n"
    "{\n"
    '  "summary": "texto del resumen",\n'
    '  "keywords": ["palabra1", "palabra2"],\n'
    '  "entities": [\n'
    '    {"type": "PERSON", "text": "Ejemplo de nombre"}\n'
    "  ]\n"
    "}\n"
    "No incluyas comentarios, explicaciones ni texto fuera del JSON.\n"
)


class ChunkEnricher:
    """Genera summary, keywords y entities para un chunk usando el LLM activo."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        max_calls_per_minute: int = 9,
    ) -> None:
        self._provider = provider or get_active_provider()
        self._llm = self._provider.create_llm(temperature=0.2, use_case="ingest_enrichment")

        # Rate limiting sólo para Gemini (cuota gratuita de Google)
        if isinstance(self._provider, GeminiProvider):
            self._rate_limiter: RateLimiter | _NoOpRateLimiter = RateLimiter(
                max_calls=max_calls_per_minute
            )
        else:
            self._rate_limiter = _NoOpRateLimiter()

        logger.info(
            "ChunkEnricher inicializado: proveedor=%s modelo=%s structured_output=%s",
            type(self._provider).__name__,
            self._provider.model_name,
            self._provider.supports_structured_output,
        )

    def enrich_chunk(
        self,
        text: str,
        doc_metadata: dict | None = None,
    ) -> ChunkMetadata:
        self._rate_limiter.wait_for_slot()
        print(f"  [model] enriqueciendo datos con modelo: {self._provider.model_name}")

        meta_str = ""
        if doc_metadata:
            meta_str = (
                "Metadatos del documento (pueden ayudar a contextualizar el fragmento):\n"
                f"{json.dumps(doc_metadata, ensure_ascii=False)}\n\n"
            )

        if doc_metadata and doc_metadata.get("doc_type") == "normativa":
            base_prompt = _ENRICH_PROMPT_NORMATIVA
        else:
            base_prompt = _ENRICH_PROMPT

        prompt = base_prompt + meta_str + f"Texto del chunk:\n{text}\n\n"

        if self._provider.supports_structured_output:
            structured_llm = self._llm.with_structured_output(ChunkMetadata)
            result = structured_llm.invoke(prompt)
            return result  # type: ignore[return-value]

        # Fallback: prompting manual + parseo JSON (Gemma-3 vía Google GenAI)
        full_prompt = prompt + _JSON_INSTRUCTION
        response = self._llm.invoke(full_prompt)
        raw = (getattr(response, "content", "") or "").strip()

        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and start < end:
            raw = raw[start : end + 1]

        data = json.loads(raw)
        return ChunkMetadata(**data)


# ---------------------------------------------------------------------------
# Chunking helpers
# ---------------------------------------------------------------------------


def _build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ".", " ", ""],
    )


def _sanitize_articulo(articulo: str) -> str:
    """Normaliza el identificador de artículo para que sea estable y legible en un chunk_id."""
    # Reemplaza cualquier secuencia de caracteres no alfanuméricos por un guion
    # y recorta guiones sobrantes en los extremos.
    return re.sub(r"[^0-9A-Za-z]+", "-", str(articulo)).strip("-")


def _chunk_section(doc: Document, splitter: RecursiveCharacterTextSplitter) -> list[Document]:
    """Divide un Document seccional en chunks preservando y extendiendo sus metadatos."""
    base_meta = dict(doc.metadata)
    source = base_meta.get("source", "unknown")
    stem = Path(source).stem
    section_idx = base_meta.get("section_index", 0)

    # chunk_id type-aware: para normativa con artículo identificado, usamos el
    # número de artículo como ancla estable; en otro caso, el índice de sección.
    articulo = base_meta.get("articulo")
    if base_meta.get("doc_type") == "normativa" and articulo not in (None, ""):
        chunk_id_prefix = f"{stem}_art{_sanitize_articulo(articulo)}_c"
    else:
        chunk_id_prefix = f"{stem}_s{section_idx}_c"

    raw_chunks = splitter.split_documents([doc])
    total = len(raw_chunks)

    result: list[Document] = []
    for idx, chunk in enumerate(raw_chunks):
        meta = {
            **base_meta,
            "chunk_index": idx,
            "chunk_id": f"{chunk_id_prefix}{idx}",
            "total_chunks_in_section": total,
        }
        result.append(Document(page_content=chunk.page_content, metadata=meta))

    return result


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


# Campos de metadata que se envían al enricher para contextualizar el fragmento.
_ENRICH_META_KEYS = (
    "source",
    "title",
    "section_name",
    "section_heading",
    "doc_type",
    "titulo",
    "capitulo",
    "articulo",
)


def _process_silver_dir(
    silver_prefix: str,
    gold_prefix: str,
    enricher: ChunkEnricher,
    splitter: RecursiveCharacterTextSplitter,
    skip_existing: bool,
) -> None:
    """Procesa todos los .jsonl de un único directorio silver hacia su gold homólogo."""
    silver_keys = list_keys(silver_prefix, suffix=".jsonl")
    if not silver_keys:
        logger.warning("No se encontraron archivos .jsonl en s3://%s", silver_prefix)
        return

    for silver_key in silver_keys:
        filename = silver_key.split("/")[-1]
        gold_key = f"{gold_prefix}{filename}"

        if skip_existing and key_exists(gold_key):
            logger.info("Saltando %s (ya existe en gold)", filename)
            print(f"[skip] {filename} ya existe en gold, se omite.")
            continue

        print(f"\n[proc] {filename}")
        section_docs = _load_docs_jsonl_file(silver_key)

        all_chunks: list[Document] = []
        for doc in section_docs:
            if not doc.page_content.strip():
                continue
            chunks = _chunk_section(doc, splitter)
            all_chunks.extend(chunks)

        print(f"  {len(section_docs)} secciones -> {len(all_chunks)} chunks")

        enriched: list[Document] = []
        for i, chunk in enumerate(all_chunks):
            logger.debug("Enriqueciendo chunk %d/%d de %s", i + 1, len(all_chunks), filename)
            print(
                f"  [{i + 1:>3}/{len(all_chunks)}] enriqueciendo chunk_id={chunk.metadata.get('chunk_id')}"
            )

            try:
                ai = enricher.enrich_chunk(
                    text=chunk.page_content,
                    doc_metadata={
                        k: v for k, v in chunk.metadata.items() if k in _ENRICH_META_KEYS
                    },
                )
                chunk.metadata["summary"] = ai.summary
                chunk.metadata["keywords"] = ai.keywords
                chunk.metadata["entities"] = [e.model_dump() for e in ai.entities]
            except Exception:
                logger.exception(
                    "Error al enriquecer chunk %s; se guarda sin metadatos de IA.",
                    chunk.metadata.get("chunk_id"),
                )

            enriched.append(chunk)

        save_docs_jsonl_per_file(enriched, gold_prefix)
        print(f"  Guardados {len(enriched)} chunks enriquecidos -> s3://{gold_key}")


def split_and_enrich_directory(
    silver_prefix: str = SILVER_PREFIX,
    gold_prefix: str = GOLD_PREFIX,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    max_calls_per_minute: int = 9,
    skip_existing: bool = True,
) -> None:
    """Fragmenta y enriquece los documentos silver hacia gold con el LLM activo.

    Por defecto recorre todos los tipos de documento (DOC_TYPES) usando los
    prefijos por tipo, p.ej. ``data/silver/normativa/`` → ``data/gold/normativa/``.
    Si se pasa un par *silver_prefix*/*gold_prefix* explícito distinto del
    default, se respeta ese único par sin iterar por tipos.

    El proveedor LLM se selecciona automáticamente según las API keys disponibles:
    OPENAI_API_KEY → OPENROUTER_API_KEY → GOOGLE_API_KEY.

    Los archivos ya presentes en gold se saltan cuando skip_existing=True.
    Los errores de enriquecimiento por chunk se loggean sin interrumpir el proceso.
    """
    enricher = ChunkEnricher(max_calls_per_minute=max_calls_per_minute)
    splitter = _build_splitter(chunk_size, chunk_overlap)

    if silver_prefix == SILVER_PREFIX and gold_prefix == GOLD_PREFIX:
        # Modo por defecto: recorre cada tipo de documento con su prefijo propio.
        for doc_type in DOC_TYPES:
            print(f"\n=== Tipo de documento: {doc_type} ===")
            _process_silver_dir(
                silver_prefix=layer_prefix("silver", doc_type),
                gold_prefix=layer_prefix("gold", doc_type),
                enricher=enricher,
                splitter=splitter,
                skip_existing=skip_existing,
            )
    else:
        # Override explícito: un único par de prefijos.
        _process_silver_dir(
            silver_prefix=silver_prefix,
            gold_prefix=gold_prefix,
            enricher=enricher,
            splitter=splitter,
            skip_existing=skip_existing,
        )

    print("\n[done] Proceso split_and_enrich completado.")


def main() -> None:
    split_and_enrich_directory()


if __name__ == "__main__":
    main()
