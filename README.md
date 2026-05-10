# ATLAS

**Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre playas en Colombia.**

Agente conversacional de **jurisprudencia colombiana sobre playas y dominio público marítimo-terrestre**. Procesa sentencias en PDF (Consejo de Estado, Tribunales Administrativos), las indexa semánticamente y las expone como un agente **LangGraph** sobre una API FastAPI consumida por un frontend Next.js con autenticación, historial de conversaciones, calificación de respuestas y panel de administración.

- [Registro de archivos indexados](docs/archivos-indexados.md)
- [Estructura típica de los documentos](docs/DOCUMENT_SECTIONS.md)
- [Configuración manual de Firebase](docs/firebase-config-manual.md)

---

## Arquitectura

Tres capas independientes que comparten `data/` y servicios externos (ChromaDB, Ollama, Firebase, proveedor LLM):

```
┌──────────────────────┐     ┌──────────────────────────────────┐     ┌──────────────────┐
│  Pipeline de ingesta │  →  │  Agente LangGraph + API FastAPI  │ ←→  │ Frontend Next.js │
│  (paquete `ingest/`) │     │       (paquete `rag/`)           │     │  (`frontend/`)   │
└──────────────────────┘     └──────────────────────────────────┘     └──────────────────┘
```

`rag/` y `ingest/` son **paquetes Python independientes** dentro del workspace `uv`: no comparten código, solo el directorio `data/` y los servicios externos. El frontend (Bun) habla con la API por SSE para streaming y directamente con Firestore para historial/feedback.

---

## Pipeline de ingesta

![Pipeline de ingesta ATLAS](docs/images/pipeline.png)

1. **PDF → Markdown** (`data/bronze/`) — Docling con OCR, tablas e imágenes; limpieza exhaustiva de encabezados, pies y numeraciones.
2. **Bronze → Silver** (`data/silver/`) — normalización, fusión con metadatos legales del CSV (`metadata.csv`) y segmentación por encabezados.
3. **Silver → Gold** (`data/gold/`) — chunking de ~1000 tokens (200 de overlap) y enriquecimiento con LLM (resumen, keywords, entidades), inyectado en la metadata.
4. **Gold → ChromaDB** — embeddings con Ollama (`embeddinggemma`) e indexación. En runtime el retriever combina **BM25 (30%) + vector (70%)** con fusión RRF.

---

## Agente RAG (LangGraph)

El sistema **no es un pipeline RAG fijo**: es un agente compilado en LangGraph con memoria multi-turno (`MemorySaver`) y una tool de recuperación que el LLM invoca solo cuando hace falta.

**Grafo principal** (proveedores con tool calling):

```
START → enrich_query → agent ⇆ tools(retrieve) → END
```

- `enrich_query` reescribe la consulta con terminología jurídica para mejorar el recall.
- `agent` decide si invocar la tool `retrieve` (consulta jurídica) o responder directo (saludo, meta-pregunta).
- `tools.retrieve` corre el `HybridEnsembleRetriever` y devuelve fragmentos como `ToolMessage` + actualización de `sources` en el state.
- El agente vuelve con los docs en contexto y responde citando `[docN]`.

**Grafo fallback** (proveedores sin tool calling, p. ej. Gemma):

```
START → enrich_query → retrieve_forced → generate → END
```

`build_graph()` elige uno u otro según `get_active_provider().supports_structured_output`.

**Memoria** — el `thread_id` (UUID del frontend) persiste el historial en `MemorySaver` mientras viva el proceso. Si el servidor reinicia, el endpoint hidrata el estado desde `conversations/{id}/messages` en Firestore usando el `conversation_id`.

**Streaming SSE** — `/api/query/stream` emite eventos `status` (etapa del nodo), `token` (tokens del LLM en vivo) y un `sources` final con fuentes agrupadas y métricas de contexto.

**Selección de proveedor LLM** — `rag/core/llm_factory.py` resuelve en orden: `OPENAI_API_KEY` → `OPENROUTER_API_KEY` → `GOOGLE_API_KEY`.

---

## Integración Firebase

Autenticación, historial, calificaciones y roles viven en Firebase. El backend usa **Firebase Admin SDK** (`rag/api/firebase_admin.py`); el frontend usa el SDK cliente (`frontend/lib/firebase.ts`).

> **Antes de ejecutar el proyecto** hay que configurar manualmente Firebase Console (Auth, reglas, índices, service account, roles): seguir paso a paso [`docs/firebase-config-manual.md`](docs/firebase-config-manual.md).

**Modelo en Firestore:**

| Colección                             | Propósito                                                                   |
| ------------------------------------- | --------------------------------------------------------------------------- |
| `users/{uid}`                         | `email`, `displayName`, `role` (`user`/`admin`/`super-admin`), `createdAt`. |
| `conversations/{id}`                  | `userId`, `threadId`, `title`, `createdAt`, `updatedAt`, `messageCount`.    |
| `conversations/{id}/messages/{msgId}` | `role`, `text`, `sources?`, `createdAt`.                                    |
| `feedback/{id}`                       | `userId`, `rating` (1-5), `comment`, `conversationId`, `createdAt`.         |

