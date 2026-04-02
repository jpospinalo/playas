# src/ingest/enrich.py  (ajusta la ruta según tu estructura real)

from __future__ import annotations

import json
import os
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass

from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------
# Constantes y configuración
# ---------------------------------------------------------------------

load_dotenv()


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL")
# ---------------------------------------------------------------------
# 1. Modelos de salida (schema)
# ---------------------------------------------------------------------


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


# ---------------------------------------------------------------------
# 2. Rate limiter simple
# ---------------------------------------------------------------------


@dataclass
class RateLimiter:
    max_calls: int
    period_seconds: int = 60

    def __post_init__(self) -> None:
        self._calls: deque[float] = deque()

    def wait_for_slot(self) -> None:
        """Bloquea hasta que haya cupo disponible según max_calls/period_seconds."""
        now = time.time()
        # Limpiar entradas antiguas
        while self._calls and now - self._calls[0] > self.period_seconds:
            self._calls.popleft()

        if len(self._calls) >= self.max_calls:
            wait = self.period_seconds - (now - self._calls[0]) + 0.1
            print(f"[RateLimiter] Esperando {wait:.1f}s para respetar el límite...")
            time.sleep(wait)
            now = time.time()
            while self._calls and now - self._calls[0] > self.period_seconds:
                self._calls.popleft()

        self._calls.append(time.time())


# ---------------------------------------------------------------------
# 3. Cliente Gemini y lógica de enriquecimiento
# ---------------------------------------------------------------------


class GeminiEnricher:
    """
    Encapsula la llamada a Gemini/Gemma para enriquecer chunks con resumen,
    palabras clave y entidades nombradas.
    """

    def __init__(
        self,
        model: str = GEMINI_MODEL,
        max_calls_per_minute: int = 9,
    ) -> None:
        if not GOOGLE_API_KEY:
            raise RuntimeError(
                "GOOGLE_API_KEY no está definida. Asegúrate de declararla en el archivo .env."
            )

        self.client = genai.Client(api_key=GOOGLE_API_KEY)
        self.model = model
        self.rate_limiter = RateLimiter(max_calls=max_calls_per_minute)

    def enrich_chunk(
        self,
        text: str,
        doc_metadata: dict | None = None,
    ) -> ChunkMetadata:
        """
        Enriquecimiento de un solo chunk de texto usando Gemini/Gemma.
        Si el modelo no soporta JSON mode (p.ej. gemma-3-*), se hace
        prompting para JSON y se parsea manualmente.
        """
        self.rate_limiter.wait_for_slot()

        meta_str = ""
        if doc_metadata:
            meta_str = (
                "Metadatos del documento (pueden ayudar a contextualizar el fragmento):\n"
                f"{json.dumps(doc_metadata, ensure_ascii=False)}\n\n"
            )

        base_prompt = (
            "Eres un asistente para preparar datos de un sistema de Recuperación "
            "Aumentada por Generación (RAG) en español. A partir del siguiente "
            "fragmento de texto (chunk), debes generar:\n"
            "1) Un resumen muy breve (máximo ~40 palabras) que capture la idea "
            "   principal del chunk.\n"
            "2) Entre 5 y 10 palabras clave relevantes para búsqueda semántica.\n"
            "3) Una lista de entidades nombradas importantes (personas, lugares, "
            "   fechas, organizaciones u otras).\n\n"
            f"{meta_str}"
            "Texto del chunk:\n"
            f"{text}\n\n"
        )

        # --------- RAMA 1: modelos que SÍ soportan JSON mode (Gemini 2.5, etc.) ---------
        # Usamos structured outputs solo si NO es Gemma 3.
        if not (self.model or "").startswith("gemma-3"):
            prompt = base_prompt + (
                "Responde SOLO con los campos solicitados en formato JSON con esta forma:\n"
                "{\n"
                '  "summary": "...",\n'
                '  "keywords": ["..."],\n'
                '  "entities": [\n'
                '    {"type": "...", "text": "..."}\n'
                "  ]\n"
                "}\n"
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ChunkMetadata,
                    temperature=0.2,
                ),
            )

            return response.parsed

        # --------- RAMA 2: Gemma 3 (NO soporta JSON mode) ---------
        # Aquí pedimos JSON por prompt y parseamos manualmente.
        prompt = base_prompt + (
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

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.2,
            ),
        )

        # En el SDK nuevo, response.text expone el contenido como string
        raw = response.text or ""
        raw = raw.strip()

        # Quitar fences tipo ```json ... ``` si los hubiera
        if raw.startswith("```"):
            lines = raw.splitlines()
            # quitar primera línea (``` o ```json)
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            # quitar última línea ``` si está
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        # Intentar recortar desde el primer '{' hasta el último '}'
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and start < end:
            raw = raw[start : end + 1]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print("Error al parsear JSON devuelto por el modelo:\n", raw)
            raise e

        return ChunkMetadata(**data)


