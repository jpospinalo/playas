.PHONY: install lint format typecheck test test-cov test-integration app frontend clean help

ROOT := $(shell git rev-parse --show-toplevel)

install:  ## Instalar dependencias (incluidas las de desarrollo)
	cd $(ROOT) && uv sync --group dev

lint:  ## Verificar errores de estilo y lógica con ruff
	cd $(ROOT) && uv run ruff check rag/backend/rag/ rag/tests/ rag/evaluation/

format:  ## Formatear código con ruff
	cd $(ROOT) && uv run ruff format rag/backend/rag/ rag/tests/ rag/evaluation/

typecheck:  ## Verificar tipos con mypy
	cd $(ROOT) && uv run mypy rag/backend/rag/

test:  ## Ejecutar tests unitarios
	cd $(ROOT) && uv run pytest rag/tests/unit/ -v

test-cov:  ## Ejecutar tests con informe de cobertura
	cd $(ROOT) && uv run pytest rag/tests/unit/ --cov=rag --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	cd $(ROOT) && uv run pytest rag/tests/integration/ -m integration -v

app:  ## Lanzar la API FastAPI
	cd $(ROOT) && uv run uvicorn rag.api.main:app --reload --port 8080

frontend:  ## Lanzar el frontend Next.js
	cd $(ROOT)/rag/frontend && bun run dev

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
