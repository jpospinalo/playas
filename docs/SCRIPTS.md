# Scripts operacionales y utilidades

Referencia de todos los scripts de operación, infraestructura y mantenimiento del proyecto.

> **Organización por dominio.** Tras la reestructuración, cada script/utilidad vive junto al módulo al que sirve:
> - `ingest/scripts/` — orquestación del pipeline de datos.
> - `ingest/tools/` — utilidades Python sobre S3 y diagnóstico de modelos.
> - `rag/backend/rag/tools/` — utilidades Python sobre el almacén de serving (ChromaDB, Firestore).
> - `infra/scripts/` — provisioning e infraestructura (EC2, SageMaker, Docker, deploy).
>
> El paquete `rag` vive en `rag/backend/rag/`. Los comandos `python -m rag.tools.*`
> requieren `PYTHONPATH=rag/backend`. Los de `ingest.*` se ejecutan desde la raíz sin nada extra.

---

## Pipeline de ingesta

### `ingest/scripts/run_pipeline.sh`

Ejecuta las **3 etapas de datos** del pipeline de ingesta (produce `data/gold/`). No indexa en ChromaDB ni levanta la API: respeta la independencia entre `ingest` y `rag`.

```bash
bash ingest/scripts/run_pipeline.sh
```

**Pasos que ejecuta (en orden):**

| Paso | Comando | Descripción |
|------|---------|-------------|
| 1/3 | `ingest.pdf_to_md` | Convierte PDFs de `data/raw/` a Markdown limpio en `data/bronze/` (Docling OCR + 12 pasos de limpieza) |
| 2/3 | `ingest.loaders` | Normaliza, secciona y guarda como JSONL en `data/silver/` (4 secciones para jurisprudencia, 1 artículo por unidad para normativa) |
| 3/3 | `ingest.splitter_and_enrich` | Chunking (~1000 tokens, 200 overlap) + enriquecimiento LLM (resumen, keywords, entidades) → `data/gold/` |

**Cuándo usarlo:** Para regenerar las capas bronze/silver/gold (ej: cambiar parámetros de chunking o enriquecimiento) antes de indexar.

### Pipeline completo (datos + indexación)

`make pipeline` encadena el pipeline de datos anterior **y** la indexación en ChromaDB (orquestación cruzada a nivel del repo, ya que la indexación es responsabilidad de `rag`):

```bash
make pipeline
# equivale a:
#   bash ingest/scripts/run_pipeline.sh
#   PYTHONPATH=rag/backend uv run python -m rag.core.vectorstore
```

La API se levanta por separado con `make app`.

**Cuándo usarlo:** Primera vez que se despliega el sistema, o cuando se agregan nuevos documentos al corpus.

---

## Infraestructura EC2 (`infra/scripts/`)

### `infra/scripts/ec2_chroma_db.sh`

Script de **provisioning para una instancia EC2** que corre ChromaDB. Diseñado para ejecutarse como `user-data` de AWS (al iniciar la instancia) o manualmente via SSH.

```bash
bash infra/scripts/ec2_chroma_db.sh
```

**Qué hace:**

1. Actualiza paquetes del sistema (`apt-get update/upgrade`)
2. Instala Docker (`docker.io`)
3. Crea directorio persistente `/opt/chroma-data`
4. Ejecuta ChromaDB en Docker (`chromadb/chroma:1.3.5`) con:
   - Puerto 8000 expuesto
   - Volumen persistente en `/opt/chroma-data`
   - `IS_PERSISTENT=TRUE`
   - Reinicio automático (`--restart unless-stopped`)

**Resultado:** ChromaDB accesible en `http://<ip-ec2>:8000`.

**Requisitos previos:** Instancia EC2 Ubuntu con Security Group que permita tráfico en puerto 8000.

---

### `infra/scripts/ec2_ollama_embeddings.sh`

Script de **provisioning para una instancia EC2** que corre Ollama con el modelo de embeddings.

```bash
bash infra/scripts/ec2_ollama_embeddings.sh
```

**Qué hace:**

1. Actualiza paquetes e instala Docker
2. Crea volumen Docker persistente `ollama`
3. Ejecuta Ollama en Docker con:
   - Puerto 11434 expuesto
   - Volumen persistente para modelos descargados
   - Reinicio automático (`--restart always`)
4. Descarga el modelo `embeddinggemma:latest`

**Resultado:** Ollama accesible en `http://<ip-ec2>:11434` con el modelo de embeddings listo.

**Requisitos previos:** Instancia EC2 Ubuntu con Security Group que permita tráfico en puerto 11434. Se recomienda `t3.large` o superior (el modelo de embeddings necesita RAM).

