# Scripts operacionales — RAG

Referencia de scripts de despliegue, SageMaker, utilidades ChromaDB y migraciones del subsistema RAG.

Los scripts de infraestructura ECS Fargate (`deploy.sh`, `push_images.sh`, `start.sh`, `stop.sh`, `export_postgres.sh`) están documentados en [`../infrastructure/README.md`](../infrastructure/README.md), no aquí.

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

## Pruebas de carga

### `scripts/load_test.py`

Lanza N usuarios concurrentes contra `/api/query/stream` (el endpoint SSE que usa el frontend), y reporta latencias (tiempo al primer evento `status`, a la primera fracción de respuesta, total — con min/avg/p50/p95/p99/max).

```bash
export RAG_LOAD_TEST_TOKEN=<jwt>   # el endpoint exige autenticación
uv run python rag/scripts/load_test.py --url http://localhost:8080 --users 10 --timeout 60
```

**Sin URL por defecto:** `--url` es obligatorio. Apuntar a un host que no sea local exige además `--allow-remote` y, en una terminal interactiva, escribir el host exacto como confirmación — así se evita generar tráfico de carga contra el ALB de producción por accidente.

**Credencial:** el endpoint exige un JWT válido; pásalo por `RAG_LOAD_TEST_TOKEN` (recomendado) o `--token`. Sin ninguno de los dos el script se detiene con un mensaje claro (`--allow-unauthenticated` para el caso excepcional de un backend sin auth).

**Nota sobre "primer token":** el backend calcula la respuesta completa y luego la trocea en fragmentos que emite sin pausas — no hay streaming incremental real de tokens. El tiempo a la "primera fracción de respuesta" reportado por el script es, en la práctica, casi igual al tiempo total; no lo interpretes como time-to-first-token.

**Cuándo usarlo:** para validar manualmente latencia/estabilidad del backend bajo concurrencia antes o después de un despliegue. Ejecutarlo contra producción requiere autorización explícita — no es un chequeo de solo lectura.

---

## Utilidades ChromaDB (`utils/`)

### `utils/chroma_count.py`

Consulta la **cantidad de documentos** en la colección de ChromaDB.

```bash
uv run python -m utils.chroma_count
```

---

### `utils/chroma_clear.py`

**Elimina todos los documentos** de una colección de ChromaDB. **Simulación (dry-run) por defecto** — sin `--execute` solo muestra host, colección y cantidad de documentos, sin borrar nada. `--collection` es obligatorio (sin valor por defecto: nunca borra una colección resuelta implícitamente del entorno).

```bash
# Dry-run: solo describe la colección, no borra nada
uv run python -m utils.chroma_clear --collection rag_playas

# Borrado real: además exige escribir el nombre EXACTO de la colección
# como confirmación interactiva (se cancela si no hay terminal disponible)
uv run python -m utils.chroma_clear --collection rag_playas --execute
```

**Precaución:** con `--execute`, operación destructiva. Úsala cuando se quiere re-indexar desde cero.

---

### `utils/list_gemini_models.py`

Lista los **modelos disponibles** en la API de Google GenAI con sus acciones soportadas.

```bash
uv run python -m utils.list_gemini_models
```

**Cuándo usarlo:** Para verificar modelos disponibles o confirmar soporte de tool calling / structured output.

---

## Herramientas externas al runtime del RAG

### Tutorial de construcción de ground truth (`docs/ground-truth/`)

Subsistema autocontenido, ajeno al pipeline de ingesta/servicio del RAG, para
publicar el tutorial interno de construcción de ground truth como una página
web independiente:

- `docs/ground-truth/tutorial2.html` — el tutorial en sí.
- `docs/index.html` — redirige a `./ground-truth/tutorial2.html`.
- `scripts/deploy-tutorial-html.ps1` — despliega **únicamente** ese HTML
  (copiado a una carpeta temporal aislada) al proyecto Vercel
  `atlas-tutorial-groundtruth`; requiere Vercel CLI (`npm i -g vercel`) y
  sesión iniciada (`vercel login`).

```powershell
pwsh scripts/deploy-tutorial-html.ps1            # despliega a producción
pwsh scripts/deploy-tutorial-html.ps1 -Preview   # despliega una preview
```

`docs/ground-truth/` también contiene material relacionado con el mismo
tutorial, no enlazado desde `tutorial2.html`
(`ATLAS_Cartilla_Ground_Truth.md`, `ATLAS_Tutorial_Construccion_Ground_Truth.md`,
`ATLAS_Tutorial_Plataforma.md`, `1.jpeg`). Herramienta del equipo
jurídico/de anotación, no del servicio RAG — no la modifiques al tocar
`backend/rag/` o `frontend/`.

---

## Resumen de uso frecuente

| Tarea | Comando |
|-------|---------|
| Verificar chunks en ChromaDB | `uv run python -m utils.chroma_count` |
| Limpiar ChromaDB para re-indexar | `uv run python -m utils.chroma_clear --collection rag_playas --execute` |
| Instalar Docker en Ubuntu | `sudo bash rag/scripts/install-docker-ubuntu.sh` |
| Prueba de carga contra ECS | `uv run python rag/scripts/load_test.py --url http://localhost:8080 --users 10` |
