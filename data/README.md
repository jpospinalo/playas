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

## Conservación y actualización

- No borrar fuentes, exports o datos semilla por su extensión o antigüedad.
- Antes de actualizar el corpus, identificar origen, fecha, responsable y
  relación con la versión desplegada. No confundir cambios en Git con una
  actualización del índice ChromaDB.
- No ejecutar importaciones, migraciones ni reindexaciones para validar cambios
  documentales. Requieren autorización y revisión del destino.
- El importador actual informa errores por lote, pero no devuelve una salida
  fallida al terminar con importación parcial. Revisar el resumen, no solo el
  mensaje de éxito del script que lo llama; esta limitación requiere corrección
  funcional antes de confiar en una importación automatizada.
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
