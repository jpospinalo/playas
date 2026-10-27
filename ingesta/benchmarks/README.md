# Benchmarks de escalabilidad

Harness separado de `ingest`, ejecutable desde la raíz del repositorio. No modifica
el pipeline ni `data/documents/`. Todos los resultados se imprimen como JSON y se
guardan bajo el `--out` explícito, excepto `cost` sin `--out`, que solo imprime.
`report --out` recibe un **archivo Markdown**, la excepción explícita al directorio.
Solo se usan colecciones `bench_`. No se llama a modelos generativos ni proveedores
externos; los únicos servicios son Ollama y Chroma locales cuando corresponde.

## Preparación

Entorno objetivo: EC2 t3.large, 2 vCPU, 8 GB, Ubuntu 24.04, Python 3.12,
PyMuPDF y chromadb del entorno offline, GNU `/usr/bin/time`, Tesseract con idioma
`spa`, Ollama con el digest de `embeddinggemma:latest` fijado por el pipeline en
`127.0.0.1:11434` y Chroma en `127.0.0.1:8000`. Si falta GNU time se requiere
`psutil`; no hay instalación ni descarga automática. El splitter del pipeline
también debe estar instalado. Ollama/Chroma deben iniciarse previamente y guardar
su propio estado en las ubicaciones configuradas por el operador; ese almacenamiento
de los servidores no se incluye en las escrituras ni en el tamaño de disco local
del harness. Chroma conserva las colecciones del pipeline para permitir sync/add;
el script de consultas elimina su colección propia al terminar, incluso ante errores.

Ejecutar desde la raíz. Estas variables evitan bytecode fuera de las salidas:

```bash
export PYTHONPATH="$PWD/ingesta"
export PYTHONDONTWRITEBYTECODE=1
export ANONYMIZED_TELEMETRY=False
PY="$PWD/ingesta/.venv/bin/python"
OUT="$PWD/ingesta/benchmarks/resultados"
```

## Orden exacto de ejecución

1. Extracción/OCR del corpus real; todas las mediciones usan caché nueva por PDF.

   ```bash
   "$PY" -B -m benchmarks.extract_parallel --input data/documents/raw \
     --workers 1,2,4 --out "$OUT/extract"
   # Prueba corta opcional: añadir --limit 5.
   ```

2. Construir escalas sintéticas. Cada `raw` de destino debe estar vacío. Orden
   lexicográfico de rutas relativas, ciclo determinista y PRNG con semilla explícita.

   ```bash
   for N in 56 112 224; do
     "$PY" -B -m benchmarks.synth_corpus --src data/documents/raw \
       --n "$N" --seed 0 --out "$OUT/corpus_$N"
   done
   ```

3. Medir el pipeline completo en escalas con embeddings reales. Las colecciones
   deben ser nuevas; en repeticiones completas usar otro prefijo y otro `--out`.
   Los `run_pipeline.json` distinguen el sync inicial del segundo sync sin cambios.

   ```bash
   for N in 56 112 224; do
     "$PY" -B -m benchmarks.run_pipeline --input "$OUT/corpus_$N/raw" \
       --out "$OUT/pipeline_$N" --collection "bench_esc_real_$N" \
       --chunker legacy --repeat-sync
   done
   ```

   Para aislar el costo Python/Chroma en escalas mayores, hacer una serie separada
   con `--fake-embeddings`, un estado nuevo y otra colección `bench_esc_fake_N`.
   **Embeddings ficticios = embeddings NO medidos**; su tasa real queda `null`.
   `--layers-root`, `--state` y `--cache` son rutas relativas a `--out` (por defecto
   `layers`, `state`, `cache`); las absolutas deben estar dentro de ese directorio.
   Sus árboles deben ser separados. Se rechazan salidas que solapen la entrada,
   enlaces/junctions y destinos bajo `data/documents`.

   Reprocesar capas existentes, sin volver a usar ese tiempo como escala fría:

   ```bash
   "$PY" -B -m benchmarks.run_pipeline --input "$OUT/corpus_56/raw" \
     --out "$OUT/pipeline_56" --collection bench_esc_real_56 --from-stage gold
   ```

   `--from-stage bronze|silver|gold|embeddings` solo afecta al primer sync del
   comando; los siguientes sync/add son incrementales normales. A partir de silver
   se requieren capas previas válidas. Los overrides manuales se desactivan con una
   ruta ausente dentro de `--out`; los CSV presentes en input se leen normalmente.

