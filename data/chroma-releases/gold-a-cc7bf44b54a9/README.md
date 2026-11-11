# Respaldo lógico Gold A — gold-a-cc7bf44b54a9

Contiene 5.862 registros de Gold del commit `323fda951c74099fa92602b7ada634542b967ee3`: 5.852 vectores originales del paquete padre y diez vectores nuevos verificados. Actualiza once payloads respecto al padre, incluidos los metadatos de Rodadero con su vector conservado. No cambia los documentos de Bronze, Silver o Gold ni la colección activa.

## Contenido y comprobación

La carpeta contiene exactamente cinco archivos: `GOLD_A.jsonl.gz`, `PROCEDENCIA_GOLD_A.json`, `manifest.json`, `verificar_paquete.py` y este README. Con Python 3.11 o posterior, desde cualquier ubicación:

```sh
python3 -I -S -B /ruta/a/gold-a-cc7bf44b54a9/verificar_paquete.py
```

El verificador usa solo la biblioteca estándar. Lee la carpeta que contiene el script; no necesita el repositorio, rutas históricas, credenciales, servicios ni modelos. Comprueba integridad de los archivos, cabecera, 5.862 IDs y orden, cuerpos, metadata, inputs de embedding, procedencia, 768 componentes por vector y partición 5.852/10. Calcula las coincidencias finales y conserva los tres pares históricos. No modifica ni repara archivos. Un retorno distinto de cero exige detenerse.

Los hashes de vectores describen los números JSON originales; la comprobación Float32 no sustituye, redondea ni normaliza esos valores. La metadata adapta los tipos admitidos por Chroma: omite None, deriva keywords_str y serializa listas/objetos como cadenas JSON. El input de embedding añade los encabezados de la receta ce71bedba019d7cd54952a22fb2973fc462924f6549baec808c6f059ea531739; el cuerpo documental se conserva por separado.

## Perfil y procedencia

Perfil A: embeddinggemma:latest, digest 85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1, Ollama 0.40.13, dimensión 768, contexto 2.048, parallel 1 y batch/microbatch 2.048. Solo los diez inputs nuevos se contaron en esta ejecución: 194–407 tokens, total 3.080, incluidos especiales. El resto conserva vectores y evidencia del padre `gold-a-769a847f096b`.

El sidecar separa la fuente documental actual (commit, ruta, línea y hashes) del origen del vector (padre o resultado P2 aceptado). Guarda anclas de recibos completos; `partial_sources` está vacío. La cadena forense externa completa P0/P1/P2 no está incluida y debe conservarse aparte. Ninguna comprobación del paquete necesita abrir esas referencias históricas. La carpeta se nombra por los doce primeros caracteres del SHA-256 del gzip; no hay hashes circulares.

## Alcance y reservas

Es una preparación lógica offline: no se ha importado, restaurado de forma independiente ni activado esta versión; tampoco se ha ensayado su durabilidad. El verificador acredita el archivo y su procedencia anclada, no el estado de Chroma ni la calidad jurídica de las respuestas. No se traslada el contrato HNSW de una imagen antigua a esta versión. Antes de importar se requiere un plan con colección nueva y preservación de la activa. La reserva histórica de SQLite en la capa del contenedor, fuera del volumen previsto, permanece pendiente.

Preparación: directorio 0700 y archivos 0600. Un clone o una copia puede cambiar permisos; la integridad portable se comprueba por contenido y tipos de archivo. La nueva versión conserva las reservas documentales previas; no modifica main, corpus, infraestructura ni configuraciones de despliegue.
