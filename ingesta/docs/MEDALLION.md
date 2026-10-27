# Capas medallion de la ingesta offline

La identidad de un documento es el SHA256 de sus bytes originales. Las capas
persistentes permiten repetir una etapa sin volver a extraer el PDF. No se usan
LLM para extraer metadatos ni para medir calidad. Los embeddings reales requieren
el Ollama local ya utilizado por el pipeline; la publicación usa Chroma local.

```text
raw/ (originales + metadata.csv; solo lectura)
  |
  | PyMuPDF + Tesseract spa local si la página tiene <80 caracteres no blancos
  v
documents-v2/bronze/<doc_id>.txt + .extraction.json + .quality.json
  |
  | limpieza con mapa de offsets + reglas legales con evidencia + CSV separado
  v
documents-v2/silver/<doc_id>.txt + .jsonl + .context.json
  |
  | chunker legacy o structure + cabecera de plantilla
  v
documents-v2/gold/<doc_id>.jsonl
  |
  | referencia por SHA256(digest_modelo + NUL + page_content)
  +------> caché SQLite de vectores ------> Chroma
  v
documents-v2/embeddings/<doc_id>.json (referencias, nunca vectores)

capas existentes + caché opcional + revisión opcional
  |
  v
documents-v2/quality/{quality_report.json,quality_por_documento.csv,quality_report.md}
```

## Archivos y compatibilidad con v1

| Capa | v1 | v2 |
|---|---|---|
| raw | PDF y CSV originales | Los mismos, sin escrituras |
| bronze | Markdown Docling por nombre, entidades, imágenes y calidad histórica | Texto NFC por hash; páginas separadas por `\n\f\n`; extracción y medidas objetivas separadas |
| silver | JSONL `{page_content, metadata}`, cuatro secciones en jurisprudencia, artículos en normativa; campos del CSV | La misma envoltura JSONL, `section_index`, `section_name`, offsets y metadatos legales con evidencia; CSV bajo `metadata_curada` |
| gold | JSONL de chunks por nombre de archivo | La misma envoltura JSONL; cabecera incluida en `page_content`, `chunk_id`, offsets, digest y clave de caché |

`bronze/*.extraction.json` incluye extractor y versión, caracteres no blancos por
página, páginas OCR, confianza OCR por página (media de palabras TSV con confianza
finita >=0), errores OCR y referencia al original conservado en caché. La media
del informe promedia las confidencias disponibles por página; una página sin
confianza no se convierte en cero. `bronze/*.quality.json` contiene exclusivamente
medidas de extracción con umbrales y banderas; no contiene opiniones ni una nota.

Silver conserva todo el texto: fragmentos contiguos, incluido el preámbulo. En
jurisprudencia clasifica encabezados reconocidos en Contexto del caso (1),
Desarrollo procesal (2), Análisis del tribunal (3) y Decisión (4). No inventa
secciones faltantes. En normativa separa por artículo y conserva el preámbulo con
índice 0. Los nombres canónicos son compatibles con v1; el reconocimiento por
reglas puede producir menos secciones que el proceso histórico. `.context.json`
conserva el texto limpio, mapas de páginas/offsets, metadatos y origen necesarios
para reconstruir gold sin repetir limpieza ni metadatos.

Los campos legales mantienen `valor`, `evidencia`, `confianza` y `razon`, conforme
a `legal-metadata-2`. La evidencia se busca antes de retirar cabeceras/pies. La
confianza de una regla es una configuración heurística de esa regla, no una
medición de exactitud jurídica. Los offsets son posiciones Unicode, fin exclusivo;
`source_start/source_end` se refieren al texto NFC de bronze, no a bytes del PDF.
`clean_start/clean_end` se refieren al texto silver. Las páginas se numeran desde 1.

Gold conserva los campos usados por Chroma como escalares; `legal_metadata` y
`metadata_curada` se serializan como JSON en cadenas. Incluye `section_index`,
`embedding_cache_key`, `embedding_model_digest`, `token_budget` y `chunker`.
No hay vectores en ninguna capa. `embeddings/*.json` registra dimensión, digest
y claves después de publicar; los vectores quedan en la caché y Chroma.

