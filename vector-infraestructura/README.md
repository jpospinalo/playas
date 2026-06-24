# vector-infraestructura

Infraestructura Terraform para las instancias EC2 que soportan el sistema RAG:

- **Ollama** — servidor de embeddings (`embeddinggemma:latest`) en el puerto 11434
- **ChromaDB** — base de datos vectorial (`chromadb/chroma:1.3.5`) en el puerto 8000

Cada instancia recibe una **Elastic IP estática** que no cambia entre reinicios.

---

## Requisitos previos

| Herramienta | Versión mínima | Verificar |
|---|---|---|
| Terraform | 1.7 | `terraform version` |
| AWS CLI | 2.x | `aws --version` |
| Python + uv | cualquiera | `uv --version` |
| curl | cualquiera | `curl --version` |

**Credenciales AWS** configuradas con permisos para crear EC2, Elastic IP y Security Groups:

```bash
# Opción A — variables de entorno (AWS Academy / voclabs)
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...

# Opción B — perfil en ~/.aws/credentials
aws configure --profile rag-playas
export AWS_PROFILE=rag-playas
```

**Key pair de EC2** existente en la región `us-east-1`. El nombre por defecto es `vockey`; se puede cambiar en `variables.tf` o pasando `-var key_pair_name=<nombre>`.

---

## Despliegue con el script

El script `scripts/deploy.sh` automatiza todo el proceso en un solo comando.

### Ejecución

Desde la raíz del repositorio (`playas/`):

```bash
./vector-infraestructura/scripts/deploy.sh
```

Con aprobación automática (sin confirmación interactiva de Terraform):

```bash
./vector-infraestructura/scripts/deploy.sh --auto-approve
```

### Qué hace el script

```
1. terraform apply          — crea/actualiza las EC2 con sus Elastic IPs
2. terraform output         — lee las IPs estáticas resultantes
3. Actualiza rag/.env       — CHROMA_HOST y OLLAMA_BASE_URL
4. Actualiza rag/infrastructure/terraform.tfvars — chroma_host y ollama_base_url
5. Espera que ChromaDB responda (máx. 7 min)
6. Importa data/*.jsonl.gz  — carga los documentos en ChromaDB
```

### Salida esperada

```
▶ Ejecutando terraform apply en vector-infraestructura...
  ... (plan de Terraform) ...
▶ Leyendo IPs estáticas desde Terraform outputs...
✓ ChromaDB IP: 54.x.x.x
✓ Ollama IP:   3.x.x.x
▶ Actualizando rag/.env...
✓ .env actualizado
▶ Actualizando rag/infrastructure/terraform.tfvars...
✓ terraform.tfvars actualizado
▶ Esperando a que ChromaDB esté disponible en 54.x.x.x:8000...
   (la EC2 necesita instalar Docker y arrancar el contenedor — puede tardar varios minutos)
..........
✓ ChromaDB disponible
▶ Importando chroma-rag_playas_magdalena-20260617-195224.jsonl.gz → ChromaDB 54.x.x.x:8000...
  Importing 1842 documents in batches of 100 ...
  1842/1842 (100.0%)  312 docs/s  errors=0
✓ Importación completada

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Despliegue completado

  CHROMA_HOST     = 54.x.x.x
  OLLAMA_BASE_URL = http://3.x.x.x:11434

  Archivos actualizados:
    • rag/.env
    • rag/infrastructure/terraform.tfvars

  Para aplicar en ECS Fargate:
    cd rag/infrastructure && terraform apply
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### Después del script

Si también tienes el stack ECS Fargate desplegado, aplica los nuevos valores:

```bash
cd rag/infrastructure
terraform apply
```

---

## Despliegue manual paso a paso

Si prefieres ejecutar cada paso por separado:

```bash
# 1. Inicializar Terraform (solo la primera vez)
cd vector-infraestructura
terraform init

# 2. Ver el plan
terraform plan

# 3. Aplicar
terraform apply

# 4. Ver las IPs asignadas
terraform output

# 5. Importar datos a ChromaDB manualmente
cd ../rag
uv run python3 ../data/import_to_chromadb.py \
  ../data/chroma-rag_playas_magdalena-20260617-195224.jsonl.gz \
  --host <chromadb_public_ip> \
  --port 8000
```

---

## Archivos de importación

El script toma el `.jsonl.gz` más reciente que encuentre en `data/`. Para generar un nuevo archivo de exportación desde una instancia ChromaDB existente consulta la documentación de la pipeline de ingesta.

---

## Destruir la infraestructura

```bash
cd vector-infraestructura
terraform destroy
```

> Las Elastic IPs se liberan automáticamente. Los datos en las EC2 **no persisten** — si necesitas conservar el índice ChromaDB, exporta la colección antes de destruir.

---

## Variables

| Variable | Por defecto | Descripción |
|---|---|---|
| `project` | `rag-playas` | Prefijo usado en nombres y tags |
| `environment` | `prod` | Entorno (`dev`, `staging`, `prod`) |
| `key_pair_name` | `vockey` | Key pair EC2 para acceso SSH |

Para sobreescribir alguna variable crea un archivo `terraform.tfvars` en este directorio:

```hcl
key_pair_name = "mi-key-pair"
environment   = "dev"
```
