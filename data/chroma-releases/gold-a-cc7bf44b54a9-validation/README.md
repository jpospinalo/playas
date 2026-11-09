# Validación histórica de Gold A — cc7bf44b54a9

Estado: **PASS técnico con hallazgos de respaldo textual; colección inactiva**. Ensayos realizados el 8 de noviembre de 2026 (hora de Bogotá). No se otorga una nota jurídica ni se certifica calidad global.

Este archivo acompaña, sin modificarlo, al paquete inmutable [gold-a-cc7bf44b54a9](../gold-a-cc7bf44b54a9/README.md). Conserva evidencia seleccionada de su restauración y de una pasada funcional real del RAG de `corpus`, commit `9c5dc755e327ad02000f7721d08e8728c8f163f8`. El estado declarado por los manifiestos del paquete original corresponde al momento de empaquetar; estos resultados posteriores se registran aquí por separado.

## Contenido

La entrega tiene exactamente tres archivos: este README, `validation.json` y `evidence.jsonl.gz`. El manifiesto de validación fija el tamaño y SHA-256 del gzip y de este README, así como la lista, tipo, tamaño y hash canónico de sus 42 registros JSONL. No contiene hashes circulares: `validation.json` excluye su propia huella.

El gzip determinístico (sin nombre de archivo ni fecha en la cabecera, mtime=0) contiene:

- Una cabecera de identidad, commits, paquete y muestra.
- La comparación completa de seis preguntas originales sobre tres colecciones: sus 18 resultados con orden, distancias, cuerpos y metadata. No acredita el perfil documental desconocido de la activa ni calidad jurídica.
- La caché histórica del 7 de noviembre: seis vectores de preguntas literales originales y su recibo. El runner histórico completo no está acreditado; esta caché no sustituye los seis vectores de consultas enriquecidas del ensayo funcional y no añade llamadas a su presupuesto.
- El diagnóstico offline actual de selección y generación, como Markdown y datos JSON inertes; sus hipótesis no son cambios implementados ni nuevos experimentos.
- Seis resultados funcionales completos: respuestas, cuerpos, metadata, candidatos, fusión y contexto.
- Seis pares de intención/resultado de embeddings de consulta, con sus vectores completos de 768 dimensiones y hashes.
- Doce pares de intención/resultado LLM: prompts reales, respuestas y uso; sin encabezados de autorización ni credenciales.
- Hechos seleccionados de restauración: 5.862 registros, colección nueva, preservación de tres colecciones anteriores mediante huellas y dos consultas técnicas con vectores documentales. Estas consultas no evalúan calidad jurídica.
- Métricas funcionales saneadas y los seis hallazgos de respaldo textual.
- Seis snapshots exactos de código auxiliar: tres de restauración y tres del ensayo funcional, conservados como texto con SHA-256.

No se incluyen archivos de entorno, claves PEM, known_hosts, credenciales, configuraciones o aprobaciones privadas, capturas AWS privadas, logs, transporte HTTP crudo, volcados completos de las colecciones ni dependencias. Tampoco se incluyen planes históricos o informes de rondas anteriores. La procedencia conserva nombres relativos y hashes de las fuentes seleccionadas; abrir esas rutas históricas no es necesario para leer o contrastar este bundle.

## Resultados y alcance

La restauración lógica quedó completa: 5.862 IDs, cuerpos, metadata y vectores acreditados; 5.852 vectores reutilizados y diez nuevos del perfil A. La huella de lectura `ab86f995dee8aacb8259818255906e5a2f2768dee8cb48b3bbc15479b00672cd` solo se acredita para la imagen/build y transformación Float32 T descritas en los registros. No es una propiedad universal de cualquier versión, arquitectura o índice Chroma.

La pasada funcional comprende seis preguntas independientes del banco provisional, doce invocaciones `gpt-5-nano` y seis embeddings de consulta. Las 24 fuentes seleccionadas conservan cuerpos y metadata; en 13 solo se añadió `id=chunk_id` en RAM. Los contextos y prompts se conservaron. Las citas de formato/rango válido no demuestran respaldo semántico: los hallazgos señalan extrapolaciones y límites de atribución. El banco continúa **Esperando validación final**. No es una evaluación de interfaz, conversaciones persistidas, despliegue completo, RAGAS o superioridad estadística. Las diferencias no se atribuyen causalmente solo a la curación.

No hubo escrituras Chroma durante el ensayo funcional, embeddings documentales, activación ni cambios en `main`. El UUID y los nombres guardados son observaciones históricas; un servidor nuevo asignará sus propios UUID. Este resguardo no autoriza nuevas operaciones o inferencias.

## Recuperación y código histórico

Los cinco archivos del paquete Gold A original incluyen todos los registros y vectores necesarios para restaurarlo sin regenerar embeddings, sin el paquete padre y sin consultar el laboratorio anterior. No son una copia física de Chroma ni del estado completo de AWS. Para recuperar una colección se requiere aprovisionar un runtime Chroma compatible, elegir un destino nuevo, configurar explícitamente el índice y verificar el resultado. Para usar el RAG después se deben aprovisionar externamente los modelos/runtime y verificar sus versiones y digest; no se incluyen sus pesos ni credenciales. Los seis vectores enriquecidos del ensayo funcional y los seis vectores históricos de preguntas originales quedan identificados por separado, con sus textos y hashes. Permiten estudiar las dos ejecuciones sin repetir inferencias; no son intercambiables ni se suman como doce llamadas nuevas. El diagnóstico actual se incluye completo como texto/datos, sin ejecutarse ni trasladarse a la documentación productiva.

**Los seis snapshots de código son evidencia histórica, no una CLI portable. No ejecutarlos directamente.** Contienen rutas, contratos, configuraciones de ejecución y supuestos del laboratorio original; necesitan adaptación revisada y autorización propia antes de cualquier uso operativo. La copia exacta permite estudiar qué se ejecutó, no concede permiso para conectarse o escribir. No se han añadido dependencias ni scripts autoejecutables a esta entrega.

La reserva de persistencia continúa abierta: SQLite se observó fuera del montaje previsto del contenedor. Perder o recrear ese contenedor puede perder la colección. La restauración lógica probada no acredita durabilidad y este resguardo no corrige infraestructura.

## Lectura offline

JSON y JSONL gzip se leen con herramientas estándar; no hace falta importar ni ejecutar el código archivado. Comprobar primero los hashes y tamaños indicados en `validation.json`, y después los hashes canónicos por registro. La serialización canónica usa UTF-8, claves ordenadas, `ensure_ascii=False`, separadores `,`/`:`, y rechaza NaN/Infinity. Los números y textos originales se conservan; no se normalizan vectores ni Unicode para archivarlos.
