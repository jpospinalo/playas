# Plan: inclusión de normativa en el pipeline de ingesta

## Contexto

El pipeline de ATLAS está diseñado exclusivamente para **sentencias de
jurisprudencia** (Consejo de Estado y tribunales administrativos). La etapa de
seccionado asume una estructura de sentencia de 4 secciones. Necesitamos indexar
también **normativa** (decretos, reglamentos), cuya estructura es distinta
(`TÍTULO`, `CAPÍTULO`, `Artículo N`) y no encaja en ese seccionado.

Este documento define la estrategia para soportar ambos tipos de documento en un
mismo pipeline, diferenciados por **carpeta de origen** (opción A).

---

## Análisis del pipeline actual

El flujo tiene 4 etapas; cada una lee de una capa y escribe en la siguiente:

| Etapa | Módulo | Entrada → Salida |
|---|---|---|
| 1. OCR / conversión | `ingest.pdf_to_md` | PDF (`raw/`) → Markdown + assets (`bronze/`) |
| 2. Normalización + seccionado | `ingest.loaders` → `ingest.sections` | `bronze/*.md` → `silver/*.jsonl` |
| 3. Chunking + enriquecimiento | `ingest.splitter_and_enrich` | `silver/` → `gold/*.jsonl` |
| 4. Indexación | `rag.core.vectorstore` | `gold/` → ChromaDB |

### Estructura de capas

- **`data/raw/`** — PDFs + `metadata.csv` (delimitado por `;`, indexado por
  columna `Archivo` con nombre `.pdf`). Aporta metadatos legales:
  `Corporación`, `Radicado`, `Magistrado ponente`, `Partes procesales`,
  `Tema principal`, etc.
- **`data/bronze/`** — un `.md` por documento + carpeta `assets/`. Los `.md`
  traen headings `## Página N` (marcadores de página de `pdf_to_md`), **no**
  headings de estructura jurídica.
- **`data/silver/`** — un `.jsonl` por documento, ya partido en exactamente
  **4 secciones**.
- **`data/gold/`** — un `.jsonl` por documento, con chunks de ~1000 tokens
  (overlap 200) + `summary`, `keywords`, `entities` generados por LLM.

### Punto crítico — `ingest/sections.py`

`split_by_sections()` está cableado al formato de **sentencia**:

- Asume las 4 secciones canónicas (`Contexto del caso`, `Desarrollo procesal`,
  `Análisis del tribunal`, `Decisión`).
- Clasifica por headings `## ` contra un diccionario de variantes
  (`antecedentes`, `consideraciones de la sala`, `resuelve`…).
- **Siempre produce 4 documentos**, uno por sección.

Qué pasaría con la normativa hoy: los `.md` de normativa solo tienen
`## Página N`. Ninguno clasifica como sección de sentencia → todo el contenido
cae en `active_section=1` ("Contexto del caso"). La estructura real
(`TÍTULO I`, `Artículo 1:`, `Artículo 2:`) está en **texto plano**, no en
headings, así que se ignora por completo. Resultado: un documento normativo
entero etiquetado como "Contexto del caso" de una sentencia inexistente.
Semánticamente roto.

Problemas aguas abajo:

- `metadata_csv.py` no encontrará match (no hay fila de sentencia para un
  decreto) → sin metadatos.
- `tools.build_context_block()` cita con `Corporación` / `Magistrado ponente` /
  `section_name` — campos que no aplican a una norma (que se cita por
  `Artículo` y `Título`).
- El retriever **no filtra por tipo** hoy, así que en una misma búsqueda se
  mezclarían normas y sentencias sin distinción.

---

## Estrategia: discriminador `doc_type` enrutado por carpeta (opción A)

Idea central: introducir un metadato **`doc_type`** (`jurisprudencia` |
`normativa`) que se fija al inicio según la **carpeta de origen** y **enruta
solo la etapa de seccionado (Silver)**, que es la única realmente acoplada al
tipo. Las etapas 1, 3 y 4 se comparten con pequeños ajustes "type-aware".

### Decisión del tipo (opción A — por carpeta)

El tipo se infiere de la ruta de origen. Estructura propuesta en `raw/`
(y espejada en las capas siguientes):

```
data/raw/jurisprudencia/...
data/raw/normativa/...
```

