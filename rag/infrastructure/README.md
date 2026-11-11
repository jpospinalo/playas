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

- Terraform ≥ 1.7, AWS CLI 2.x, Docker, Python ≥ 3.11 y credenciales AWS
  con permisos para ECS, ECR, ALB, EFS, IAM y EC2.
- ChromaDB y Ollama disponibles para el despliegue directo de ECS. Ver
  [infraestructura vectorial](../../vector-infraestructura/README.md).
- `terraform.tfvars` (copiar de `terraform.tfvars.example`) con, como mínimo,
  `postgres_password`, `jwt_secret_key`, `chroma_host`, `ollama_base_url`, y
  una credencial de proveedor LLM (`openai_api_key`, `openrouter_api_key` o
  `google_api_key`).
- Session Manager Plugin para cargar usuarios semilla o exportar PostgreSQL
  mediante ECS Exec. La exportación usa también `uv` y el entorno de `rag/`.

En AWS Academy, configurar las credenciales de la sesión de laboratorio y
usar el rol `LabRole`. El
[README de infraestructura vectorial](../../vector-infraestructura/README.md#requisitos-previos)
describe cómo cargar las credenciales y preparar el par de claves.

En `corpus`, `scripts/deploy.sh` verifica Gold A y el modelo antes de aplicar
Terraform y selecciona `rag_playas_gold_a_cc7bf44b54a9`, incluso si el archivo
de variables conserva otro nombre. Debe haberse completado el paso vectorial;
ECS solo verifica y no restaura datos. La colección anterior permanece intacta.
Ver [entrega y recuperación](../../data/chroma-releases/README.md).

Terraform solo es necesario para **provisionar/desplegar** (`deploy.sh`,
`push_images.sh`, `terraform plan/apply/destroy`). Las operaciones diarias
de encendido/apagado (`start.sh`/`stop.sh`) **no usan Terraform en absoluto**:
descubren los recursos directamente contra la API de AWS por tag/nombre
(EC2 por `tag:Name`, ECS por nombre de clúster/servicio, el ALB por su
nombre), así que funcionan aunque no tengas el state de Terraform
inicializado localmente — solo requieren AWS CLI 2.x (y `curl`, únicamente
`start.sh`).

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
| `start.sh` | Enciende **todo** el cómputo de la aplicación: primero las EC2 de ChromaDB y Ollama (descubiertas por tag, sin Terraform), verificadas por HTTP; luego, solo si responden, los servicios ECS `app` y `frontend`. No termina hasta comprobar por HTTP que el backend (`/api/ready`) y el frontend responden — ver detalle abajo. |
| `stop.sh` | Apaga **todo** el cómputo en el orden inverso: primero ECS (confirmando, con una sola consulta agregada, que AMBOS servicios quedaron simultáneamente en `desired=running=pending=0`), y solo entonces las EC2 de ChromaDB/Ollama. No depende del ALB ni de `curl` en ningún punto. Los datos de Postgres (EFS) y de ChromaDB/Ollama (EBS) se conservan. |
| `export_postgres.sh` | Exporta un volcado de la base de datos Postgres en EFS. |

### Encendido y apagado seguro (`start.sh` / `stop.sh`)

Para encender desde la raíz del repositorio:

```bash
./rag/infrastructure/scripts/start.sh
```

Para apagar:

```bash
./rag/infrastructure/scripts/stop.sh
```

Ambos scripts descubren sus recursos directamente contra AWS CLI (sin leer
outputs ni state de Terraform): las EC2 de ChromaDB/Ollama por su tag
`Name` (fallan si encuentran cero o más de una coincidencia, en vez de
asumir un ID), y el clúster/servicios ECS por nombre. Son idempotentes
(seguros de ejecutar más de una vez o después de una ejecución parcial) y
terminan con código de salida `0` únicamente cuando la operación completa
fue verificada:

- **Región y clúster**: la región se resuelve como `AWS_REGION` >
  `AWS_DEFAULT_REGION` > `us-east-1` (en ese orden de precedencia); el
  clúster ECS se resuelve como `RAG_ECS_CLUSTER` > `rag-playas-prod`. Ambas
  variables son opcionales.
- **Identidad antes de mutar**: antes de encender o apagar nada, ambos
  scripts muestran la cuenta AWS activa, el ARN de las credenciales en uso
  y la región resuelta (vía `aws sts get-caller-identity`). Si defines
  `RAG_EXPECTED_AWS_ACCOUNT_ID` (12 dígitos), el script falla antes de
  cualquier mutación si la cuenta activa no coincide — una salvaguarda
  opcional contra ejecutar el script con las credenciales de la cuenta
  equivocada.
- `start.sh` verifica primero que el ALB exista y esté `active` (antes de
  encender nada), y no enciende ECS si ChromaDB u Ollama no responden por
  HTTP primero (evita que el backend intente arrancar con sus dependencias
  externas apagadas); no declara éxito hasta que `/api/ready` del backend y
  `/` del frontend responden a través del ALB. Es el único de los dos
  scripts que requiere `curl` y que depende del ALB.
- `stop.sh` no depende del ALB en ningún punto (debe poder apagar aunque el
  ALB esté degradado o no responda) y no requiere `curl`. No apaga las EC2
  de ChromaDB/Ollama hasta confirmar, con una sola llamada agregada a
  `describe-services` (no solo esperar `services-stable`, que no distingue
  "estable en 0" de otros fallos), que se devolvieron exactamente los dos
  servicios esperados y que **ambos** están simultáneamente en
  `desiredCount=runningCount=pendingCount=0` — que uno de los dos lo esté y
  el otro no (o que AWS devuelva menos servicios de los pedidos) se trata
  como fallo, sin apagar ninguna EC2.
- Cada `update-service` (encendido o apagado) se protege con una
  comprobación explícita e inmediata del `desiredCount` que AWS devuelve en
  la misma respuesta: si no coincide exactamente con el valor solicitado (1
  al encender, 0 al apagar) — vacío, `None` o cualquier otro valor — el
  script falla de inmediato en vez de seguir esperando un estado que nunca
  pidió.
- Cada operación mutante (`start-instances`, `stop-instances`,
  `update-service`) se marca como **intentada** justo antes de invocarla —
  no después de recibir respuesta. Esto es deliberado: si AWS llega a
  aplicar la operación y la respuesta se pierde (red, timeout), un fallo
  posterior igual se trata como **estado potencialmente parcial**, nunca
  como si no hubiera pasado nada. Ningún fallo hace rollback automático de
  lo que ya se haya intentado: si un script termina con código distinto de
  cero **después de haber intentado alguna mutación**, imprime el estado
  observable de los cuatro componentes (2 EC2 + 2 servicios ECS) y comandos
  de diagnóstico sugeridos. **La forma normal de reconciliar un estado
  potencialmente parcial es volver a ejecutar el mismo script** — cada paso
  comprueba el estado real antes de actuar, así que no repite una mutación
  innecesaria.
- Una interrupción (Ctrl+C / `SIGTERM`) es distinta de un fallo: **no**
  imprime el diagnóstico de los cuatro componentes ni hace ninguna llamada
  adicional a AWS — solo un aviso corto indicando si ya se había intentado
  alguna operación mutante antes de interrumpir (estado potencialmente
  parcial) o no. Para ver el estado real tras una interrupción, usa los
  comandos de diagnóstico del README o vuelve a ejecutar el mismo script.
- Solo usan `start-instances`/`stop-instances` sobre las EC2 (nunca
  `terminate-instances`) y `desired_count` sobre ECS: no destruyen
  Terraform, no liberan las Elastic IP, no borran EBS/EFS, no reindexan ni
  reimportan datos. Un ciclo `stop.sh` → `start.sh` conserva discos,
  identificadores, endpoints y los datos de ChromaDB/Postgres.
- Se mantiene HTTP en todo momento (el ALB de este despliegue solo expone
  `http://...`; `start.sh` falla si el DNS del ALB no está `active`, en vez
  de intentar reescribirlo a HTTPS).
- **Apagar no deja el costo en cero**: el ALB, EFS, EBS, CloudWatch y las
  direcciones Elastic IP de ChromaDB/Ollama siguen existiendo y pueden
  seguir generando costo aunque ECS y las EC2 estén apagados.

Precondiciones operativas que los scripts **no pueden verificar por sí
solos** — son responsabilidad de quien los ejecuta:

- No ejecutar `start.sh` y `stop.sh` al mismo tiempo, ni desde dos
  terminales u operadores distintos.
- No ejecutar `stop.sh` mientras un flujo autorizado (ingesta, evaluación,
  mantenimiento) esté usando ChromaDB u Ollama — estas EC2 son recursos
  compartidos por otros componentes del repositorio, y el script no tiene
  forma fiable de detectar esa actividad desde afuera.

## Despliegue en AWS

### Desplegar desde un bastion

El [script de bastion](../../scripts/deploy_bastion_ec2.sh) instala las
herramientas en una EC2 y coordina el aprovisionamiento vectorial y ECS.
Requiere AWS CLI, Git y Python 3.11 o posterior en el equipo local, un par de
claves EC2 y el archivo `.pem` correspondiente. Ejecutarlo desde una copia
limpia y publicada de `corpus` con una sola asignación `OPENAI_API_KEY` en
`rag/.env`. La clave se transfiere por stdin.

Desde la raíz del repositorio:

```bash
KEY_FILE=/ruta/a/vockey.pem ./scripts/deploy_bastion_ec2.sh
```

La opción `BOOTSTRAP_ONLY=1` instala las herramientas en el bastion y
termina antes de los despliegues de Terraform. Para reutilizar una instancia,
resguardar sus estados y configuraciones y preparar un directorio de trabajo
nuevo. El script exige que la ruta `~/playas` esté libre antes de copiar
credenciales o semillas.

### Desplegar desde un equipo preparado

Primero seguir el
[despliegue vectorial](../../vector-infraestructura/README.md#despliegue-con-el-script).
Ese paso verifica Gold A y prepara `rag/infrastructure/terraform.tfvars` con
los endpoints y los secretos de PostgreSQL y JWT. Completar en ese archivo
la credencial del proveedor LLM y ejecutar desde la raíz:

```bash
./rag/infrastructure/scripts/deploy.sh
```

El script admite `--auto-approve` para entornos cuya aplicación de
Terraform ya esté aprobada.

### Despliegue manual

Preparar primero Chroma y Ollama según
[infraestructura vectorial](../../vector-infraestructura/README.md#preparación-manual)
y [verificar Gold A](../../data/chroma-releases/README.md#verificar-una-colección-existente).
Crear `rag/infrastructure/terraform.tfvars` desde el ejemplo si falta y
completar las variables con los valores del entorno. Para Gold A, usar
`chroma_host` y `chroma_port` del servidor verificado, fijar
`chroma_collection = "rag_playas_gold_a_cc7bf44b54a9"` y configurar
`ollama_base_url` y `ollama_embedding_model = "embeddinggemma:latest"`.

El ejemplo parte de la raíz del repositorio y usa los nombres y la región
por defecto.

```bash
cd rag/infrastructure
terraform init
terraform plan
terraform apply

# Construir y subir imágenes
./scripts/push_images.sh

aws ecs update-service --cluster rag-playas-prod --service rag-playas-prod-app \
  --force-new-deployment --region us-east-1
aws ecs update-service --cluster rag-playas-prod --service rag-playas-prod-frontend \
  --force-new-deployment --region us-east-1
```

### Consultar estado y logs

Desde la raíz del repositorio, obtener la URL de ATLAS y consultar los logs.
La salida `alb_url` ya incluye el esquema HTTP.

```bash
terraform -chdir=rag/infrastructure output -raw alb_url
aws logs tail /ecs/rag-playas-prod-app --region us-east-1 --follow
aws logs tail /ecs/rag-playas-prod-frontend --region us-east-1 --follow
```

La [guía de uso de Gold A](../docs/DESPLIEGUE.md#usar-gold-a-en-atlas)
describe la consulta de comprobación para el equipo.

## Exportar PostgreSQL

El exportador usa un bucket S3 como puente y descarga el volcado en
`data/backups/`. Desde la raíz del repositorio:

```bash
./rag/infrastructure/scripts/export_postgres.sh --bucket "nombre-del-bucket"
```

La copia permanece en S3 por defecto. La opción `--delete-remote` la retira
después de la descarga.

## Destruir la infraestructura

```bash
terraform destroy
```

> El volumen EFS de Postgres se elimina con `terraform destroy` salvo que
> se haya configurado explícitamente lo contrario — exporta los datos con
> `scripts/export_postgres.sh` antes de destruir si necesitas conservarlos.
