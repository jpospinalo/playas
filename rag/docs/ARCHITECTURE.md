# Arquitectura — ATLAS RAG

Estado actual del sistema, confirmado contra el código (`backend/rag/`,
`frontend/`). Para el mapa de directorios completo del repo ver el
[README de la raíz](../../README.md); este documento se enfoca en cómo encajan las piezas.

---

## 1. Paquete Python (`backend/rag/`)

```
backend/rag/
├── config.py                 # Env vars: S3, Chroma, Ollama, LLM, enriquecimiento, límite de contexto
├── s3_client.py               # S3 read-only (list, read)
├── core/
│   ├── agent.py               # LangGraph: grafo único determinista (§2)
│   ├── tools.py                # build_context_block + sanitize_replacement_chars
│   ├── prompts.py              # Prompts de sistema/humano del agente + enricher
│   ├── embeddings.py           # Adaptadores Chroma/LangChain + embeddings async de consulta Ollama
│   ├── chroma_query.py         # Búsqueda REST v2 asíncrona con cliente propio de la API
│   ├── vectorstore.py          # Build/update de la colección ChromaDB desde gold
│   ├── retriever.py            # BM25 (tokenizador español) + vector + HybridEnsembleRetriever (RRF c=2, multiconsulta, jerarquía normativa) (§3)
│   ├── territorio.py           # Lugares de las normas locales y prioridad territorial (§3)
│   ├── query_enricher.py       # Construcción del prompt del enricher, parseo JSON, API pública enrich_query/enrich_query_async
│   ├── domain_scope.py         # Esquema EnrichedQuery + clasificador determinista de alcance costero/jurídico
│   ├── legal_resolution.py     # Resolución documental sobre el snapshot BM25 con procedencia verificada
│   ├── normative_context.py    # Selección acotada de artículos y adopción de planes sobre el mismo snapshot verificado
│   ├── generator.py            # Adaptador de evaluación: mismo grafo, aislado por pregunta (§10)
│   ├── observability.py        # Instrumentación de logging (etapas del grafo, conteos, sin filtrar contenido)
│   └── llm_factory.py          # OpenAI → OpenRouter → Gemini → error
└── api/
    ├── main.py                 # App FastAPI: lifespan (compila grafo + init_db), health, ready, query, query/stream
    ├── query_support.py         # Helpers de main.py: fuentes, contexto, config del grafo, hidratación de historial
    ├── conversation_lock.py     # Registro de locks por conversación (evita turnos concurrentes en el mismo thread_id)
    ├── rate_limit.py             # Rate limiting (query, generate-title, login) + backpressure de concurrencia global
    ├── passwords.py              # Hash y verificación de contraseñas (SHA-256 + bcrypt)
    ├── auth.py                  # Dependencias JWT: get_optional_user / get_current_user / require_admin
    ├── database.py              # Motor/sesión async SQLAlchemy (Postgres en prod, SQLite de respaldo); init_db crea tablas y agrega columnas opcionales nuevas a tablas existentes
    ├── models.py                 # User, Conversation, Message, Feedback, MessageFeedback
    ├── schemas.py                 # Modelos Pydantic de request/response
    └── routes/
        ├── auth.py               # POST /api/auth/login, /register — emisión de JWT
        ├── conversations.py      # CRUD conversaciones/mensajes, POST .../generate-title
        ├── feedback.py            # POST /api/feedback, POST /api/feedback/message
        └── admin.py               # GET/POST /api/admin/* (feedback, message-feedback, usuarios)
```

`rag/backend/` es el miembro del workspace `uv`; el paquete importable es
`rag` (`import rag...`), con `pythonpath = ["backend"]` en
`pyproject.toml` para que `tests/` y `evaluation/` lo resuelvan sin cd.

## 2. Agente RAG (LangGraph)

