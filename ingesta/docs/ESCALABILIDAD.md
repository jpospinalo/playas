# Escalabilidad de la ingesta offline

Mediciones del pipeline `ingest.offline` con capas medallion, en una sola
máquina. Los scripts están en `ingesta/benchmarks/` (ver su README). Los
valores marcados **EXTRAPOLADA** no se ejecutaron.

## Entorno

| | |
|---|---|
| Instancia | EC2 **t3.large** (2 vCPU = 1 núcleo físico con hyperthreading, 8 GiB), `i-0c851c2238e90fe25`, ya terminada |
| Sistema | Ubuntu 24.04, Python del venv de `ingesta/`, Tesseract spa |
| Embeddings | Ollama 0.40.11, `embeddinggemma` (digest `85462619ee72…`, 768 dim), CPU |
| Chroma | 1.3.5 local en la misma instancia |
| Uso de EC2 | ≈ 2 h 49 min en dos sesiones (límite: 3 h) |
| Al terminar | `rag-playas-ollama` (`i-03c5de31fb6f876b3`) y `rag-playas-chromadb` (`i-091d4f3eaed43cb5d`) detenidas, no terminadas; estaban encendidas al inicio. `mlflow2`, ECS y el ALB no se tocaron |
| Código | rama `feat/ingesta-medallion-escalabilidad` |

Salvo que se diga lo contrario, las corridas usan `--fake-embeddings` (vectores
SHA256 deterministas, solo en colecciones `bench_`). **En esas corridas los
embeddings NO están medidos.** El coste de los embeddings reales se midió
aparte (ver más abajo) y se suma de forma explícita.

## Resultados por escala

| Escala | Tipo | Pared pipeline | Docs/h (sin embeddings reales) | Páginas OCR | Chunks | RSS máx. | Estado |
|---:|---|---:|---:|---:|---:|---:|---|
| 55 | real (56 archivos) | 1.008 s | 196 | 304 | 5.528 | 555 MB | medida |
| 200 | sintético | 3.529 s | 204 | 1.103 | 20.059 | 603 MB | medida |
| 500 | — | ≈ 2,5 h | ≈ 200 | — | ≈ 50.000 | — | **EXTRAPOLADA** |
| 1.000 | — | ≈ 5 h | ≈ 200 | — | ≈ 100.000 | — | **EXTRAPOLADA** |
| 2.000 | — | ≈ 10 h | ≈ 200 | — | ≈ 200.000 | — | **EXTRAPOLADA** |

Con embeddings reales en CPU (≈ 100 chunks por documento):

| Escala | Docs/h | Pared total | Estado |
|---:|---:|---:|---|
| 55 (real) | 20–25 | 2,2–2,7 h | **EXTRAPOLADA** desde el throughput medido (abajo) |
| 1.000 | 20–25 | 40–50 h | **EXTRAPOLADA** |
| 2.000 | 20–25 | 80–100 h | **EXTRAPOLADA** |

Base de la extrapolación:

- **Pipeline:** las dos escalas medidas dan ≈ 18 s por documento, y todas
  las etapas crecen de forma lineal (tabla siguiente).
- **Embeddings:** se suma el número de chunks entre el throughput real
  medido:
  - 0,628 emb/s con la configuración por defecto;
  - 0,805 emb/s con `num_thread=2`.

  Medido sobre 300 chunks gold con sal, de unos 930 caracteres.

El corpus sintético se generó con una sal que la limpieza eliminaba, por eso
solo 5.368 de sus 20.059 chunks necesitaron embedding nuevo. No se usa para
proyectar embeddings. La sal ya está corregida en `synth_corpus.py`, pero no
se repitió la corrida.

## Tiempo por etapa

| Etapa | 55 reales (s) | % | 200 sintéticos (s) | % |
|---|---:|---:|---:|---:|
| extraction (sin OCR) | 29,0 | 2,9 | 128,1 | 3,6 |
| **ocr** | **885,0** | **87,8** | **3.071,5** | **87,0** |
| cleaning | 6,9 | 0,7 | 27,5 | 0,8 |
| metadata | 0,4 | 0,0 | 1,6 | 0,0 |
| chunking | 4,2 | 0,4 | 8,8 | 0,2 |
| duplicates | 7,8 | 0,8 | 30,1 | 0,9 |
| embeddings (falsos) | 14,8 | 1,5 | 22,6 | 0,6 |
| chroma_publish | 40,7 | 4,0 | 160,0 | 4,5 |
| quality_report | 12,2 | 1,2 | 49,0 | 1,4 |

### Cuellos de botella

1. **Embeddings reales en CPU.** Con 0,63–0,82 emb/s, los 5.528 chunks del
   corpus real necesitan entre 1,9 y 2,4 h, más que todo el resto del
   pipeline junto (17 min). Durante la medición `llama-server` usaba un núcleo
   al 99 %. En el microbenchmark de `/api/embed`, `num_thread=2` y lotes de 32
   dieron hasta 1,28 emb/s con textos de unos 1.150 caracteres.
2. **OCR**, si los embeddings ya están en caché o se calculan en otra máquina:
   el 87 % del tiempo, unos 2,8–2,9 s por página escaneada.
3. Lo demás es menor: la publicación en Chroma toma unos 8 ms por chunk y el
   informe de calidad crece de forma lineal.

## Paralelismo de extracción (`--workers`)

`extract_parallel.py` sobre 14 documentos reales con OCR:

| Workers | Pared | Docs/h | Speedup |
|---:|---:|---:|---:|
| 1 | 422,6 s | 119 | 1,00× |
| 2 | 358,9 s | 140 | 1,18× |
| 4 | 338,8 s | 149 | 1,25× |

