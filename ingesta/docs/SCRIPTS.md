# Scripts operacionales — Ingesta

Referencia de scripts de pipeline, infraestructura EC2 y utilidades S3 del subsistema de ingesta.

---

## Pipeline de ingesta

### `scripts/run_pipeline.sh`

Ejecuta el **pipeline completo de ingesta + arranca la API**. Es el script principal para levantar el sistema desde cero.

```bash
make pipeline
bash ingesta/scripts/run_pipeline.sh
```

| Paso | Comando | Descripción |
|------|---------|-------------|
| 1/5 | `ingest.pdf_to_md` | Convierte PDFs de `data/raw/` a Markdown limpio en `data/bronze/` (Docling OCR + 12 pasos de limpieza) |
| 2/5 | `ingest.loaders` | Normaliza, secciona y guarda como JSONL en `data/silver/` |
| 3/5 | `ingest.splitter_and_enrich` | Chunking (~1000 tokens, 200 overlap) + enriquecimiento LLM → `data/gold/` |
| 4/5 | `rag.core.vectorstore` | Genera embeddings (Ollama) e indexa en ChromaDB |
| 5/5 | `uvicorn rag.api.main:app` | Levanta la API FastAPI en puerto 8080 |

**Cuándo usarlo:** Primera vez que se despliega el sistema, o cuando se agregan nuevos documentos al corpus.

---

### `scripts/run_data_pipeline.sh`

Ejecuta solo los **pasos de datos** (1-3) sin indexar en ChromaDB ni levantar la API.

```bash
bash ingesta/scripts/run_data_pipeline.sh
```

**Cuándo usarlo:** Cuando se quiere regenerar las capas bronze/silver/gold sin tocar ChromaDB.

---

## Infraestructura EC2

### `scripts/ec2_chroma_db.sh`

Script de **provisioning para una instancia EC2** que corre ChromaDB. Diseñado para ejecutarse como `user-data` de AWS o manualmente via SSH.

```bash
bash ingesta/scripts/ec2_chroma_db.sh
```

**Qué hace:**
1. Actualiza paquetes del sistema
2. Instala Docker
3. Crea directorio persistente `/opt/chroma-data`
4. Ejecuta ChromaDB en Docker (`chromadb/chroma:1.3.5`), puerto 8000, reinicio automático

**Resultado:** ChromaDB accesible en `http://<ip-ec2>:8000`.

---

### `scripts/ec2_ollama_embeddings.sh`

Script de **provisioning para una instancia EC2** que corre Ollama con el modelo de embeddings.

```bash
bash ingesta/scripts/ec2_ollama_embeddings.sh
```

**Qué hace:**
1. Instala Docker
2. Ejecuta Ollama en Docker, puerto 11434, volumen persistente
3. Descarga el modelo `embeddinggemma:latest`

**Resultado:** Ollama accesible en `http://<ip-ec2>:11434`.

---

## Infraestructura Terraform

El directorio `ingesta/infrastructure/` contiene los recursos Terraform para el entorno de datos compartido:

- **S3 bucket** — almacenamiento del pipeline (bronze/silver/gold)
- **EC2 ChromaDB** — instancia con IP elástica, usa `ec2_chroma_db.sh` como user-data
- **EC2 Ollama** — instancia con IP elástica, usa `ec2_ollama_embeddings.sh` como user-data

```bash
cd ingesta/infrastructure
terraform init
terraform plan
terraform apply
```

---

## Utilidades S3 (`utils/`)

### `utils/bucket_backup.py`

Descarga todos los objetos del bucket S3 a una carpeta local con timestamp.

```bash
make bucket-backup
uv run python -m utils.bucket_backup
```

**Resultado:** Carpeta `bucket-backup-YYYYMMDD-HHMMSS/` con la estructura completa del bucket.

---

### `utils/migrate_doc_type.py`

Migra objetos S3 de la raíz de cada capa hacia subcarpetas por `doc_type`.

```bash
uv run python -m utils.migrate_doc_type              # dry-run
uv run python -m utils.migrate_doc_type --apply      # aplica
```

---

### `utils/backfill_doc_type.py`

Añade el metadato `doc_type` a chunks ya indexados en ChromaDB que no lo tienen.

```bash
uv run python -m utils.backfill_doc_type              # dry-run
uv run python -m utils.backfill_doc_type --apply
```

---

### `utils/backfill_doc_type_s3.py`

Añade `doc_type` a los chunks en los JSONL de S3 (silver/gold).

```bash
uv run python -m utils.backfill_doc_type_s3              # dry-run
uv run python -m utils.backfill_doc_type_s3 --apply
```

---

## Resumen de uso frecuente

| Tarea | Comando |
|-------|---------|
| Pipeline completo | `make pipeline` |
| Solo procesar datos (sin indexar) | `bash ingesta/scripts/run_data_pipeline.sh` |
| Backup del bucket S3 | `make bucket-backup` |
| Provisionar EC2 para ChromaDB | `bash ingesta/scripts/ec2_chroma_db.sh` |
| Provisionar EC2 para Ollama | `bash ingesta/scripts/ec2_ollama_embeddings.sh` |