## CSV curado y diferencias respecto a las reglas

Se leen CSV UTF-8 con BOM opcional y separador `;`, coma o tabulación, dentro de
input-dir. La columna `Archivo` (también `file`, `source`, `ruta`) se empareja por
stem normalizado sin acentos ni diferencias de mayúsculas. Más de una fila
coincidente se registra como `origen_csv.conflicto_csv`: no se elige una al azar.
Se conservan las columnas con nombre y sus valores, incluso vacíos. No se importa
el cargador S3 de v1 ni se hace ninguna consulta de red para leer el CSV.

El CSV se guarda bajo `metadata_curada` y nunca reemplaza `campos`. Por cada
columna `cobertura_csv` registra campo regex, `reproducido` y estado: `coincide`,
`sin_regla`, `sin_evidencia` o `difiere`. Coincidencia compara valores sin acentos,
mayúsculas ni puntuación; es una comprobación de cadenas, no equivalencia jurídica.

| Columna del CSV histórico | Regla comparable | Cobertura |
|---|---|---|
| Corporación | corporacion | Disponible si hay evidencia textual |
| Radicado | radicado | Disponible si hay evidencia textual |
| Magistrado ponente | magistrado_ponente | Disponible si hay evidencia textual |
| Archivo | ninguna | Procedencia, no metadato jurídico inferido |
| Nº (SM-xx) | ninguna | Identificador editorial; no equivale al número de sentencia |
| Instancia | ninguna | No se reproduce por las reglas actuales |
| Partes procesales | ninguna | No se reproduce |
| Tema principal | ninguna | No se reproduce |
| RELACIÓN PLAYAS | ninguna | No se reproduce |
| CATEGORIA ANALISIS | ninguna | No se reproduce |
| TEMÁTICA | ninguna | No se reproduce |

Otros CSV pueden aportar Tipo de documento/Tipo documento, Fecha, Número, Año,
Sala y Municipio, comparables con los campos regex homónimos. La tabla ejecutable
está en `CSV_REGEX_FIELDS`, en `ingest/offline/layers.py`; el resultado real por
documento queda en silver y en el informe de calidad. `Nº` deliberadamente no se
asocia a `numero`.

## Ejecución y reanudación

Desde la raíz del repositorio, con `ingesta` instalado o `PYTHONPATH=ingesta`:

```bash
python -m ingest.offline --collection atlas_medallion --layers-root data/documents-v2 sync
python -m ingest.offline --collection atlas_medallion add data/documents/raw/jurisprudencia/fallo.pdf
python -m ingest.offline --collection atlas_medallion --from-stage silver sync
python -m ingest.offline --collection atlas_medallion sync --from-stage gold
python -m ingest.offline --collection atlas_medallion --from-stage embeddings sync
python -m ingest.offline --collection atlas_medallion export ingesta/salida/chunks.jsonl.gz
```

`--layers-root` vale `data/documents-v2/` por defecto en el CLI. La API Python
histórica `Pipeline(...)` sin este argumento usa `<state>/layers`, para mantener
aislados los consumidores y pruebas existentes. Los demás argumentos posicionales
de esa API no cambian. `sync`, `add` y `export` conservan su función; el artefacto
comprimido histórico sigue disponible para exportar.

`--from-stage bronze` fuerza extracción (su caché puede evitar trabajo repetido)
y todas las etapas posteriores. `silver` lee bronze, `gold` lee silver y
`embeddings` lee gold. Cada etapa anterior debe existir y tener hashes/versiones
válidos; si no, se informa qué etapa reconstruir. No hay fallback silencioso a
reextraer. La reanudación de sync desde silver/gold/embeddings usa las rutas del
manifiesto o catálogo: puede operar sin originales disponibles. Para detectar
altas, modificaciones y bajas del raw se ejecuta sync normal. Si raw no existe,
se conserva el CSV ya registrado en silver; si está disponible se vuelve a leer.

