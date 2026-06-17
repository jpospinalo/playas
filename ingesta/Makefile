.PHONY: install lint format typecheck test test-cov test-integration pipeline bucket-backup clean help

ROOT := $(shell git rev-parse --show-toplevel)

install:  ## Instalar dependencias (incluidas las de desarrollo)
	cd $(ROOT) && uv sync --group dev

lint:  ## Verificar errores de estilo y lógica con ruff
	cd $(ROOT) && uv run ruff check ingesta/ingest/ ingesta/tests/

format:  ## Formatear código con ruff
	cd $(ROOT) && uv run ruff format ingesta/ingest/ ingesta/tests/

typecheck:  ## Verificar tipos con mypy
	cd $(ROOT) && uv run mypy ingesta/ingest/

test:  ## Ejecutar tests unitarios
	cd $(ROOT) && uv run pytest ingesta/tests/unit/ -v

test-cov:  ## Ejecutar tests con informe de cobertura
	cd $(ROOT) && uv run pytest ingesta/tests/unit/ --cov=ingest --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	cd $(ROOT) && uv run pytest ingesta/tests/integration/ -m integration -v

pipeline:  ## Ejecutar el pipeline completo de ingesta
	bash $(ROOT)/ingesta/scripts/run_pipeline.sh

bucket-backup:  ## Descargar todos los objetos del bucket S3
	cd $(ROOT) && uv run python -m utils.bucket_backup

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
