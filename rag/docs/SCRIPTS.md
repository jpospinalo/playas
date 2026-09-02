# Scripts operacionales — RAG

Referencia de scripts de despliegue, SageMaker, pruebas de carga, utilidades ChromaDB y herramientas auxiliares del módulo RAG.

Los scripts de infraestructura ECS Fargate (`deploy.sh`, `push_images.sh`, `start.sh`, `stop.sh`, `export_postgres.sh`) están documentados en [`../infrastructure/README.md`](../infrastructure/README.md), no aquí.

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

```bash
export RAG_LOAD_TEST_TOKEN=<jwt>   # el endpoint exige autenticación
uv run python rag/scripts/load_test.py --url http://localhost:8080 --users 10 --timeout 60
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
servicio — ver la sección "Evaluación offline" de
[`docs/ARCHITECTURE.md`](ARCHITECTURE.md#10-evaluación-offline-evaluation).

**⚠️ Requiere autorización explícita antes de correrse de verdad.** Una
corrida real invoca el grafo real de producción pregunta por pregunta y
llama a un LLM/juez externo (Gemini u Ollama) por cada métrica — no es un
comando inocuo para ejecutar "para probar". `--validate-only` (más abajo)
no tiene ese costo ni ese riesgo.

### Dataset (`evaluation/data/legal-ground-truth-v0.1.json`)

21 preguntas jurídicas reales sobre playas/dominio público
marítimo-terrestre, cada una con sus 5 campos obligatorios diligenciados:
`doc_principal`, `doc_secundario`, `pregunta`, `respuesta`,
`ubicacion_evidencia` (más `id`). Cargador y validación de ese contrato en
`evaluation/ground_truth.py`: si falta alguno de esos cinco campos o
contiene un valor vacío, `load_ground_truth_cases()` falla explícitamente
en vez de evaluar un registro incompleto en silencio.

Los registros `registro-017` a `registro-022` (`AMBIGUOUS_DOCUMENT_CASE_IDS`
en `ragas_common.py`) tienen referencias documentales aún ambiguas (no
permiten identificar inequívocamente la sentencia esperada) — se incluyen
en la evaluación de todas las demás métricas, pero se excluyen por diseño
de cualquier métrica de "documento esperado".

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

### RAGAS y `langchain-community`

`ragas==0.4.3` (última versión publicada) importa
`ChatVertexAI` desde `langchain_community.chat_models.vertexai`, símbolo
que `langchain-community` retiró en 0.4.x. El grupo `dev` de
`pyproject.toml` fija `langchain-community==0.3.31` (que sí lo expone)
para que `import ragas` funcione sin tocar `ragas` ni añadir
`langchain-google-vertexai` — ver el comentario junto al pin en
`pyproject.toml`. El pin es solo de desarrollo/evaluación: no cambia
ninguna dependencia de producción (`uv export --no-dev --package rag` es
idéntico con o sin él).

---

## Herramientas externas al runtime del RAG

### Tutorial de construcción de ground truth (`docs/ground-truth/`)

Subsistema autocontenido, ajeno al pipeline de ingesta/servicio del RAG, para
publicar el tutorial interno de construcción de ground truth como una página
web independiente:

- `docs/ground-truth/tutorial2.html` — el tutorial en sí.
- `docs/index.html` — redirige a `./ground-truth/tutorial2.html`.
- `scripts/deploy-tutorial-html.ps1` — despliega **únicamente** ese HTML
  (copiado a una carpeta temporal aislada) al proyecto Vercel
  `atlas-tutorial-groundtruth`; requiere Vercel CLI (`npm i -g vercel`) y
  sesión iniciada (`vercel login`).

```powershell
pwsh scripts/deploy-tutorial-html.ps1            # despliega a producción
pwsh scripts/deploy-tutorial-html.ps1 -Preview   # despliega una preview
```

`docs/ground-truth/` también contiene material relacionado con el mismo
tutorial, no enlazado desde `tutorial2.html`
(`ATLAS_Cartilla_Ground_Truth.md`, `ATLAS_Tutorial_Construccion_Ground_Truth.md`,
`ATLAS_Tutorial_Plataforma.md`, `1.jpeg`). Herramienta del equipo
jurídico/de anotación, no del servicio RAG — no la modifiques al tocar
`backend/rag/` o `frontend/`.

---

## Resumen de uso frecuente

| Tarea | Comando |
|-------|---------|
| Verificar chunks en ChromaDB | `uv run python -m utils.chroma_count` |
| Limpiar ChromaDB para re-indexar | `uv run python -m utils.chroma_clear --collection rag_playas --execute` |
| Instalar Docker en Ubuntu | `sudo bash rag/scripts/install-docker-ubuntu.sh` |
| Prueba de carga contra ECS | `uv run python rag/scripts/load_test.py --url http://localhost:8080 --users 10` |