Las reglas (`firestore.rules`) garantizan que cada usuario solo acceda a sus conversaciones, que el campo `role` no sea mutable desde el cliente y que el feedback solo lo lean los admins. `firestore.indexes.json` versiona los dos índices compuestos requeridos.

`rag/api/auth.py` ofrece tres dependencias FastAPI: `get_optional_user` (token opcional), `get_current_user` (obligatorio) y `require_admin` (verifica `role` en Firestore).

---

## Estructura del repositorio

```
rag_playas/
├── rag/                          ← Paquete API + agente
│   ├── core/                     ← agent, tools, retriever, llm_factory, ...
│   └── api/                      ← FastAPI: main, auth, firebase_admin, routes/
├── ingest/                       ← Pipeline de ingesta (independiente)
├── frontend/                     ← Next.js 16 (React 19, Bun)
├── data/                         ← raw / bronze / silver / gold
├── docs/                         ← guías (incluye firebase-config-manual.md)
├── firestore.rules               ← reglas de seguridad versionadas
├── firestore.indexes.json        ← índices compuestos
├── infrastructure/               ← Terraform (EC2 Chroma + Ollama)
├── scripts/                      ← run_pipeline.sh, ec2_*.sh
├── tests/, evaluation/
└── Makefile
```

`uv` gestiona el workspace Python (raíz + `rag/` + `ingest/`); `bun` gestiona el workspace Node (raíz + `frontend/`). El `.env` es único y vive en la raíz.

---

## Requisitos

- Python 3.12+, [`uv`](https://docs.astral.sh/uv/)
- [Bun](https://bun.sh/)
- Docker (para ChromaDB)
- Ollama (local o en EC2)
- Cuenta de Firebase con Auth + Firestore habilitados
- API key de al menos un proveedor LLM: OpenAI, OpenRouter o Gemini

Diseñado para Linux. Compatible con WSL aplicando `dos2unix scripts/*.sh`.

---

## Instalación

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/jpospinalo/rag_playas.git
cd rag_playas
uv sync --group dev
bun install
cp .env.example .env
```

Luego configurar Firebase siguiendo [`docs/firebase-config-manual.md`](docs/firebase-config-manual.md) y completar las variables de entorno descritas abajo.

---

## Variables de entorno

**Backend (`.env` en la raíz):**

```dotenv
# ChromaDB
CHROMA_HOST=<ip>
CHROMA_PORT=8000
CHROMA_COLLECTION=rag_playas_5_docs

# Ollama
OLLAMA_BASE_URL=http://<ip>:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma:latest

# Proveedor LLM (al menos uno)
OPENAI_API_KEY=...
OPENROUTER_API_KEY=...
GOOGLE_API_KEY=...

# Firebase Admin SDK
FIREBASE_SERVICE_ACCOUNT_PATH=firebase-service-account.json
```

**Frontend (`frontend/.env.local`):**

```dotenv
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_FIREBASE_API_KEY=...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=...
NEXT_PUBLIC_FIREBASE_PROJECT_ID=...
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=...
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
NEXT_PUBLIC_FIREBASE_APP_ID=...
```

Cómo obtener cada una: secciones 4 y 5 de [`docs/firebase-config-manual.md`](docs/firebase-config-manual.md).

---

## Infraestructura en AWS

Dos instancias EC2 (recomendado con IP elástica). La carpeta `infrastructure/` provisiona ambas con Terraform:

| Máquina  | Tipo        | Almacenamiento | Puerto |
| -------- | ----------- | -------------- | ------ |
| ChromaDB | `t3.medium` | 12 GB gp3      | 8000   |
| Ollama   | `t3.large`  | 20 GB gp3      | 11434  |

```bash
cd infrastructure/ && terraform init && terraform apply
```

Setup manual alternativo: `bash scripts/ec2_chroma_db.sh` y `bash scripts/ec2_ollama_embeddings.sh`.

---

## Ejecución

```bash
# Pipeline de ingesta (todas las etapas)
make pipeline

# API FastAPI (docs interactivas en http://localhost:8080/docs)
make app

# Frontend (http://localhost:3000)
make frontend
```

La documentación de los endpoints está disponible automáticamente en `/docs` y `/redoc` (Swagger UI / ReDoc generadas por FastAPI).

---

## Comandos útiles

```bash
make install          # dependencias Python
make lint / format    # ruff
make test             # pytest unitarios
make test-integration # tests con servicios reales (Chroma + Ollama)
make pipeline         # pipeline completo de ingesta
make app / frontend   # API / frontend
make help             # listar todos los targets
```
