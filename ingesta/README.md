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

La conversión por lote conserva el tipo explícito del primer directorio bajo
`data/raw/`: por ejemplo, `data/raw/normativa/decreto.pdf` produce
`data/bronze/normativa/decreto.md`, junto con sus assets y sidecars bajo
`data/bronze/normativa/decreto/`. Las subcarpetas adicionales no cambian el
nombre de salida. Cada PDF usa temporales aislados y el conversor se reutiliza.
Si dos keys fuente distintas tienen el mismo destino, el lote se rechaza
antes de descargar, convertir o subir archivos.

Las entradas sin tipo reconocido conservan su salida heredada en la raíz
`data/bronze/`, con advertencia: `loaders` no las recoge automáticamente.
No inferir su tipo ni aplicar la migración heredada indiscriminadamente.
`process_single_pdf()` conserva su default en esa raíz; para una salida
tipificada, pasar `layer_prefix("bronze", doc_type)` como `output_prefix`.
Estas reglas no comprueban objetos ya existentes ni garantizan IDs Gold únicos
entre documentos: verificar el corpus con su responsable antes de indexarlo.

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
- [Corpus local: capas, metadata, registro e inventarios](../data/README.md)
- [Herramienta de inventario offline](docs/SCRIPTS.md#inventario-técnico-local)
- [Desarrollo y controles](../CONTRIBUTING.md)
