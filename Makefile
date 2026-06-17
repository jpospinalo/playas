.PHONY: install lint format test test-cov pipeline app frontend clean help

install:  ## Instalar dependencias en ambos subsistemas
	$(MAKE) -C ingesta install
	$(MAKE) -C rag install

lint:  ## Lint en ambos subsistemas
	$(MAKE) -C ingesta lint
	$(MAKE) -C rag lint

format:  ## Formatear código en ambos subsistemas
	$(MAKE) -C ingesta format
	$(MAKE) -C rag format

test:  ## Tests unitarios en ambos subsistemas
	$(MAKE) -C ingesta test
	$(MAKE) -C rag test

test-cov:  ## Tests con cobertura en ambos subsistemas
	$(MAKE) -C ingesta test-cov
	$(MAKE) -C rag test-cov

pipeline:  ## Ejecutar el pipeline de ingesta
	$(MAKE) -C ingesta pipeline

app:  ## Lanzar la API RAG
	$(MAKE) -C rag app

frontend:  ## Lanzar el frontend Next.js
	$(MAKE) -C rag frontend

clean:  ## Limpiar artefactos en ambos subsistemas
	$(MAKE) -C ingesta clean
	$(MAKE) -C rag clean

help:  ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
