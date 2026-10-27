# Ingesta offline e incremental de ATLAS

El paquete `ingest.offline` prepara documentos por lotes sin LLM, sin S3 y sin
APIs con cuota. Solo usa archivos locales, Tesseract y el endpoint de embeddings
de Ollama. Los proveedores LLM pueden tener sus claves vacías. Los tests lo
comprueban bloqueando sockets durante un lote con adaptadores de almacenamiento.

Los metadatos y los datasets de evaluación están **no validados por abogados**.
Cobertura de campos, evidencia textual y similitud no prueban corrección jurídica.

## Entorno y dependencias

Linux, Python 3.12+, Tesseract con idioma español, Chroma y Ollama propios.
El extra `offline` de `ingesta/pyproject.toml` agrega PyMuPDF 1.26.5 y Chroma;
el paquete ya declara `langchain-text-splitters`. La ruta histórica con Docling
y enriquecimiento no se ejecuta por estos comandos.

Para un entorno pequeño, sin instalar Docling/Torch del pipeline histórico:

```bash
uv venv --python 3.12 .offline-venv
uv pip install --python .offline-venv/bin/python \
  pymupdf==1.26.5 chromadb==1.3.5 langchain-text-splitters==1.1.1
export PYTHONPATH="$PWD/ingesta"
export OPENAI_API_KEY='' OPENROUTER_API_KEY='' GOOGLE_API_KEY='' GEMINI_API_KEY=''
```

Chroma escucha en localhost:8000 con persistencia propia; Ollama en 11434.
El modelo `embeddinggemma:latest` debe tener este digest exacto:
`85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1`.
Se comprueba por `/api/tags` antes de calcular vectores; un digest distinto
aborta. Todos los vectores deben tener 768 componentes numéricos finitos.

## Agregar y sincronizar

`make -C ingesta pipeline COLLECTION=v2a` y ambos scripts históricos de
`ingesta/scripts/` invocan ahora exclusivamente `ingest.offline`. No arrancan
la API ni invocan el enriquecimiento. Aceptan los argumentos del CLI mediante
`PIPELINE_ARGS` (Make) o argumentos posicionales (scripts). El intérprete por
defecto es `.offline-venv/bin/python`; `OFFLINE_PYTHON` permite uno alternativo.
Estas entradas vacían las claves de proveedores antes de ejecutar el lote.

Ejemplos desde la raíz del repo, con documentos en `data/documents/raw/`:

```bash
.offline-venv/bin/python -m ingest.offline --collection v2a \
  --chunker legacy sync

.offline-venv/bin/python -m ingest.offline --collection v2a \
  --chunker legacy add data/documents/raw/jurisprudencia/nuevo.pdf

.offline-venv/bin/python -m ingest.offline --collection v2b \
  --chunker structure --token-budget 1024 sync
```

`add` exige que el archivo esté dentro de input-dir y no procesa eliminaciones
ajenas. `sync` detecta nuevos, modificados, renombrados y eliminados. Rechaza
enlaces que salgan de la raíz y aborta si no puede recorrerla. Una raíz inexistente
no se interpreta como corpus vacío. `--input-dir`, `--state`, `--cache`, `--port`
y `--batch-size` permiten elegir ubicaciones. El estado por defecto es
`.offline/<coleccion>/` y la caché compartida `.offline/cache/`; están ignorados.

La publicación está limitada a Chroma localhost. Los nombres `v1`, `atlas_v1`,
`rag_playas` y `rag_playas_magdalena` se rechazan antes de conectar. Ollama remoto
requiere `--allow-remote-ollama`; en el experimento se autorizó únicamente el
servicio vectorial propio del sandbox. No hay credenciales AWS en el pipeline.

## Manifiesto y cachés

SQLite `manifest.sqlite` contiene:

| Tabla | Función |
|---|---|
| settings | Hash de pipeline, extractor, normalizador, esquema, chunker, modelo/digest y dimensión |
| documents | doc_id, hash de construcción, artefacto, estado, hash normalizado y SimHash64 |
| paths | Etiquetas/rutas relativas asociadas al doc_id, incluidos alias idénticos |
| runs | Contadores y tiempos de cada ejecución |

`doc_id=SHA256(bytes originales)`: renombrar conserva identidad; modificar
contenido crea otra identidad y retira la versión obsoleta de la colección.
Archivos homónimos con contenido diferente no colisionan. Copias byte a byte
comparten identidad y conservan todos sus alias; no se borra ningún archivo.
Los originales y extracciones NFC quedan en la caché por hash. Los artefactos
`documents/<doc_id>.json.gz` conservan original, texto limpio, metadatos,
páginas, mapa de offsets y chunks. Los offsets son puntos Unicode en la
extracción NFC anterior a limpieza, fin exclusivo; no son offsets binarios PDF.

