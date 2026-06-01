"""Constantes configurables del pipeline PDF → Markdown.

Organizadas por categoría: procesamiento de imágenes, limpieza de texto,
perfilado de documentos, corrección OCR, y patrones regex compartidos.

Para ajustar el comportamiento del pipeline, modificar los valores aquí
(en código) o sobreescribirlos antes de llamar a ``convert_pdfs_to_markdown()``.
"""

from __future__ import annotations

import re

# ── Procesamiento de imágenes ────────────────────────────────────────────────
# Controlan qué imágenes se conservan durante la limpieza de markdown.

IMAGE_RESOLUTION_SCALE = 2.0        # Factor de escala para extracción de imágenes del PDF
MIN_IMAGE_PIXELS = 350              # Dimensión mínima (px) para conservar una imagen
IMAGE_LOW_VARIANCE = 100.0          # Varianza de píxeles por debajo de la cual la imagen se descarta (blanca/uniforme)
IMAGE_CONTEXT_WINDOW = 300          # Caracteres alrededor de la imagen para buscar contexto semántico
IMAGE_REQUIRE_SEMANTIC_CONTEXT = True  # Exigir palabras de contexto (figura, tabla, etc.) cerca de la imagen
IMAGE_MIN_AREA_KEEP_WITHOUT_CONTEXT = 250_000  # Área mínima (px²) para conservar imagen sin contexto semántico
IMAGE_FALLBACK_KEEP_ENABLED = True  # Si todas las imágenes se descartarían, conservar las más grandes
IMAGE_FALLBACK_MAX_KEEP = 2         # Máximo de imágenes a conservar en modo fallback
IMAGE_FALLBACK_MIN_AREA = 160_000   # Área mínima (px²) para candidatas a fallback

# ── Limppieza de texto ───────────────────────────────────────────────────────

MIN_BLOCK_REPEATS = 2        # Mínimo de repeticiones para considerar un bloque como header/footer repetido
NOISE_CHAR_RATIO = 0.45      # Ratio máximo de caracteres no lingüísticos antes de descartar línea como ruido

# ── Umbrales de perfilado de documentos ──────────────────────────────────────
# Usados por ``profiler.py`` para clasificar el documento y adaptar la limpieza.

LEGAL_DENSITY_THRESHOLD = 0.15       # Densidad de citaciones legales para considerar documento jurídico
FOOTNOTE_DENSITY_THRESHOLD = 0.10    # Densidad de notas al pie para activar remoción de footnotes
OCR_NOISE_THRESHOLD = 0.05           # Ratio de ruido OCR para activar correcciones agresivas
REPEATED_FURNITURE_THRESHOLD = 0.60  # Frecuencia de líneas repetidas para detectar headers/footers de página
COASTAL_DENSITY_THRESHOLD = 0.02     # Densidad de términos costeros para clasificar relevancia costera

# ── Scoring de referencias internas ──────────────────────────────────────────
# Usado por ``references.py`` para decidir si una línea es una referencia
# interna del documento (pie de página, citación) que debe removerse.
# Un score >= INTERNAL_REF_SCORE_THRESHOLD se considera referencia interna.

INTERNAL_REF_SCORE_THRESHOLD = 3

# ------------------------------------------------------------------
# OCR correction table
# ------------------------------------------------------------------

OCR_CORRECTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"ci6nes\b"), "ciones"),
    (re.compile(r"ci6n\b"), "ción"),
    (re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6n\b"), r"\1ón"),
    (re.compile(r"([A-Za-záéíóúüñÁÉÍÓÚÜÑ])6s\b"), r"\1ós"),
    (re.compile(r"([a-záéíóúüñ])6([a-záéíóúüñ])"), r"\1ó\2"),
    (re.compile(r"\b0([a-záéíóúüñ])"), r"o\1"),
    (re.compile(r"([a-záéíóúüñ])0\b"), r"\1o"),
    (re.compile(r"\bl([0O])s\b"), "los"),
    (re.compile(r"\bd([0O])s\b"), "dos"),
    (re.compile(r"(?i)\bpr([0O])ceso\b"), "proceso"),
    (re.compile(r"(?i)\bc([0O])nsejo\b"), "consejo"),
]

# ------------------------------------------------------------------
# Shared regex patterns
# ------------------------------------------------------------------

MD_STRUCTURE_RE: re.Pattern[str] = re.compile(r"^\s*(#{1,6}\s|[-*|!]|\d+\.|---)")

FOOTNOTE_LEGAL_CONTEXT: re.Pattern[str] = re.compile(
    r"(?i)(ley|artículo|articulo|decreto|numeral|inciso|parágrafo"
    r"|paragrafo|literal|ordinal|resolución|resolucion)\s*$"
)

IMAGE_CONTEXT_RE: re.Pattern[str] = re.compile(
    r"(?i)\b(figura|tabla|imagen|gráfico|grafico|ilustración"
    r"|ilustracion|foto|fotografía|fotografia|esquema|diagrama"
    r"|mapa|mapas|plano|planos|croquis|anexo|anexos|cronograma"
    r"|fase|fases)\b"
)

# Coastal/beach law semantic terms used across profiling and segmentation
COASTAL_TERMS: list[str] = [
    "playa",
    "playas",
    "bahía",
    "bahia",
    "bajamar",
    "litoral",
    "erosión",
    "erosion",
    "ocupación",
    "ocupacion",
    "espacio público",
    "espacio publico",
    "dimar",
    "concesión marítima",
    "concesion maritima",
    "bienes de uso público",
    "bienes de uso publico",
    "recuperación costera",
    "recuperacion costera",
    "servidumbre",
    "protección litoral",
    "proteccion litoral",
    "zona costera",
    "franja de playa",
    "línea de costa",
    "linea de costa",
    "pleamar",
    "marea",
    "puerto",
    "muelle",
    "embarcadero",
    "zona de bajamar",
    "terrenos de bajamar",
    "bien público",
    "bien publico",
    "dominio público",
    "dominio publico",
    "restinga",
    "manglar",
    "estuario",
    "acantilado",
    "vertimiento",
    "vertimientos",
    "aguas residuales",
    "emisario submarino",
    "emisario",
    "arrecife",
    "arrecifes",
    "coral",
    "corales",
    "colector pluvial",
    "colector",
    "contaminación marina",
    "contaminacion marina",
    "pradera marina",
    "praderas marinas",
    "pastos marinos",
    "capitanía de puerto",
    "corpamag",
]

COASTAL_PATTERN: re.Pattern[str] = re.compile(
    r"(?i)\b(" + "|".join(re.escape(t) for t in COASTAL_TERMS) + r")\b"
)

# ------------------------------------------------------------------
# S3 key prefixes
# ------------------------------------------------------------------

RAW_PREFIX: str = "data/raw/"
BRONZE_PREFIX: str = "data/bronze/"
