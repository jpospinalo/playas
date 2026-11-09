# Respaldos lógicos Gold de Chroma

Esta carpeta conserva paquetes versionados con documentos, metadata adaptada y vectores existentes. En la rama `corpus`, el despliegue selecciona Gold A `cc7bf44b54a9` y configura `rag_playas_gold_a_cc7bf44b54a9` después de verificarla. Publicar el código no ejecuta ese despliegue ni modifica la colección de una aplicación que ya está funcionando.

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

## Restaurador del despliegue de corpus

El punto de entrada es [deploy_bastion_ec2.sh](../../scripts/deploy_bastion_ec2.sh).
Exige una copia limpia y publicada de `corpus`, comprueba el paquete antes de
crear recursos y clona esa rama verificando el commit. La entrega se obtiene
del repositorio: no se copian automáticamente exports locales antiguos.

[restore_gold_release.py](../restore_gold_release.py) verifica y restaura la
entrega fija, con biblioteca estándar de Python 3.11 o posterior:

```sh
# Solo lectura local: sin AWS, Chroma u Ollama.
python3 -I -S -B data/restore_gold_release.py --check

# Operación remota: ejecutar solo con el destino confirmado y sin otras escrituras.
python3 -B data/restore_gold_release.py --execute \
  --host <chroma-host> --port 8000 \
  --ollama-base-url http://<ollama-host>:11434 \
  --receipt /ruta/recibo-nuevo.jsonl
```

El recibo debe estar fuera del repositorio, ser nuevo y tener su carpeta con
permisos `0700`; se conserva ante
fallos. Los scripts crean esa carpeta bajo `~/.local/state/playas-corpus/`.
Resguardar los recibos antes de terminar el laboratorio. El restaurador no solicita
embeddings, no borra colecciones y no escribe en `rag_playas`. Si la colección
versionada ya existe, solo la verifica: reutiliza una coincidencia completa y
se detiene ante una carga parcial o diferente. No continúa ni corrige lotes de
una ejecución incierta. `--verify-only` comprueba un destino existente sin
crearlo ni escribir; el script de ECS lo usa antes de aplicar su configuración.

La colección, los modelos y el destino se configuran después de la verificación.
Un fallo no permite volver automáticamente al export de julio. Los scripts de
esta rama fuerzan la colección versionada también frente a un `tfvars` antiguo.
Ejecutar Terraform manualmente fuera de los scripts requiere conservar esa
selección explícita y hacer previamente las mismas comprobaciones.

## Controles de recuperación

La recuperación requiere una configuración operativa nueva y explícita. Las direcciones, claves públicas, UUID y aprobaciones de un laboratorio anterior no se convierten en valores predeterminados.

1. Acreditar servidor, acceso, tenant/database, runtime y capacidad actuales. Identificar la colección activa e inventariar los UUID preexistentes; protegerlos contra escrituras y conservar sus referencias de contenido.
2. Usar el nombre versionado. Si existe, verificarlo por completo sin escribir; si falta, crear una sola colección con UUID nuevo, sin adoptar el del ensayo anterior. No usar `--recreate` ni borrar colecciones. El cambio de configuración del RAG ocurre después de la verificación.
3. Cargar exclusivamente los registros y vectores existentes del paquete. No ejecutar ingesta, reindexar Gold ni generar embeddings documentales. Los datos no necesitan un modelo para restaurarse; el camino de despliegue consulta Ollama por lectura para comprobar la compatibilidad del modelo que después usará el RAG.
4. Registrar intención y resultados durables, cargar serialmente y comprobar readback por ID: cuerpos, metadata con sus tipos, dimensión, representación vectorial acreditada y conteos. Al terminar, exigir 5.862 IDs únicos sin faltantes ni extras, configuración del índice correcta y preservación de las colecciones protegidas. Un ACK o un conteo aislados no bastan. Estas comprobaciones no califican la calidad de recuperación.
5. Conservar fallos y resultados inciertos sin reenviar automáticamente. Conciliar por lectura antes de continuar. Dejar la colección nueva inactiva; la selección por el RAG y cualquier despliegue son operaciones separadas.

El archivo de evidencia de validación conserva los auxiliares ejecutados, recibos, seis vectores de consulta, prompts y trazas. **Es evidencia archivada, no el restaurador actual.** Sus auxiliares fijan rutas, roles y destinos particulares: no ejecutar directamente sus CLI históricas. La herramienta actual está fuera de los cinco archivos inmutables del paquete.

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

## Alcance de la validación y conservación

La restauración lógica y la prueba funcional de seis casos se completaron en el laboratorio del 8 de noviembre de 2026 sin activar la candidata. El PASS técnico coexistió con hallazgos de respaldo textual; no acredita calidad jurídica global, funcionamiento completo de la aplicación o superioridad frente a otras colecciones. Las observaciones del laboratorio no prueban su disponibilidad futura.

En el entorno del ensayo histórico SQLite residía en `/data`, fuera del
montaje previsto. El aprovisionamiento actual corrige ese montaje para
contenedores nuevos. No migra los existentes ni acredita su durabilidad;
tampoco conserva EBS si se destruye la instancia o termina el laboratorio.
El respaldo lógico permite reconstruir los datos y no es una copia física del
servidor. El resultado histórico de persistencia permanece sin cambios.

Estos archivos tampoco incluyen pesos o imágenes de modelos, PostgreSQL y sus interacciones, secretos ni estados Terraform. El responsable de cada recurso debe conservar lo necesario bajo su política de respaldo y acceso, fuera del corpus y de la documentación pública. Conservar la cadena externa completa cuando se necesite su alcance forense, además del paquete y la evidencia de validación versionados.

## Pendientes antes de usar esta entrega en otro despliegue

La preservación de los datos no depende del laboratorio. Antes de desplegar,
publicar el commit de `corpus`, confirmar destino, capacidad, perfil y ausencia
de otras escrituras, y conservar los recibos. Los controles offline de los
scripts no sustituyen un ensayo real. La persistencia debe verificarse en el
servidor nuevo; no aplicar automáticamente estas instrucciones a una colección
activa o a una instancia reutilizada con datos sin respaldar.
