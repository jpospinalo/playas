.PHONY: install lint format typecheck test test-cov test-integration pipeline app frontend clean bucket-backup help

# El paquete `rag` vive en rag/backend/rag; se expone vía PYTHONPATH sin instalarlo.
RAG_PY := PYTHONPATH=rag/backend

install:  ## Instalar dependencias (incluidas las de desarrollo)
	uv sync --group dev

lint:  ## Verificar errores de estilo y lógica con ruff
	uv run ruff check rag/backend/rag ingest tests

format:  ## Formatear código con ruff
	uv run ruff format rag/backend/rag ingest tests

typecheck:  ## Verificar tipos con mypy
	uv run mypy rag/backend/rag ingest

test:  ## Ejecutar tests unitarios
	uv run pytest tests/unit/ -v

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest tests/unit/ --cov=rag --cov=ingest --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest -m integration -v

pipeline:  ## Pipeline de datos (ingest: bronze→silver→gold) + indexar en ChromaDB
	bash ingest/scripts/run_pipeline.sh
	$(RAG_PY) uv run python -m rag.core.vectorstore

app:  ## Lanzar la API FastAPI
	$(RAG_PY) uv run uvicorn rag.api.main:app --reload --port 8080

frontend:  ## Lanzar el frontend Next.js
	cd rag/frontend && bun run dev

bucket-backup:  ## Descargar todos los objetos del bucket S3 a bucket-backup-<fecha-hora>/
	uv run python -m ingest.tools.bucket_backup

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
