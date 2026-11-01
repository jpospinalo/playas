# Scripts operacionales — Ingesta

Los comandos de esta página se ejecutan desde `ingesta/`, salvo donde se
indica otro directorio. Leer [el contrato y límites del pipeline](../README.md)
antes de procesar documentos. Cada sección distingue archivos locales de
servicios externos. No ejecutar pipelines o migraciones para validar una
edición de documentación.

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

## Inventario técnico local

`utils/audit_local_corpus.py` inspecciona `../data/documents/` y genera
`data/corpus-catalog.json` y `data/CORPUS_CATALOG.md`. Usa solo la biblioteca
estándar; no importa la ingesta productiva ni consulta S3, ChromaDB, Ollama o
un LLM. Ver [capas, registro y uso del corpus](../../data/README.md).

Desde `ingesta/`, con su Python 3.12 ya instalado:

```bash
# Comprobar los dos inventarios sin escribir archivos.
.venv/bin/python -m utils.audit_local_corpus --export data/chroma-rag_playas_magdalena-20260731-135720.jsonl.gz --check
```

Para inspeccionar sin cotejar los artefactos generados, omitir `--check`.
Para regenerarlos, reemplazarlo por `--write`: esta opción escribe solamente
los dos inventarios y no modifica el corpus. No regenerarlos si sus entradas
no cambiaron. La herramienta también se puede ejecutar por ruta; los argumentos
relativos, incluido `--export`, se resuelven respecto del repositorio.

El export se indica explícitamente; no se selecciona por fecha. Sin `--export`,
la comparación con el backup queda sin comprobar. Su colección y fecha se
leen del manifest y no describen el índice desplegado hoy.

| Salida | Significado |
|---|---|
| `0` | Operación completada sin errores técnicos; puede haber avisos |
| `1` | Errores técnicos, o inventarios ausentes/desactualizados en `--check` |
| `2` | Operación incompleta por lectura, rutas inseguras, entradas cambiantes o destino no permitido |

`--write` puede generar un informe con errores: leer el resumen antes de
considerar válida la salida.

### Comprobaciones y límites

- Asocia capas por tipo y nombre normalizado Unicode solo si la relación es
  inequívoca; conserva rutas e IDs. Una fuente idéntica no autoriza fusionar
  representaciones y un nombre largo o descompuesto no demuestra corrupción.
- Comprueba UTF-8/JSON, firma PDF básica y referencias inline a imágenes de
  Bronze. No hace OCR, renderizado, validación completa de PDF ni navegación
  de enlaces. Las rutas de imagen deben ser locales, internas al corpus y sin
  symlinks; sintaxis no soportada se informa sin inventar un destino ausente.
- Una sección Silver vacía es aviso; un chunk o archivo Gold vacío es error.
  Los IDs duplicados reconocibles se detectan aunque una fila sea inválida;
  los ambiguos y los registros inválidos se excluyen de la comparación.
- Compara JSONL/gzip de forma secuencial y comprueba estabilidad de entradas.
  No retiene embeddings. La comparación de metadata respeta omisión de `None`,
  serialización de listas/objetos y `keywords_str` del contrato de
  [vectorstore](../../rag/backend/rag/core/vectorstore.py). Conserva el orden
  de listas y no reinterpreta referencias jurídicas como números u objetos.
- Los hallazgos no acreditan fidelidad integral, vigencia, selección jurídica,
  correspondencia con S3 o presencia en el índice vivo. No reemplazan datos
  automáticamente. El detalle de sintaxis y casos límite está en
  [la herramienta](../utils/audit_local_corpus.py) y sus
  [contratos offline](../tests/unit/test_local_corpus_catalog.py).

## Infraestructura: responsabilidades

- `ingesta/infrastructure/`: bucket S3, no instancias ChromaDB/Ollama.
- [vector-infraestructura](../../vector-infraestructura/README.md):
  Terraform y scripts de las EC2 de ChromaDB y Ollama.
- [RAG](../../rag/README.md): servicio/API/frontend.
- [Guía operacional de la raíz](../../README.md): despliegue y arranque/apagado.

No aplicar Terraform ni operar AWS como parte de pruebas offline o
mantenimiento documental.

## Utilidades de mantenimiento

No son etapas habituales del pipeline. Antes de escribir o mover datos:
confirmar colección/bucket, respaldo y clasificación con su responsable.
Un dry-run puede consultar servicios reales y necesita permisos de lectura.