El sistema **no es tool-calling / ReAct**: `build_graph()` (`core/agent.py`)
compila los mismos nodos para cualquier proveedor LLM. Las capacidades del
proveedor adaptan las llamadas dentro de los nodos; la ruta de recuperación
se elige a partir del análisis de la consulta, sin invocación de herramientas
decidida por el LLM.

```
START → enrich_query → route_after_analysis → {retrieve_forced → generate, respond_without_retrieval} → END
```

- **`enrich_query`** reformula la consulta con terminología jurídica para la
  búsqueda y la clasifica en una de cuatro rutas: `in_scope`,
  `out_of_scope`, `conversation`, `needs_clarification`.
- **`route_after_analysis`** es un edge condicional simple: `in_scope` →
  `retrieve_forced`; cualquier otra ruta → `respond_without_retrieval`.
- **`retrieve_forced`** atiende consultas `in_scope`. Si la verificación
  documental está configurada, puede resolver preguntas explícitas de
  jurisprudencia con procedencia y snapshot BM25 verificados, o abstenerse
  por falta de evidencia, antes del híbrido. El mismo perfil permite seleccionar
  contexto normativo verificado en los casos acotados descritos abajo. Si no
  hay una selección directa suficiente, ejecuta el `HybridEnsembleRetriever`
  exactamente una vez (con `afuse_queries`: la pregunta original, la
  autosuficiente y la enriquecida, recuperadas por separado sin duplicados y
  fusionadas; ver §3) — la recuperación no es opcional, a diferencia de un
  agente ReAct que podría invocar una herramienta cero, una o varias veces.
  Llena `sources` y, vía `tools.build_context_block`, el contexto formateado
  que ve el LLM.
- **Resolución documental (opcional, `legal_resolution.py`)**: se activa con
  `LEGAL_RESOLUTION_PROVENANCE_PATH` y `LEGAL_RESOLUTION_PROVENANCE_SHA256`
  (en ECS, `legal_resolution_enabled`; apagada por defecto). Al arrancar
  verifica que el índice BM25 coincide fragmento a fragmento con la
  procedencia de Gold A. Ante «¿qué ordenó/resolvió/decidió en … instancia …
  en el radicado …?», tanto `retrieve_forced` como `respond_without_retrieval`
  (si la ruta era `out_of_scope` o `needs_clarification`) intentan primero la
  respuesta documental, que cita textualmente la parte resolutiva. Si no la
  hay, `retrieve_forced` recupera con una consulta compuesta, sin el tope de un
  fragmento por sentencia, y se queda solo con los fragmentos verificados. Con
  identidad verificada, `build_context_block` omite los nombres de archivo y
  radicados históricos del contexto.
- **`generate`** devuelve `documentary_answer` si existe, o una respuesta
  fija si no hay `sources`, sin llamar al LLM de generación. En los demás
  casos construye el contexto con `tools.build_context_block`, genera la
  respuesta y valida sus citas (`_validate_citations`); si fallan, devuelve
  la respuesta fija de citas inválidas. Antes de validar, `_tidy_answer` quita
  líneas que solo contienen marcadores `[docN]` y títulos de sección
  repetidos, sin tocar el contenido.
- **`respond_without_retrieval`** responde saludos/meta-preguntas, pide
  aclaración o devuelve la respuesta fija de fuera de alcance — sin llamar
  nunca al retriever híbrido ni al LLM de generación. También puede resolver
  preguntas explícitas por radicado con el índice documental verificado.
  Estas respuestas **guían** al usuario: muestran ejemplos de consultas reales
  (lugar + actividad + autoridad) y los tres datos que faltan (dónde, qué
  actividad o trámite, quién intervino). Un saludo solo («hola», «buenos
  días») recibe la guía con ejemplos; un saludo seguido de un asunto («hola,
  tengo un problema con la playa») se trata como consulta y se pide el dato
  que falta. Si la heurística de `domain_scope.py` encuentra una sola señal
  (costera o jurídica) y el modelo dijo `out_of_scope`, la ruta se degrada a
  `needs_clarification`: se pide el dato en vez de cerrar la consulta. Una
  referencia a «ese plan» sin identificarlo ni historial pertinente también
  pide aclaración.

