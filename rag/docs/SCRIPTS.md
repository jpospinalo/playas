# Scripts operacionales — RAG

Referencia de scripts de despliegue, SageMaker, pruebas de carga, utilidades ChromaDB y herramientas auxiliares del módulo RAG.

Los scripts de infraestructura ECS Fargate (`deploy.sh`, `push_images.sh`, `start.sh`, `stop.sh`, `export_postgres.sh`) están documentados en [`../infrastructure/README.md`](../infrastructure/README.md), no aquí.

La colección Gold de `corpus` se restaura y verifica con
`data/restore_gold_release.py`. La versión del paquete, el perfil de embeddings
y las instrucciones están en [versiones y recuperación](../../data/chroma-releases/README.md).

---

## Despliegue

### `scripts/install-docker-ubuntu.sh`

Instala **Docker Engine + Compose plugin** en Ubuntu 22.04 (Jammy) o 24.04 (Noble).

```bash
sudo bash rag/scripts/install-docker-ubuntu.sh
```

**Qué hace:**
1. Verifica que sea root y Ubuntu
2. Añade la GPG key y repositorio oficial de Docker
3. Instala `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`
4. Habilita el servicio Docker y añade el usuario al grupo `docker`

**Cuándo usarlo:** En máquinas Ubuntu frescas que necesitan Docker (VMs locales, otros proveedores cloud).

---

## Mantenimiento SQL

### `scripts/migrate_message_feedback_unique.py`

Comprueba o añade únicamente el índice único de calificación por usuario/mensaje.
No se ejecuta desde el arranque ni el despliegue. Necesita `DATABASE_URL` explícita
en el entorno: no carga `.env` ni selecciona `atlas.db` por defecto. No pasar
credenciales como argumentos ni pegarlas en informes.

Desde `rag/`, con el entorno existente preparado:

```bash
.venv/bin/python -B scripts/migrate_message_feedback_unique.py
```

Por defecto sólo comprueba. `ready` con `index_verified: false` significa que
el esquema admite la migración y falta el índice; no garantiza la unicidad.
`verified` confirma el índice exacto. Sólo después de autorizar una ventana
sin escrituras y disponer de respaldo recuperable, añadir `--apply` para
crearlo; `applied` confirma la creación y comprobación. No regenera la base.

La salida contiene estado y conteos, sin filas ni credenciales. `blocked` o
un error devuelven salida no exitosa: detenerse y diagnosticar. Si hay
duplicados, otra unicidad equivalente o un índice/esquema incompatible, no
borra, fusiona, renombra ni elige registros. El responsable de los datos debe
decidir el tratamiento de cualquier duplicado antes de reintentar.

Sólo admite PostgreSQL con `asyncpg` o un archivo SQLite existente con
`aiosqlite`. SQLite se abre sin crear archivos y con lectura sola al comprobar;
el modo `--apply` usa una transacción efectiva para que un fallo revierta el DDL.
Las cotas locales son 5 s de espera por bloqueo SQLite/locks PostgreSQL y, para PostgreSQL,
10 s de conexión y 30 s por comando. No son un SLA físico de limpieza. Las
pruebas temporales SQLite no certifican una migración PostgreSQL desplegada.

## SageMaker

### `scripts/sagemaker-on_start_lifecycle.sh`

**Lifecycle hook** para instancias SageMaker. Reconfigura Docker para usar almacenamiento persistente en EBS.

```bash
# Se configura como "OnStart" lifecycle hook en la configuración de la instancia SageMaker
```

**Qué hace:**
1. Reescribe `/etc/docker/daemon.json` para usar el EBS como `data-root`
2. Configura NVIDIA Container Runtime (para GPUs)
3. Reinicia Docker

---

### `scripts/sagemaker-phi4-mini.sh`