Cero ambigüedad, trivial de extender a un tercer tipo en el futuro.

### Qué hace cada etapa según el tipo

```
                          ┌─ doc_type = jurisprudencia ─┐
raw → bronze (pdf_to_md)  │                             │
  (idéntico ambos tipos)  │  Silver: split_by_sections  │  4 secciones canónicas
                          │         (actual)            │
                          ├─ doc_type = normativa ──────┤
                          │  Silver: split_by_articles  │  1 unidad por Artículo
                          │         (NUEVO)             │  (Título/Capítulo como jerarquía)
                          └─────────────┬───────────────┘
                                        ▼
              Gold: splitter_and_enrich (compartido, prompt type-aware)
                                        ▼
              ChromaDB: vectorstore (compartido, doc_type en metadata)
```

**Etapa 1 — `pdf_to_md` (sin cambios).** La normativa ya está en Markdown; entra
directo a `bronze/`.

**Etapa 2 — Seccionado (aquí está toda la divergencia).** Refactor a un patrón
estrategia: `loaders.py` lee `doc_type` (de la carpeta) y despacha:

- `jurisprudencia` → `split_by_sections()` (lo actual, intacto).
- `normativa` → nuevo `split_by_articles()` que segmenta por `Artículo N`
  (regex sobre texto plano, no headings), arrastrando jerarquía `TÍTULO` /
  `CAPÍTULO` como metadatos. Cada artículo (o grupo de artículos cortos) es la
  unidad natural — equivale a la "sección" de una sentencia. Antes de segmentar
  conviene **eliminar los `## Página N`** porque parten artículos a la mitad.
- Metadatos por tipo: para normativa, en vez de `Corporación/Magistrado`,
  campos como `norma` (ej. "Decreto 2324 de 1984"), `tipo_norma`, `articulo`,
  `titulo`, `capitulo`, `anio`.

**Etapa 3 — Chunking + enriquecimiento (compartido, ajuste menor).** El
`RecursiveCharacterTextSplitter` sirve para ambos. Dos retoques:

- El `chunk_id` ya usa `section_index`; para normativa puede ser
  `{stem}_art{N}_c{idx}`.
- El `_ENRICH_PROMPT` se vuelve type-aware (o se pasa `doc_type` en
  `doc_metadata`) para que el resumen/keywords usen terminología normativa vs
  jurisprudencial.

**Etapa 4 — Indexación (compartido + 1 campo).** `vectorstore` ya serializa
cualquier metadato. Solo hay que **garantizar `doc_type` en cada chunk** para
poder filtrar después. El mismo collection sirve.

### Aguas abajo (RAG serving) — lo que habilita el `doc_type`

- **Retriever:** filtrar/balancear por `doc_type` (ej. traer tanto la norma
  aplicable como la jurisprudencia que la interpreta).
- **`build_context_block()`:** ramificar la cita según tipo — sentencias por
  `Corporación`/`section_name`, normas por `norma`/`artículo`. Clave para que el
  LLM cite "Artículo 2 del Decreto 2324/1984" en vez de inventar una
  corporación.

---

## Resumen de cambios concretos

| Componente | Cambio | Esfuerzo |
|---|---|---|
| `raw/` (estructura) | Subcarpetas por tipo (`jurisprudencia/`, `normativa/`) | Bajo |
| `loaders.py` | Inyectar `doc_type` + despachar estrategia de seccionado | Medio |
| `sections.py` | **Sin tocar** (estrategia jurisprudencia) | — |
| `sections_normativa.py` (nuevo) | `split_by_articles()` por `Artículo/Título` | Medio-alto |
| `normalize.py` | Limpieza opcional de `## Página N` para normativa | Bajo |
| `splitter_and_enrich.py` | Prompt y `chunk_id` type-aware | Bajo |
| `vectorstore.py` | Asegurar `doc_type` en metadata | Mínimo |
| `tools.py` / retriever | Cita y filtro por tipo (fase RAG, posterior) | Medio |

Principio de diseño: **el tipo de documento se resuelve una sola vez al entrar
(por carpeta), y solo la etapa Silver se bifurca**; el resto del pipeline
permanece único. Esto deja la puerta abierta a un tercer tipo futuro (ej.
`doctrina`, `conceptos`) añadiendo solo una estrategia de seccionado más, sin
tocar las demás etapas.
