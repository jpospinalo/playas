# Scripts operacionales — RAG

Referencia de scripts de despliegue, SageMaker, utilidades ChromaDB y migraciones del subsistema RAG.

---

## Despliegue

### `scripts/install-docker-ubuntu.sh`

Instala **Docker Engine + Compose plugin** en Ubuntu 22.04 (Jammy) o 24.04 (Noble).

```bash
sudo bash rag/scripts/install-docker-ubuntu.sh
```

**Qué hace:**
1. Verifica que sea root y Ubuntu
2. Añade la GPG key y repositorio oficial de Docker
3. Instala `docker-ce`, `docker-ce-cli`, `containerd.io`, `docker-buildx-plugin`, `docker-compose-plugin`
4. Habilita el servicio Docker y añade el usuario al grupo `docker`

**Cuándo usarlo:** En máquinas Ubuntu frescas que necesitan Docker (VMs locales, otros proveedores cloud).

---

## SageMaker

### `scripts/sagemaker-on_start_lifecycle.sh`

**Lifecycle hook** para instancias SageMaker. Reconfigura Docker para usar almacenamiento persistente en EBS.

```bash
# Se configura como "OnStart" lifecycle hook en la configuración de la instancia SageMaker
```

**Qué hace:**
1. Reescribe `/etc/docker/daemon.json` para usar el EBS como `data-root`
2. Configura NVIDIA Container Runtime (para GPUs)
3. Reinicia Docker

---

### `scripts/sagemaker-phi4-mini.sh`

Referencia rápida para levantar Ollama con `phi4-mini:3.8b` en SageMaker.

```bash
docker run -d -v ollama:/root/.ollama -p 11434:11434 --name ollama ollama/ollama
docker exec -it ollama ollama pull phi4-mini:3.8b
```

**Nota:** Es una referencia/cheatsheet, no un script ejecutable automatizado.

---

## Migraciones

### `scripts/migrate_feedback_ratings.py`

Migra documentos de feedback del formato legacy (`rating: int`) al formato multi-dimensional (`ratings: {tone, length, usability, overall}`).

```bash
uv run python rag/scripts/migrate_feedback_ratings.py --dry-run   # vista previa
uv run python rag/scripts/migrate_feedback_ratings.py             # aplica
```

**Cuándo usarlo:** Una sola vez, después de desplegar el sistema de feedback multi-dimensional.

---

## Pruebas de carga

### `scripts/load_test.py`

Lanza N usuarios concurrentes contra `/api/query/stream` (el endpoint SSE que usa el frontend) en el ALB de ECS, y reporta latencias (tiempo al primer evento, al primer token, total).

```bash
uv run python rag/scripts/load_test.py --users 10 --timeout 60
```

**Nota:** la URL del ALB está hardcodeada en el script (`BASE_URL`); actualízala si el ALB cambia (p. ej. tras recrear la infraestructura Terraform).

**Cuándo usarlo:** para validar manualmente latencia/estabilidad del backend bajo concurrencia antes o después de un despliegue.

---

## Utilidades ChromaDB (`utils/`)

### `utils/chroma_count.py`

Consulta la **cantidad de documentos** en la colección de ChromaDB.

```bash
uv run python -m utils.chroma_count
```

---

### `utils/chroma_clear.py`

**Elimina todos los documentos** de la colección activa en ChromaDB. Pide confirmación interactiva.

```bash
uv run python -m utils.chroma_clear
```

**Precaución:** operación destructiva. Úsala cuando se quiere re-indexar desde cero.

---

### `utils/list_gemini_models.py`

Lista los **modelos disponibles** en la API de Google GenAI con sus acciones soportadas.

```bash
uv run python -m utils.list_gemini_models
```

**Cuándo usarlo:** Para verificar modelos disponibles o confirmar soporte de tool calling / structured output.

---

## Resumen de uso frecuente

| Tarea | Comando |
|-------|---------|
| Verificar chunks en ChromaDB | `uv run python -m utils.chroma_count` |
| Limpiar ChromaDB para re-indexar | `uv run python -m utils.chroma_clear` |
| Instalar Docker en Ubuntu | `sudo bash rag/scripts/install-docker-ubuntu.sh` |
| Migrar feedback a multi-dimensional | `uv run python rag/scripts/migrate_feedback_ratings.py --dry-run` |
| Prueba de carga contra ECS | `uv run python rag/scripts/load_test.py --users 10` |
