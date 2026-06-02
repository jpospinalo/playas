# Scripts operacionales y utilidades

Referencia de todos los scripts de operación, infraestructura y mantenimiento del proyecto.

---

## Pipeline de ingesta

### `scripts/run_pipeline.sh`

Ejecuta el **pipeline completo de ingesta + arranca la API**. Es el script principal para levantar el sistema desde cero.

```bash
make pipeline           # equivalente con make
bash scripts/run_pipeline.sh
```

**Pasos que ejecuta (en orden):**

| Paso | Comando | Descripción |
|------|---------|-------------|
| 1/5 | `ingest.pdf_to_md` | Convierte PDFs de `data/raw/` a Markdown limpio en `data/bronze/` (Docling OCR + 12 pasos de limpieza) |
| 2/5 | `ingest.loaders` | Normaliza, secciona y guarda como JSONL en `data/silver/` (4 secciones para jurisprudencia, 1 artículo por unidad para normativa) |
| 3/5 | `ingest.splitter_and_enrich` | Chunking (~1000 tokens, 200 overlap) + enriquecimiento LLM (resumen, keywords, entidades) → `data/gold/` |
| 4/5 | `rag.core.vectorstore` | Genera embeddings (Ollama) e indexa en ChromaDB |
| 5/5 | `uvicorn rag.api.main:app` | Levanta la API FastAPI en puerto 8080 |

**Cuándo usarlo:** Primera vez que se despliega el sistema, o cuando se agregan nuevos documentos al corpus.

---

### `scripts/run_data_pipeline.sh`

Ejecuta solo los **pasos de datos** (1-3) **sin indexar en ChromaDB ni levantar la API**.

```bash
bash scripts/run_data_pipeline.sh
```

**Cuándo usarlo:** Cuando se quiere regenerar las capas bronze/silver/gold sin tocar ChromaDB (ej: cambiar parámetros de chunking o enriquecimiento, luego revisar los JSONL antes de indexar).

---

## Infraestructura EC2

### `scripts/ec2_chroma_db.sh`

Script de **provisioning para una instancia EC2** que corre ChromaDB. Diseñado para ejecutarse como `user-data` de AWS (al iniciar la instancia) o manualmente via SSH.

```bash
bash scripts/ec2_chroma_db.sh
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

### `scripts/ec2_ollama_embeddings.sh`

Script de **provisioning para una instancia EC2** que corre Ollama con el modelo de embeddings.

```bash
bash scripts/ec2_ollama_embeddings.sh
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

### `scripts/install-docker-ubuntu.sh`

Instala **Docker Engine + Compose plugin** en Ubuntu 22.04 (Jammy) o 24.04 (Noble).

