# ATLAS — RAG

Sistema agéntico de apoyo para la orientación normativa y jurisprudencial sobre
playas en Colombia (dominio público marítimo-terrestre). Este directorio
contiene el servicio RAG: API FastAPI + agente LangGraph + frontend Next.js +
infraestructura ECS Fargate.

Para la ingestión de documentos (PDF → Markdown → chunks enriquecidos →
ChromaDB) ver `../ingesta/`. Ambos son proyectos `uv`/`bun` independientes;
ver el `CLAUDE.md` en la raíz del repositorio para el mapa completo.

---

## Empezar aquí

```bash
make install        # uv sync --all-packages --group dev (workspace: backend/)
make test            # pytest tests/unit/ -v (486 pruebas)
make lint             # ruff check backend/rag/ tests/ evaluation/ scripts/ utils/
make app              # uvicorn rag.api.main:app --reload --port 8080  (se ejecuta desde rag/)
```

```bash
cd frontend
bun install
bun dev              # http://localhost:3000
```

Requiere `rag/.env` (ver `.env.example`) con credenciales de ChromaDB, Ollama,
al menos un proveedor LLM (OpenAI/OpenRouter/Gemini), `JWT_SECRET_KEY` y
`POSTGRES_PASSWORD` (o `DATABASE_URL` para SQLite local). Ver
[`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) para el detalle completo.

## Documentación

| Documento | Contenido |
|---|---|
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Arquitectura real del sistema: agente LangGraph, retriever híbrido, memoria, streaming SSE, auth JWT+SQL |
| [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) | Despliegue con Docker Compose, variables de entorno, solución de problemas |
| [`docs/PRODUCT.md`](docs/PRODUCT.md) | Producto: usuarios, propósito, personalidad de marca |
| [`docs/DESIGN.md`](docs/DESIGN.md) | Especificación prescriptiva del sistema de diseño ("Bioluminiscencia"): color, tipografía, componentes — el objetivo a implementar |
| [`docs/SCRIPTS.md`](docs/SCRIPTS.md) | Scripts operacionales: despliegue, SageMaker, utilidades ChromaDB |
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
├── evaluation/       # Scripts de evaluación RAGAS
├── scripts/          # Ops one-offs (Docker install, SageMaker, pruebas de carga)
├── utils/            # CLI: conteo/limpieza ChromaDB, listado de modelos Gemini
├── tests/            # unit/ + integration/
└── docker-compose.yml
```
