# Infraestructura RAG — ECS Fargate

Terraform que provisiona el despliegue en AWS del backend + frontend del
subsistema RAG: ALB, ECS Fargate, ECR, EFS (volumen de Postgres). Esta es
la alternativa a un despliegue de un solo host con Docker Compose — ver
[`../docs/DESPLIEGUE.md`](../docs/DESPLIEGUE.md) para esa otra vía.

No incluye ChromaDB ni Ollama: esos servicios se provisionan por separado
en `../../vector-infraestructura/` (EC2). Tampoco incluye el bucket S3 del
pipeline de datos, provisionado en `../../ingesta/infrastructure/`.

---

## Requisitos previos

- Terraform ≥ 1.7, AWS CLI 2.x, credenciales AWS con permisos para ECS/ECR/ALB/EFS/IAM.
- ChromaDB y Ollama ya desplegados y accesibles (ver `../../vector-infraestructura/`).
- `terraform.tfvars` (copiar de `terraform.tfvars.example`) con, como mínimo,
  `postgres_password`, `jwt_secret_key`, `chroma_host`, `ollama_base_url`, y
  al menos una API key de LLM (`openai_api_key` o `google_api_key`).

## Recursos que provisiona

| Archivo | Recursos |
|---|---|
| `ecs.tf` | Clúster ECS, definición de tarea (backend + sidecar Postgres en la misma tarea), servicios `app` y `frontend` |
| `alb.tf` | Application Load Balancer, listeners, target groups |
| `ecr.tf` | Repositorios ECR para las imágenes de backend y frontend |
| `efs.tf` | Volumen EFS para los datos de Postgres (persisten entre despliegues) |
| `security_groups.tf` | Grupos de seguridad de ALB/ECS/EFS |
| `iam.tf` | Roles y políticas de ejecución/tarea de ECS |
| `variables.tf` | Todas las variables de entrada (ver `terraform.tfvars.example`) |
| `outputs.tf` | `alb_url`, `ecr_backend_url`, `ecr_frontend_url`, `ecs_cluster_name`, `aws_account_id` |

`DATABASE_URL` del backend apunta a `localhost:5432`: el sidecar de
Postgres corre en la misma tarea Fargate que el backend.

## Scripts (`scripts/`)

| Script | Qué hace |
|---|---|
| `deploy.sh [--auto-approve]` | Inicializa Terraform, aplica la infraestructura, construye y sube las imágenes, fuerza el redespliegue de los servicios ECS. Requiere `terraform.tfvars` completo y credenciales AWS en el entorno. |
| `push_images.sh [TAG]` | Construye las imágenes de backend/frontend y las sube a los repositorios ECR (lee las URLs desde los outputs de Terraform). Tag por defecto: `latest`. |
| `start.sh` | Enciende los servicios ECS (`desired_count=1`). Postgres arranca desde el volumen EFS existente — los datos previos se conservan. |
| `stop.sh` | Apaga los servicios ECS (`desired_count=0`) para detener la facturación de cómputo Fargate mientras el sistema no está en uso. Los datos de Postgres persisten en EFS. |
| `export_postgres.sh` | Exporta un volcado de la base de datos Postgres en EFS. |

## Despliegue manual paso a paso

```bash
cd rag/infrastructure
cp terraform.tfvars.example terraform.tfvars   # completar con valores reales
terraform init
terraform plan
terraform apply

# Construir y subir imágenes, y forzar redespliegue
./scripts/push_images.sh
```

O con el script que encadena todo:

```bash
./scripts/deploy.sh --auto-approve
```

## Destruir la infraestructura

```bash
terraform destroy
```

> El volumen EFS de Postgres se elimina con `terraform destroy` salvo que
> se haya configurado explícitamente lo contrario — exporta los datos con
> `scripts/export_postgres.sh` antes de destruir si necesitas conservarlos.