Cada compilación exitosa registra `legal_resolution_state`:
`not_configured` si la capacidad optativa no se solicitó,
`snapshot_verified` si se habilitó el índice con una instantánea verificada,
o `unavailable` si la procedencia configurada no permitió habilitarlo.
Describe el arranque, no la suficiencia jurídica para cada pregunta ni la
salud permanente. Conserva los diagnósticos existentes y no cambia
`/api/ready`, que comprueba grafo, BM25 y SQL.

`normative_context.py` usa exclusivamente el snapshot verificado, el filtro
original de tipos documentales y los cuerpos originales. Puede seleccionar
contexto taxonómico de un artículo y una norma identificados inequívocamente,
con sus encabezados y continuaciones dentro de un máximo de cuatro fuentes.
También admite una pregunta inicial de adopción de un plan nombrado cuando
el cuerpo prueba su identidad y alias único en la misma fuente y norma y otro
artículo completo atribuye explícitamente la adopción. No sustituye adopción
por formulación o ejecución, ni admite por esta vía planes sin prueba,
historial heredado, filtros excluyentes o rutas terminales ajenas. Conserva la
pregunta original frente a reformulaciones sobre otro plan. La gramática es
deliberadamente limitada: si falta o es ambigua la prueba, conserva la
clasificación y recuperación existentes, sin inventar una atribución. No
garantiza recuperar íntegro cualquier artículo o plan.

## 3. Retrieval híbrido

