# Guía de uso y despliegue — ATLAS RAG

Stack: FastAPI + Next.js + PostgreSQL + Nginx, orquestado con Docker Compose.
Servicios externos requeridos: ChromaDB y Ollama (embeddings) en EC2.

Para el despliegue en AWS ECS Fargate (alternativa a este stack de un solo host) ver [`infrastructure/README.md`](../infrastructure/README.md). Para la arquitectura del sistema ver [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Usar Gold A en ATLAS

Para consultar o evaluar desde la aplicación, pedir al responsable del
entorno la URL y una cuenta habilitada. Confirmar que el backend de esa URL
usa la colección `rag_playas_gold_a_cc7bf44b54a9` y el
[perfil de embeddings de Gold A](../../data/chroma-releases/README.md#perfil-y-lectura-vectorial).
Iniciar sesión y hacer una consulta con evidencia conocida. Por ejemplo,
preguntar qué establece el artículo 166 del Decreto Ley 2324 sobre las
playas marítimas. Revisar la respuesta y el pasaje citado.

Para ejecutar un RAG propio, seguir la
[configuración de Gold A](#conectar-el-rag-a-gold-a). El responsable del
entorno puede [verificar la colección existente](../../data/chroma-releases/README.md#verificar-una-colección-existente)
o recuperarla desde el paquete versionado.

## Conectar el RAG a Gold A

El código y el paquete Gold A se entregan en `corpus`. Solicitar los
endpoints autorizados de Chroma y Ollama y las credenciales del proveedor LLM.
Para una evaluación, registrar el commit, la entrega Gold y el modelo de
generación utilizados.

---

## Requisitos previos

- Docker ≥ 24 y Docker Compose v2
- Acceso a los servicios EC2 de ChromaDB y Ollama
- API key de OpenAI (u OpenRouter / Google Gemini como alternativa)
- Colección Gold A preparada por el responsable del entorno. El
  [paquete versionado](../../data/chroma-releases/README.md#paquetes)
  permite recuperarla con los vectores existentes.

---

## 1. Clonar el repositorio y ubicarse en `rag/`

```bash
git clone --branch corpus --single-branch https://github.com/jpospinalo/playas.git
cd playas/rag
```

---

## 2. Configurar variables de entorno

Copiar el archivo de ejemplo y editarlo:

```bash
cp .env.example .env
```

Valores obligatorios a definir:

```env
# ── Servicios externos (EC2) ──────────────────────────────────────────────────
CHROMA_HOST=<dominio-o-IP-del-servidor-ChromaDB>
CHROMA_PORT=8000
CHROMA_COLLECTION=rag_playas_gold_a_cc7bf44b54a9

OLLAMA_BASE_URL=http://<dominio-o-IP-del-servidor-Ollama>:11434
OLLAMA_EMBEDDING_MODEL=embeddinggemma:latest

# ── LLM (prioridad: OpenAI → OpenRouter → Gemini) ────────────────────────────
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-5-nano

# ── Base de datos ─────────────────────────────────────────────────────────────
# Docker Compose usa PostgreSQL automáticamente; no cambiar DATABASE_URL.
POSTGRES_PASSWORD=<contraseña-segura>

# ── Autenticación JWT ─────────────────────────────────────────────────────────
# Generar con: python3 -c "import secrets; print(secrets.token_hex(32))"
JWT_SECRET_KEY=<clave-aleatoria-larga>

# ── Frontend ──────────────────────────────────────────────────────────────────
# Dejar vacío para que el frontend use rutas relativas (/api/...) a través de nginx.
NEXT_PUBLIC_API_URL=
```

Usar en `CHROMA_HOST` el nombre o IP sin esquema, y en `OLLAMA_BASE_URL` la
URL del servicio con esquema y puerto. Con Compose, las direcciones deben
ser accesibles desde el contenedor del backend. `localhost` en esa
configuración apunta al propio contenedor. Completar las credenciales del
proveedor elegido y retirar del archivo local las claves de ejemplo.

> **Nota:** `NEXT_PUBLIC_API_URL` debe quedar vacío (no `http://localhost:8080` ni `/api`)
> cuando se despliega con Docker Compose. El frontend construye URLs como
> `${API_URL}/api/query`; con valor vacío resultan en `/api/query`, que nginx
> enruta correctamente al backend.

---

## 3. Comprobar la colección y el modelo

Para un entorno ya preparado, usar la
[verificación de Gold A en modo de lectura](../../data/chroma-releases/README.md#verificar-una-colección-existente)
con los mismos endpoints configurados en el backend. Esperar
`REUSED_VERIFIED`, 5.862 registros y `Chroma_writes: 0`.
Si falta la colección, el responsable puede
[restaurar el paquete](../../data/chroma-releases/README.md#restaurador-del-despliegue-de-corpus).

---

## 4. Construir y levantar el stack

```bash
cd /ruta/al/repositorio/rag
docker compose up -d --build
```

Docker Compose levanta cuatro servicios:

| Servicio    | Descripción                          | Puerto interno |
|-------------|--------------------------------------|----------------|
| `postgres`  | Base de datos PostgreSQL             | 5432           |
| `backend`   | API FastAPI (uvicorn)                | 8080           |
| `frontend`  | Next.js (producción)                 | 3000           |
| `nginx`     | Reverse proxy — entrada pública      | **80**         |

La app queda disponible en `http://<IP-o-dominio-del-servidor>`.

---

## 5. Verificar el estado

```bash
# Estado de los contenedores
docker compose ps

# Logs en tiempo real
docker compose logs -f

# Health del backend
curl -fsS http://localhost/api/health
curl -fsS http://localhost/api/ready
```

Todos los servicios deben mostrar `(healthy)` o `Up`.
Una vez disponible el backend, realizar la
[consulta de comprobación](#usar-gold-a-en-atlas). Las
[pruebas de humo](SMOKE_TESTS.md) describen la comprobación por API.

---

## 6. Operaciones frecuentes

### Reiniciar un servicio sin reconstruir

```bash
docker compose restart backend
docker compose restart frontend
```

### Reconstruir un solo servicio (tras cambios en código o `.env`)

```bash
docker compose up -d --build backend
docker compose up -d --build frontend
```

> Reconstruir el frontend es necesario cuando se cambia `NEXT_PUBLIC_API_URL`
> u otras variables `NEXT_PUBLIC_*`, ya que se hornean en el bundle en tiempo de build.

### Ver logs de un servicio

```bash
docker compose logs -f backend
docker compose logs -f frontend
```

### Detener el stack

```bash
docker compose down          # detiene y elimina contenedores (conserva volúmenes)
docker compose down -v       # elimina también el volumen de PostgreSQL
```

---

## 7. Solución de problemas frecuentes

| Síntoma | Causa | Solución |
|---------|-------|----------|
| Backend sin conexión a ChromaDB | Host o puerto inaccesible | Verificar destino, conectividad y logs antes de importar datos |
| `/api/ready` no indica disponibilidad | Base de datos sin respuesta, grafo sin compilar o índice BM25 vacío | Revisar el detalle de readiness y la colección seleccionada |
| `NetworkError` al consultar en la app | `NEXT_PUBLIC_API_URL` apunta a `localhost:8080` | Dejarlo vacío y reconstruir el frontend |
| `{"detail":"Not Found"}` en consultas | `NEXT_PUBLIC_API_URL=/api` genera rutas duplicadas (`/api/api/...`) | Dejarlo vacío y reconstruir el frontend |
| Corpus vacío o sin fuentes recuperables | Colección vacía o distinta de la esperada | Comprobar destino y conteo de la entrega; no iniciar una ingesta para diagnosticarlo |
