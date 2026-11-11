# Respaldos lógicos Gold de Chroma

Los paquetes contienen documentos, metadata adaptada y vectores listos para
restaurar. El despliegue de `corpus` selecciona Gold A `cc7bf44b54a9` y
configura `rag_playas_gold_a_cc7bf44b54a9` después de verificarla.

## Paquetes

| Entrega | Función |
| --- | --- |
| [gold-a-cc7bf44b54a9](gold-a-cc7bf44b54a9/README.md) | Respaldo actual: 5.862 registros, 5.852 vectores reutilizados y diez nuevos; once payloads actualizados. |
| [gold-a-769a847f096b](gold-a-769a847f096b/README.md) | Paquete padre y referencia de procedencia de los vectores reutilizados. |

Conservar juntos los cinco archivos del paquete actual: `GOLD_A.jsonl.gz`,
`PROCEDENCIA_GOLD_A.json`, `manifest.json`, `verificar_paquete.py` y
`README.md`. El verificador comprueba sus huellas. El README y el
manifiesto internos describen el estado al empaquetar.

El corpus documental fuente corresponde a
`323fda951c74099fa92602b7ada634542b967ee3`. El paquete se incorporó en
`9c5dc755e327ad02000f7721d08e8728c8f163f8` y se puede verificar y restaurar
de forma autónoma. Para cotejar campos e IDs, consultar el
[inventario y la descripción de Gold](../README.md).

## Obtener y comprobar el respaldo

Trabajar en una copia nueva de `corpus`, registrar el commit recibido y elegir la carpeta exacta del paquete:

```sh
git clone --branch corpus --single-branch https://github.com/jpospinalo/playas.git playas-corpus
git -C playas-corpus rev-parse HEAD
python3 -I -S -B playas-corpus/data/chroma-releases/gold-a-cc7bf44b54a9/verificar_paquete.py
```

El verificador usa Python 3.11 o posterior y solo su biblioteca estándar.
Comprueba localmente archivos, registros, IDs, textos, metadata, vectores y
procedencia. Conservar los nombres y bytes de los cinco archivos al copiar el
paquete. Resolver cualquier error del verificador antes de restaurar.

## Restaurador del despliegue de corpus

El punto de entrada es [deploy_bastion_ec2.sh](../../scripts/deploy_bastion_ec2.sh).
Exige una copia limpia y publicada de `corpus`, comprueba el paquete antes de
crear recursos y clona esa rama verificando el commit. La entrega se obtiene
del repositorio: no se copian automáticamente exports locales antiguos.

[restore_gold_release.py](../restore_gold_release.py) verifica y restaura la
entrega fija con Python 3.11 o posterior. Desde la raíz del repositorio se
puede comprobar el paquete local:

```sh
python3 -I -S -B data/restore_gold_release.py --check
```

Para preparar una colección ausente, el responsable confirma el servidor,
el espacio y el perfil de consulta. Ejecuta el comando de la sección
siguiente con `--execute` como único selector de modo y un recibo nuevo.
El restaurador carga los vectores del paquete en la colección versionada.
Si ya existe, la reutiliza únicamente cuando coincide completa. Ante una
carga parcial o una escritura incierta, cotejar el estado antes de continuar.

## Verificar una colección existente

Desde la raíz del repositorio y con acceso a los servicios, sustituir los
hosts y puertos de ejemplo por los que usa el backend. El restaurador
consulta `default_tenant/default_database` en Chroma. Guardar el recibo en
una carpeta privada nueva fuera del repositorio.

```sh
chroma_host='chroma.equipo.example'
chroma_port=8000
ollama_url='http://ollama.equipo.example:11434'
recibos="$(mktemp -d /tmp/atlas-gold.XXXXXX)"
python3 -I -S -B data/restore_gold_release.py --execute --verify-only \
  --host "$chroma_host" --port "$chroma_port" \
  --ollama-base-url "$ollama_url" --receipt "$recibos/verificacion.jsonl"
```

