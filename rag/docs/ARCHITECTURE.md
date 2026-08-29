# Arquitectura — ATLAS RAG

Estado actual del sistema, confirmado contra el código (`backend/rag/`,
`frontend/`). Para el mapa de directorios completo del repo ver el
`CLAUDE.md` de la raíz; este documento se enfoca en cómo encajan las piezas.

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
│   ├── embeddings.py           # Cliente de embeddings Ollama (ChromaDB + LangChain)
│   ├── vectorstore.py          # Build/update de la colección ChromaDB desde gold
│   ├── retriever.py            # BM25 + vector + HybridEnsembleRetriever (RRF c=160)
│   ├── query_enricher.py       # Reescritura de consulta + clasificación de ruta
│   └── llm_factory.py          # OpenAI → OpenRouter → Gemini → error
└── api/
    ├── main.py                 # App FastAPI: lifespan (compila grafo + init_db), health, ready, query, query/stream
    ├── auth.py                  # Dependencias JWT: get_optional_user / get_current_user / require_admin
    ├── database.py              # Motor/sesión async SQLAlchemy (Postgres en prod, SQLite de respaldo)
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
compila un único grafo determinista, el mismo para cualquier proveedor LLM —
no hay ramas por `supports_structured_output` ni por ninguna otra capacidad
del proveedor, y el LLM nunca decide si recuperar documentos.

```
START → enrich_query → route_after_analysis → {retrieve_forced → generate, respond_without_retrieval} → END
```

- **`enrich_query`** reescribe la consulta con terminología jurídica (mejora
  el recall) y la clasifica en una de cuatro rutas: `in_scope`,
  `out_of_scope`, `conversation`, `needs_clarification`.
- **`route_after_analysis`** es un edge condicional simple: `in_scope` →
  `retrieve_forced`; cualquier otra ruta → `respond_without_retrieval`.
- **`retrieve_forced`** ejecuta el `HybridEnsembleRetriever` exactamente una
  vez, solo para consultas `in_scope` — la recuperación no es opcional, a
  diferencia de un agente ReAct que podría invocar una herramienta cero, una
  o varias veces. Llena `sources` y, vía `tools.build_context_block`, el
  contexto formateado que ve el LLM.
- **`generate`** construye la respuesta a partir de `sources`, valida sus
  citas (`_validate_citations`) y, si la validación falla o no hay
  evidencia, cae a una respuesta fija de "sin evidencia/citas inválidas".
- **`respond_without_retrieval`** responde saludos/meta-preguntas, pide
  aclaración o devuelve la respuesta fija de fuera de alcance — sin llamar
  nunca al retriever ni al LLM de generación.

## 3. Retrieval híbrido

`core/retriever.py` combina BM25 (léxico) y búsqueda vectorial (ChromaDB,
embeddings `embeddinggemma:latest` vía Ollama) mediante
`HybridEnsembleRetriever`, fusionando ambos rankings con Reciprocal Rank
Fusion (constante `c=160`). Filtra por `doc_type` (`jurisprudencia` /
`normativa`) cuando la consulta lo especifica.

## 4. Memoria y persistencia de conversación

Dos mecanismos independientes, con propósitos distintos:

- **`MemorySaver`** (LangGraph, en memoria del proceso) — el checkpointer
  que mantiene el estado del grafo (`state["messages"]`) mientras el
  servidor vive, indexado por `thread_id` (UUID generado en el frontend).
  Es lo que permite que un turno 2+ de la misma conversación no tenga que
  releer nada de SQL: el grafo ya tiene el estado en memoria.
- **Base de datos SQL** (Postgres en prod, SQLite de respaldo local, vía
  SQLAlchemy async) — persiste cada mensaje de forma independiente al
  grafo. El frontend hace `POST /api/conversations/{id}/messages` tanto
  para el mensaje del usuario como para la respuesta del asistente; esta
  escritura ocurre siempre, tenga o no el servidor un checkpoint en memoria
  para esa conversación.