---

### `infra/scripts/install-docker-ubuntu.sh`

Instala **Docker Engine + Compose plugin** en Ubuntu 22.04 (Jammy) o 24.04 (Noble).

```bash
sudo bash infra/scripts/install-docker-ubuntu.sh
```

**Qué hace:**

1. Verifica que sea root y Ubuntu
2. Instala dependencias (`ca-certificates`, `curl`, `gnupg`)
3. Añade la GPG key y repositorio oficial de Docker
4. Instala `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`
5. Habilita el servicio Docker
6. Añade el usuario invocante al grupo `docker`

**Cuándo usarlo:** En máquinas Ubuntu frescas que necesitan Docker pero no están provisionadas por EC2 (ej: VMs locales, otros proveedores cloud).

---

## SageMaker (`infra/scripts/`)

### `infra/scripts/sagemaker-on_start_lifecycle.sh`

**Lifecycle hook** para instancias SageMaker. Reconfigura Docker para usar almacenamiento persistente en el EBS de la instancia.

```bash
# Se configura como "OnStart" lifecycle hook en la configuración de la instancia SageMaker
```

**Qué hace:**

1. Crea directorio `/home/ec2-user/SageMaker/docker_data`
2. Reescribe `/etc/docker/daemon.json` para:
   - `data-root`: apuntar al EBS persistente (sobrevive reinicios de instancia)
   - `runtimes.nvidia`: configurar NVIDIA Container Runtime (para GPUs)
3. Reinicia Docker

**Cuándo usarlo:** Cuando se usa SageMaker como entorno de desarrollo y se quiere que los contenedores Docker (y sus datos) persistan entre reinicios de instancia.

---

### `infra/scripts/sagemaker-phi4-mini.sh`

Referencia rápida para levantar Ollama con el modelo `phi4-mini:3.8b` en SageMaker.

```bash
# Ejecutar los comandos manualmente (no es un script automatizado)
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
docker exec -it ollama ollama pull phi4-mini:3.8b
```

**Nota:** Este archivo es una referencia/cheatsheet, no un script ejecutable automatizado.

---

### `infra/scripts/deploy-tutorial-html.ps1`

Script PowerShell para desplegar el HTML del tutorial de la cartilla (ground-truth).

**Cuándo usarlo:** Al publicar una versión actualizada del tutorial de la plataforma.

---

## Migraciones (`rag/backend/rag/tools/`)

### `rag/backend/rag/tools/migrate_feedback_ratings.py`

Migra documentos de feedback del formato legacy (`rating: int`) al formato multi-dimensional (`ratings: {tone, length, usability, overall}`).

```bash
PYTHONPATH=rag/backend uv run python -m rag.tools.migrate_feedback_ratings --dry-run   # Vista previa
PYTHONPATH=rag/backend uv run python -m rag.tools.migrate_feedback_ratings             # Aplica cambios
```

**Qué hace:**

1. Lee todos los documentos de la colección `feedback` en Firestore
2. Para cada documento que tenga `rating` pero no `ratings`:
   - Crea `ratings` copiando el valor legacy a las 4 dimensiones
   - Elimina el campo `rating` del documento
3. Documenta progreso y errores

**Cuándo usarlo:** Una sola vez, después de desplegar el sistema de feedback multi-dimensional. Verificar con `--dry-run` antes de aplicar.

---

## Utilidades de serving (`rag/backend/rag/tools/`)

Operan sobre el almacén de serving (ChromaDB). Requieren `PYTHONPATH=rag/backend`.

### `rag/backend/rag/tools/chroma_count.py`

Consulta la **cantidad de documentos** en la colección de ChromaDB.

```bash
PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_count
```

**Resultado:** Imprime el conteo de documentos de la colección configurada en `CHROMA_COLLECTION_NAME`.

**Cuándo usarlo:** Para verificar que la indexación se completó correctamente (comparar con el número esperado de chunks).

---

### `rag/backend/rag/tools/chroma_clear.py`

**Elimina todos los documentos** de la colección activa en ChromaDB. Pide confirmación interactiva.

```bash
PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_clear
```

**Qué hace:**

1. Conecta a ChromaDB y muestra el conteo actual
2. Pide confirmación (`¿Eliminar todos los documentos? [y/N]`)
3. Elimina la colección y la recrea vacía

**Cuándo usarlo:** Cuando se quiere re-indexar desde cero (ej: después de cambiar la estrategia de embeddings o enriquecimiento). **Precaución:** operación destructiva.

---

### `rag/backend/rag/tools/backfill_doc_type.py`

Añade el metadato `doc_type` a chunks que ya están indexados en ChromaDB pero no lo tienen.