El manifiesto SQLite añade `layers(doc_id, stage, version, input_hash, artifacts)`;
`artifacts` contiene SHA256 por archivo. Las entradas incluyen hashes de etapas
previas y configuración relevante. `STAGE_VERSIONS` permite invalidar solo una
etapa y las posteriores; las versiones de extractor, normalizador, esquema legal
y chunker también intervienen en sus entradas. Cambiar modelo/digest, modalidad
de chunker o presupuesto sigue requiriendo estado y colección nuevos, como antes.
Las versiones internas de etapa pueden cambiar dentro de la misma colección.
Se reconoce y migra el hash histórico de configuración únicamente cuando coincide
exactamente con la configuración solicitada (incluida la versión previa del
extractor); se conserva la protección ante cambios de modelo o modalidad.

Un segundo sync sin cambios no reescribe capas ni informes objetivos y no calcula
embeddings. Se compara el hash antes de escribir y se preservan mtimes. El
manifiesto y los registros operativos de cada ejecución sí se actualizan:
`runs` y `run_manifest.json` incluyen tiempos y fecha. No forman parte de las
capas deterministas. Al renombrar, se conservan bytes y origen inicial de las
capas; los alias actuales quedan en `catalog.json`, el manifiesto y Chroma.
Al modificar los bytes se genera otro doc_id; el anterior queda `deleted` en
SQLite y en `catalog.json.retirados`, y se elimina de
Chroma. Sus capas se conservan para auditoría y se excluyen del informe activo.
No se borran originales. Si falla un documento, se conservan las bajas pendientes
hasta completar una ejecución sin errores.

Las salidas se resuelven antes de escribir; se rechazan input/raw, sus ancestros,
las capas v1 y los enlaces que conduzcan allí. También se valida cada destino de
capa y quality. Las escrituras usan temporal y `os.replace`. Bloqueos exclusivos
locales `.writer.lock` protegen estado, capas y caché; otro bloqueo serializa cada
operación Chroma por puerto/colección en `.offline/chroma-writers/`. Ante un cierre
abrupto, comprobar que no haya un proceso activo antes de retirar manualmente un
bloqueo huérfano. No hay coordinación de escritores entre máquinas distintas.

## Informe objetivo de calidad

```bash
python -m ingest.offline quality --layers-root data/documents-v2
python -m ingest.offline quality --layers-root data/documents-v2 --state .offline/atlas_medallion --cache .offline/cache
python -m ingest.offline quality --layers-root data/documents-v2 --compare-v1 data/documents
python -m ingest.offline quality --layers-root data/documents-v2 --enforce
```

No necesita colección, Ollama, Tesseract ni Chroma. Lee capas, catálogo, manifiesto
y cola de revisión opcionales, y abre la caché SQLite en modo solo lectura.
Escribe únicamente dentro de `<layers-root>/quality/`. Los tres informes son
deterministas, ordenados y sin fecha. Si falta una capa se informa, sin abortar;
si no hay caché o no puede leerse, los embeddings quedan `no medido`. Las capas
retiradas se excluyen. La copia de capas sin estado puede analizarse, pero para
medir la cola de revisión debe pasarse `--state`.

El informe también se ejecuta al final de sync/add. Por defecto informa. Con
`--enforce`, cualquier bandera roja produce salida no exitosa; las puertas
históricas siguen poniendo en cuarentena documentos antes de publicar. Las
banderas adicionales del informe final no deshacen publicaciones ya realizadas.
No se calcula puntuación compuesta ni se presenta el resultado como verdad sobre
la calidad jurídica o semántica.

Cada métrica incorpora su valor, umbral y bandera. La constante única
`THRESHOLDS` de `ingest/offline/quality.py` es la fuente ejecutable; el informe
Markdown reproduce la tabla completa. La tabla siguiente documenta sus valores:

