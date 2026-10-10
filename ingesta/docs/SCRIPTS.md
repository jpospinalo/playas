# Scripts operacionales — Ingesta

Los comandos de esta página se ejecutan desde `ingesta/`, salvo donde se
indica otro directorio. Leer [el contrato y límites del pipeline](../README.md)
antes de procesar documentos. No ejecutar estos scripts para validar una
limpieza de código: pueden escribir datos y consumir servicios externos.

## Pipelines

`scripts/run_pipeline.sh` ejecuta cinco pasos y termina con una API de
desarrollo (`--reload`, puerto 8080); no sustituye el despliegue ECS:

| Paso | Entorno | Módulo | Efecto |
| --- | --- | --- | --- |
| 1/5 | ingesta | `ingest.pdf_to_md` | Lee PDFs de S3 y escribe Markdown Bronze |
| 2/5 | ingesta | `ingest.loaders` | Secciona Bronze por tipo y escribe Silver en S3 |
| 3/5 | ingesta | `ingest.splitter_and_enrich` | Divide texto por caracteres, enriquece con LLM y escribe Gold en S3 |
| 4/5 | rag | `rag.core.vectorstore` | Genera embeddings e indexa Gold en ChromaDB |
| 5/5 | rag | `uvicorn rag.api.main:app` | Inicia la API local |

El splitter utiliza por defecto 1000 **caracteres**, con solapamiento de 200;
no son límites de tokens. Cada entorno tiene su propio lock y dependencias.

```bash
# Desde ingesta/, solo si el procesamiento/indexación está autorizado:
make pipeline

# Solo pasos 1–3; también escribe S3 y utiliza OCR/LLM:
bash scripts/run_data_pipeline.sh
```

Ambos wrappers resuelven sus directorios a partir de la ubicación del script.
Desde la raíz del repositorio, las rutas equivalentes son
`bash ingesta/scripts/run_pipeline.sh` y
`bash ingesta/scripts/run_data_pipeline.sh`.

La conversión por lote escribe en `data/bronze/<doc_type>/` cuando el primer
directorio bajo `data/raw/` es exactamente `jurisprudencia` o `normativa`.
Markdown y sidecars conservan el nombre del PDF; subcarpetas adicionales no
cambian ese nombre. Los destinos coincidentes de fuentes distintas se rechazan
antes de procesar el lote, y los temporales de cada PDF están aislados.

**Límite heredado:** las entradas sin tipo reconocido siguen escribiéndose en
`data/bronze/`, con advertencia; loaders no las recoge. `process_single_pdf()`
también conserva ese default, salvo que se pase un prefijo explícito.
No asumir que estas comprobaciones validan los IDs Gold ni el corpus existente.
Tampoco asumir que un Gold existente garantiza enriquecimiento completo:
los errores de LLM y la política de omitir existentes deben revisarse.

## Infraestructura: responsabilidades

- `ingesta/infrastructure/`: bucket S3, no instancias ChromaDB/Ollama.
- [vector-infraestructura](../../vector-infraestructura/README.md):
  Terraform y scripts de las EC2 de ChromaDB y Ollama.
- [RAG](../../rag/README.md): servicio/API/frontend.
- [Guía operacional de la raíz](../../README.md): despliegue y arranque/apagado.

Los antiguos nombres `ingesta/scripts/ec2_chroma_db.sh` y
`ingesta/scripts/ec2_ollama_embeddings.sh` no existen en este checkout.
No son comandos de aprovisionamiento disponibles. No aplicar Terraform ni
operar AWS como parte de pruebas offline o mantenimiento documental.

## Utilidades de mantenimiento

No son etapas habituales del pipeline. Antes de escribir o mover datos:
confirmar colección/bucket, respaldo y clasificación con su responsable.
Un dry-run puede consultar servicios reales y necesita permisos de lectura.

### Backup S3

```bash
make bucket-backup
```

`utils/bucket_backup.py` descarga el bucket a una carpeta local con timestamp.
No incorpora automáticamente el backup al corpus versionado.

### Migración de prefijos heredados

```bash
uv run python -m utils.migrate_doc_type
```

Dry-run por defecto. Propone mover objetos sin subcarpeta de tipo a
`data/<capa>/jurisprudencia/`; no determina jurídicamente su tipo.
Con `--apply` realiza copia y borrado en S3. No aplicarlo a un corpus mixto
ni utilizarlo para resolver automáticamente el límite Bronze descrito arriba.

### Backfill de metadata en S3

```bash
uv run python -m utils.backfill_doc_type_s3
```

Dry-run por defecto sobre Silver y Gold de jurisprudencia. Permite
`--doc-type normativa` y `--layers silver` o `--layers gold`.
Con `--apply` reescribe los JSONL en S3, conservando los demás metadatos.

### Backfill de metadata en ChromaDB

`utils/backfill_doc_type.py` necesita `chromadb`, que pertenece al entorno
`rag/`, no al lock de ingesta. Desde `rag/`, ejecutar el archivo con ese
entorno, proporcionando host, puerto y colección reales explícitamente:

```bash
# Plantilla de dry-run; reemplazar host y colección antes de ejecutar.
CHROMA_HOST=host-real CHROMA_PORT=8000 uv run python ../ingesta/utils/backfill_doc_type.py --collection coleccion-real
```

No suponer que este script carga `rag/.env`: utiliza `load_dotenv()`
según la ubicación del archivo. Las variables explícitas del entorno evitan
esa ambigüedad. Por defecto asigna jurisprudencia a chunks sin `doc_type`;
`--doc-type` permite indicar el tipo. Con `--apply` actualiza metadata
en ChromaDB, sin recalcular embeddings, solo con autorización.

## Validación sin efectos externos

`make test-integration` ejecuta contratos offline entre seccionado y
chunking con textos sintéticos. No prueba OCR, S3, enriquecimiento LLM,
indexación ni despliegue. Ver [controles de desarrollo](../../CONTRIBUTING.md).