```bash
sudo bash scripts/install-docker-ubuntu.sh
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

## SageMaker

### `scripts/sagemaker-on_start_lifecycle.sh`

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

### `scripts/sagemaker-phi4-mini.sh`

Referencia rápida para levantar Ollama con el modelo `phi4-mini:3.8b` en SageMaker.

```bash
# Ejecutar los comandos manualmente (no es un script automatizado)
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
docker exec -it ollama ollama pull phi4-mini:3.8b
```

**Nota:** Este archivo es una referencia/cheatsheet, no un script ejecutable automatizado.

---

## Migraciones

### `scripts/migrate_feedback_ratings.py`

Migra documentos de feedback del formato legacy (`rating: int`) al formato multi-dimensional (`ratings: {tone, length, usability, overall}`).

```bash
uv run python scripts/migrate_feedback_ratings.py --dry-run   # Vista previa
uv run python scripts/migrate_feedback_ratings.py             # Aplica cambios
```

**Qué hace:**

1. Lee todos los documentos de la colección `feedback` en Firestore
2. Para cada documento que tenga `rating` pero no `ratings`:
   - Crea `ratings` copiando el valor legacy a las 4 dimensiones
   - Elimina el campo `rating` del documento
3. Documenta progreso y errores

**Cuándo usarlo:** Una sola vez, después de desplegar el sistema de feedback multi-dimensional. Verificar con `--dry-run` antes de aplicar.

---

## Utilidades (`utils/`)

### `utils/bucket_backup.py`

Descarga **todos los objetos del bucket S3** a una carpeta local con timestamp.

```bash
make bucket-backup                           # equivalente con make
uv run python -m utils.bucket_backup
```

**Resultado:** Carpeta `bucket-backup-YYYYMMDD-HHMMSS/` en la raíz del proyecto con la estructura completa del bucket.

**Cuándo usarlo:** Antes de hacer cambios destructivos en el pipeline, o para tener un backup offline del corpus.

---

### `utils/chroma_count.py`

Consulta la **cantidad de documentos** en la colección de ChromaDB.

```bash
uv run python -m utils.chroma_count
```

**Resultado:** Imprime el conteo de documentos de la colección configurada en `CHROMA_COLLECTION_NAME`.

**Cuándo usarlo:** Para verificar que la indexación se completó correctamente (comparar con el número esperado de chunks).

---

### `utils/chroma_clear.py`

**Elimina todos los documentos** de la colección activa en ChromaDB. Pide confirmación interactiva.

```bash
uv run python -m utils.chroma_clear
```

**Qué hace:**

1. Conecta a ChromaDB y muestra el conteo actual
2. Pide confirmación (`¿Eliminar todos los documentos? [y/N]`)
3. Elimina la colección y la recrea vacía

**Cuándo usarlo:** Cuando se quiere re-indexar desde cero (ej: después de cambiar la estrategia de embeddings o enriquecimiento). **Precaución:** operación destructiva.

---

### `utils/migrate_doc_type.py`

Migra objetos S3 de la raíz de cada capa hacia subcarpetas por `doc_type`.

```bash
uv run python -m utils.migrate_doc_type              # dry-run
uv run python -m utils.migrate_doc_type --apply      # aplica
```

**Qué hace:** Reubica objetos de `data/<capa>/archivo.jsonl` → `data/<capa>/jurisprudencia/archivo.jsonl` para todas las capas (raw, bronze, silver, gold). Es idempotente: no mueve objetos que ya estén bajo un subnivel de doc_type.

**Cuándo usarlo:** Migración única al agregar soporte para `normativa` como tipo de documento separado. Los objetos existentes (todos jurisprudencia) necesitan moverse a la subcarpeta correcta.

---

### `utils/backfill_doc_type.py`

Añade el metadato `doc_type` a chunks que ya están indexados en ChromaDB pero no lo tienen.

```bash
uv run python -m utils.backfill_doc_type              # dry-run
uv run python -m utils.backfill_doc_type --apply      # aplica
uv run python -m utils.backfill_doc_type --apply --doc-type jurisprudencia
```

**Qué hace:**

1. Lee todos los chunks de la colección ChromaDB
2. Para cada chunk sin `doc_type`, actualiza su metadata con el tipo indicado
3. Procesa en batches de 200 chunks
4. Solo actualiza metadata, NO regenera embeddings

**Cuándo usarlo:** Después de la migración a multi-tipo, para que los chunks legacy indexados antes de la feature `normativa` sean filtrables por `doc_type`.

---

### `utils/backfill_doc_type_s3.py`

Añade el metadato `doc_type` a los chunks almacenados en los JSONL de S3 (silver/gold).

```bash
uv run python -m utils.backfill_doc_type_s3                       # dry-run
uv run python -m utils.backfill_doc_type_s3 --apply               # aplica
uv run python -m utils.backfill_doc_type_s3 --apply --layers gold # solo gold
```

**Qué hace:** Similar a `backfill_doc_type.py` pero sobre los archivos JSONL en S3. Reescribe cada objeto S3 con el campo `doc_type` añadido a los chunks que no lo tengan.

**Cuándo usarlo:** Complemento del backfill de ChromaDB. Sin esto, si se re-ejecuta el pipeline de indexación (`rag.core.vectorstore`), los chunks sin `doc_type` en S3 volverían a indexarse sin el discriminador.

---

### `utils/list_gemini_models.py`

Lista los **modelos disponibles** en la API de Google GenAI (Gemini/Gemma) con sus acciones soportadas.

```bash
uv run python -m utils.list_gemini_models
```

**Cuándo usarlo:** Para verificar qué modelos están disponibles con la API key configurada, o para confirmar que un modelo específico soporta las capacidades necesarias (tool calling, structured output).

---

## Resumen de uso frecuente

| Tarea | Script/Comando |
|-------|---------------|
| Levantar el sistema completo | `make pipeline` |
| Solo procesar datos (sin indexar) | `bash scripts/run_data_pipeline.sh` |
| Backup del bucket S3 | `make bucket-backup` |
| Verificar chunks en ChromaDB | `uv run python -m utils.chroma_count` |
| Limpiar ChromaDB para re-indexar | `uv run python -m utils.chroma_clear` |
| Provisionar EC2 para ChromaDB | `bash scripts/ec2_chroma_db.sh` |
| Provisionar EC2 para Ollama | `bash scripts/ec2_ollama_embeddings.sh` |
| Instalar Docker en Ubuntu | `sudo bash scripts/install-docker-ubuntu.sh` |
| Migrar feedback a multi-dimensional | `uv run python scripts/migrate_feedback_ratings.py --dry-run` |
