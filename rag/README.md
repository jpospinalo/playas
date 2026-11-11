# ATLAS — RAG

Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre
playas en Colombia (dominio público marítimo-terrestre). Este directorio
contiene el servicio RAG: API FastAPI + agente LangGraph + frontend Next.js +
infraestructura ECS Fargate.

Para la ingestión de documentos (PDF → Markdown → chunks enriquecidos →
ChromaDB) ver [`../ingesta/README.md`](../ingesta/README.md). Son proyectos
Python `uv` independientes; Bun se utiliza únicamente en el frontend del
workspace RAG. Ver el [`README.md` raíz](../README.md) para el mapa completo.

---

Para consultar o evaluar la colección, seguir la
[guía de uso de Gold A](docs/DESPLIEGUE.md#usar-gold-a-en-atlas).

## Empezar aquí

```bash
make install        # uv sync --all-packages --group dev (workspace: backend/)
make test            # pytest tests/unit/ -v
make lint             # ruff check backend/rag/ tests/ evaluation/ scripts/ utils/
make app              # uvicorn rag.api.main:app --app-dir backend --reload --port 8080 (desde rag/)
```

```bash
cd frontend
bun install
bun dev              # http://localhost:3000
```

Configurar `rag/.env` a partir de `.env.example` con los endpoints de ChromaDB
y Ollama, las credenciales de un proveedor LLM, `JWT_SECRET_KEY` y los datos
del entorno de base de datos. Ver
[`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) para el detalle completo.

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Arquitectura real del sistema: agente LangGraph, retriever híbrido, memoria, streaming SSE, auth JWT+SQL |
| [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) | Uso de Gold A, conexión del RAG y despliegue con Docker Compose |
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | Producto: usuarios, propósito, personalidad de marca |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Especificación prescriptiva del sistema de diseño ("Bioluminiscencia"): color, tipografía, componentes — el objetivo a implementar |
| [`docs/SCRIPTS.md`](docs/SCRIPTS.md) | Scripts operacionales: despliegue, SageMaker, utilidades ChromaDB, [evaluación del RAG con RAGAS](docs/SCRIPTS.md#evaluación-del-rag) |
| [`evaluation/README.md`](evaluation/README.md) | Evaluación offline con RAGAS: módulos, resultados sobre el ground truth jurídico v0.2, informe para el equipo jurídico y registro de evaluaciones |
| [`docs/SMOKE_TESTS.md`](docs/SMOKE_TESTS.md) | Pruebas de humo contra un despliegue real |
| [`frontend/README.md`](frontend/README.md) | Inventario del frontend tal como está implementado: stack, rutas, componentes, hooks |
| [`infrastructure/README.md`](infrastructure/README.md) | Infraestructura ECS Fargate (Terraform) |

## Estructura

```
rag/
├── backend/rag/     # Paquete Python: API + agente (ver ARCHITECTURE.md)
├── frontend/        # Next.js 16 / React 19 (bun)
├── infrastructure/  # Terraform: ECS Fargate, ALB, ECR, EFS
├── docker/           # Dockerfiles + nginx.conf
├── evaluation/       # Evaluación RAGAS + diagnósticos offline reproducibles (RRF, cobertura de citas)
├── scripts/          # Ops one-offs (Docker install, SageMaker, pruebas de carga)
├── utils/            # CLI: conteo/limpieza ChromaDB, listado de modelos Gemini
├── tests/            # unit/ + integration/
└── docker-compose.yml
```