# ---------------------------------------------------------------------
# 4. Utilidades de I/O
# ---------------------------------------------------------------------


def iter_jsonl_chunks(input_path: str) -> Iterator[dict]:
    """Itera sobre los registros de un archivo .jsonl."""
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def write_jsonl(records: list[dict], output_path: str) -> None:
    """Escribe una lista de registros en formato .jsonl."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------
# 5. Pipeline principal
# ---------------------------------------------------------------------


def enrich_directory(
    silver_chunk_dir: str = "data/silver/chunked",
    gold_dir: str = "data/gold",
    model_name: str = GEMINI_MODEL,
    max_calls_per_minute: int = 9,
) -> None:
    """
    Recorre todos los .jsonl de la carpeta silver_chunk_dir, enriquece cada chunk
    con Gemini y guarda los resultados en gold_dir (un archivo .jsonl de salida
    por cada archivo de entrada).
    """
    enricher = GeminiEnricher(
        model=model_name,
        max_calls_per_minute=max_calls_per_minute,
    )

    os.makedirs(gold_dir, exist_ok=True)

    for file_name in sorted(os.listdir(silver_chunk_dir)):
        if not file_name.endswith(".jsonl"):
            continue

        input_path = os.path.join(silver_chunk_dir, file_name)
        output_path = os.path.join(gold_dir, file_name)

        # Saltar si el archivo ya fue enriquecido
        if os.path.exists(output_path):
            print(f"Saltando {input_path} porque ya existe {output_path}")
            continue

        print(f"Procesando {input_path} -> {output_path}")

        enriched_records: list[dict] = []

        for chunk in iter_jsonl_chunks(input_path):
            text = chunk.get("page_content") or chunk.get("text") or chunk.get("content") or ""
            if not text.strip():
                continue

            base_meta: dict = chunk.get("metadata") or {}

            # En caso de que metadata esté vacío, intentar reconstruir lo básico
            if not base_meta:
                for key in ("source", "title", "author"):
                    if key in chunk:
                        base_meta[key] = chunk[key]

            metadata_model = enricher.enrich_chunk(text, doc_metadata=base_meta)

            enriched_meta = {
                **base_meta,
                "summary": metadata_model.summary,
                "keywords": metadata_model.keywords,
                "entities": [e.model_dump() for e in metadata_model.entities],
            }

            enriched_record = {
                **chunk,
                "metadata": enriched_meta,
            }

            enriched_records.append(enriched_record)

        write_jsonl(enriched_records, output_path)
        print(f"Guardados {len(enriched_records)} chunks enriquecidos en {output_path}")


def print_example_from_gold(gold_dir: str) -> None:
    """
    Lee el primer archivo .jsonl de gold y muestra el primer registro enriquecido.
    """
    if not os.path.isdir(gold_dir):
        print(f"No existe el directorio gold: {gold_dir}")
        return

    for file_name in os.listdir(gold_dir):
        if not file_name.endswith(".jsonl"):
            continue

        path = os.path.join(gold_dir, file_name)
        with open(path, encoding="utf-8") as f:
            first_line = f.readline().strip()
            if not first_line:
                continue

            record = json.loads(first_line)
            print(f"\nEjemplo de registro enriquecido desde: {path}")
            print(json.dumps(record, ensure_ascii=False, indent=2))
            return

    print("No se encontraron archivos .jsonl con contenido en la carpeta gold.")


if __name__ == "__main__":
    gold_dir = "data/gold"

    # Si no hay archivos .jsonl en gold, lanzar el proceso de enriquecimiento
    if (not os.path.isdir(gold_dir)) or not any(f.endswith(".jsonl") for f in os.listdir(gold_dir)):
        print(f"No se encontraron archivos .jsonl en {gold_dir}. Iniciando enriquecimiento...")
        enrich_directory(
            silver_chunk_dir="data/silver/chunked",
            gold_dir=gold_dir,
            model_name=GEMINI_MODEL,
            max_calls_per_minute=25,
        )

    # Mostrar ejemplo (si ya hay algo enriquecido)
    print_example_from_gold(gold_dir)