| Métrica | Dirección | Verde | Amarillo |
|---|---|---:|---:|
| pages | min | 1 | 1 |
| extracted_chars | min | 200 | 80 |
| chars_per_page | min | 80 | 40 |
| near_empty_pct | max | 5 | 20 |
| ocr_pct | max | 25 | 75 |
| ocr_confidence | min | 85 | 60 |
| extraction_errors | max | 0 | 0 |
| invalid_pct | max | 0.2 | 1 |
| mojibake_pct | max | 0.2 | 1 |
| alphabetic_pct | min | 50 | 30 |
| eol_hyphenations | max | 0 | 3 |
| repeated_corner_lines | max | 0 | 2 |
| removed_chars | max | 10000 | 100000 |
| removed_pct | max | 10 | 30 |
| sections_detected | min | 1 | 1 |
| sections_expected | min | 1 | 1 |
| structure_coverage_pct | min | 100 | 50 |
| metadata_present | min | 12 | 6 |
| metadata_absent | max | 0 | 6 |
| metadata_conflicts | max | 0 | 0 |
| metadata_without_evidence | max | 0 | 0 |
| review_queue_entries | max | 0 | 6 |
| chunk_count | min | 1 | 1 |
| chunk_median | min | 200 | 100 |
| chunk_p5 | min | 200 | 100 |
| chunk_p95 | max | 4000 | 8000 |
| short_chunks_pct | max | 5 | 20 |
| over_budget_pct | max | 0 | 5 |
| exact_duplicates | max | 0 | 2 |
| near_duplicates | max | 0 | 2 |
| embedding_dimension | equal | 768 | 768 |
| invalid_vectors | max | 0 | 0 |
| chunks_without_vector | max | 0 | 0 |
| missing_layers | max | 0 | 0 |

Dirección `min`: verde si valor >= límite verde, amarillo si >= límite amarillo;
`max`: verde si <= límite verde, amarillo si <= límite amarillo. Fuera de ambos,
rojo. `equal` exige igualdad. Ausencia de medición: `no medido`. Son reglas
operativas explícitas, no umbrales validados en un conjunto de referencia.

Los porcentajes están en 0–100. Caracteres/página y páginas casi vacías excluyen
blancos; total de caracteres incluye espacios y separadores de página. La tasa
OCR expresa cuánto se recurrió a OCR, no demuestra errores. Los caracteres
inválidos (`invalid_pct`) cuentan U+FFFD y controles C0/C1 salvo LF/TAB/FF;
CR sí se cuenta. `mojibake_pct` mide por separado posiciones únicas de patrones
heurísticos: `Ã[\x80-\xBF]`, `Ã[a-zA-Z©±³º¡]`, `â€` con el carácter siguiente si
existe, `Â[^\w]` e `ï¿½`. También cuenta los glifos `Æ æ Ø ø œ Œ ł ˇ` cuando
son adyacentes a una letra latina dentro de una palabra, incluso al inicio/final
(`BogotÆ`, `diecisØis`); aislados no se cuentan. Son indicios de codificación o
de correspondencias WinAnsi/MacRoman en fuentes PDF, no una prueba lingüística.
`Bogotá` y los acentos españoles correctos no se cuentan. Una posición puede
contribuir a ambas métricas si también es un control: ninguna oculta a la otra.
Ambas tasas tienen umbrales propios: verde <=0,2%, amarillo <=1%, rojo >1%.
La proporción alfabética usa `str.isalpha()` sobre caracteres totales.
La guionización residual cuenta palabras partidas con guion al final de línea.
Los posibles restos de cabecera/pie son líneas cortas de las dos primeras/últimas
líneas de cada página limpia, normalizadas por números y repetidas en >=60% de
las páginas, con mínimo 2; se excluyen encabezados estructurales reconocidos.