`core/retriever.py` combina BM25 (léxico) y búsqueda vectorial (ChromaDB,
embeddings `embeddinggemma:latest` vía Ollama, colección con distancia
coseno) mediante `HybridEnsembleRetriever`. Filtra por `doc_type`
(`jurisprudencia` / `normativa`) cuando la consulta lo especifica. Cada
parámetro de abajo se midió sobre el ground truth v0.2; las cifras están en
los comentarios del código y en
[`evaluation/README.md`](../evaluation/README.md#estado-al-2026-11-11-gold-a-corregido-mejoras-de-recuperación-y-qa-sin-juez).

1. **Tokenizador español para BM25** (`_tokenize_bm25`, el mismo para indexar
   y consultar): minúsculas y sin tildes, palabras con `\w+`, sin palabras
   vacías del español ni tokens de una letra, y plural ligero (`playas` →
   `playa`, `concesiones` → `concesion`, `parque`/`parques` → `parqu`).
2. **Multiconsulta** (`afuse_queries`): la pregunta original, la
   autosuficiente y la enriquecida se recuperan por separado (sin duplicados
   ni vacías) en un único `asyncio.gather`, y todas las listas se fusionan
   juntas.
3. **Fusión RRF ponderada:** constante `RRF_C = 2`, pesos `BM25_WEIGHT = 0.8`
   y `VECTOR_WEIGHT = 0.2`. Con la constante anterior (160) el resultado era
   en la práctica el top vectorial.
4. **Un fragmento por sentencia** (`fragmentos_por_sentencia = 1`): los
   fragmentos siguientes de la misma sentencia pasan al final (no se
   descartan), para que el top-k no se llene con una sola sentencia. Las
   normas no tienen tope.
5. **Prioridad territorial** (`core/territorio.py`): las normas locales de
   Cartagena, Santa Marta o Turbo que la consulta no menciona se demotan al
   final (no se descartan). Los lugares se reconocen como palabra completa
   (`LUGARES`: Rodadero, Taganga y Tayrona cuentan como Santa Marta;
   Bocagrande y Barú como Cartagena; «turbocompresor» no es Turbo).
6. **Jerarquía normativa** (`_priorizar_normativa`): se reserva
   `CUPOS_NORMATIVA = 1` puesto a una norma aplicable (nacional, o local del
   lugar mencionado) si la selección no trae ninguna, reemplazando la
   jurisprudencia peor ubicada, y las normas se ordenan antes que las
   sentencias. El prompt (regla 5) pide exponer primero la norma y luego la
   jurisprudencia que la interpreta.

`tools.build_context_block` arma el contexto que lee el modelo: cabecera de
la norma (con su ámbito territorial si es local) o de la sentencia
(corporación, radicado, magistrado, tema, sección), el resumen marcado como
«auxiliar (contrastar con el cuerpo)» y el «Texto del fragmento».

El arranque de la API usa el SDK síncrono de Chroma para preparar el
vectorstore y el snapshot de documentos de BM25. El lifespan abre clientes
HTTP asíncronos propios para búsquedas REST v2 de Chroma y embeddings de
Ollama y los inyecta al grafo. Si Chroma tiene un proveedor de autenticación
del SDK, conserva la ruta SDK/LangChain y los embeddings heredados en vez
de abrir esos clientes. La E/S de los clientes propios admite cancelación
y sus contextos se cierran al salir del lifespan; esto no garantiza cancelar
el respaldo SDK ni la inicialización mediante `to_thread(init_retrievers)`.

## 4. Memoria y persistencia de conversación

Dos mecanismos independientes, con propósitos distintos:

- **`MemorySaver`** (LangGraph, en memoria del proceso) — el checkpointer
  que mantiene el estado del grafo (`state["messages"]`) mientras el
  servidor vive, indexado por `thread_id` (UUID generado en el frontend).
  Un checkpoint con mensajes evita recargar el historial; solo se añade
  la pregunta nueva al estado existente.
- **Base de datos SQL** (Postgres en prod, SQLite de respaldo local, vía
  SQLAlchemy async) — persiste cada mensaje de forma independiente al
  grafo. El frontend hace `POST /api/conversations/{id}/messages` tanto
  para el mensaje del usuario como para la respuesta del asistente; esta
  escritura ocurre siempre, tenga o no el servidor un checkpoint en memoria
  para esa conversación.

SQL permite reconstruir el historial tras un reinicio; no convierte
`MemorySaver` en un checkpoint durable, no reanuda un nodo interrumpido y no
coordina checkpoints entre procesos o réplicas.

`api/query_support.py::_get_initial_messages()`, usada por `api/main.py`,
consulta SQL cuando hay `conversation_id` para comprobar la pertenencia
al usuario. Si se aporta `current_message_id`, valida además que pertenece
a esa conversación, tiene rol `user` y coincide con la pregunta. Estas
validaciones ocurren **también con un checkpoint caliente**.

Sin checkpoint, carga el historial persistido como
`HumanMessage`/`AIMessage` y añade la pregunta nueva. Con
`current_message_id`, carga solo el prefijo anterior al mensaje actual,
ordenado por `(created_at, id)`; sin ese ID, carga **todos** los mensajes de
la conversación, sin límite. Sin `conversation_id`, comienza con la
pregunta nueva y no admite `current_message_id`.

El LLM de generación no recibe directamente `state["messages"]`, sino el
contexto recuperado y la pregunta, incluida su reformulación contextual si
existe. `enrich_query_node` consume una ventana reciente de los últimos
~4000 caracteres del historial (`_MAX_ANALYSIS_HISTORY_CHARS`). Esa ventana
no limita el historial persistido ni el estado del grafo: no hay una
política de retención ni un tope global de RAM implementados aquí.

El campo de respuesta `context_tokens` sí depende de cuántos mensajes trae
`state["messages"]` en ese momento — es una función directa del tamaño de
ese estado, no un valor independiente. Cualquier cambio futuro a cómo se
carga o acota el historial debe preservar el valor/significado de
`context_tokens` tal como lo consume el frontend hoy.

## 5. API HTTP y streaming SSE

`api/main.py` expone `GET /api/health`, `GET /api/ready`, `POST /api/query`
y `POST /api/query/stream`, además de los routers de `auth`, `conversations`,
`feedback` y `admin` (`api/routes/`).

**`/api/query/stream` no transmite tokens en vivo desde el LLM.**
`generate_node` espera la respuesta completa (`chain.ainvoke`, no
`.astream()`), valida sus citas, y solo entonces `event_generator()`
(`api/main.py`) trocea la respuesta ya completa y ya validada en fragmentos
de texto de tamaño fijo, emitidos como eventos `token` consecutivos sin
pausa entre ellos — no es generación incremental real. El endpoint emite
`status` (etapa del nodo, en vivo vía `get_stream_writer()`), luego esos
fragmentos `token`, y finalmente un evento `sources` con las fuentes
agrupadas y las métricas de contexto, seguido de `[DONE]` en un cierre normal.

OpenAPI declara la respuesta `200` como `text/event-stream`. Validar el
formato y rango de las citas no demuestra por sí solo respaldo semántico:
esa comprobación exige cotejar la respuesta con los pasajes visibles.

En un cierre de éxito, el cliente exige un único evento `sources` (una lista
vacía es válida) antes de `[DONE]`. Rechaza truncamientos, duplicados y eventos
conocidos fuera de orden. Un error o una cancelación no se tratan como una
respuesta completada para persistir.

## 6. Autenticación

Auth propia con **JWT + PostgreSQL**. `api/auth.py` emite/valida tokens HS256
(`JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES`); las contraseñas
se hashean con SHA-256 seguido de bcrypt (`api/passwords.py`).

`get_current_user` lee el usuario con la sesión de la solicitud y la cierra
enseguida: así devuelve la conexión al pool antes de que el endpoint ejecute
la consulta (que puede tardar hasta `RAG_QUERY_TOTAL_TIMEOUT_SECONDS`, 280 s).
Sin esto, cada consulta retenía una conexión todo ese tiempo y con más de 15
consultas simultáneas el pool (5 + 10) se agotaba (500 a los 30 s). Para
rechazar el exceso de carga con un 503 inmediato hay que activar
`RAG_BACKPRESSURE_MODE=enforce` y ajustar `RAG_BACKPRESSURE_MAX_CONCURRENT`;
por defecto está en `off`.

En el frontend, `lib/auth.ts` guarda el token y una caché de usuario ligada
a ese token en `localStorage` (sin cookies ni SDK de terceros).
`AuthProvider` valida `/api/auth/me` al montar y al observar un cambio
efectivo de token entre pestañas. Las operaciones fijan su credencial según
la identidad mostrada, incluso antes del evento `storage`, y un `401` tardío
no cierra otra sesión. Estas guardas dan coherencia a la UI; el backend sigue
verificando JWT, roles y propiedad en cada petición. Véanse la migración de
caché, cancelación y aislamiento del chat en el
[contrato del cliente](../frontend/README.md#autenticación-jwt-propio).

## 7. Selección de proveedor LLM

`core/llm_factory.py` selecciona proveedor en orden: **OpenAI** →
**OpenRouter** → **Gemini** → error. Gana el primero con API key
configurada; un fallo de ese proveedor no hace que pruebe el siguiente.
El soporte de salida estructurada y de rol de sistema se
detecta automáticamente por nombre de modelo (las variantes Gemma carecen
de ambos vía Google GenAI).

## 8. Infraestructura externa (AWS)

- **ChromaDB + Ollama** — EC2, provisionadas por Terraform en
  `../../vector-infraestructura/` (Chroma en el puerto 8000;
  modelo de embeddings `embeddinggemma:latest` en el puerto 11434).
  La colección es configurable con `CHROMA_COLLECTION` (alias legado
  `CHROMA_COLLECTION_NAME`); `rag_playas` es el valor por defecto legado.
  Para Gold A y su perfil optativo de procedencia, consultar la
  [configuración existente](DESPLIEGUE.md#perfiles-de-gold-a).
  Reranker opcional (`OllamaReranker`, no usado en el flujo principal):
  requiere `OLLAMA_RERANK_BASE_URL` y `OLLAMA_RERANK_MODEL` (o su alias
  legado `OLLAMA_RERANKER_MODEL`) explícitos — `config.py` no define un
  valor por defecto. `llama3.2:3b` es el valor configurado en
  `.env.example` y el valor por defecto de `variable.ollama_reranker_model`
  en `../infrastructure/variables.tf`.
- **App RAG (backend + frontend)** — ECS Fargate, provisionada por
  Terraform en `../infrastructure/`. El servicio `app` corre el backend
  FastAPI y un sidecar `postgres:16-alpine` (datos en volumen EFS) en la
  misma tarea; `DATABASE_URL` apunta a `localhost:5432`.
- **Bucket de datos** — S3, provisionado por Terraform en
  `../../ingesta/infrastructure/`, con las capas `raw/bronze/silver/gold`.

## 9. Estructura de documentos indexados

La jurisprudencia se organiza en contexto del caso, desarrollo procesal,
argumentación jurídica y decisión. Los límites y las variantes se describen
en [Seccionado de jurisprudencia](../../ingesta/docs/DOCUMENT_SECTIONS.md).

**Normativa** (decretos, reglamentos) se segmenta por `Artículo N` (regex
sobre texto plano), preservando la jerarquía `TÍTULO`/`CAPÍTULO` como
metadata. Una unidad `"Preámbulo"` captura el texto previo al primer
artículo.

`doc_type` se fija una sola vez al cargar desde la carpeta origen y se
propaga por todas las capas del pipeline de ingesta; la colección ChromaDB
es compartida, y el filtrado por `doc_type` permite servir ambos tipos
desde el mismo retriever.

El [corpus versionado](../../data/README.md#campos-de-gold) documenta los
campos de Gold, la adaptación a Chroma y su uso en la recuperación y la
respuesta.

## 10. Evaluación del RAG (`evaluation/`)

Los comandos de evaluación se ejecutan aparte del servicio. Los adaptadores
de RAGAS usan `rag.core.generator.generate_answer` para invocar el mismo
grafo del RAG, con un grafo nuevo y un `thread_id` efímero por pregunta.
Si la resolución documental está configurada, precarga el snapshot BM25
antes de compilarlo. No ejecuta el lifespan de la API ni inyecta sus
clientes REST de búsqueda y embeddings. La corrida completa evalúa el
contexto y la respuesta con llamadas a modelos y requiere servicios
configurados. El modo `--validate-only` comprueba el banco y la configuración
local. Compartir grafo no hace idénticos los transportes, presupuestos de
timeout, cancelación o presentación pública de fuentes. Para medir el
comportamiento de la aplicación, capturar sus endpoints JSON/SSE y registrar
el perfil de procedencia activo; el evaluador directo conserva su alcance.

El banco `evaluation/data/legal-ground-truth-v0.1.json` está versionado y
pendiente de validación final. `evaluation/ground_truth.py` comprueba su
estructura. Consultar [los comandos y el reporte](SCRIPTS.md#evaluación-del-rag).

La línea base sobre `evaluation/data/legal-ground-truth-v0.2.json` (66 casos
generados desde el Excel del equipo jurídico por `ground_truth_v02.py`; 27
marcados como revisados, sin sustituir la validación final del banco) sigue
la misma regla y corre en fases independientes y reanudables:
`retrieval_baseline.py` (recuperación sin LLM) → `generation_cache.py` (grafo
real una vez por caso, en caché) → `ragas_v02.py` (métricas RAGAS sobre la
caché) → `baseline_report.py` (tablas) → `registro.py` (registro versionado
de cada corrida). Ver
[`docs/SCRIPTS.md`](SCRIPTS.md#línea-base-sobre-legal-ground-truth-v02).