Referencia rápida para levantar Ollama con `phi4-mini:3.8b` en SageMaker.

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
docker exec -it ollama ollama pull phi4-mini:3.8b
```

**Nota:** Es una referencia/cheatsheet, no un script ejecutable automatizado.

---

## Pruebas de carga

### `scripts/load_test.py`

Lanza N usuarios concurrentes contra `/api/query/stream` (el endpoint SSE que usa el frontend), y reporta latencias (tiempo al primer evento `status`, a la primera fracción de respuesta, total — con min/avg/p50/p95/p99/max).

Desde `rag/`, sustituir el valor de ejemplo por el JWT de una cuenta de prueba:

```bash
export RAG_LOAD_TEST_TOKEN="jwt-de-prueba"
uv run python scripts/load_test.py --url http://localhost:8080 --users 10 --timeout 60
```

**Sin URL por defecto:** `--url` es obligatorio. Apuntar a un host que no sea local exige además `--allow-remote` y, en una terminal interactiva, escribir el host exacto como confirmación — así se evita generar tráfico de carga contra el ALB de producción por accidente.

**Credencial:** el endpoint exige un JWT válido; pásalo por `RAG_LOAD_TEST_TOKEN` (recomendado) o `--token`. Sin ninguno de los dos el script se detiene con un mensaje claro (`--allow-unauthenticated` para el caso excepcional de un backend sin auth).

**Nota sobre "primer token":** el backend calcula la respuesta completa y luego la trocea en fragmentos que emite sin pausas — no hay streaming incremental real de tokens. El tiempo a la "primera fracción de respuesta" reportado por el script es, en la práctica, casi igual al tiempo total; no lo interpretes como time-to-first-token.

**Cuándo usarlo:** para validar manualmente latencia/estabilidad del backend bajo concurrencia antes o después de un despliegue. Ejecutarlo contra producción requiere autorización explícita — no es un chequeo de solo lectura.

---

## Utilidades ChromaDB (`utils/`)

### `utils/chroma_count.py`

Consulta la **cantidad de documentos** en la colección de ChromaDB.

```bash
uv run python -m utils.chroma_count
```

---

### `utils/chroma_clear.py`

**Elimina todos los documentos** de una colección de ChromaDB. **Simulación (dry-run) por defecto** — sin `--execute` solo muestra host, colección y cantidad de documentos, sin borrar nada. `--collection` es obligatorio (sin valor por defecto: nunca borra una colección resuelta implícitamente del entorno).

```bash
# Dry-run: solo describe la colección, no borra nada
uv run python -m utils.chroma_clear --collection rag_playas

