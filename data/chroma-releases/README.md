# Respaldos lógicos Gold de Chroma

Esta carpeta conserva paquetes versionados con documentos, metadata adaptada y vectores existentes. Un respaldo, una colección restaurada y la colección utilizada por el RAG son estados distintos: publicar o recuperar un paquete no activa esa colección.

## Paquetes y evidencia

| Entrega | Función |
| --- | --- |
| [gold-a-cc7bf44b54a9](gold-a-cc7bf44b54a9/README.md) | Respaldo actual: 5.862 registros, 5.852 vectores reutilizados y diez nuevos; once payloads actualizados. |
| [gold-a-769a847f096b](gold-a-769a847f096b/README.md) | Paquete padre histórico; conservarlo sin cambios. |
| [Validación de cc7bf44b54a9](gold-a-cc7bf44b54a9-validation/README.md) | Evidencia posterior de restauración, comparación y prueba funcional; anclajes en [validation.json](gold-a-cc7bf44b54a9-validation/validation.json). |

El paquete actual contiene exactamente cinco archivos: `GOLD_A.jsonl.gz`, `PROCEDENCIA_GOLD_A.json`, `manifest.json`, `verificar_paquete.py` y `README.md`. Son inmutables: no editar, recomprimir ni actualizar sus estados para registrar ensayos posteriores. El manifiesto y su README describen el momento del empaquetado; la validación posterior se conserva por separado.

El corpus documental fuente corresponde a `323fda951c74099fa92602b7ada634542b967ee3`. Los cinco archivos se incorporaron a `corpus` en `9c5dc755e327ad02000f7721d08e8728c8f163f8`.

En la comprobación remota del 8 de noviembre de 2026, `corpus` apuntaba a ese commit y la rama predeterminada era `main`, en `813b6aab5407bbfc362ce9a6b05aadc34ef0a1d7`, sin este paquete. Es una observación fechada, no una garantía sobre referencias futuras ni una integración en `main`.

## Obtener y comprobar el respaldo

Trabajar en una copia nueva de `corpus`, registrar el commit recibido y elegir la carpeta exacta del paquete:

```sh
git clone --branch corpus --single-branch https://github.com/jpospinalo/playas.git playas-corpus
git -C playas-corpus rev-parse HEAD
python3 -I -S -B playas-corpus/data/chroma-releases/gold-a-cc7bf44b54a9/verificar_paquete.py
```

El commit `9c5dc755…` identifica la incorporación del respaldo probado; la guía y su evidencia pueden añadirse en commits posteriores sin cambiar los cinco archivos del paquete. Conservar también ese commit de entrega al archivar una copia.

El verificador usa Python 3.11 o posterior y solo su biblioteca estándar. Comprueba los cinco archivos, registros, IDs, payloads, vectores y procedencia anclada; no conecta servicios, genera embeddings ni necesita rutas históricas. Un retorno distinto de cero exige detenerse. Conservar juntos los cinco archivos y sus nombres; la carpeta puede trasladarse sin cambiar el contenido.

## Recuperar en un servidor nuevo

La recuperación requiere una configuración operativa nueva y explícita. Las direcciones, claves públicas, UUID y aprobaciones de un laboratorio anterior no se convierten en valores predeterminados.

1. Acreditar servidor, acceso, tenant/database, runtime y capacidad actuales. Identificar la colección activa e inventariar los UUID preexistentes; protegerlos contra escrituras y conservar sus referencias de contenido.
2. Elegir un nombre nuevo, acreditar su ausencia y crear una sola colección sin reutilización. Su UUID será nuevo: no exigir ni adoptar el UUID del ensayo anterior. No usar `--recreate`, borrar colecciones ni cambiar la configuración activa del RAG.
3. Cargar exclusivamente los registros y vectores existentes del paquete, con un restaurador revisado para ese destino. No ejecutar ingesta, reindexar Gold ni generar embeddings documentales. La restauración de estos datos no necesita Ollama ni un LLM.
4. Registrar intención y resultados durables, cargar serialmente y comprobar readback por ID: cuerpos, metadata con sus tipos, dimensión, representación vectorial acreditada y conteos. Al terminar, exigir 5.862 IDs únicos sin faltantes ni extras, búsquedas técnicas comprobadas y preservación de las colecciones protegidas. Un ACK o un conteo aislados no bastan.
5. Conservar fallos y resultados inciertos sin reenviar automáticamente. Conciliar por lectura antes de continuar. Dejar la colección nueva inactiva; la selección por el RAG y cualquier despliegue son operaciones separadas.

