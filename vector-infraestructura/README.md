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
| Python | 3.11 | `python3 --version` |
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

1. Comprueba localmente la entrega Gold A fijada, antes de Terraform.
2. Crea o actualiza las EC2 y obtiene sus direcciones.
3. Espera a ChromaDB y al modelo de embeddings, sin generarlos desde el restaurador.
4. Verifica el perfil de consulta y restaura `gold-a-cc7bf44b54a9` en
   `rag_playas_gold_a_cc7bf44b54a9`, con los vectores existentes.
5. Contrasta IDs, textos, metadata y vectores. Si la colección ya existe,
   solo comprueba que coincida completamente; no la sobrescribe ni completa.
6. Solo después actualiza `rag/.env` y `rag/infrastructure/terraform.tfvars`
   con el destino, colección y modelo comprobados.

Un fallo detiene el proceso. No se seleccionan exports por fecha ni se utiliza
el respaldo de julio como alternativa. `rag_playas` y las entregas anteriores
se conservan como históricos. Un recibo de carga incompleta se conserva para
conciliar por lectura antes de decidir una reparación.

### Después del script

Continuar en el
[despliegue de la aplicación en ECS](../rag/infrastructure/README.md#desplegar-desde-un-equipo-preparado).

## Preparación manual

Terraform aprovisiona recursos; no equivale a restaurar y validar el corpus.
Si se usa `terraform apply` directamente, completar después las comprobaciones
y la configuración descritas en la
[guía de recuperación de Gold A](../data/chroma-releases/README.md).

El [restaurador dedicado](../data/restore_gold_release.py) admite `--check`
para verificación estrictamente local. La operación con `--execute` requiere
confirmar el servidor, conservar un recibo nuevo y evitar otras escrituras.
No genera embeddings ni borra colecciones. El importador genérico queda para
recuperaciones históricas expresamente seleccionadas.

## Persistencia

El contenedor nuevo monta `/opt/chroma-data` en `/data`, la ruta utilizada por
la imagen acreditada. Esto no migra contenedores existentes, ni conserva los
datos cuando se destruye la EC2 o termina el laboratorio. No reprovisionar una
instancia con datos sin resguardar. El paquete Gold versionado permite recuperar
la entrega en otro destino compatible.

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