# Borrado real: además exige escribir el nombre EXACTO de la colección
# como confirmación interactiva (se cancela si no hay terminal disponible)
uv run python -m utils.chroma_clear --collection rag_playas --execute
```

**Precaución:** con `--execute`, operación destructiva. Úsala cuando se quiere re-indexar desde cero.

---

### `utils/list_gemini_models.py`

Lista los **modelos disponibles** en la API de Google GenAI con sus acciones soportadas.

```bash
uv run python -m utils.list_gemini_models
```

**Cuándo usarlo:** Para verificar modelos disponibles o confirmar soporte de tool calling / structured output.

---

## Evaluación del RAG

Evaluación reproducible con [RAGAS](https://github.com/vibrantlabsai/ragas)
sobre un dataset jurídico versionado, en `evaluation/` (`ragas_common.py` +
un adaptador por juez intercambiable). No forma parte de la ruta de
servicio. El alcance de la herramienta se describe en
[Arquitectura](ARCHITECTURE.md#10-evaluación-del-rag-evaluation).

**⚠️ Requiere autorización explícita antes de correrse de verdad.** Una
corrida real usa `rag.core.generator`, adaptador del grafo común del RAG:
precarga BM25 cuando hay procedencia documental configurada y crea un
grafo y un `thread_id` propios por pregunta. No usa el lifespan de la API
ni sus clientes REST/embeddings inyectados. Ejecuta el RAG con sus modelos
y llama a un LLM/juez (Gemini u Ollama) para las métricas — no es un
comando inocuo para ejecutar "para probar". `--validate-only` (más abajo)
valida datos y configuración sin red, sin ese costo ni ese riesgo.

Hay dos flujos independientes:

- **Banco v0.1** (21 casos) con los adaptadores `ragas_eval_gemma.py` y
  `ragas_eval_ollama.py`: secciones *Banco de preguntas* y *Reporte* a continuación.
- **Línea base v0.2** (66 casos, por fases, juez gpt-5-nano): sección
  [Línea base sobre `legal-ground-truth-v0.2`](#línea-base-sobre-legal-ground-truth-v02).

### Banco de preguntas (`evaluation/data/legal-ground-truth-v0.1.json`)

El [banco activo](../evaluation/data/legal-ground-truth-v0.1.json) conserva
la anotación **Esperando validación final**. El Excel
`evaluation/data/legal-ground-truth-v0.2.xlsx` es una fuente versionada
adicional, no una sustitución automática del JSON ni una validación final del
banco. Ver [datos del proyecto](../../data/README.md#ground-truth).

21 preguntas jurídicas reales sobre playas/dominio público
marítimo-terrestre, cada una con sus 5 campos obligatorios diligenciados:
`doc_principal`, `doc_secundario`, `pregunta`, `respuesta`,
`ubicacion_evidencia` (más `id`). Cargador y validación de ese contrato en
`evaluation/ground_truth.py`: si falta alguno de esos cinco campos o
contiene un valor vacío, `load_ground_truth_cases()` falla explícitamente
en vez de evaluar un registro incompleto en silencio.

Los registros `registro-017` a `registro-022` (`AMBIGUOUS_DOCUMENT_CASE_IDS`
en `ragas_common.py`) tienen referencias documentales ambiguas. El reporte
omite la métrica de documento esperado para los 21 casos porque falta un
mapeo entre las referencias del banco y los IDs de Gold. Para evaluar
recuperación, vincular cada caso con los pasajes verificables del
[corpus versionado](../../data/README.md#campos-de-gold). Registrar la versión
de Gold y conservar la pregunta, los pasajes recuperados, la respuesta y el
cotejo de sus citas por caso.

### Comandos

```bash
uv run python -m evaluation.ragas_eval_gemma                  # juez Gemini: evaluación real
uv run python -m evaluation.ragas_eval_ollama                 # juez Ollama: evaluación real
uv run python -m evaluation.ragas_eval_gemma  --validate-only # solo valida config y dataset, sin red
uv run python -m evaluation.ragas_eval_ollama --validate-only # solo valida config y dataset, sin red
```

`--validate-only` carga y valida el dataset, imprime cuáles de las
variables de entorno obligatorias faltan (sin nunca imprimir su valor) y
sale con 0/1 — nunca importa `ragas` ni abre una conexión de red. Es lo
que hay que correr para confirmar que el entorno está listo, sin disparar
una evaluación real.

**Variables de entorno obligatorias** (ver `.env.example`, sección
"Evaluación"; ausentes, vacías o solo espacios cuentan como faltantes):

| Adaptador | Variables | Métricas reales que ejecuta |
|---|---|---|
| `ragas_eval_gemma.py` | `GOOGLE_API_KEY2` (`GEMINI_MODEL` opcional, default `gemma-3-27b-it`) | `context_precision`, `context_recall`, `faithfulness`, `answer_relevancy` |
| `ragas_eval_ollama.py` | `OLLAMA_EVAL_BASE_URL`, `OLLAMA_EVAL_MODEL` (sin default: obligatorias) | `answer_relevancy` |

Ambos adaptadores validan esa configuración **antes** de importar `ragas`
o construir cualquier cliente — un valor faltante nunca llega a un
constructor, tanto en `--validate-only` como en una corrida real.

### Reporte (`evaluation/results/*.json`, no versionado)

Cada corrida real escribe un JSON reproducible con, entre otros campos:

- `dataset`, `annotation`, `dataset_sha256` — identidad exacta del dataset evaluado.
- `git`: `{"commit": "<sha o \"desconocido\">", "dirty": true|false|null}` —
  estado del árbol en el momento de la corrida (`dirty=true` con cambios sin
  commit, `null` si no se pudo determinar). Un árbol sucio no impide
  escribir el reporte, solo se advierte por stdout y se refleja aquí: el
  reporte no corresponde entonces exactamente al código de `git.commit`.
- `metric_results`: por métrica, `{"mean": ..., "scores_by_case": {"<case_id>": <puntaje o null>, ...}, "scored_count": ..., "missing_count": ...}`
  — cada puntaje queda asociado a su `case_id` explícitamente, nunca por
  posición; un valor no finito que devuelva RAGAS para un caso se conserva
  como `null` (información, no se descarta). Un caso cuya generación falló
  nunca aparece aquí (se identifica por su `error` en `cases`, no por un
  `null`).
- `cases` — una fila por caso (incluidos los que fallaron en generación,
  con su `error`), con `expected_document_metric` explicando por qué se
  omite esa métrica para ese caso (`"omitted:ambiguous_reference"` para
  17–22, `"omitted:no_deterministic_mapping_available"` para el resto: no
  existe hoy un mapeo determinista entre `doc_principal`/`doc_secundario`
  del dataset y la metadata real del corpus indexado en ChromaDB).
- `summary`, `errors` — agregados derivados de `cases`/`metric_results`.

### Métricas fijas sin LLM (correr siempre)

Se corren después de **cualquier** cambio en la ingesta, el retriever o los
prompts, antes de gastar en el juez. No llaman a ningún modelo generador ni
juez (0 tokens), dan el mismo resultado en cada corrida y tardan ~20 s.
Necesitan el ChromaDB y el Ollama de embeddings (los del proyecto o los
locales de la sección [Comparar con un modelo local](#comparar-con-un-modelo-local-sin-aws-ni-costo-de-generación)).

```bash
export CHROMA_HOST=<ip-chromadb> OLLAMA_BASE_URL=http://<ip-ollama>:11434
make eval-sin-llm                  # = uv run python -m evaluation.metricas_sin_llm

# Solo las métricas de respuesta, sobre una caché ya generada (sin ChromaDB)
uv run python -m evaluation.metricas_sin_llm --sin-recuperacion --cache <caché.jsonl> --tag <tag>

# Aceptar un cambio: guardar la corrida como nueva línea base y versionarla
uv run python -m evaluation.metricas_sin_llm --guardar-linea-base
```

Escribe `evaluation/results/metricas-sin-llm-v0.2[-<tag>].json` (detalle por
caso) y `.md` (tablas con IC 95 %, desgloses y casos a revisar). Si existe
`evaluation/data/linea-base-sin-llm-v0.2.json`, compara contra ella e imprime
`REGRESIÓN frente a la línea base: …` cuando una métrica sale del intervalo
de la línea base en la dirección mala, y `Empeora dentro del margen (revisar
casos): …` cuando empeoran casos sin salir del intervalo. Qué mide
cada métrica y cómo leerla: [`evaluation/README.md` § Métricas fijas sin LLM](../evaluation/README.md#métricas-fijas-sin-llm).
El juez RAGAS (fase 4) se reserva para los hitos, porque es el único que
dice si la respuesta es jurídicamente correcta.

### Línea base sobre `legal-ground-truth-v0.2`

Evaluación por fases sobre los 66 casos del ground truth v0.2. Resultados,
cómo leer las métricas y hallazgos en
[`docs/EVALUACION_LINEA_BASE.md`](EVALUACION_LINEA_BASE.md). La v0.1 y sus
adaptadores no cambian.

```bash
# Fase 0 — regenera el JSON versionado desde el Excel (sin red, sin costo)
uv run python -m evaluation.ground_truth_v02

# Las fases 1, 2 y 4 usan el ChromaDB y el Ollama del proyecto:
export CHROMA_HOST=<ip-chromadb> OLLAMA_BASE_URL=http://<ip-ollama>:11434

# Fase 1 — recuperación por documento esperado, sin LLM (sin costo)
uv run python -m evaluation.retrieval_baseline

# Fase 2 — grafo real una vez por caso, en caché y reanudable (OPENAI_API_KEY)
uv run python -m evaluation.generation_cache --limit 2      # piloto
uv run python -m evaluation.generation_cache                # resto

# Fase 4 — RAGAS con juez gpt-5-nano sobre la caché (OPENAI_API_KEY)
uv run python -m evaluation.ragas_v02 --limit 3             # piloto
uv run python -m evaluation.ragas_v02                       # resto

# Fase 5 — tablas consolidadas
uv run python -m evaluation.baseline_report
```

Para evaluar el corpus versionado sin S3 ni tocar el índice desplegado, levantar
un ChromaDB aparte e indexar Gold en él. Todas las fases aceptan `--tag`:

```bash
CHROMA_PORT=8001 uv run python -m evaluation.indexar_gold_local
CHROMA_PORT=8001 uv run python -m evaluation.retrieval_baseline --tag corpus-congelado
uv run python -m evaluation.baseline_report --tag corpus-congelado
```

| Módulo | Escribe (en `evaluation/results/`, no versionado) | Costo LLM |
|---|---|---|
| `ground_truth_v02.py` | `evaluation/data/legal-ground-truth-v0.2.json` (sí versionado) | ninguno |
| `retrieval_baseline.py` | `retrieval-baseline-v0.2.json` | ninguno |
| `metricas_sin_llm.py` | `metricas-sin-llm-v0.2.json` y `.md` | ninguno |
| `generation_cache.py` | `generation-cache-v0.2.jsonl` | ~0,0035 USD por caso |
| `ragas_v02.py` | `ragas-v0.2.jsonl` | ~0,008 USD por caso |
| `baseline_report.py` | `linea-base-v0.2.md` | ninguno |

`generation_cache.py` y `ragas_v02.py` escriben caso a caso y, al
relanzarse, solo procesan lo pendiente. Ambos imprimen los tokens y el
costo estimado de cada corrida.

### Comparar con un modelo local (sin AWS ni costo de generación)

Misma evaluación cambiando solo el modelo que responde. Todo corre en el
equipo local; el juez sigue siendo gpt-5-nano. Requiere `podman` u otro motor
de contenedores, `ollama` y una GPU de ~4 GB para `gemma4:e2b`.

```bash
# 1. ChromaDB 1.3.5 (misma versión que en AWS) con la colección exacta del repo
podman run -d --name atlas-chroma -p 127.0.0.1:8000:8000 \
  -v ~/.local/share/atlas-chroma:/data:Z -e IS_PERSISTENT=TRUE \
  docker.io/chromadb/chroma:1.3.5
uv run python ../data/import_to_chromadb.py \
  ../data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz \
  --host 127.0.0.1 --port 8000 --collection rag_playas

# 2. Ollama: embeddings en CPU (:11435) y modelo generador en GPU (:11434)
CUDA_VISIBLE_DEVICES= OLLAMA_HOST=127.0.0.1:11435 ollama serve &
OLLAMA_HOST=127.0.0.1:11435 ollama pull embeddinggemma:latest
OLLAMA_HOST=127.0.0.1:11434 OLLAMA_CONTEXT_LENGTH=8192 OLLAMA_NUM_PARALLEL=1 ollama serve &
OLLAMA_HOST=127.0.0.1:11434 ollama pull gemma4:e2b

# 3. Verificar que la búsqueda local es idéntica a la de producción
CHROMA_HOST=127.0.0.1 OLLAMA_BASE_URL=http://127.0.0.1:11435 \
  uv run python -m evaluation.retrieval_baseline --tag local-infra

# 4. Generar con el modelo local (ATLAS lo usa vía la API compatible con OpenAI)
CHROMA_HOST=127.0.0.1 OLLAMA_BASE_URL=http://127.0.0.1:11435 \
OPENAI_BASE_URL=http://127.0.0.1:11434/v1 OPENAI_MODEL=gemma4:e2b OPENAI_API_KEY=ollama \
  uv run python -m evaluation.generation_cache --tag gemma4-e2b --concurrency 1

# 5. Juez (gpt-5-nano, sin OPENAI_BASE_URL) y registro
OLLAMA_BASE_URL=http://127.0.0.1:11435 uv run python -m evaluation.ragas_v02 --tag gemma4-e2b
uv run python -m evaluation.registro --tag gemma4-e2b --modelo "gemma4:e2b (local)"
```

**Con el Gold A corregido (vigente desde 2026-11-11):** en el paso 1, en vez
de importar `rag_playas`, restaurar la colección versionada
`rag_playas_gold_a_cc7bf44b54a9` siguiendo la
[recuperación de Gold A](../../data/chroma-releases/README.md), y pasar
`CHROMA_COLLECTION=rag_playas_gold_a_cc7bf44b54a9` (y `CHROMA_PORT` si no es
8000) en los pasos 3 a 5. Las métricas sin LLM de una corrida se obtienen con
`uv run python -m evaluation.metricas_sin_llm --tag <tag> --cache
evaluation/results/generation-cache-v0.2-<tag>.jsonl`; no necesitan key.
Los modelos con modo de razonamiento (p. ej. Qwen 3.5) deben correr con el
razonamiento apagado (`reasoning_effort: "none"` en la API compatible con
OpenAI de Ollama); si no, consumen los tokens pensando y devuelven la
respuesta vacía.

`generation_cache` registra por caso si el clasificador de consultas tuvo que
usar su respaldo de reglas (`enrichment_fallback`) porque el modelo no devolvió
el formato esperado; el conteo es por caso aunque corran varios en paralelo. El costo de generación de un modelo
servido en `localhost` se registra como 0.

### RAGAS y `langchain-community`

`ragas==0.4.3` (versión bloqueada en `uv.lock`) importa
`ChatVertexAI` desde `langchain_community.chat_models.vertexai`, símbolo
que `langchain-community` retiró en 0.4.x. El grupo `dev` de
`pyproject.toml` fija `langchain-community==0.3.31` (que sí lo expone)
para que `import ragas` funcione sin tocar `ragas` ni añadir
`langchain-google-vertexai` — ver el comentario junto al pin en
`pyproject.toml`. El pin es solo de desarrollo/evaluación: no cambia
ninguna dependencia de producción (`uv export --no-dev --package rag` es
idéntico con o sin él).

### Captura pública JSON/SSE con los dos bancos

`evaluation/api_capture.py` registra los endpoints públicos `/api/query` y
`/api/query/stream`, con el decodificador de `api_capture_protocol.py`. Captura
el comportamiento servido por la API; no sustituye esta ruta por una llamada
al grafo ni ejecuta jueces RAGAS. Los bancos y cargadores se incorporaron
selectivamente desde `11e3cef67c4bc25ee1714221c9a917bbeec21b97`, sin importar
los cambios de recuperación, agente, autenticación o infraestructura de esa rama.

Los insumos de esta CLI son:

| Banco versionado | Casos | Turnos por canal |
| --- | ---: | ---: |
| [legal-ground-truth-v0.2.json](../evaluation/data/legal-ground-truth-v0.2.json) | 66 independientes | 66 |
| [preguntas-reales-v1.json](../evaluation/data/preguntas-reales-v1.json) | 34 individuales y seis conversaciones | 52 |

Son insumos aceptados por el equipo y se conservan byte a byte. `revisado`
retiene su valor original; no se modifica para seleccionar o aprobar casos.
`ground_truth_v02.py` resuelve las referencias del Excel por títulos explícitos
de Gold, comparados en NFC, porque los códigos SM del Excel y la metadata
`Nº` del corpus no representan la misma numeración. No hace búsquedas difusas.
El Excel existente se consulta por lectura; no hay que regenerar el JSON para
capturar estos bancos.

Los **106 casos y 118 turnos** en ambos canales sumarían **236 solicitudes RAG**.
Es un presupuesto para una ejecución futura, no una corrida realizada ni
una promesa de completarla en una hora. La captura puede generar embeddings
de consulta y llamadas al modelo de la API;
no regenera vectores documentales. RAGAS conserva su banco v0.1 y sus defaults
actuales: esta CLI no cambia la configuración de los evaluadores anteriores.

Desde `rag/`, con el entorno Python existente y preparado, la validación es
el modo predeterminado:

```bash
python -B -m evaluation.api_capture --config /ruta/privada/configuracion.json
```

Valida la configuración y los bancos locales sin resolver DNS, abrir una
conexión, leer el contenido del token ni importar el agente o clientes del
RAG. Los datos efectivos que aún no estén confirmados se dejan pendientes;
validar un archivo no autoriza una consulta real.

Una configuración inicial puede dejar los datos remotos pendientes. Guardar
este ejemplo fuera del repo, sustituir las rutas locales y elegir una salida
externa que todavía no exista:

```json
{
  "schema_version": 1,
  "datasets": [
    {
      "name": "legal-v02",
      "path": "/ruta/al/repo/rag/evaluation/data/legal-ground-truth-v0.2.json",
      "sha256": "edb4ecdaa7655a3505025c159eae471fcb2088be9442187870b35b951dbf8225"
    },
    {
      "name": "preguntas-reales-v1",
      "path": "/ruta/al/repo/rag/evaluation/data/preguntas-reales-v1.json",
      "sha256": "2b1562f973f5eaaa611f30241396a3761e6e2c50bafdca64e357d8974d789597"
    }
  ],
  "channels": ["JSON", "SSE"],
  "base_url": null,
  "bearer_token_file": null,
  "output_dir": "/ruta/privada/resultados/captura-nueva",
  "expected": {},
  "runtime_confirmation": {},
  "conversation": {},
  "authorization": {}
}
```

El resultado `validated_not_executed` enumera los `pending`: un código cero
en este modo acredita entradas locales válidas, no preparación remota ni
autorización. `datasets[].case_ids` permite seleccionar IDs existentes;
`channels` admite uno o ambos canales. La selección conserva el orden del
banco. La CLI informa el número exacto de solicitudes antes de enviar
ninguna; cada ventana o selección posterior necesita su propia autorización
y salida, sin reanudar o fusionar corridas automáticamente.

La configuración externa identifica los bancos por ruta, nombre y SHA-256;
selecciona casos y canales; fija parámetros de consulta y límites; y declara
el backend, Gold/colección, receta de embeddings, modelos y procedencia
P1–P3 esperados. Las confirmaciones efectivas se registran por separado con
su referencia de evidencia. El commit local no demuestra qué versión sirve
un backend remoto. No guardar credenciales dentro de la configuración: usar
`bearer_token_file` privado, separado de las salidas y fuera del repo.

Solo después de confirmar identidad, destino, exclusividad y autorización
expresa de la ventana se podrá usar:

```bash
python -B -m evaluation.api_capture --config /ruta/privada/configuracion.json --execute
```

La configuración debe fijar también la caducidad de la autorización, un
límite total externo y su limpieza. Los timeouts del transporte son un
presupuesto cooperativo; no demuestran por sí solos una interrupción de
DNS o de cabeceras lentas. Las pruebas sintéticas no acreditan ese límite
externo ni una ejecución contra el laboratorio.

Cada pregunta independiente omite los campos de sesión para usar la
limpieza efímera de la API. Solo los turnos de una conversación comparten
su hilo y usuario, exclusivo por corrida, caso y canal. Requieren un backend
temporal estable de un proceso y su retirada al terminar; no acreditan
persistencia SQL, reinicio, hidratación en frío o continuidad entre procesos.
Ante un turno fallido o incierto, la conversación se detiene y los restantes
se registran como no ejecutados.

Las salidas usan un directorio externo nuevo y privado. Antes de cada envío
se registra su intención; se conservan manifiesto, respuestas y bytes
parciales si falla. No hay reintentos, reanudación, sobrescritura ni caché
automática por ID. Una captura incompleta permanece incompleta. No añadir
al repo tokens, resultados, recibos o informes de ejecuciones.

Se conservan respuesta, grupos de fuentes, fragmentos, cuerpos, índices y
metadata pública, junto con ruta y pregunta enriquecida cuando estén
expuestas. Las citas usan el patrón público compartido y los índices
globales de `sources[].fragments[]`, no el número de grupos: un grupo puede
contener varios `[docN]`. La validez del índice es sintáctica; no prueba que
el pasaje respalde una afirmación. Un HTTP 200 tampoco acredita exactitud.
JSON y SSE se normalizan al mismo contrato, sin exigir igualdad literal entre
respuestas reales no deterministas. El flujo SSE exige fuentes y `[DONE]`;
no se trata un truncamiento o error como éxito.

El contexto público permite cotejar citas y omisiones visibles; no reconstruye
el prompt completo ni el ranking inicial del recuperador. Las respuestas de
evaluación se conservan como datos, sin ejecutar contenido Markdown/HTML ni
instrucciones recuperadas. Consultar la [guía de Gold y sus campos](../../data/README.md#campos-de-gold)
y la [recuperación de Gold A](../../data/chroma-releases/README.md) para identificar los
insumos usados en una referencia real.

---

## Herramientas externas al runtime del RAG

### Tutorial de construcción de ground truth (`docs/ground-truth/`)

El [tutorial web de anotación](index.html), la
[cartilla de Ground Truth](ground-truth/ATLAS_Cartilla_Ground_Truth.md) y el
[tutorial escrito](ground-truth/ATLAS_Tutorial_Construccion_Ground_Truth.md)
explican la metodología con la muestra de la primera ronda. Para evaluar
Gold A, consultar el [inventario vigente](../../data/CORPUS_CATALOG.md) y el
[banco de preguntas versionado](#banco-de-preguntas-evaluationdatalegal-ground-truth-v01json).

`scripts/deploy-tutorial-html.ps1` publica el tutorial HTML en el proyecto
Vercel `atlas-tutorial-groundtruth`. Requiere Vercel CLI y una sesión iniciada.

```powershell
pwsh scripts/deploy-tutorial-html.ps1            # despliega a producción
pwsh scripts/deploy-tutorial-html.ps1 -Preview   # despliega una preview
```

---

## Resumen de uso frecuente

| Tarea | Comando |
|-------|---------|
| Verificar chunks en ChromaDB | `uv run python -m utils.chroma_count` |
| Limpiar ChromaDB para re-indexar | `uv run python -m utils.chroma_clear --collection rag_playas --execute` |
| Instalar Docker en Ubuntu | `sudo bash rag/scripts/install-docker-ubuntu.sh` |
| Prueba de carga | [Comando y requisitos](#pruebas-de-carga) |
