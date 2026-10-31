# Corpus y datos del proyecto

El corpus local versionado reúne documentos normativos y jurisprudenciales
sobre playas. Sus capas están en `documents/`; su presencia aquí no acredita
que coincidan con S3 o con el índice desplegado del RAG.

| Capa | Contenido |
|---|---|
| `documents/raw/` | Fuentes originales locales, incluidos extractos y copias Markdown |
| `documents/bronze/` | Texto Markdown, imágenes y sidecars de procesamiento |
| `documents/silver/` | Secciones documentales en JSONL |
| `documents/gold/` | Fragmentos y metadata de enriquecimiento en JSONL |

## Uso de Gold

Cada línea contiene `page_content` y `metadata`. Los campos dependen del tipo
y de la evidencia disponible:

| Campo | Interpretación |
|---|---|
| `chunk_id` | Identificador del fragmento; se conserva entre reparaciones |
| `source`, `title`, `doc_type` | Referencia de origen, título y tipo documental |
| `section_index`, `chunk_index` y campos de sección/artículo | Ubicación dentro de la representación procesada |
| `Corporación`, `Magistrado ponente`, `Radicado` | Identidad descriptiva de jurisprudencia, cuando está respaldada |
| `norma` | Identidad normativa incorporada donde hay respaldo suficiente |
| `summary`, `keywords`, `entities` | Resumen, términos y menciones descriptivas para recuperación |

Los IDs e índices son históricos y pueden tener huecos; no regenerarlos desde
la posición actual de una fila. El ponente identifica al documento principal,
no necesariamente a la voz de cada cita, aclaración o salvamento. Los resúmenes
y entidades son enriquecimiento: para sustentar una respuesta, cotejar el
pasaje documental y su fuente.

## Registro descriptivo de curación

[corpus-curation.json](corpus-curation.json) relaciona cada fuente con su ruta,
huella, rótulo descriptivo, identidad, selección y evidencias. Sus rótulos son
propuestos y las identidades pueden seguir provisionales; no renombra archivos
ni es consumido directamente por la ingesta o el RAG.

Las notas fechadas conservan procedencia y decisiones. Deben leerse en conjunto
y en orden: una adición posterior puede cerrar o precisar una observación
anterior. Una nota antigua aislada no representa necesariamente un pendiente
actual. No eliminar esa trazabilidad ni copiar sus afirmaciones al corpus sin
un mapa de cambio sustentado.

## Inventario técnico reproducible

- [CORPUS_CATALOG.md](CORPUS_CATALOG.md): tabla de fuentes, capas y hallazgos.
- [corpus-catalog.json](corpus-catalog.json): hashes, asociaciones, metadata
  observada y comparación con el backup indicado.

Ambos son artefactos generados del mismo inventario, con `schema_version: 1`.
No editarlos manualmente. Los recuentos vigentes se consultan allí para evitar
mantener cifras duplicadas en otros documentos.

La herramienta local, sus comandos y límites están en
[Inventario técnico local](../ingesta/docs/SCRIPTS.md#inventario-técnico-local).
Un aviso no equivale a un error ni autoriza una reparación automática.

## Entrega y reservas

Para una entrega coherente, compartir desde una misma versión del repositorio
`documents/`, este README, el registro de curación y los dos inventarios.
Identificar la versión y comprobar sus huellas; no sustituirlos por un paquete
o un backup de una fecha anterior. Los planes y reportes de ejecución quedan
fuera de la documentación del corpus.

El registro conserva las reservas de identidad, procedencia y selección. Hay
extractos, extensiones sin verificar, referencias discutidas y campos ausentes
o vacíos deliberados. No completar metadata por cuota, ampliar una selección
ni deducir vigencia jurídica a partir de un título. La curación técnica y el
enriquecimiento no certifican cobertura literal integral ni calidad medida de
las respuestas del RAG.

## Conservación y actualización

- Preservar originales, IDs, permisos y campos ajenos a cada reparación.
- Sustentar cada cambio con un mapa literal, evidencia local y verificación
  offline antes de actualizar el registro y, si corresponde, los inventarios.
- Mantener separados el corpus local, el export histórico de ChromaDB y el
  índice desplegado. Este último se actualiza mediante una operación distinta.

El pipeline de [ingesta](../ingesta/README.md) opera sobre prefijos S3
`data/<capa>/<tipo>/`, no sobre `data/documents/`. No ejecutar pipelines,
importaciones o reindexaciones para comprobar una edición documental.

También hay archivos operacionales en este directorio: los exports `*.jsonl.gz`,
el [importador de ChromaDB](import_to_chromadb.py) y `seed_users.sql`.
No forman parte de las capas documentales. Consultar
[su operación y efectos](../ingesta/docs/SCRIPTS.md) antes de utilizarlos.
Los dumps PostgreSQL de `backups/` son locales y no se versionan.

## Ground truth

El banco activo es [legal-ground-truth-v0.1.json](../rag/evaluation/data/legal-ground-truth-v0.1.json),
**Esperando validación final**. El Excel
[legal-ground-truth-v0.2.xlsx](../rag/evaluation/data/legal-ground-truth-v0.2.xlsx)
es una fuente adicional y no sustituye automáticamente el JSON. Los contratos
y comandos de evaluación están en [Scripts del RAG](../rag/docs/SCRIPTS.md).
