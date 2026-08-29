.PHONY: install lint format format-check typecheck test test-cov test-integration \
	frontend-lint frontend-typecheck frontend-build quality app frontend clean help

install:  ## Instalar dependencias de todo el workspace (incluidas las de desarrollo)
	uv sync --all-packages --group dev

lint:  ## Verificar errores de estilo y lógica con ruff
	uv run ruff check backend/rag/ tests/ evaluation/ scripts/ utils/

format:  ## Formatear código con ruff
	uv run ruff format backend/rag/ tests/ evaluation/ scripts/ utils/

format-check:  ## Verificar formato sin modificar archivos (usado en CI)
	uv run ruff format --check backend/rag/ tests/ evaluation/ scripts/ utils/

typecheck:  ## Verificar tipos con mypy
	uv run mypy backend/rag/

test:  ## Ejecutar tests unitarios
	uv run pytest tests/unit/

test-cov:  ## Ejecutar tests con informe de cobertura
	uv run pytest tests/unit/ --cov=rag --cov-report=term-missing --cov-report=html

test-integration:  ## Ejecutar tests de integración (requiere servicios activos)
	uv run pytest tests/integration/ -m integration

frontend-lint:  ## Lint del frontend (eslint)
	cd frontend && bun run lint

frontend-typecheck:  ## Chequeo de tipos del frontend (tsc --noEmit)
	cd frontend && bunx tsc --noEmit

frontend-build:  ## Build de producción del frontend
	cd frontend && bun run build

quality:  ## Ejecutar todos los checks de calidad (backend + frontend), sin modificar archivos
	$(MAKE) lint
	$(MAKE) format-check
	$(MAKE) typecheck
	$(MAKE) test
	$(MAKE) frontend-lint
	$(MAKE) frontend-typecheck
	$(MAKE) frontend-build

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
