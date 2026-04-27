# Bug de codificación en `bronze → silver`

**Estado:** abierto · Diagnosticado 2026-04-27

## Síntoma

Metadatos como `Corporación`, `Magistrado ponente`, `Tema principal`, y los
textos de los chunks contienen U+FFFD (`�`) en `data/silver/*.jsonl` y
`data/gold/*.jsonl`.

Ejemplo: `"Mar�a Victoria Qui�ones Triana"` en lugar de
`"María Victoria Quiñones Triana"`. En la UI los popovers de citas y las
tarjetas de fuentes muestran esos `�` directamente.

## Diagnóstico

Conteo de U+FFFD en un mismo documento (`AP Rodrigo Martínez Silva VS
Minambiente y otros`):

| Capa     | U+FFFD |
|----------|--------|
| bronze   | 0      |
| silver   | 48     |
| gold     | 3 732  |

La corrupción nace en `bronze → silver`, es decir en alguno de:

- `ingest/loaders.py`
- `ingest/normalize.py`
- `ingest/sections.py`

Causa más probable: lectura del .md con encoding incorrecto (no `utf-8`), un
`str.encode("ascii", errors="replace")` aplicado en algún paso de
normalización, o un regex aplicado a `bytes` en vez de `str`.

## Mitigación temporal (en producción)

`rag/core/tools.py:sanitize_replacement_chars()` elimina los `\uFFFD` antes de:

- enviar metadatos y contenido al frontend
  (`_docs_to_source_groups` en `rag/api/main.py`).
- enviar el bloque de contexto al LLM (`build_context_block` en
  `rag/core/tools.py`).

Esto **oculta el síntoma** pero no resuelve el problema:

- BM25 sigue indexando tokens rotos como `Acci`, `Qui`, `Corporaci`.
- Los embeddings ya están calculados sobre el texto roto, así que la
  similitud semántica está degradada.
- El frontend muestra texto incompleto ("Mara Victoria Quiones") en lugar de
  garbage, pero sigue siendo incorrecto.

## Fix definitivo

1. Comparar bronze vs silver para el mismo doc y aislar la transformación que
   introduce U+FFFD. Empezar por `ingest/loaders.py` (apertura del .md).
2. Forzar `encoding="utf-8"` en cualquier `open(...)`. Buscar y eliminar
   conversiones a ASCII / regex sobre bytes.
3. Re-correr `make pipeline` (regenera silver, gold y vectorstore con embeddings
   correctos).
4. Eliminar `sanitize_replacement_chars` y todas sus llamadas — son trivialmente
   identificables por grep.