4. Medir altas incrementales en otro estado. `--extra-dir` debe contener al menos
   K documentos **con bytes nuevos**, separados del corpus inicial. El script copia
   input a `--out/input`, hace sync y luego copia e ingresa un archivo por llamada
   CLI `add`; no escribe en el input original. El copiado no entra al cronómetro.

   ```bash
   "$PY" -B -m benchmarks.run_pipeline --input "$OUT/corpus_56/raw" \
     --out "$OUT/incremental" --collection bench_esc_incremental \
     --repeat-sync --add-new 5 --extra-dir /ruta/local/documentos_nuevos
   ```

5. Medir embeddings directamente usando los JSONL v2 creados en el paso 3.
   Prefijo UUID distinto para cada texto, sin caché cliente, `truncate=false`,
   comprobación de 768 dimensiones finitas y del digest del modelo.

   ```bash
   "$PY" -B -m benchmarks.embed_throughput --gold "$OUT/pipeline_56/layers/gold" \
     --n 300 --num-thread 2 --batch 16 --out "$OUT/embed_t2"
   ```

   Omitir `--num-thread` usa las opciones por defecto del servidor. Si hay menos
   de N chunks fuente se ciclan, siempre con sal única. No hay calentamiento aparte;
   se registra la duración completa de los lotes, incluida carga inicial del modelo
   si estaba fuera de memoria. La generación de prefijos y lectura gold se excluyen.

6. Medir SimHash. No usa servicios. Importa `simhash` real y replica **exactamente**
   el bucle near de `Pipeline._reports`: cuatro bandas de 16 bits, distancia <=3,
   exclusión de hashes textuales exactos y pares repetidos. Excluye CSV/artefactos.

   ```bash
   "$PY" -B -m benchmarks.simhash_scaling --sizes 1000,5000,20000,50000 \
     --out "$OUT/simhash"
   ```

   El pipeline aplica ese bucle a documentos; aquí se alimenta con textos sintéticos
   tipo chunk. Se cronometran fingerprints y detección por separado. La pendiente
   log-log corresponde a detección; 1.8–2.2 se etiqueta como comportamiento cuadrático
   observado, sin afirmar una prueba asintótica. Por defecto se usan palabras variadas
   y semilla 0. `--workload clustered` concentra fingerprints y puede producir O(N²)
   pares y memoria como el algoritmo original: empezar con `--sizes 100,300,1000`.

7. Medir consultas Chroma con vectores aleatorios normalizados y semilla 0. Se
   incrementa una misma colección propia hasta cada escala; inserciones por lotes
   de 256, verificación del conteo, cinco consultas de calentamiento y 50 consultas
   cronometradas por escala, k=5. Los vectores se suministran explícitamente y no se
   descarga un modelo. Los percentiles usan interpolación lineal en milisegundos.

   ```bash
   "$PY" -B -m benchmarks.chroma_query_latency --sizes 1000,5000,20000 \
     --out "$OUT/chroma"
   ```

8. Calcular costos con una tasa **medida**, precio y fuente aportados por el operador.
   No hay precio de EC2 codificado ni consulta de tarifas. Ambos importes usan la
   misma moneda; la fuente debe incluir región, modalidad y fecha de la cotización.

   ```bash
   "$PY" -B -m benchmarks.cost --docs-per-hour "$DOCS_H_MEDIDOS" \
     --price-per-hour "$PRECIO_H_COTIZADO" --source "$FUENTE_PRECIO" \
     --out "$OUT/costo"
   ```

9. Agregar resultados y, opcionalmente, extrapolar. Solo se agrupan sync completos
   exitosos con estado, capas y caché iniciales vacíos, sin `from-stage`, separando chunker y modo de
   embeddings. Se requieren al menos dos tamaños distintos. Todas las filas
   proyectadas llevan **EXTRAPOLADA**, incluso las calculadas con una tasa real.

   ```bash
   "$PY" -B -m benchmarks.report --results "$OUT" \
     --out ingesta/docs/ESCALABILIDAD_tablas.md --extrapolate-sizes 1000,5000,20000
   # Añadir --chunks-per-doc C con una razón documentada para proyectar embeddings.
   ```

   `extrapolate` ajusta tiempo = intercepto + pendiente × documentos;
   `extrapolate_embeddings` usa chunks / emb/s medidos. No se infiere una proporción
   de chunks por documento ni una velocidad de embeddings a partir de vectores fake.
   Los Markdown solo se generan al ejecutar el comando, no al instalar el harness.

## Interpretación de tiempos, cachés y recursos

- Los hooks actuales están en `state/run_manifest.json` y `manifest.sqlite`, tabla
  `runs`, columna JSON `report`. El runner consulta la última fila **nueva** por CLI,
  conserva el informe completo y las etapas `extraction`, `ocr`, `cleaning`,
  `metadata`, `chunking`, `duplicates`, `embeddings`, `chroma_publish`,
  `quality_report`. Si el proceso falla sin fila nueva no reutiliza un informe viejo.
