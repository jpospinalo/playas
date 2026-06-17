# Infraestructura RAG

El despliegue del subsistema RAG (backend + frontend + proxy) se gestiona mediante Docker Compose.

## Despliegue con Docker Compose

```bash
# Desde el directorio rag/
docker compose up -d --build   # construir e iniciar todos los servicios
docker compose logs -f         # ver logs en tiempo real
docker compose down            # detener
```

### Servicios

| Servicio | Puerto interno | Descripción |
|----------|---------------|-------------|
| `backend` | 8080 | FastAPI + uvicorn |
| `frontend` | 3000 | Next.js (producción) |
| `nginx` | 80 (público) | Reverse proxy, SSE-aware |

### Requisitos previos

- Archivo `rag/.env` con las variables de entorno (ver `rag/.env.example`)
- Archivo `rag/firebase-service-account.json` (gitignored, descargarlo desde Firebase Console)
- Servicios externos activos: ChromaDB y Ollama (provisionar con `ingesta/infrastructure/`)

## Infraestructura de servicios compartidos

Los servicios de datos (S3, ChromaDB EC2, Ollama EC2) se provisionan con Terraform desde `ingesta/infrastructure/`.
