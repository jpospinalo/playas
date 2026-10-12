# Datos del proyecto

Este directorio reúne fuentes y artefactos de datos; no es un paquete Python
ni la base de datos que consulta directamente la API.

| Ruta | Uso |
|---|---|
| `documents/raw/` | Documentos fuente del corpus versionado |
| `documents/bronze/` | Markdown, imágenes y sidecars de procesamiento |
| `documents/silver/` | Documentos seccionados en JSONL |
| `documents/gold/` | Chunks y metadata de enriquecimiento en JSONL |
| `*.jsonl.gz` | Export de ChromaDB, con registros y embeddings |
| `import_to_chromadb.py` | Herramienta de importación del export, ejecutada con el entorno de `rag/` |
| `seed_users.sql` | Datos semilla utilizados por los scripts de despliegue |

`documents/` es una copia versionada del corpus incorporada en el commit
`90d0628`. Esta referencia indica su procedencia en Git, no certifica que
coincida con S3 ni con el índice de un despliegue actual. El pipeline de
[ingesta](../ingesta/README.md) trabaja con prefijos S3 `data/<capa>/<tipo>/`,
no con `data/documents/` local.

## Inventario técnico reproducible

- [Tabla de fuentes y hallazgos](CORPUS_CATALOG.md): vista generada para revisión.
- [Catálogo JSON](corpus-catalog.json): evidencia por archivo, hashes, capas,
  metadatos descriptivos observados y comparación con el backup indicado.
- [Catálogo descriptivo de nueve sentencias](../ingesta/docs/archivos-indexados.md):
  conserva su propósito y metadatos jurídicos; no es el inventario técnico.

Los dos artefactos técnicos se versionan, pero son **derivados, no fuentes de verdad editables**.
No editarlos manualmente. El formato JSON tiene `schema_version: 1`; las rutas
son relativas al repositorio. No se guardan embeddings, textos de chunks,
credenciales ni la dirección del servidor del export. La fecha y colección
proceden del manifest del backup; no se inventa una fecha del índice actual.

Desde `ingesta/`, usando su entorno Python 3.12 ya instalado:

```bash
# Inspeccionar sin escribir (el argumento del export es relativo al repositorio).
.venv/bin/python -m utils.audit_local_corpus --export data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz

# Verificar que ambos artefactos coinciden con las entradas actuales, sin escribir.
.venv/bin/python -m utils.audit_local_corpus --export data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz --check

# Regenerar solamente los dos artefactos técnicos, sin modificar el corpus.
.venv/bin/python -m utils.audit_local_corpus --export data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz --write
```

La herramienta usa solo la biblioteca estándar. También se puede ejecutar por
ruta desde otra carpeta; los argumentos relativos se resuelven respecto del
repositorio, no del directorio de ejecución. No selecciona backups por fecha
ni se conecta a S3, ChromaDB, Ollama o un LLM. Sin `--export`, la comparación
del índice queda explícitamente sin comprobar.

Salida `0`: inventario generado/verificado sin errores técnicos; **puede tener
advertencias**. Salida `1`: errores técnicos registrados o artefactos ausentes/
desactualizados en `--check`. Salida `2`: no se completó la operación (lectura,
rutas inseguras, entradas cambiantes o intento de sobrescribir archivos ajenos).
`--write` puede producir un informe de errores; leer su resumen antes de usarlo.

### Alcance y límites de las comprobaciones

- Asociar capas por tipo y nombre normalizado Unicode solo cuando la relación
  es inequívoca. Se conservan nombres, rutas y todos los IDs originales.
- Identificar archivos fuente idénticos por SHA-256; no fusionar versiones,
  extractos ni documentos distintos por similitud de nombres.
- Leer JSONL/gzip secuencialmente, comparar IDs y hashes de texto/metadata, y
  comprobar que las entradas no cambien durante la lectura. Los embeddings no
  se retienen; sus dimensiones no certifican el modelo ni su calidad.
  Los IDs reconocibles repetidos se detectan incluso cuando uno de sus registros
  es inválido. En Gold se excluyen de la comparación por ser ambiguos; en el
  export se registra el error y no se compara la aparición repetida. Los registros
  del export con `source`/`doc_type` inválidos tampoco se comparan.