```bash
PYTHONPATH=rag/backend uv run python -m rag.tools.backfill_doc_type              # dry-run
PYTHONPATH=rag/backend uv run python -m rag.tools.backfill_doc_type --apply      # aplica
PYTHONPATH=rag/backend uv run python -m rag.tools.backfill_doc_type --apply --doc-type jurisprudencia
```

**Qué hace:**

1. Lee todos los chunks de la colección ChromaDB
2. Para cada chunk sin `doc_type`, actualiza su metadata con el tipo indicado
3. Procesa en batches de 200 chunks
4. Solo actualiza metadata, NO regenera embeddings

**Cuándo usarlo:** Después de la migración a multi-tipo, para que los chunks legacy indexados antes de la feature `normativa` sean filtrables por `doc_type`.

---

## Utilidades de ingesta (`ingest/tools/`)

Operan sobre S3 y diagnóstico de modelos. Se ejecutan desde la raíz (sin `PYTHONPATH` extra).

### `ingest/tools/bucket_backup.py`

Descarga **todos los objetos del bucket S3** a una carpeta local con timestamp.

```bash
make bucket-backup                           # equivalente con make
uv run python -m ingest.tools.bucket_backup
```

**Resultado:** Carpeta `bucket-backup-YYYYMMDD-HHMMSS/` en la raíz del proyecto con la estructura completa del bucket.

**Cuándo usarlo:** Antes de hacer cambios destructivos en el pipeline, o para tener un backup offline del corpus.

---

### `ingest/tools/migrate_doc_type.py`

Migra objetos S3 de la raíz de cada capa hacia subcarpetas por `doc_type`.

```bash
uv run python -m ingest.tools.migrate_doc_type              # dry-run
uv run python -m ingest.tools.migrate_doc_type --apply      # aplica
```

**Qué hace:** Reubica objetos de `data/<capa>/archivo.jsonl` → `data/<capa>/jurisprudencia/archivo.jsonl` para todas las capas (raw, bronze, silver, gold). Es idempotente: no mueve objetos que ya estén bajo un subnivel de doc_type.

**Cuándo usarlo:** Migración única al agregar soporte para `normativa` como tipo de documento separado. Los objetos existentes (todos jurisprudencia) necesitan moverse a la subcarpeta correcta.

---

### `ingest/tools/backfill_doc_type_s3.py`

Añade el metadato `doc_type` a los chunks almacenados en los JSONL de S3 (silver/gold).

```bash
uv run python -m ingest.tools.backfill_doc_type_s3                       # dry-run
uv run python -m ingest.tools.backfill_doc_type_s3 --apply               # aplica
uv run python -m ingest.tools.backfill_doc_type_s3 --apply --layers gold # solo gold
```

**Qué hace:** Similar a `backfill_doc_type.py` pero sobre los archivos JSONL en S3. Reescribe cada objeto S3 con el campo `doc_type` añadido a los chunks que no lo tengan.

**Cuándo usarlo:** Complemento del backfill de ChromaDB. Sin esto, si se re-ejecuta el pipeline de indexación (`rag.core.vectorstore`), los chunks sin `doc_type` en S3 volverían a indexarse sin el discriminador.

---

### `ingest/tools/list_gemini_models.py`

Lista los **modelos disponibles** en la API de Google GenAI (Gemini/Gemma) con sus acciones soportadas.

```bash
uv run python -m ingest.tools.list_gemini_models
```

**Cuándo usarlo:** Para verificar qué modelos están disponibles con la API key configurada, o para confirmar que un modelo específico soporta las capacidades necesarias (tool calling, structured output).

---

## Resumen de uso frecuente

| Tarea | Script/Comando |
|-------|---------------|
| Pipeline de datos + indexación | `make pipeline` |
| Solo procesar datos (sin indexar) | `bash ingest/scripts/run_pipeline.sh` |
| Backup del bucket S3 | `make bucket-backup` |
| Verificar chunks en ChromaDB | `PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_count` |
| Limpiar ChromaDB para re-indexar | `PYTHONPATH=rag/backend uv run python -m rag.tools.chroma_clear` |
| Provisionar EC2 para ChromaDB | `bash infra/scripts/ec2_chroma_db.sh` |
| Provisionar EC2 para Ollama | `bash infra/scripts/ec2_ollama_embeddings.sh` |
| Instalar Docker en Ubuntu | `sudo bash infra/scripts/install-docker-ubuntu.sh` |
| Migrar feedback a multi-dimensional | `PYTHONPATH=rag/backend uv run python -m rag.tools.migrate_feedback_ratings --dry-run` |
