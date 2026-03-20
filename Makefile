.PHONY: install lint format typecheck test test-cov pipeline app clean help

install:  ## Instalar dependencias (incluidas las de desarrollo)
	uv sync --dev

lint:  ## Verificar errores de estilo y lógica con ruff
	uv run ruff check src/ tests/ evaluation/

format:  ## Formatear código con ruff
	uv run ruff format src/ tests/ evaluation/

typecheck:  ## Verificar tipos con mypy
	uv run mypy src/

test:  ## Ejecutar tests unitarios
	uv run pytest tests/unit/ -v

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest tests/unit/ --cov=src --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest -m integration -v

pipeline:  ## Ejecutar el pipeline completo de ingesta
	bash scripts/run_pipeline.sh

app:  ## Lanzar la interfaz Gradio
	uv run python -m src.frontend.gradio_app

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
