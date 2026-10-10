# Ingesta documental

Proyecto Python independiente que convierte PDFs a Markdown con Docling,
secciona jurisprudencia y normativa, y genera chunks enriquecidos para el RAG.
Sus operaciones leen y escriben S3; no cargan directamente el corpus local
de `../data/documents/`.

## Entorno y comprobaciones

Desde `ingesta/`, con Python 3.12 y `uv`:

```bash
uv sync --frozen --group dev --python 3.12
UV_FROZEN=1 make lint
UV_FROZEN=1 make format-check
UV_FROZEN=1 make test
UV_FROZEN=1 make test-integration
```

Las pruebas de integración son contratos offline entre seccionado y chunking,
no una ejecución de extremo a extremo contra S3, OCR o LLM. Algunas pruebas
unitarias sobre archivos normativos locales se omiten si sus fixtures no están
disponibles. No interpretar un skip como validación de esos documentos.

Para operaciones reales, completar `ingesta/.env` a partir de `.env.example`
con bucket, credenciales AWS y proveedor LLM. No versionar secretos. Ver
[scripts y efectos](docs/SCRIPTS.md) antes de ejecutar pipelines o migraciones.

## Organización

- `ingest/pdf_to_md/`: conversión OCR, limpieza, imágenes y reporte de calidad.
- `ingest/loaders.py`: normalización, metadata CSV y despacho por tipo.
- `ingest/sections.py` y `sections_normativa.py`: estrategias de seccionado.
- `ingest/splitter_and_enrich.py`: fragmentación y enriquecimiento LLM.
- `ingest/s3_client.py`: acceso al almacenamiento.
- `scripts/`: pipelines de tres etapas y de cinco etapas con indexación/API.
- `utils/`: backup y mantenimiento de corpus heredados; no son etapas normales.
- `infrastructure/`: bucket S3. Las EC2 pertenecen a `../vector-infraestructura/`.

## Contrato actual y límites operacionales

`loaders` lee `data/bronze/<doc_type>/` y escribe
`data/silver/<doc_type>/`; el enriquecedor escribe `data/gold/<doc_type>/`.
Los tipos admitidos son `jurisprudencia` y `normativa`.

La conversión PDF actual escribe en la raíz `data/bronze/`, sin conservar el
subprefijo de tipo. Esos archivos no son recogidos automáticamente por
`loaders`. No ejecutar el pipeline completo suponiendo que esta transición ya
está resuelta; requiere una corrección funcional y pruebas antes de procesar
nuevos documentos. No usar la migración heredada para clasificar indiscriminadamente
todos los archivos nuevos como jurisprudencia.

Si falla un enriquecimiento, el chunk se guarda sin metadata de IA. Con
`skip_existing=True` no se vuelve a procesar el archivo Gold existente. Revisar
los errores de la corrida antes de considerar completa la capa; cualquier
reprocesamiento o reindexación necesita autorización del responsable del corpus.

La limpieza mantiene una secuencia fija: aunque la API se denomina
`adaptive_cleanup`, su parámetro `profile` no selecciona pasos actualmente.
No cambiar las reglas de texto o chunking como parte de una limpieza de código.

## Documentación

- [Scripts y mantenimiento](docs/SCRIPTS.md)
- [Secciones documentales](docs/DOCUMENT_SECTIONS.md)
- [Catálogo de sentencias](docs/archivos-indexados.md), no inventario vivo de ChromaDB
- [Datos versionados](../data/README.md)
- [Desarrollo y controles](../CONTRIBUTING.md)