La comprobación en modo de lectura debe devolver `REUSED_VERIFIED`,
5.862 registros y `Chroma_writes: 0`. Coteja IDs, textos, metadata tipada,
vectores, configuración del índice y perfil del modelo. Guardar el recibo
con las evidencias operativas del equipo. Si falla, revisar el destino y el
resultado antes de conectar el RAG. La
[configuración del backend](../../rag/docs/DESPLIEGUE.md#conectar-el-rag-a-gold-a)
detalla las variables y la consulta de comprobación.

## Perfil y lectura vectorial

| Elemento | Contrato acreditado |
| --- | --- |
| Embeddings documentales | `embeddinggemma:latest`, digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1` |
| Runtime de generación del respaldo | Ollama `0.40.13`, dimensión 768, contexto 2.048, parallel 1, batch/microbatch 2.048 |
| Runtime Chroma verificado | `chromadb/chroma:1.3.5`, Linux/AMD64 |
| ID de imagen verificado | `sha256:111a6bd768be19721f5b4e88567d0e1d1f5c2ab5161129e711c0a431e667b128` |
| Índice HNSW | cosine, `ef_construction=100`, `ef_search=100`, `max_neighbors=16`, `resize_factor=1.2`, `sync_threshold=1000` |

El ID observado de imagen identifica el runtime acreditado; no es una instrucción de descarga. La receta y los hashes completos están en el manifiesto. Una etiqueta `latest` o una dimensión coincidente no prueban compatibilidad: las consultas sobre esta colección deben usar embeddings compatibles con ese perfil.

Los números JSON fuente, su transporte Float32 little-endian/Base64 y el readback HNSW tienen representaciones distintas. En el build acreditado se comparó la lectura con la transformación Float32 esperada; no se normalizó el respaldo ni se usaron vectores exportados de lectura como fuente. Si cambia imagen, arquitectura o implementación, revisar ese contrato antes de aceptar el readback; no ampliar tolerancias para producir un PASS.

## Relación con el despliegue existente

El bootstrap [deploy_bastion_ec2.sh](../../scripts/deploy_bastion_ec2.sh),
[el despliegue vectorial](../../vector-infraestructura/scripts/deploy.sh) y
[el despliegue ECS](../../rag/infrastructure/scripts/deploy.sh) de `corpus`
comparten la selección de la entrega corregida. La colección anterior
`rag_playas`, el export de julio y el paquete padre se conservan como históricos.
No se renombran ni se migran automáticamente. `main` conserva su propio código
de despliegue hasta una integración aprobada aparte.

[import_to_chromadb.py](../import_to_chromadb.py) puede leer el formato del gzip, pero permite reutilizar una colección, borrarla con `--recreate` y continuar después de errores por lote. La cabecera de este paquete no fija host, puerto o colección: sin argumentos operativos explícitos el importador utiliza sus valores predeterminados. No ofrece las garantías de la recuperación supervisada acreditada.

Los scripts que descargan Ollama y `embeddinggemma:latest` no garantizan por sí
solos el perfil de esta tabla. Antes de aceptar la restauración, el restaurador
contrasta versión, digest, dimensión y contexto declarados por Ollama y se
detiene ante diferencias. Estas consultas no acreditan paralelismo, tamaños de
lote ni la identidad completa del runtime histórico. Consultar también
[Despliegue del RAG](../../rag/docs/DESPLIEGUE.md) y
[Scripts operacionales](../../rag/docs/SCRIPTS.md).

## Estado de la entrega

Se restauraron los 5.862 registros en una colección aislada y se cotejaron
IDs, textos, metadata y vectores. Una consulta autenticada, con el backend
`517c399` y el modelo de embeddings restaurado, devolvió HTTP 200 y cuatro
fuentes que coincidieron con Gold. Para medir la cobertura de consultas y
el respaldo jurídico de las respuestas, usar el
[banco y las herramientas de evaluación](../../rag/docs/SCRIPTS.md#evaluación-del-rag).

El paquete recupera la colección lógica. Para consultar desde un entorno
nuevo, el equipo necesita también un Ollama con el modelo del perfil
verificado. El archivo `MODELO_OLLAMA_v1_1.tar` se restauró con éxito y su
SHA-256 es `29994bee6e99dd7519ba38f3cd089bf963fb6a21bf46a2eddba2d554978e247d`.
Solicitar al responsable la copia compartida del modelo y conservar por
separado PostgreSQL, sus interacciones, los secretos y los estados Terraform.
La operación de la infraestructura y el montaje persistente de Chroma se
documentan en
[infraestructura vectorial](../../vector-infraestructura/README.md#persistencia).
