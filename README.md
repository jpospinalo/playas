# ATLAS — Orientación normativa y jurisprudencial sobre playas

Sistema agéntico de orientación normativa y jurisprudencial sobre playas en Colombia.

## Organización y documentación

| Directorio | Responsabilidad | Documentación |
|---|---|---|
| `rag/` | API, agente, frontend y evaluación | [RAG](rag/README.md) |
| `ingesta/` | Conversión, seccionado y enriquecimiento de documentos | [Ingesta](ingesta/README.md) |
| `vector-infraestructura/` | EC2 de ChromaDB y Ollama | [Infraestructura vectorial](vector-infraestructura/README.md) |
| `rag/infrastructure/` | ECS, ALB, ECR y EFS de la aplicación | [Infraestructura RAG](rag/infrastructure/README.md) |
| `ingesta/infrastructure/` | Bucket S3 de las capas del pipeline | [Scripts de ingesta](ingesta/docs/SCRIPTS.md#infraestructura-responsabilidades) |
| `data/` | Corpus versionado, respaldo de ChromaDB y datos semilla | [Datos](data/README.md) |
| `scripts/` | Herramientas que coordinan varios componentes | Despliegue desde bastion, descrito abajo |

`rag/` e `ingesta/` son proyectos Python independientes, con sus propios
entornos y locks. El frontend utiliza Bun dentro del workspace de `rag/`.
No se necesita mover carpetas ni compartir un entorno para trabajar en ellos.
Para desarrollo local, empezar por el README del componente. Ver
[CONTRIBUTING.md](CONTRIBUTING.md) para ramas, alcance y controles de cambios.

La guía siguiente describe el despliegue AWS con HTTP. Provisionar o importar
datos no es lo mismo que encender una aplicación ya desplegada: para uso diario
consultar [encendido y apagado](#apagarencender-el-cómputo-ahorro-de-costos).

## Evaluación de calidad

La calidad de ATLAS se mide con [RAGAS](https://docs.ragas.io/) contra el ground truth del equipo jurídico. Resultados, informe para el equipo jurídico y registro de evaluaciones: [`rag/evaluation/README.md`](rag/evaluation/README.md#resultados-sobre-el-ground-truth-v02).

---

## Requisitos previos

| Herramienta | Versión mínima |
|---|---|
| Terraform | 1.7 |
| AWS CLI | 2.x |
| Session Manager Plugin (AWS) | cualquiera |
| Docker | 24.x |
| Python + uv | cualquiera |

**Credenciales AWS** con permisos para EC2, ECS, ECR, ALB, EFS y IAM (rol `LabRole` en AWS Academy):

> No es necesario configurar credenciales si se usa una máquina Cloud9, pero esta debe tener al menos 100 GB en disco.

```bash
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_SESSION_TOKEN=...      # solo AWS Academy
```

- **Instalar Terraform (Ubuntu):**

```bash
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install terraform
```

- **Instalar uv:**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- **Instalar Session Manager Plugin (Ubuntu):** requerido por `deploy.sh` para el paso de ECS Exec (`aws ecs execute-command`) que importa los usuarios semilla a PostgreSQL.

```bash
# x86_64 (usar ubuntu_arm64 en la URL si `uname -m` devuelve aarch64)
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb" -o session-manager-plugin.deb
sudo dpkg -i session-manager-plugin.deb
session-manager-plugin   # debe responder "was installed successfully"
```

## Despliegue automático

### 1. Infraestructura vectorial (ChromaDB + Ollama en EC2)

El script crea las EC2 con IP estática, actualiza las variables de entorno del proyecto con las IPs resultantes e importa los datos en ChromaDB:

```bash
./vector-infraestructura/scripts/deploy.sh --auto-approve
```

Al finalizar, `rag/.env` y `rag/infrastructure/terraform.tfvars` quedan actualizados con `CHROMA_HOST` y `OLLAMA_BASE_URL`.

### 2. Aplicación RAG en ECS Fargate

El paso anterior generó `rag/infrastructure/terraform.tfvars` con `postgres_password` y `jwt_secret_key` ya completados. Solo falta agregar al menos una API key de LLM:

```hcl
# Al menos una de las siguientes
openai_api_key     = "..."   # OpenAI (prioridad 1)
openrouter_api_key = "..."   # OpenRouter (prioridad 2)
google_api_key     = "..."   # Gemini (prioridad 3)
```

Despliega la infraestructura ECS, construye las imágenes y las sube a ECR:

```bash
./rag/infrastructure/scripts/deploy.sh --auto-approve
```

### 3. Verificar

```bash
# URL pública
terraform -chdir=rag/infrastructure output -raw alb_url

# Logs en tiempo real
aws logs tail /ecs/rag-playas-prod-app      --region us-east-1 --follow
aws logs tail /ecs/rag-playas-prod-frontend --region us-east-1 --follow
```

La salida `alb_url` ya incluye `http://`; no agregar otro prefijo:

- `/` → Frontend Next.js
- `/api/` → Backend FastAPI
- `/api/health` → Healthcheck

### 4. Exportar la base de datos PostgreSQL

Fargate no permite `docker cp` ni montar el volumen EFS directamente, así que
el script sube el dump a un bucket S3 puente (vía URL prefirmada) y luego lo
descarga localmente en `data/backups/`:

```bash
./rag/infrastructure/scripts/export_postgres.sh --bucket <nombre-bucket-s3>
```

Por defecto conserva la copia en el bucket S3; usar `--delete-remote` para
borrarla tras la descarga. Requiere el Session Manager Plugin (mismo requisito
que `deploy.sh`, usa `aws ecs execute-command`).

### Alternativa: desplegar desde una EC2 bastion

Si no quieres instalar Terraform, Docker, AWS CLI, etc. localmente, `scripts/deploy_bastion_ec2.sh`
crea una EC2 temporal que hace todo el trabajo por ti: instala las dependencias, clona el
repositorio y ejecuta los pasos 1 y 2 del despliegue automático descritos arriba.

Requisitos:

- Key pair `vockey` ya creado en EC2 (estándar en AWS Academy) y su `.pem` descargado localmente
- `rag/.env` con `OPENAI_API_KEY` configurada (se transfiere a la EC2 por stdin, nunca queda
  expuesta en logs ni en el script)

```bash
KEY_FILE=/ruta/a/vockey.pem ./scripts/deploy_bastion_ec2.sh
```

La EC2 (`m4.large`, Ubuntu 24.04, 50GB, instance profile `LabInstanceProfile`) queda como bastion
tras el despliegue — puedes conectarte por SSH para depurar o repetir pasos manualmente. El script
imprime cada paso que ejecuta, tanto localmente como dentro de la instancia.

Usa `BOOTSTRAP_ONLY=1` para solo aprovisionar la EC2 e instalar dependencias (git, Docker,
Terraform, AWS CLI, uv, Session Manager Plugin) sin ejecutar los despliegues de Terraform:

```bash
BOOTSTRAP_ONLY=1 KEY_FILE=/ruta/a/vockey.pem ./scripts/deploy_bastion_ec2.sh
```

Si ya existe una instancia bastion (`rag-playas-bastion`) corriendo, el script la reutiliza en
vez de crear una nueva.

> Antes de repetir este despliegue, el responsable de infraestructura debe
> resguardar los estados Terraform y las configuraciones locales del bastion.
> El script actual elimina su checkout `~/playas` antes de clonar, también si
> reutiliza la instancia. No usarlo para encendido/apagado diario ni asumir que
> conserva esos archivos. `BOOTSTRAP_ONLY=1` tampoco evita esa eliminación.

---

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

Inicializa Terraform, aplica la infraestructura, construye las imágenes y fuerza el redespliegue:

```bash
cd rag/infrastructure
terraform init
terraform apply

./scripts/push_images.sh

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
| ChromaDB | EC2 `t3.large` 30 GB | 8000 |
| Ollama | EC2 `t3.large` 20 GB | 11434 |

---

## Apagar/encender el cómputo (ahorro de costos)

`stop.sh` apaga primero ambos servicios ECS (`app` y `frontend`) y confirma
que quedaron en cero; después detiene las EC2 de ChromaDB y Ollama. No elimina
EFS, EBS, índices ni conversaciones:

```bash
./rag/infrastructure/scripts/stop.sh
```

`start.sh` verifica primero las EC2 y sus servicios HTTP, enciende ECS y solo
declara éxito cuando el backend (`/api/ready`) y el frontend responden a través
del ALB:

```bash
./rag/infrastructure/scripts/start.sh
```

> Apagar no deja el costo en cero: ALB, EFS, EBS, CloudWatch y Elastic IP siguen
> existiendo. No ejecutar ambos scripts simultáneamente ni apagar mientras
> ingesta, evaluación o mantenimiento estén usando ChromaDB/Ollama. Requieren
> credenciales AWS vigentes; iniciar primero el lab si se utiliza AWS Academy.
> Ver [requisitos y comprobaciones](rag/infrastructure/README.md#encendido-y-apagado-seguro-startsh--stopsh).

---

## Destruir la infraestructura

```bash
# ECS Fargate — revisar el plan y exportar PostgreSQL antes de destruir
terraform -chdir=rag/infrastructure destroy

# EC2 vectorial
terraform -chdir=vector-infraestructura destroy
```

> `terraform destroy` elimina también el EFS administrado por este stack,
> salvo protección configurada explícitamente. Exportar PostgreSQL antes de
> destruir. Destruir las EC2 elimina sus discos e índice: conservar también un
> respaldo de ChromaDB. Para ahorrar cómputo sin destruir datos, usar `stop.sh`.
