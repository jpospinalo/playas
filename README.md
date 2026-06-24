# ATLAS — Guía de despliegue

Sistema agéntico de orientación normativa y jurisprudencial sobre playas en Colombia.

Esta guía cubre el despliegue completo en AWS: servicios de vectores en EC2 y la aplicación RAG en ECS Fargate.

---

## Requisitos previos

| Herramienta | Versión mínima |
|---|---|
| Terraform | 1.7 |
| AWS CLI | 2.x |
| Docker | 24.x |
| Python + uv | cualquiera |
| Bun | 1.x |

**Credenciales AWS** con permisos para EC2, ECS, ECR, ALB, EFS y IAM (rol `LabRole` en AWS Academy):

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...      # solo AWS Academy
```

---

## Despliegue automático

### 1. Infraestructura vectorial (ChromaDB + Ollama en EC2)

El script crea las EC2 con IP estática, actualiza las variables de entorno del proyecto con las IPs resultantes e importa los datos en ChromaDB:

```bash
./vector-infraestructura/scripts/deploy.sh --auto-approve
```

Al finalizar, `rag/.env` y `rag/infrastructure/terraform.tfvars` quedan actualizados con `CHROMA_HOST` y `OLLAMA_BASE_URL`.

### 2. Aplicación RAG en ECS Fargate

Completa las variables restantes en `rag/infrastructure/terraform.tfvars` (se crean en el paso anterior):

```hcl
postgres_password  = "..."
jwt_secret_key     = "..."

# Al menos una API key de LLM
openai_api_key     = "..."   # OpenAI (prioridad 1)
openrouter_api_key = "..."   # OpenRouter (prioridad 2)
google_api_key     = "..."   # Gemini (prioridad 3)
```

Despliega la infraestructura ECS, construye las imágenes y las sube a ECR:

```bash
cd rag/infrastructure
terraform init
terraform apply -auto-approve

./scripts/push_images.sh

# Forzar nuevo despliegue con las imágenes recién subidas
aws ecs update-service --cluster rag-playas-prod --service rag-playas-prod-app \
  --force-new-deployment --region us-east-1

aws ecs update-service --cluster rag-playas-prod --service rag-playas-prod-frontend \
  --force-new-deployment --region us-east-1
```

### 3. Verificar

```bash
# URL pública
terraform output alb_url

# Logs en tiempo real
aws logs tail /ecs/rag-playas-prod-app      --region us-east-1 --follow
aws logs tail /ecs/rag-playas-prod-frontend --region us-east-1 --follow
```

La aplicación queda disponible en `http://<alb_url>`:

- `/` → Frontend Next.js
- `/api/` → Backend FastAPI
- `/api/health` → Healthcheck

-----------------------------------------------------------------------------------------------------------------------------------------------------------------

## Despliegue manual

### 1. Infraestructura vectorial (ChromaDB + Ollama en EC2)

```bash
cd vector-infraestructura
terraform init
terraform apply

# Ver las IPs asignadas
terraform output
```

Actualiza manualmente `rag/.env` y `rag/infrastructure/terraform.tfvars` con los valores obtenidos:

```bash
# rag/.env
CHROMA_HOST=<chromadb_public_ip>
OLLAMA_BASE_URL=http://<ollama_public_ip>:11434

# rag/infrastructure/terraform.tfvars
chroma_host     = "<chromadb_public_ip>"
ollama_base_url = "http://<ollama_public_ip>:11434"
```

Importa los datos en ChromaDB una vez que la instancia esté disponible:

```bash
cd rag
uv run python3 ../data/import_to_chromadb.py \
  ../data/<archivo>.jsonl.gz \
  --host <chromadb_public_ip> \
  --port 8000
```

### 2. Aplicación RAG en ECS Fargate

Configura las variables de entorno:

```bash
cp rag/infrastructure/terraform.tfvars.example rag/infrastructure/terraform.tfvars
# Editar terraform.tfvars con todos los valores requeridos
```

Despliega la infraestructura:

```bash
cd rag/infrastructure
terraform init
terraform apply
```

Construye y sube las imágenes a ECR:

```bash
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com

./scripts/push_images.sh
```

Fuerza el redespliegue de los servicios ECS con las nuevas imágenes:

```bash
aws ecs update-service --cluster rag-playas-prod --service rag-playas-prod-app \
  --force-new-deployment --region us-east-1

aws ecs update-service --cluster rag-playas-prod --service rag-playas-prod-frontend \
  --force-new-deployment --region us-east-1
```

---

## Arquitectura desplegada

```
Internet
   └── ALB (puerto 80)
        ├── /api/*  → ECS Service: backend (FastAPI :8080) + postgres sidecar (:5432)
        └── /*      → ECS Service: frontend (Next.js :3000)

EFS         ←→ postgres  (persistencia)
ChromaDB EC2 ←→ backend  (índice vectorial)
Ollama EC2   ←→ backend  (embeddings)
```

| Servicio | Tipo | Puerto |
|---|---|---|
| Backend (FastAPI) | ECS Fargate 1024 CPU / 2048 MB | 8080 |
| Frontend (Next.js) | ECS Fargate 256 CPU / 512 MB | 3000 |
| ChromaDB | EC2 `t3.medium` 12 GB | 8000 |
| Ollama | EC2 `t3.large` 20 GB | 11434 |

---

## Destruir la infraestructura

```bash
# ECS Fargate
cd rag/infrastructure && terraform destroy

# EC2 vectorial
cd vector-infraestructura && terraform destroy
```

> Los datos en EFS (PostgreSQL) no se eliminan automáticamente — destruye el sistema de archivos manualmente si es necesario.
