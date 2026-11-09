# Guía de despliegue — ATLAS RAG

Stack: FastAPI + Next.js + PostgreSQL + Nginx, orquestado con Docker Compose.
Servicios externos requeridos: ChromaDB y Ollama (embeddings) en EC2.

Para el despliegue en AWS ECS Fargate (alternativa a este stack de un solo host) ver [`infrastructure/README.md`](../infrastructure/README.md). Para la arquitectura del sistema ver [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Selección de código y datos

El código y la entrega Gold A actual se conservan en `corpus`. Consultar
[versiones y recuperación de Chroma](../../data/chroma-releases/README.md) antes
de elegir un respaldo. El despliegue mediante bastion de esta rama clona
`corpus`, comprueba el commit publicado y restaura Gold A en
`rag_playas_gold_a_cc7bf44b54a9`. Mantiene la colección antigua como histórica.

Registrar explícitamente el commit de código, versión del paquete, perfil de
embeddings y colección de destino. Ejecutar los scripts de despliegue es una
operación distinta de publicarlos. Este camino está preparado en `corpus` y
no modifica `main` ni cambia una aplicación desplegada hasta que se ejecute.

---

## Requisitos previos

- Docker ≥ 24 y Docker Compose v2
- Acceso a los servicios EC2 de ChromaDB y Ollama
- API key de OpenAI (u OpenRouter / Google Gemini como alternativa)
- Archivo de exportación de ChromaDB (`.jsonl.gz`) con los documentos indexados

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

> **Nota:** `NEXT_PUBLIC_API_URL` debe quedar vacío (no `http://localhost:8080` ni `/api`)
> cuando se despliega con Docker Compose. El frontend construye URLs como
> `${API_URL}/api/query`; con valor vacío resultan en `/api/query`, que nginx
> enruta correctamente al backend.

---

## 3. Importar documentos en ChromaDB

Usar la [recuperación de Gold A](../../data/chroma-releases/README.md), con el
restaurador dedicado. No mover el paquete a la raíz de `data/` ni usar el
importador histórico para este despliegue. La restauración conserva los
vectores y no necesita generar embeddings nuevos.

Antes de presentar la aplicación, comprobar conectividad y que la colección
seleccionada contiene la entrega esperada. El índice BM25 vacío ya se maneja
sin `ZeroDivisionError`; eso no hace que una colección vacía sea apta para
responder con evidencia.

```bash
cd /ruta/al/repositorio
python3 -B data/restore_gold_release.py --execute \
  --host <CHROMA_HOST> \
  --port 8000 \
  --ollama-base-url http://<OLLAMA_HOST>:11434 \
  --receipt /ruta/recibo-nuevo.jsonl
```

El restaurador verifica los registros completos; un conteo aislado no basta.
Para comprobar un destino ya preparado, añadir `--verify-only`; nunca se
reescribe una colección existente.

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
curl http://localhost/api/health
```

Todos los servicios deben mostrar `(healthy)` o `Up`.

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