- `stage_timings` contiene `seconds` y `calls`. El pipeline resta OCR de extracción;
  OCR se informa por separado. Los hooks no cubren todo el tiempo de arranque,
  lectura/escritura de capas y cierre, por lo que no deben sumar necesariamente el
  tiempo de `/usr/bin/time`. Se mantienen los nombres y los alcances existentes.
- `docs_per_hour` usa documentos procesados / tiempo total; `scanned_docs_per_hour`
  usa documentos activos / tiempo total. Un segundo sync no es solo hash: valida
  capas/caché y vuelve a generar duplicados y calidad. `chunks_per_second` usa chunks
  enviados o reutilizados; `embeddings_per_second` solo nuevos / tiempo de API
  registrado por el embedder, y queda `null` en fake o sin embeddings nuevos.
- La tasa de hits es hits / (hits + nuevos). Se reconstruyen las consultas a partir
  de los keys de caché antes de cada CLI y gold de documentos publicados, separando
  repeticiones coalescidas dentro del documento. No se cuentan chunks de documentos
  saltados como hits. `cache_count_consistent` revela informes parciales/inconsistentes.
  Los conteos gold en disco pueden incluir artefactos retirados; no son un catálogo
  de chunks activos. Se leen/hashean fuera del cronómetro y pueden calentar page cache.
- `/usr/bin/time -v` registra CPU user/sys del trabajo y sus hijos, porcentaje de un
  núcleo (puede superar 100%) y máximo RSS de un proceso del trabajo, **no suma del
  árbol**. El fallback psutil muestrea CPU/RSS del árbol cada 50 ms y puede perder
  hijos breves. Ninguno incluye CPU/RSS de servidores Ollama o Chroma ya iniciados.
  Extracción informa además CPU acumulada por documento, incluyendo Tesseract en Linux.
- El subproceso usa cwd=`--out` para contener `.offline/chroma-writers`; temporales,
  HOME, cachés XDG y bytecode se redirigen o desactivan allí. No se vacía la page
  cache del SO: una caché del pipeline vacía no equivale a disco frío. Mantener carga
  y créditos CPU de t3 comparables y registrar el estado térmico de los servidores.
- Se miden bytes lógicos de bronze/silver/gold/quality, SQLite y caché; no bloques
  asignados, almacenamiento del servidor Chroma ni caché del modelo Ollama.

## Limitación del corpus sintético

Cada PDF recibe una sal corta (<80 caracteres) en **cada página**, fuente pequeña
en una esquina. Cambian bytes/doc_id y la clave OCR, que actualmente incluye el hash
del documento. Las páginas escaneadas que solo añaden esa sal siguen bajo el umbral
de OCR, aunque una página previamente casi en el umbral podría cruzarlo. El manifiesto
registra fuente, sal y SHA-256. Los CSV se copian si están bajo `--src`, sin reescribir
sus filas: los nombres sintéticos pueden dejar de coincidir con los metadatos curados.

**Una sal por página no garantiza textos únicos en todos los chunks.** La limpieza
elimina muebles repetidos, OCR puede no leer una fuente pequeña y los chunks interiores
de páginas largas pueden no contener la sal. Se esperan avisos de duplicados/casi
duplicados. No se altera el pipeline para ocultar esta limitación. Revisar hits,
coalescidos y `gold_unique_texts_on_disk`; usar `embed_throughput` con prefijos únicos
para medir embeddings nuevos de manera aislada. Una corrida real con muchos hits no
representa el costo completo de generar todos sus embeddings desde cero.

Antecedentes proporcionados (no se vuelven a medir automáticamente como calibración):
~1.06 emb/s por defecto, ~1.25 con `num_thread=2`, efecto pequeño del tamaño de lote,
~1% CPU Python mientras espera Ollama; extracción/OCR de 56 documentos reales
~514 CPU-segundos. Son contexto del experimento, no resultados nuevos ni constantes
usadas para generar cifras medidas o proyecciones.

## Pruebas sin servicios

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=ingesta ingesta/.venv/bin/python -B -m pytest \
  -p no:cacheprovider ingesta/tests/unit/test_benchmarks.py
ingesta/.venv/bin/python -B -m ruff check --no-cache ingesta/benchmarks \
  ingesta/tests/unit/test_benchmarks.py
ingesta/.venv/bin/python -B -m ruff format --check --no-cache ingesta/benchmarks \
  ingesta/tests/unit/test_benchmarks.py
```

La prueba de PDFs se omite si falta PyMuPDF; las demás no necesitan Ollama, Chroma,
Tesseract ni acceso de red.
