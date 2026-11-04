# Respaldo lógico Gold A — gold-a-769a847f096b

Esta versión contiene los registros y vectores originales del corpus Gold. `manifest.json` es la fuente de los conteos, hashes, procedencia, configuración y estado fechado de la entrega.

## Verificación offline

Con Python 3.12 o posterior y su biblioteca estándar, ejecutar desde cualquier directorio:

```bash
python3 -B /ruta/a/gold-a-769a847f096b/verificar_paquete.py
```

El comando lee únicamente esta carpeta. Si termina con código 0, los archivos, registros y procedencia concuerdan; no conecta con Chroma, AWS u Ollama ni altera datos. Mantener exactamente los cinco archivos listados por el manifiesto. Los modos 0600 registrados describen la preparación; un clone Git puede producir archivos 0644 sin cambiar su contenido.

`GOLD_A.jsonl.gz` y `PROCEDENCIA_GOLD_A.json` se conservan byte a byte. El manifiesto interno del gzip registra la generación anterior a la carga; su estado histórico `not_loaded` no describe el estado posterior de la importación. Las rutas históricas de la procedencia no se abren ni son requisitos de recuperación en otro equipo.

## Recuperación posterior

La importación previa fue verificada según el cierre identificado en el manifiesto. Esta entrega todavía no acredita un ensayo independiente de recuperación ni durabilidad del servidor. El estado remoto se cita como última observación documentada; no se consultó durante el empaquetado.

Para ensayar recuperación se debe autorizar y fijar un destino explícito, crear una colección nueva de forma exclusiva y preservar las colecciones existentes. Se importan los vectores originales, sin generar embeddings ni cargar Ollama. El controlador supervisado deberá comprobar todos los registros y las huellas protegidas; este paquete no ejecuta una restauración por defecto.

Conservar separados los hashes del vector fuente, el transporte Float32 y su lectura reconstruida por HNSW. El contrato de comparación acreditado está ligado a la imagen y arquitectura registradas; un cambio de compilación requiere revisar el verificador antes de escribir. La configuración del modelo es procedencia de generación, no una instalación incluida en esta carpeta.

## Uso y reservas

Esta subcarpeta queda fuera de la selección no recursiva `data/*.jsonl.gz` de los despliegues actuales. Para conservar esa propiedad, no mover el gzip a la raíz de `data/` ni a `seed_data`. Su publicación en `corpus` no activa la colección ni modifica `main`. El backup histórico del repositorio permanece separado.

La verificación P3 de origen fue una lectura paginada compuesta, no transaccional. Las dos consultas técnicas se acreditan por hashes y código sellado; las listas detalladas de resultados no se conservaron. Esta entrega mínima no incluye el archivo forense completo.

Sigue vigente la reserva observada de persistencia: la base efectiva de Chroma estaba fuera del bind previsto, dentro de la capa del contenedor. Recrearlo puede perder sus colecciones. El responsable del despliegue debe resolver y comprobar esa persistencia antes de una activación. Los vectores originales aquí conservados permiten preparar un ensayo lógico de reconstrucción; dicho ensayo y la evaluación funcional del RAG son etapas posteriores.

Los recibos posteriores se ligan al SHA de este manifiesto y conservan su propia fecha; no se reescribe retrospectivamente esta versión para cambiar el estado al empaquetar.