- Al comparar metadata, considerar la omisión de `None`, la serialización de
  listas/objetos y el campo derivado `keywords_str` observados en
  `rag/backend/rag/core/vectorstore.py`. Si cambia ese contrato, revisar esta
  comparación offline; nunca resolver divergencias reemplazando datos automáticamente.
  Se normalizan `keywords`/`entities` y los campos que eran listas/objetos en
  Gold, conservando el orden de las listas. El resto del texto se compara sin
  reinterpretar referencias jurídicas como números u objetos JSON.
- Verificar firma PDF básica, UTF-8/JSON y referencias inline a imágenes de
  Bronze. No se hace OCR, renderizado, validación completa de PDF, extracción
  del número de páginas ni comprobación de enlaces externos o de referencias
  Markdown indirectas. Se reconocen destinos inline simples, entre `<...>` o
  URL-encoded, con títulos delimitados por comillas o paréntesis simples. Una
  cola de palabras sin delimitar no se considera un título. Para rutas locales
  heredadas con espacios, una sola línea, sin comillas ni delimitadores ambiguos
  y extensión `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.tif`, `.tiff` o
  `.svg`, se comprueba la ruta completa y se registra `unescaped_image_path`.
  Esta recuperación no convierte la referencia en Markdown válido. La sintaxis
  no soportada, incluidos destinos sin delimitar con paréntesis anidados, se
  registra con ruta y línea como `unsupported_image_syntax`, sin inferir una
  ausencia parcial. No se descargan URLs ni se siguen symlinks, incluso en
  componentes intermedios; se rechazan destinos fuera del corpus. El detector
  no es un parser Markdown general ni comprueba el renderizado del documento.
  Una sección Silver vacía es advertencia; un chunk Gold vacío o un archivo Gold
  sin registros (incluido uno con solo espacios o saltos de línea) es error.
- Un nombre Unicode descompuesto o de más de 180 bytes es una advertencia de
  portabilidad, no evidencia de corrupción. Las posibles erratas e identidades
  jurídicas no se corrigen por inferencia.

Presencia en un backup **no demuestra presencia en el índice desplegado hoy**.
Vigencia jurídica, cobertura completa, fidelidad OCR y correspondencia con S3
quedan sin validar. El JSON contiene observaciones de Gold, no una nueva
aprobación jurídica. Los hallazgos no autorizan renombrados, borrados,
reprocesamientos ni reindexaciones: esas reparaciones requieren un plan separado.

## Registro descriptivo de curación

[corpus-curation.json](corpus-curation.json) es un registro de edición humana
revisable, separado del catálogo técnico generado. Relaciona las rutas y hashes
de las fuentes con rótulos propuestos, identidad, selección declarada y
evidencias. Las identidades pueden seguir provisionales; los conflictos no se
resuelven automáticamente ni la selección declarada equivale a aprobación.

Ni la ingesta ni el RAG consumen este registro. Editarlo no renombra documentos,
no cambia los títulos o metadatos de las capas y no actualiza el índice. El
respaldo local no certifica vigencia, fidelidad ni cobertura completa. Los
contratos offline comprueban estructura y asociación con el catálogo, no la
verdad jurídica de las evidencias.

## Conservación y actualización

- No borrar fuentes, exports o datos semilla por su extensión o antigüedad.
- Antes de actualizar el corpus, identificar origen, fecha, responsable y
  relación con la versión desplegada. No confundir cambios en Git con una
  actualización del índice ChromaDB.
- No ejecutar importaciones, migraciones ni reindexaciones para validar cambios
  documentales. Requieren autorización y revisión del destino.
- El importador exige `--batch-size > 0`; un tamaño inválido termina con código
  `2` antes de conectar. Si falla un lote, continúa con los siguientes, muestra
  el resumen y termina con código `1`. Sin errores termina con código `0`,
  también con un export vacío. Los registros ya escritos no se revierten:
  revisar el resumen y el destino antes de autorizar una recuperación.
- Los backups PostgreSQL se generan en `data/backups/`, fuera de Git. No subir
  dumps, credenciales ni respuestas de usuarios al repositorio.

## Ground truth

La evaluación usa el JSON
[`legal-ground-truth-v0.1`](../rag/evaluation/data/legal-ground-truth-v0.1.json),
con la anotación **Esperando validación final**. El archivo
[`legal-ground-truth-v0.2.xlsx`](../rag/evaluation/data/legal-ground-truth-v0.2.xlsx)
es una fuente adicional versionada, no sustituye automáticamente ese JSON ni
certifica una nueva validación jurídica. No cambiar el banco activo sin un
proceso explícito de selección, validación y versionado.
