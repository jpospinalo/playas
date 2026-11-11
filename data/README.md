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

## Campos de Gold

Cada línea JSONL contiene el cuerpo del fragmento en `page_content` y sus
metadatos en `metadata`. El seccionado aporta la estructura documental y el
fragmentador conserva esa metadata y agrega los identificadores e índices
de cada fragmento.

| Campos | Función |
|---|---|
| `chunk_id` | Identificador estable del fragmento y clave de cotejo con la colección |
| `source`, `title`, `doc_type` | Referencia de origen, título documental y tipo (`jurisprudencia` o `normativa`) |
| `section_index`, `section_name`, `chunk_index`, `total_chunks_in_section` | Localización en la representación procesada |
| `section_heading`, `Corporación`, `Magistrado ponente`, `Radicado` | Encabezado e identificación de la pieza jurisprudencial |
| `Archivo`, `Nº`, `Partes procesales`, `Tema principal`, `RELACIÓN PLAYAS`, `CATEGORIA ANALISIS`, `TEMÁTICA` | Campos descriptivos presentes en parte de la jurisprudencia |
| `titulo`, `capitulo`, `articulo`, `articulo_titulo`, `norma` | Jerarquía de la normativa, identificación del artículo y rótulo de la norma cuando está respaldado |

Conservar los IDs e índices existentes al corregir el texto o la metadata. La
numeración admite huecos y el número de artículo se conserva como texto.
`source` suele referir al derivado Markdown. Para identificar el original,
consultar la asociación de capas del catálogo y el registro de curación.
`title` es el título del documento y `titulo` corresponde al nivel estructural
de la norma. El ponente identifica la pieza principal. Para atribuir una cita,
aclaración o salvamento, cotejar la voz en el cuerpo documental.

### Enriquecimiento de fragmentos

El enriquecedor genera estos tres campos por fragmento. Recibe el texto y,
cuando existen, `source`, `title`, `section_name`, `section_heading`,
`doc_type`, `titulo`, `capitulo` y `articulo` como contexto.

| Campo | Forma en Gold | Contenido |
|---|---|---|
| `summary` | Cadena | Resumen breve de lo que dice el fragmento |
| `keywords` | Lista de cadenas | Términos de búsqueda asociados al fragmento |
| `entities` | Lista de objetos con `type` y `text` | Menciones identificadas de personas, autoridades, lugares, fechas, normas u otras entidades |

En los 5.862 fragmentos del respaldo `gold-a-cc7bf44b54a9` están presentes los
tres campos. Tienen contenido 5.849 resúmenes, 5.849 listas de palabras clave
y 5.761 listas de entidades. Para validar una afirmación, usar el pasaje y
su fuente como evidencia. El enriquecimiento sirve para localizar e
interpretar el fragmento.

### Representación en Chroma y uso en el RAG

- **Almacenamiento.** El ID del registro corresponde a `chunk_id` y el
  documento conserva `page_content`. La metadata conserva los valores
  escalares, omite `null` y serializa listas u objetos como cadenas JSON.
  `keywords_str` se obtiene al unir `keywords` con coma y espacio.
- **Recuperación.** La receta del vector documental antepone al cuerpo el
  encabezado normativo construido con `title` (o `norma`) y `articulo`,
  cuando corresponda, y agrega `keywords_str` y `summary` cuando tienen
  contenido. BM25 usa el cuerpo, las palabras clave y el resumen.
- **Respuesta.** El contexto del modelo incluye el cuerpo, `source`,
  `chunk_id`, campos de atribución según el tipo documental y el resumen
  auxiliar. Las entidades se conservan como metadata para inspección.

Consultar [el enriquecedor](../ingesta/ingest/splitter_and_enrich.py),
[la adaptación de metadatos](../rag/backend/rag/core/vectorstore.py) y
[el formato del contexto](../rag/backend/rag/core/tools.py).

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
Regenerar ambos con la herramienta si cambian sus entradas. La comparación
que incluyen corresponde al export histórico de julio. Para comprobar la
colección Gold actual, usar el [respaldo versionado](chroma-releases/README.md)
y su restaurador.

La herramienta local, sus comandos y límites están en
[Inventario técnico local](../ingesta/docs/SCRIPTS.md#inventario-técnico-local).
Un aviso no equivale a un error ni autoriza una reparación automática.

## Entrega y reservas

Para una entrega coherente, compartir desde una misma versión del repositorio
`documents/`, este README, el registro de curación y los dos inventarios.
Identificar la versión y comprobar sus huellas. Para recuperar la colección
se distribuye también el paquete Gold versionado.

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

## Respaldo lógico Gold para recuperación

La [referencia de versiones y recuperación](chroma-releases/README.md) identifica
`gold-a-cc7bf44b54a9` como entrega actual y conserva `gold-a-769a847f096b` como
padre histórico. El paquete actual contiene cuerpos, metadata y vectores; para
restaurarlo no se necesitan el laboratorio anterior, el padre ni una nueva
generación de embeddings documentales.

Conservar juntos los cinco archivos de cada paquete. Sus README y manifiestos
describen el estado al empaquetar. La guía de recuperación documenta la
colección `rag_playas_gold_a_cc7bf44b54a9` y su comprobación funcional.

## Ground truth

El banco activo es [legal-ground-truth-v0.1.json](../rag/evaluation/data/legal-ground-truth-v0.1.json),
**Esperando validación final**. El Excel
[legal-ground-truth-v0.2.xlsx](../rag/evaluation/data/legal-ground-truth-v0.2.xlsx)
es una fuente adicional y no sustituye automáticamente el JSON. Los contratos
y comandos de evaluación están en [Scripts del RAG](../rag/docs/SCRIPTS.md).
