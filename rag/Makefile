.PHONY: install lint format typecheck test test-cov test-integration app frontend clean help

install:  ## Instalar dependencias (incluidas las de desarrollo)
	uv sync --group dev

lint:  ## Verificar errores de estilo y lógica con ruff
	uv run ruff check backend/rag/ tests/ evaluation/

format:  ## Formatear código con ruff
	uv run ruff format backend/rag/ tests/ evaluation/

typecheck:  ## Verificar tipos con mypy
	uv run mypy backend/rag/

test:  ## Ejecutar tests unitarios
	uv run pytest tests/unit/

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest tests/unit/ --cov=rag --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest tests/integration/ -m integration

app:  ## Lanzar la API FastAPI
	uv run uvicorn rag.api.main:app --reload --port 8080

frontend:  ## Lanzar el frontend Next.js
	cd frontend && bun run dev

clean:  ## Eliminar artefactos generados
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .pytest_cache -exec rm -rf {} +
	find . -type d -name htmlcov -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name ".coverage" -delete

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