PDF digital usa PyMuPDF. Solo páginas con menos de 80 caracteres no blancos pasan
a OCR Tesseract español local; se cachean por contenido/página/versión. Fallos
de OCR aparecen explícitos, sin invocar un servicio externo. La limpieza elimina
controles, compacta espacios y guiones de fin de línea, y detecta mobiliario
por repetición en bordes de páginas (>=60%, al menos2páginas). Puede equivocarse
en casos particulares; original, offsets y evidencias quedan para revisión.

Las cachés de embeddings usan SHA256(digest+texto completo), incluidos encabezado
y sección. `/api/embed` recibe arrays y `truncate=false`: no se permite truncar
silenciosamente documentos. Cada lote valida cardinalidad, dimensión y finitud.
Se registran latencia de embeddings y tiempo por chunk nuevo. Los reintentos
de red/publicación están acotados a dos.

## Metadatos y correcciones

Las reglas se ejecutan ANTES de limpiar. Cada campo contiene `valor`,
`evidencia`, `confianza` y `razon`; ausencias usan null y razón explícita.
Las referencias conservan una lista de citas exactas. El esquema está versionado.
Corporación/ponente/radicado/fecha se extraen de la cabecera; ámbito/municipio
son inferencias por listas/reglas y deben revisarse. La primera coincidencia
gana; alternativas de radicado/ponente/sala se listan como conflictos.

`review_queue.csv` lista ausencias y conflictos. `metadata_coverage.json`
cuenta campos presentes; eso no equivale a exactitud jurídica. Para corregir,
editar `data/metadata_overrides.csv`, CSV separado por comas, UTF-8:

```csv
doc_id,campo,valor,evidencia
HASH_DEL_DOCUMENTO,magistrado_ponente,Nombre corregido,Cita literal del original
```

La corrección manual gana sobre reglas. Si su evidencia no aparece tras NFC,
se rechaza el valor con razón `override_sin_evidencia`; un valor vacío limpia
el campo con razón `correccion_manual`. No hay completado automático.
Repetir sync aplica cambios solo al doc_id afectado; renombrar no invalida los
overrides, pero modificar contenido crea otro doc_id. Los campos admitidos son
tipo_documento, corporacion, sala, clase, numero, anio, radicado, fecha_iso,
magistrado_ponente, ambito, municipio y normas_citadas.

## Variantes, calidad y publicación

`legacy` conserva RecursiveCharacterTextSplitter de 1.000 caracteres, solapamiento 200
y separadores históricos, sobre el texto limpio del documento. No reproduce
la concatenación histórica de las cuatro secciones silver: esta diferencia y
el reemplazo de Docling por extracción local forman parte de la normalización.
`structure` corta primero en artículos/encabezados jurídicos y usa presupuesto
aproximado en tokens: ceil(bytes UTF-8/3). No es el tokenizer del modelo.
El CLI usa 1.024 por defecto en structure y 512 en legacy (legacy se limita por
caracteres). `--token-budget` deja explícito el experimento. El header se descuenta
del presupuesto estructural; se conserva el nombre de sección y los offsets.

Una cabecera por plantilla antecede al texto embebido e indexado por BM25:
`tipo numero/anio — corporacion — M.P. ponente — seccion`.
No se generan resúmenes, keywords ni entidades con LLM. El chunk_id deriva del
doc_id, versión/tipo de chunker, ubicación y contenido con cabecera.

Gates de esquema, identidad, caracteres defectuosos, OCR, secciones y tamaño
solo reportan por defecto: **no excluyen documentos del experimento**.
`--enforce` pone en cuarentena los que fallen y retira sus chunks si ya estaban
en esa colección de trabajo. No borra originales. `duplicates.json` informa
duplicados exactos por texto normalizado y candidatos cercanos SimHash64,
distancia Hamming<=3; los cercanos nunca se fusionan ni eliminan.

Se calculan embeddings antes de publicar el documento, se verifican IDs nuevos
y solo entonces se borran sus chunks obsoletos. Si falla un documento, el run
devuelve código1 y no procesa eliminaciones globales. Upserts parciales son
retomables; no hay una transacción distribuida Chroma+SQLite. No deben ejecutarse
dos escritores simultáneos sobre el mismo manifiesto/colección. Si cambia
pipeline/modelo/configuración, usar otra colección Y otro estado: se rechaza
reutilizar una colección con hash diferente.

```bash
.offline-venv/bin/python -m ingest.offline --collection v2a --chunker legacy \
  export .offline/exports/v2a.jsonl.gz
```

El snapshot exportado incluye manifiesto y checksums de registros/archivo.
Vectores, cachés, manifiestos SQLite y snapshots generados no se versionan.
`run_manifest.json` informa embeddings nuevos, llamadas LLM 0 y CPU local por
documento (incluido OCR hijo). CPU del servicio Ollama, local o remoto, no está
incluida en ese contador Python/OCR; su latencia sí se mide. Una segunda corrida
sin cambios debe producir 0 embeddings nuevos.
