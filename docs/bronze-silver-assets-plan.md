# Plan ejecutivo de tablas e imagenes (Bronze -> Silver -> Silver Assets -> Gold)

## 1) Recomendacion ejecutiva

Mantener `Silver` estricto y liviano (solo metadatos + secciones), y mover imagenes/tablas a `Silver Assets` con manifiesto separado y punteros a blobs.

- Decision: no embebidos pesados en `Silver`.
- Beneficio: contrato estable, menor payload, mejor trazabilidad y escalabilidad.

## 2) Decision sobre Base64

Base64 **no** es el mecanismo por defecto.

- Usar base64 solo de forma temporal para debugging/transporte transitorio.
- Condiciones minimas: asset pequeno, TTL explicito, flag de control habilitado.
- Prohibido como persistencia estable y en la salida final de `Silver`.
- Operacion recomendada: punteros a archivos (local en MVP, object storage en produccion).

## 3) Estrategia para tablas

Cada tabla se guarda con doble representacion:

- `canonical_json`: fuente estructural exacta para validacion y reprocesado.
- `retrieval_text` o `markdown`: vista semantica para recuperacion.

Regla: para cada tabla, `canonical_json` es obligatorio y debe existir al menos una vista de recuperacion.

## 4) Arquitectura por capas

- `Bronze`: documento fuente.
- `Silver`: contrato minimo textual, sin binarios ni base64 por defecto.
- `Silver Assets`: manifiestos de imagenes/tablas, metadatos de storage, integridad y enlace a seccion.
- `Gold`: enriquecimiento (OCR/caption/features RAG) sobre assets ya trazables.

## 5) Reglas clave

- Naming:
  - `doc_id` estable desde `source_file`.
  - `section_id` por ordinal de seccion.
  - `asset_id` compuesto por `doc_id + section_id + tipo + indice + hash corto`.
- Hash e integridad:
  - `sha256` obligatorio por asset (`content_sha256`).
  - En tablas, hash sobre serializacion canonica.
- Deduplicacion:
  - Evitar duplicados dentro de documento y a nivel corpus.
  - Si hay duplicado, registrar referencia `duplicate_of` sin duplicar blob fisico.
- Enlace seccion-asset:
  - Enlace por `source_file` + `section_ordinal`.
  - El ordinal manda para integridad; el titulo solo ayuda a auditoria.
- Validaciones obligatorias:
  - Referencialidad (`source_file` y rango de `section_ordinal`).
  - Integridad (`sha256`, `size_bytes`, existencia de blob).
  - Tipo (`asset_kind` permitido, `mime_type` en allowlist).
  - Reglas de tabla (estructura + vista de recuperacion).

## 6) Plan por etapas

### Etapa 1: MVP estable

- Mantener `Silver` sin cambios de contrato.
- Implementar `Silver Assets` con punteros locales.
- Activar naming, hash, deduplicacion y validaciones minimas.

### Etapa 2: Operacion robusta

- Migrar blobs a object storage con URIs estables.
- Agregar indice global de deduplicacion por hash.
- Endurecer validaciones en CI e instrumentar metricas operativas.

### Etapa 3: Gold (RAG)

- Completar OCR/caption y enriquecimientos tabulares.
- Generar chunks Gold combinando texto de seccion y contexto de assets.
- Versionar enriquecimientos para reproducibilidad.