### Snapshot documental de ChromaDB (solo lectura)

[El exportador](../../data/export_chroma_snapshot.py) es una CLI independiente
para una colección existente. Usa Python 3.12 y Chroma 1.5.9 del entorno
`rag/`, sin cargar configuración del RAG ni generar o leer embeddings. No
crea ni modifica colecciones; la lectura sí consume recursos del servidor.

Desde la raíz del repositorio, estos comandos son locales y no exportan:

```bash
rag/.venv/bin/python -B data/export_chroma_snapshot.py --help
rag/.venv/bin/python -B -m unittest discover -s rag/tests/unit -p 'test_chroma_snapshot_export.py' -v
```

La captura real es una operación separada y supervisada. Requiere identidad
confirmada por el responsable y argumentos explícitos `--host` (nombre de host
o IPv4, sin esquema, ruta o credenciales; IPv6 no soportado), `--port`,
`--tenant`, `--database`, `--collection` y
`--output-dir`. Usa HTTP. `--confirm-no-writes` registra la declaración de que
no habrá ingestas, actualizaciones ni borrados durante la ventana; no demuestra
ausencia de escrituras. El RAG puede atender consultas, pero deben evitarse
otros procesos que puedan indexar. No ejecutar si no se puede coordinar esa
ventana. No sustituir esa confirmación por conteos estables.

El destino debe ser una carpeta nueva y privada, con padre existente y fuera
del repositorio y de paquetes de evidencia cerrados. No se sobrescribe ni se
borra nada. El lote es de 100 registros por defecto (`--batch-size` admite
1–100), con pausa de 100 ms entre páginas y sin reintentos o reanudación.
Proxies efectivos HTTP/HTTPS/ALL, incluso con bypass, o una versión distinta
del SDK detienen la operación. No hay autenticación en esta versión. El SDK
se importa en el directorio privado temporalmente usado como CWD para evitar
leer un `.env` del proyecto; se restaura el CWD al terminar.

El transporte no tiene timeout automático aquí: el responsable debe vigilar
la ejecución, fijar un límite operativo y cancelar si no responde o afecta al
servicio. Esta lectura paginada **no es transaccional**; un cambio concurrente
con igual cardinalidad puede pasar inadvertido.

La salida tiene un `snapshot.jsonl` con `id`, `document` y `metadata` observados,
y un `manifest.json` con identidad/UUID, conteos, anomalías, fechas y SHA-256.
Los IDs reales, textos, nulos y metadatos se conservan; las anomalías se cuentan,
no se reparan. No contiene vectores ni es entrada del importador siguiente.
No demuestra equivalencia con Gold o con una receta de embeddings.

Se cierra el cliente y se restaura el CWD antes de publicar mediante hardlinks sin
reemplazo; un filesystem sin ese soporte detiene la entrega sin fallback.
El punto de cierre es el manifiesto final propio `COMPLETE`, vinculado a los
bytes del JSONL. Los candidatos `.partial` se conservan como nombres del mismo
archivo; no duplican bytes. Un candidato `COMPLETE` aislado o un JSONL final
sin manifiesto final propio no acredita entrega. Antes del cierre, un error
deja la corrida incompleta. Después, un fallo o cancelación no degrada ni
reescribe lo publicado: conservarlo para revisión, sin repetir automáticamente
la captura.

Retornos: `0` publicación verificada y finalización normal; `1` error; `2`
argumentos/destino inválidos; `130` interrupción. Un retorno no cero posterior
al cierre no invalida el `COMPLETE` propio verificado. Revisar estado y huellas
antes de aceptar la captura; no confundir completitud técnica con validez del
corpus ni usarla para atribuir bajas si se informó actividad de escritura.

### Importación de un export a ChromaDB

[El importador](../../data/import_to_chromadb.py) se ejecuta con el entorno
`rag/`, no con el de ingesta. Conecta y escribe en una colección; no es una
comprobación offline del corpus.

Exige `--batch-size > 0`; un valor inválido termina con `2` antes de conectar.
Si falla un lote, continúa con los siguientes y termina con `1`; los registros
ya escritos no se revierten. Sin errores termina con `0`, también con un
export vacío. Confirmar destino y respaldo antes de autorizar su ejecución.

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