Caracteres retirados = `max(0, len(bronze)-len(silver))`; incluye separadores y
mobiliario retirado, no solo ruido. El límite de conteo es una alerta de volumen;
el porcentaje permite interpretarlo según el tamaño del documento. La estructura
esperada es 4 categorías en jurisprudencia; normativa espera los números de
artículo distintos detectados en bronze (mínimo 1). Esta expectativa es limitada:
no puede detectar artículos que ya falten en la extracción. La cobertura cuenta
categorías con encabezado/artículos presentes, sin dar crédito a secciones
inventadas. Las ausencias de campos son explícitas; evidencia ausente o que no sea
subcadena de bronze se cuenta aparte, incluidas listas de normas citadas. Los
conflictos incluyen reglas, ambigüedad CSV y discrepancias CSV/reglas.

Los tamaños de chunk usan `len(page_content)`, incluida la cabecera. Mediana y
percentiles p5/p95 usan interpolación lineal en índices `(n-1)*p`. El presupuesto
usa la estimación existente `ceil(bytes UTF-8/3)`, también en legacy: no es un
tokenizador del modelo. Duplicados exactos = ocurrencias sobrantes de texto
idéntico dentro de cada documento; cercanos = pares distintos con distancia
SimHash64 <=3, reutilizando la función del pipeline y cuatro bandas de 16 bits.
No se cuentan pares exactos como cercanos. La caché comprueba dimensión 768,
valores numéricos finitos y presencia de cada clave sin calcular vectores nuevos.

## Comparación v1/v2

`quality --compare-v1 data/documents` ignora por completo los `quality.json` v1.
Toma texto v1 de `bronze/**/*.md`, retira referencias Markdown de imágenes,
prefijos de encabezado, destinos de enlaces (mantiene etiqueta), separadores de
tabla y marcas de énfasis/código. Conserva el resto, incluidos espacios de tablas;
no aplica una limpieza agresiva que favorezca a uno de los lados. Para v2 toma
bronze. Los chunks son `page_content` de ambos gold. Se calculan con las mismas
funciones caracteres extraídos, porcentajes inválido y mojibake, cantidad, mediana, p5/p95,
porcentaje <200, duplicados exactos y cercanos.

La coincidencia usa ruta raw relativa sin extensión frente a ruta bronze relativa,
normalizada sin acentos/mayúsculas; como alternativa admite stem único. Se
registran documentos sin pareja y coincidencias ambiguas. Solo se agregan pares
coincidentes, con medias por documento para evitar comparar corpus diferentes.
Las regresiones objetivas se evalúan por métrica, sin confundir tamaño con calidad:

- `extracted_chars`: regresión solo si v2 extrae **menos del 80%** de v1;
  exactamente el 80% no activa la regla.
- `invalid_pct`, `mojibake_pct`, `short_chunks_pct`: regresión si aumentan **>20%**
  relativo y **al menos 0,1 puntos porcentuales**.
- `exact_duplicates`, `near_duplicates`: regresión si aumentan **>20%** relativo
  y **al menos 2** duplicados. Pasar de 0 a 1 no es regresión.
- `chunk_count`, `chunk_median`, `chunk_p5`, `chunk_p95`: variaciones en cualquier
  dirección **>20%** se informan como **cambio, no regresión**. Nunca cuentan como
  métricas adversas ni vuelven roja la comparación.

La variación relativa usa v1 como denominador. Para tasas/duplicados con base
cero se usa el mínimo absoluto anterior como denominador de la magnitud, finita
y determinista; el mínimo absoluto sigue siendo obligatorio. Para tamaños con
base cero, un valor nuevo positivo se registra como cambio del 100%.
La bandera `comparacion` por documento es roja si hay al menos una métrica
adversa, amarilla si solo hay cambios neutrales >20%, verde en otro caso.
Los artefactos v1 faltantes se informan aparte y no son regresiones de métricas.
Estas reglas comparativas son distintas de los umbrales absolutos de calidad.