El archivo de evidencia de validación conserva los auxiliares ejecutados, recibos, seis vectores de consulta, prompts y trazas. **Es evidencia archivada, no una herramienta portable de restauración o despliegue.** Sus auxiliares fijan rutas, roles y destinos particulares: deben adaptarse y revisarse antes de otra ejecución. No ejecutar directamente sus CLI históricas.

## Perfil y lectura vectorial

| Elemento | Contrato acreditado |
| --- | --- |
| Embeddings documentales | `embeddinggemma:latest`, digest `85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1` |
| Runtime de generación del respaldo | Ollama `0.40.13`, dimensión 768, contexto 2.048, parallel 1, batch/microbatch 2.048 |
| Lectura Chroma ensayada | `chromadb/chroma:1.3.5`, ejecutor nativo x86_64 |
| ID de imagen observado | `sha256:111a6bd768be19721f5b4e88567d0e1d1f5c2ab5161129e711c0a431e667b128` |
| Índice de la colección de ensayo | cosine, `ef_construction=100`, `ef_search=100`, `max_neighbors=16`, `resize_factor=1.2`, `sync_threshold=1000` |

El ID observado de imagen identifica el runtime acreditado; no es una instrucción de descarga. La receta y los hashes completos están en el manifiesto. Una etiqueta `latest` o una dimensión coincidente no prueban compatibilidad: las consultas sobre esta colección deben usar embeddings compatibles con ese perfil.

Los números JSON fuente, su transporte Float32 little-endian/Base64 y el readback HNSW tienen representaciones distintas. En el build acreditado se comparó la lectura con la transformación Float32 esperada; no se normalizó el respaldo ni se usaron vectores exportados de lectura como fuente. Si cambia imagen, arquitectura o implementación, revisar ese contrato antes de aceptar el readback; no ampliar tolerancias para producir un PASS.

## Relación con el despliegue existente

El bootstrap [deploy_bastion_ec2.sh](../../scripts/deploy_bastion_ec2.sh) clona la rama predeterminada remota sin fijar `corpus` o commit. Tanto ese bootstrap como [el despliegue vectorial](../../vector-infraestructura/scripts/deploy.sh) buscan únicamente `data/*.jsonl.gz` por fecha de modificación; no seleccionan estas subcarpetas. El despliegue vectorial importa a `rag_playas`. Ejecutarlos no equivale a recuperar ni activar este Gold nuevo.

[import_to_chromadb.py](../import_to_chromadb.py) puede leer el formato del gzip, pero permite reutilizar una colección, borrarla con `--recreate` y continuar después de errores por lote. La cabecera de este paquete no fija host, puerto o colección: sin argumentos operativos explícitos el importador utiliza sus valores predeterminados. No ofrece las garantías de la recuperación supervisada acreditada.

Antes de otro despliegue, fijar por separado commit, paquete, destino y configuración de modelos. Los scripts actuales que descargan Ollama y `embeddinggemma:latest` no fijan por sí solos el perfil de esta tabla. Consultar también [Despliegue del RAG](../../rag/docs/DESPLIEGUE.md) y [Scripts operacionales](../../rag/docs/SCRIPTS.md).

## Alcance de la validación y conservación

La restauración lógica y la prueba funcional de seis casos se completaron en el laboratorio del 8 de noviembre de 2026 sin activar la candidata. El PASS técnico coexistió con hallazgos de respaldo textual; no acredita calidad jurídica global, funcionamiento completo de la aplicación o superioridad frente a otras colecciones. Las observaciones del laboratorio no prueban su disponibilidad futura.

Se conserva la reserva de persistencia: en el entorno ensayado SQLite residía en `/data`, fuera del montaje previsto. No se corrigió infraestructura ni se probó supervivencia ante recrear el contenedor. El respaldo lógico permite reconstruir los datos; no es una copia física del servidor.

Estos archivos tampoco incluyen pesos o imágenes de modelos, PostgreSQL y sus interacciones, secretos ni estados Terraform. El responsable de cada recurso debe conservar lo necesario bajo su política de respaldo y acceso, fuera del corpus y de la documentación pública. Conservar la cadena externa completa cuando se necesite su alcance forense, además del paquete y la evidencia de validación versionados.

## Pendientes antes de usar esta entrega en otro despliegue

La preservación de los datos ya no depende del laboratorio. La operación automática todavía debe incorporar selección explícita del código y respaldo, una restauración revisada para el destino nuevo, verificación del modelo de consultas y comprobación de persistencia. Esos cambios del despliegue corresponden a una etapa separada. Las fuentes de los auxiliares quedaron archivadas para poder preparar esa etapa sin depender de esta máquina o del laboratorio anterior.
