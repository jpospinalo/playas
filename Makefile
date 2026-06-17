.PHONY: install lint format typecheck test test-cov test-integration pipeline app frontend clean bucket-backup help

install:  ## Instalar dependencias (incluidas las de desarrollo)
	uv sync --group dev

lint:  ## Verificar errores de estilo y lógica con ruff (ambos subsistemas)
	uv run ruff check rag/backend/rag/ ingesta/ingest/ rag/tests/ ingesta/tests/ rag/evaluation/

format:  ## Formatear código con ruff (ambos subsistemas)
	uv run ruff format rag/backend/rag/ ingesta/ingest/ rag/tests/ ingesta/tests/ rag/evaluation/

typecheck:  ## Verificar tipos con mypy (ambos subsistemas)
	uv run mypy rag/backend/rag/ ingesta/ingest/

test:  ## Ejecutar tests unitarios (ambos subsistemas)
	uv run pytest ingesta/tests/unit/ rag/tests/unit/ -v

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest ingesta/tests/unit/ rag/tests/unit/ --cov=rag --cov=ingest --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest -m integration -v

pipeline:  ## Ejecutar el pipeline completo de ingesta
	bash ingesta/scripts/run_pipeline.sh

app:  ## Lanzar la API FastAPI
	uv run uvicorn rag.api.main:app --reload --port 8080

frontend:  ## Lanzar el frontend Next.js
	cd rag/frontend && bun run dev

bucket-backup:  ## Descargar todos los objetos del bucket S3 a bucket-backup-<fecha-hora>/
	uv run python -m utils.bucket_backup

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