`api/main.py::_get_initial_messages()` es el único lugar que lee de SQL para
alimentar el grafo, y solo lo hace cuando `MemorySaver` no tiene estado para
ese `thread_id` — típicamente el primer turno de una conversación tras un
reinicio del servidor. En ese caso, hace un `SELECT` de **todos** los
mensajes de la conversación (sin límite) y los inyecta como
`HumanMessage`/`AIMessage` en el estado inicial. Este historial completo
**nunca llega al LLM de generación**: `generate_node` no recibe
`state["messages"]`, solo `context` (fragmentos recuperados) y `question`.
El único consumidor del historial es `enrich_query_node`, y ya está acotado
internamente a los últimos ~4000 caracteres (`_MAX_ANALYSIS_HISTORY_CHARS`).

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
agrupadas y las métricas de contexto.

## 6. Autenticación

Auth propia con **JWT + PostgreSQL** — no Firebase (removido por completo en
junio de 2026). `api/auth.py` emite/valida tokens HS256
(`JWT_SECRET_KEY` / `JWT_ALGORITHM` / `JWT_EXPIRE_MINUTES`); las contraseñas
se hashean con SHA-256 seguido de bcrypt (`api/routes/auth.py`).

En el frontend, `lib/auth.ts` guarda el token y el usuario en
`localStorage` (sin cookies, sin SDK de terceros); `AuthProvider`
(`components/providers/AuthProvider.tsx`) valida la sesión contra
`GET /api/auth/me` al montar la app y expone `signIn`/`signOut`. Un `401` en
cualquier llamada autenticada dispara el evento `atlas:session-expired`
(ver `lib/api.ts::throwIfSessionExpired`), que `AuthProvider` escucha para
cerrar la sesión en memoria — con un chequeo de que el token que recibió el
401 siga siendo el token activo, para que una respuesta tardía de una sesión
anterior no pueda cerrar la sesión de un usuario distinto que ya inició
sesión después en la misma pestaña.

## 7. Fallback de proveedor LLM

`core/llm_factory.py` intenta proveedores en orden: **OpenAI** →
**OpenRouter** → **Gemini** → error. Gana el primero con API key
configurada. El soporte de salida estructurada y de rol de sistema se
detecta automáticamente por nombre de modelo (las variantes Gemma carecen
de ambos vía Google GenAI).

## 8. Infraestructura externa (AWS)

- **ChromaDB + Ollama** — EC2, provisionadas por Terraform en
  `../vector-infraestructura/` (colección `rag_playas`, puerto 8000;
  modelo de embeddings `embeddinggemma:latest` en el puerto 11434).
  Reranker opcional: Ollama `mistral`.
- **App RAG (backend + frontend)** — ECS Fargate, provisionada por
  Terraform en `infrastructure/`. El servicio `app` corre el backend
  FastAPI y un sidecar `postgres:16-alpine` (datos en volumen EFS) en la
  misma tarea; `DATABASE_URL` apunta a `localhost:5432`.
- **Bucket de datos** — S3, provisionado por Terraform en
  `../ingesta/infrastructure/`, con las capas `raw/bronze/silver/gold`.

## 9. Estructura de documentos indexados

**Jurisprudencia** (sentencias del Consejo de Estado) sigue una estructura
de 4 secciones (ver `../ingesta/docs/DOCUMENT_SECTIONS.md`): Contexto del
caso, Desarrollo procesal, Argumentación jurídica, Decisión.

**Normativa** (decretos, reglamentos) se segmenta por `Artículo N` (regex
sobre texto plano), preservando la jerarquía `TÍTULO`/`CAPÍTULO` como
metadata. Una unidad `"Preámbulo"` captura el texto previo al primer
artículo.

`doc_type` se fija una sola vez al cargar desde la carpeta origen y se
propaga por todas las capas del pipeline de ingesta; la colección ChromaDB
es compartida, y el filtrado por `doc_type` permite servir ambos tipos
desde el mismo retriever.
