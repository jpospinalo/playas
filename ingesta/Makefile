.PHONY: install lint format typecheck test test-cov test-integration pipeline bucket-backup clean help

install:  ## Instalar dependencias (incluidas las de desarrollo)
	uv sync --group dev

lint:  ## Verificar errores de estilo y lógica con ruff
	uv run ruff check ingest/ tests/

format:  ## Formatear código con ruff
	uv run ruff format ingest/ tests/

typecheck:  ## Verificar tipos con mypy
	uv run mypy ingest/

test:  ## Ejecutar tests unitarios
	uv run pytest tests/unit/

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest tests/unit/ --cov=ingest --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest tests/integration/ -m integration

pipeline:  ## Ejecutar el pipeline completo de ingesta
	bash scripts/run_pipeline.sh

bucket-backup:  ## Descargar todos los objetos del bucket S3
	PYTHONPATH=. uv run python -m utils.bucket_backup

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
