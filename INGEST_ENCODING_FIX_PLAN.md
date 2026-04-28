# Plan: arreglar la corrupción U+FFFD en `bronze → silver`

> **Para Claude Code en un chat nuevo.** Este archivo es local — no está
> versionado y no debe commitearse. Léelo de principio a fin antes de tocar
> código.

## Contexto

El sistema RAG de este repo (`rag_playas`) tiene un bug de encoding en la
ingestión: documentos limpios en `data/bronze/*.md` aparecen corruptos en
`data/silver/*.jsonl` con caracteres de reemplazo Unicode (`�`, U+FFFD) en
metadatos y contenido. Esto degrada BM25, los embeddings y la respuesta del
LLM.

Hay un **parche temporal** activo (`rag/core/tools.py:sanitize_replacement_chars`)
que elimina los `\uFFFD` en runtime. Tu objetivo es **eliminar el parche y
arreglar la causa raíz**, luego re-ingestar el corpus.

Documento de referencia ya escrito: `docs/INGEST_ENCODING_BUG.md` (diagnóstico
inicial). Léelo primero.

## Estado verificado al momento de escribir este plan

Conteo de U+FFFD para `AP Rodrigo Martínez Silva VS Minambiente y otros`:

| Capa     | U+FFFD |
|----------|--------|
| bronze (`.md`)   | 0      |
| silver (`.jsonl`)| 48     |
| gold (`.jsonl`)  | 3 732  |

→ La corrupción **se introduce en el paso bronze→silver** y la enriquecimiento
de gold (Gemini) la amplifica porque se le manda contexto roto.

## Pasos

### Paso 1 — Reproducir el diagnóstico

Antes de cambiar nada, confirma que el bug sigue exactamente como se describe.
Ejecuta:

```bash
cd /Users/daniv/dev/USA/rag_playas
python3 - <<'PY'
import re
from pathlib import Path

DOC = "AP Rodrigo Martínez Silva VS Minambiente y otros"

def count(path):
    raw = Path(path).read_bytes()
    return raw.count(b"\xef\xbf\xbd")  # UTF-8 de U+FFFD

print("bronze:", count(f"data/bronze/{DOC}.md"))
print("silver:", count(f"data/silver/{DOC}.jsonl"))
print("gold  :", count(f"data/gold/{DOC}.jsonl"))
PY
```

Si bronze ≠ 0, el bug se movió a una capa anterior (Docling) y este plan no
aplica — para inmediatamente y avísale al usuario.

Si bronze = 0 y silver > 0, sigue al paso 2.

### Paso 2 — Aislar la transformación culpable

Los archivos a inspeccionar (en orden de probabilidad):

1. `ingest/loaders.py` — convierte `bronze/*.md` → `silver/*.jsonl`. Aquí ocurre
   la lectura del archivo Markdown. Es el sospechoso #1.
2. `ingest/normalize.py` — limpieza de metadatos.
3. `ingest/sections.py` — split por encabezados.

Lee los tres con `Read`. **Busca específicamente:**

- Llamadas a `open(...)` sin `encoding="utf-8"` explícito.
- Conversiones tipo `.encode("ascii", ...)`, `.encode("latin-1", ...)`,
  `bytes.decode("ascii", errors="replace")`.
- Regex aplicados a `bytes` en vez de `str` (señal: `re.compile(b"...")` o
  iterar sobre el resultado de `f.read()` cuando `f` se abrió en modo `"rb"`).
- Cualquier paso que use `unicodedata.normalize("NFKD", ...)` seguido de un
  filtro ASCII.
- Headers o nombres de columnas en formato `Corporación` que pasen por una
  función de slugify/normalización agresiva.

Reportá al usuario lo que encontraste antes de tocar código.

### Paso 3 — Confirmar la hipótesis con un experimento mínimo

Una vez identificado el sospechoso, crea un script de un solo uso (no lo
commitees) que:

1. Toma un `.md` específico de `bronze/`.
2. Aplica solo la función sospechosa (la que crees que rompe el encoding).
3. Cuenta U+FFFD en la salida.

Si confirmás que esa función introduce los `\uFFFD`, andá al paso 4. Si no,
volvé al paso 2 con otro candidato.

### Paso 4 — Corregir la causa raíz

Aplicá el fix mínimo: típicamente añadir `encoding="utf-8"` al `open(...)`,
quitar el `.encode("ascii")`, o cambiar el regex de bytes a str. **No agregues
defensas adicionales** — solo corregí lo que rompe.

