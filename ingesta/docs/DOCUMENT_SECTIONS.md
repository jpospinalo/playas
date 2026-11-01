# Seccionado de jurisprudencia

[sections.py](../ingest/sections.py) agrupa el texto de jurisprudencia en
cuatro contenedores. Los nombres e índices corresponden a `SECTION_NAMES`:

| Índice | Nombre | Ejemplos de encabezados reconocidos |
|---|---|---|
| 1 | Contexto del caso | Antecedentes, síntesis del caso, causa petendi |
| 2 | Desarrollo procesal | Contestación de la demanda, trámite de la acción, recurso de apelación |
| 3 | Análisis del tribunal | Consideraciones, consideraciones de la Sala |
| 4 | Decisión | Conclusiones, decisión, falla, resuelve |

La lista de ejemplos no sustituye las variantes y reglas del clasificador.
Las secciones 1–3 admiten un prefijo reconocido con límite de palabra; la 4
requiere un título completo. Un título explícitamente citado no provoca un
cambio de sección, incluso tras una enumeración. La normalización de títulos
no modifica el cuerpo documental.

## Salida y límites

`split_by_sections()` distribuye bloques a partir de encabezados Markdown
`##`. Un título reconocido cambia el contenedor activo; uno no reconocido
hereda el anterior. El texto inicial se asigna al contexto del caso y, sin
encabezados, todo el documento queda en ese contenedor.

La función devuelve cuatro documentos, incluso si alguno está vacío. Conserva
la metadata de origen y añade `section_index`, `section_name` y
`section_heading`. El fragmentador omite secciones vacías.

Esta agrupación estructural no identifica la voz jurídica de cada pasaje:
una sección «Decisión» no convierte una aclaración o un salvamento en fallo
mayoritario. Tampoco autoriza a renumerar el corpus local, que puede conservar
secciones e IDs históricos de reparaciones documentales posteriores al
procesamiento original.

Normativa utiliza otra estrategia, basada en unidades de artículo y estructura
normativa; ver [sections_normativa.py](../ingest/sections_normativa.py).
El [README de ingesta](../README.md) describe su despacho por tipo.