La tabla agregada incluye **documentos con regresión** por métrica (cero para
las neutrales), además del conteo explícito de documentos con retención <80%.
**Diez documentos con más regresiones objetivas** ordena primero por número de
métricas adversas y después por máxima magnitud relativa adversa; los empates
se resuelven por `doc_id`. Si hay menos de diez documentos con regresiones,
se indica cuántos hay y se completa con los mayores cambios neutrales disponibles,
rotulados **cambio, no regresión**. Los primeros cinco de esa lista muestran
extractos iniciales v1/v2 en columnas, de hasta 600 caracteres. Los encabezados
por documento y la lista incluyen las rutas raw relativas junto al `doc_id`
(todos sus alias disponibles). Se comparan todas las métricas por documento y
en agregado.

## Tiempos y benchmarks

`runs.report` y `run_manifest.json` exponen `stage_timings`: `seconds` de reloj
monótono y `calls` para extraction, ocr, cleaning, metadata, chunking, duplicates,
embeddings, chroma_publish y quality_report. Extraction descuenta el tiempo OCR;
quality_report incluye las mediciones de duplicados realizadas dentro del informe.
`calls` cuenta invocaciones, salvo OCR que cuenta páginas OCR nuevas. Los contadores
existentes de archivos, documentos, páginas OCR y embeddings nuevos siguen
disponibles. Los tiempos de lectura de capas/catálogo no se imputan a limpieza ni
extracción. Los tiempos se guardan fuera del informe objetivo determinista.

```bash
python -m ingest.offline --collection bench_medallion --state ingesta/salida/bench-state --cache ingesta/salida/bench-cache --layers-root ingesta/salida/bench-layers --fake-embeddings sync
python -m ingest.offline quality --layers-root ingesta/salida/bench-layers --cache ingesta/salida/bench-cache --fake-embeddings
```

`--fake-embeddings` nunca es el valor por defecto. Produce 768 componentes finitas,
normalizadas, derivadas de SHA256 del texto e índice, sin aleatoriedad global.
Tiene digest `bench-sha256-768-1` y archivo `bench_embeddings.sqlite`, separados de
los vectores reales. El CLI, Pipeline y publicador rechazan usar esos vectores en
colecciones cuyo nombre no empiece por `bench_`. La publicación del benchmark
sigue necesitando Chroma local. Estos vectores solo miden el coste del pipeline;
no sirven para evaluar recuperación semántica.

## Muestra versionable de tres documentos

`.gitignore` ignora las salidas de `data/documents-v2/` y permite únicamente el
subárbol `data/documents-v2/sample/`, reabriendo primero los directorios para que
la negación funcione.

La muestra versionada copia bronze, silver y gold de tres decretos digitales
cortos de la corrida real de 56 documentos en Linux. No incluye `embeddings/`
(esa corrida usó `--fake-embeddings`), `catalog.json`, `quality/`, estado, caché
ni vectores. Tampoco incluye un documento escaneado. `sample/README.md` lista los
doc_id. Para regenerarla con otros originales:

```bash
python -m ingest.offline --input-dir ingesta/salida/sample-raw --collection bench_muestra --state ingesta/salida/sample-state --cache ingesta/salida/sample-cache --layers-root data/documents-v2/sample sync
```

`.extraction.json` referencia el original por nombre de contenido, sin rutas
absolutas de la máquina que produjo la muestra.

## Verificación

En Linux con dependencias instaladas:

```bash
cd ingesta
python -m pytest tests/unit
python -m ruff check ingest/offline ingest/offline_embeddings.py tests/unit/test_medallion_offline.py
python -m ruff format --check ingest/offline ingest/offline_embeddings.py tests/unit/test_medallion_offline.py
```

Sin dependencias externas pueden ejecutarse los contratos de capas y calidad:

```bash
cd ingesta
python -m unittest discover -s tests/unit -p test_medallion_offline.py -v
```

Esas pruebas aíslan el splitter con un generador controlado; las pruebas históricas
siguen verificando el splitter real, los offsets y el presupuesto. Las pruebas de
OCR real y publicación requieren el entorno Linux y sus servicios locales.