Validá con un test rápido de un solo doc:

```bash
uv run python -m ingest.loaders   # con flag o env var para que procese 1 solo .md, si existe
# o ejecutá la función directamente sobre un doc específico via -c
```

Verificá que el silver resultante tenga 0 U+FFFD para ese doc.

### Paso 5 — Re-ingestar el corpus completo

Una vez probado en un doc:

```bash
make pipeline   # corre las 4 etapas: pdf_to_md, loaders, splitter_and_enrich, vectorstore
```

Importante:

- **`splitter_and_enrich` paga llamadas a Gemini** (re-genera summaries,
  keywords, entidades). Avisale al usuario antes de ejecutarlo y confirmá que
  está OK con el costo.
- `vectorstore` re-genera embeddings vía Ollama (EC2). Tomá nota del nombre de
  colección actual en `rag/config.py` (al momento de este plan: `rag_playas_5_docs`).
  Discutí si re-indexar in-place o crear una nueva colección y promoverla.

Después del pipeline, repetí el conteo del paso 1 — los tres niveles deben
estar en 0.

### Paso 6 — Eliminar el parche temporal

Una vez el corpus está limpio, hay que retirar `sanitize_replacement_chars`:

```bash
grep -rn "sanitize_replacement_chars" rag/ tests/
```

Esperás verlo en:

- `rag/core/tools.py` (definición + 7 llamadas dentro de `build_context_block`)
- `rag/api/main.py` (1 import + 2 llamadas en `_docs_to_source_groups`)

Borralo todo. También borrá las líneas que tratan variantes mojibake del key
"Corporación" en `tools.py:build_context_block`:

```python
# antes
corporacion = (
    meta.get("Corporación") or meta.get("CorporaciÃ³n") or meta.get("Corporacion", "")
)
# después
corporacion = meta.get("Corporación", "")
```

(Las variantes `CorporaciÃ³n` / `Corporacion` son artefactos de bugs de encoding
históricos; ya no aplican con el corpus limpio.)

Corré:

```bash
make lint
make test
```

Y probá end-to-end con `make app` + `make frontend` haciendo una consulta que
recupere ≥2 fragmentos del mismo expediente. En el popover de la cita debería
aparecer "María Victoria Quiñones Triana" correctamente.

### Paso 7 — Cerrar la documentación

- Eliminá `docs/INGEST_ENCODING_BUG.md` o reemplazá su contenido con una nota
  histórica breve apuntando al commit que corrige el bug.
- Borrá este archivo (`INGEST_ENCODING_FIX_PLAN.md`) — ya cumplió su propósito.

### Paso 8 — Commit

Un commit por bloque lógico:

1. `fix(ingest): <causa específica> en bronze→silver` — el fix de raíz.
2. `chore: re-ingestar corpus tras fix de encoding` — si querés versionar
   data/silver y data/gold (revisá `.gitignore` antes; probablemente no estén
   versionados).
3. `revert(rag): retirar parche sanitize_replacement_chars tras fix` — borra el
   parche y la doc temporal.

## Pistas adicionales

- El usuario ya verificó que el problema **no** está en Docling (bronze está
  limpio), no pierdas tiempo ahí.
- Los caracteres afectados son siempre **multibyte UTF-8** (á, í, ó, ú, ñ, ü).
  Eso descarta corrupciones aleatorias y apunta a un decode/encode mal
  configurado.
- Si encontrás que el bug está en `loaders.py` línea X, antes de fixearlo,
  buscá en git blame quién introdujo esa línea y mirá el contexto del commit —
  puede haber sido un workaround para otro problema que reaparecerá.
- No te metas con `frontend/`. El frontend ya muestra correctamente lo que el
  backend le manda. El parche actual deja "Mara Quiones" (faltan letras) en
  lugar de "Mar�a Qui�ones" — eso desaparece solo cuando re-ingestes.

## Criterios de éxito

- [ ] Conteo de U+FFFD = 0 en bronze, silver y gold para todos los docs.
- [ ] `sanitize_replacement_chars` ya no existe en el repo.
- [ ] `make lint` y `make test` pasan.
- [ ] Una consulta real al RAG muestra metadatos con tildes y eñes correctas en
      la UI.
- [ ] `docs/INGEST_ENCODING_BUG.md` y `INGEST_ENCODING_FIX_PLAN.md` ya no están
      (o están reducidos a una nota histórica).