La t3.large tiene un solo núcleo físico, por eso la ganancia es baja.
**Decisión: no implementé `--workers` en el pipeline.** En esta máquina la
ganancia no justifica el riesgo: concurrencia sobre el manifiesto SQLite y las
capas, que hoy asumen un único escritor. Queda como recomendación para
instancias con varios núcleos físicos, paralelizando solo la extracción y el
OCR (procesos puros) y manteniendo un único escritor de capas y manifiesto.

## Detección de cuasi-duplicados (SimHash + LSH)

`simhash_scaling.py`, comparación entre documentos con 4 bandas de 16 bits:

| Carga | Tamaños | Tiempo | Exponente empírico |
|---|---|---|---:|
| diversa | 1k / 5k / 20k / 50k | 0,007 / 0,020 / 0,153 / 0,449 s | 1,11 |
| agrupada (casi idénticos) | 500 / 1k / 2k / 4k | 0,45 / 2,22 / 15,8 / 166,8 s | 2,84 |

Con textos diversos el coste es casi lineal. Si muchos documentos comparten
casi todo el texto (plantillas, versiones del mismo decreto), los buckets LSH
se llenan y el coste se vuelve cuadrático: 4.000 documentos agrupados generan
unos 8 millones de pares. El corpus real está en el régimen diverso (7,8 s
para 55 documentos), pero esto es un riesgo si se ingieren colecciones
masivas de documentos casi iguales.

## Re-ejecución e incrementos

| Operación | 55 reales | 200 sintéticos |
|---|---:|---:|
| `sync` sin cambios | 20,9 s (RSS 217 MB) | 77,1 s (RSS 243 MB) |
| Añadir 1 documento sin OCR (o con 1 pág.) | — | 76–97 s (7 de 10 corridas) |
| Añadir 1 documento con OCR (29–81 págs.) | — | 151–327 s |
| `--from-stage silver` | 138,2 s, gold idéntico byte a byte | — |
| `quality --compare-v1` | 23,8–24,9 s, RSS 120 MB | — |

El `sync` sin cambios cuesta unos 0,38 s por documento en ambas escalas
(hashing de entradas y comprobación de capas). Ese coste es lineal y se paga
en cada incremento: con 2.000 documentos serían ≈ 13 min antes de procesar el
primero nuevo (**EXTRAPOLADA**).

## Chroma

`chroma_query_latency.py`, 768 dimensiones, k=5, 50 consultas, Chroma local:

| Vectores | Inserción | p50 | p95 |
|---:|---:|---:|---:|
| 1.000 | 1,2 s | 4,4 ms | 5,8 ms |
| 5.000 | 7,6 s | 5,2 ms | 7,2 ms |
| 20.000 | 42,5 s | 6,3 ms | 8,1 ms |

20.000 vectores equivalen a unos 200 documentos. La latencia de consulta crece
poco. 200.000 vectores (2.000 documentos) **no se midieron**.

## Disco

| | 55 reales | 200 sintéticos | 1.000 (**EXTRAPOLADA**) |
|---|---:|---:|---:|
| Capas (bronze+silver+gold+refs+quality) | ≈ 100 MB | 343 MB | ≈ 1,7 GB |
| Caché de embeddings | 174 MB | 421 MB | ≈ 2,1 GB |
| Estado (manifiesto, etc.) | < 1 MB | 28 MB | ≈ 140 MB |

## Coste por 1.000 documentos

Precio: t3.large on-demand Linux us-east-1, **0,0832 USD/h**, según
instances.vantage.sh (fuente de terceros, consultada el 2026-10-26). La AWS
Pricing API no estaba permitida en el sandbox. `benchmarks/cost.py` hace el
mismo cálculo.

| Escenario | Horas t3.large | Coste cómputo |
|---|---:|---:|
| Pipeline sin embeddings reales (≈ 200 docs/h) | ≈ 5 h | ≈ 0,42 USD |
| Con embeddings reales en CPU (20–25 docs/h) | 40–50 h | ≈ 3,3–4,2 USD |

Todo es **EXTRAPOLADO**. No incluye EBS, transferencia, snapshots ni el Chroma
de destino. No hay llamadas a LLM ni APIs con cuota: `llm_api_calls = 0` en
todas las corridas.

## Qué cambia al escalar

- **Más CPU (instancias c6i/c7i con varios núcleos físicos):** el OCR
  paralelizable por documento justificaría `--workers`. Con una sola
  instancia de Ollama, los embeddings escalan con `num_thread`, no con
  workers.
- **GPU para embeddings:** es la palanca principal, porque hoy los embeddings
  son unas 7 veces el resto del pipeline. No se midió.
- **Chroma gestionado o remoto:** añade latencia de red a la publicación,
  hoy unos 8 ms por chunk en local. No se midió.
- **Incrementos:** el `sync` sin cambios es O(N). Con miles de documentos
  convendría un índice de mtimes/tamaños para evitar rehashear todo.
- **Corpus con muchas plantillas:** vigilar la detección de cuasi-duplicados
  (régimen cuadrático).

## Qué no se pudo medir

- Embeddings reales a escala: solo 300 + 535 chunks reales medidos. Las cifras
  de 1.000 y 2.000 documentos con embeddings son extrapolaciones.
- Corridas de 500, 1.000 y 2.000 documentos: no caben en 3 h de EC2.
- GPU, instancias con más núcleos físicos y `--workers` sobre más de
  14 documentos.
- Chroma con más de 20.000 vectores, remoto o con consultas concurrentes.
- El throughput de embeddings del corpus sintético de 200 (sal eliminada por
  la limpieza: el 73 % reutilizó caché).
- Calidad de recuperación o de respuesta del RAG con las capas v2.
