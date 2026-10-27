# Calidad de documentos: v1 frente a v2

> **Ninguna cifra de este documento está validada por abogados.** Son
> mediciones objetivas de texto y artefactos con umbrales operativos. No
> demuestran que el contenido jurídico sea correcto, completo o útil para
> responder consultas. Una bandera verde no es una garantía y una roja no es
> por sí sola un error.

Corrida medida: 55 documentos v2 (26 jurisprudencia, 29 normativa) del corpus
real de 56 archivos (dos archivos son byte a byte idénticos y comparten
doc_id). Linux en t3.large, Tesseract spa, chunker `legacy` (1000/200) para que
sea comparable con v1. Comando:

```bash
python -m ingest.offline quality --layers-root <capas> --state <estado> --cache <caché> \
  --input-dir ../data/raw --compare-v1 ../data/documents
```

Duración: 24,9 s, 119 MB de RSS. En una corrida anterior del mismo comando,
dos ejecuciones seguidas dieron salidas idénticas en sha256; la versión final
se ejecutó una sola vez. `data/documents/` (v1) quedó sin cambios (`git status` limpio).

Salidas en `<layers-root>/quality/`: `quality_report.json`,
`quality_por_documento.csv` y `quality_report.md`. Métricas, umbrales y reglas
de comparación están en [MEDALLION.md](MEDALLION.md#informe-objetivo-de-calidad).

## Comparación agregada v1 / v2

Medias por documento sobre los 54 pares emparejados. Ambos lados se miden con
el mismo código. Al v1 se le quita el marcado Markdown y al v2 la cabecera de
plantilla de cada chunk (`chunk_body`), así que se compara texto con texto.

| Métrica | v1 | v2 | Docs con regresión |
|---|---:|---:|---:|
| Caracteres extraídos | 63.667 | 75.620 | 0 por debajo del 80 % de v1 |
| `invalid_pct` | 0,00 | 0,00 | 0 |
| `mojibake_pct` | 0,0148 | 0,00 | 0 |
| Chunks por documento | 98,4 | 97,6 | cambio neutral |
| Mediana de chunk (car.) | 677 | 892 | cambio neutral |
| p5 de chunk (car.) | 218 | 461 | cambio neutral |
| Chunks cortos (%) | 10,49 | 0,57 | 1 |
| Duplicados exactos | 0,41 | 0,06 | 0 |
| Cuasi-duplicados | 5,54 | 8,11 | **8** |

Lectura:

- v2 extrae más texto en promedio, y ningún documento queda por debajo del
  80 % de v1.
- El mojibake de v1 (`BogotÆ`, `diecisØis`) desaparece en v2.
- Los chunks son más uniformes: hay muchos menos fragmentos cortos.
- **Los cuasi-duplicados empeoran** en 8 documentos. Antes de quitar la
  cabecera de plantilla el agregado v2 era 4,19, porque la cabecera hacía
  distintos chunks que en el cuerpo son casi iguales. La cifra válida es 8,11.
  No diagnostiqué la causa. Hipótesis por verificar:
  - líneas de encabezado y pie repetidas que v2 conserva: 16 documentos tienen
    `repeated_corner_lines` en amarillo y 1 en rojo;
  - documentos 100 % OCR cuyo v1 era una transcripción más limpia.

Sin pareja: el doc_id `376195b0…` (Gabriel Carrero) corresponde a dos archivos
idénticos con dos Markdown v1 distintos. Se informa como `coincidencia_ambigua`
y no se compara. No hay documentos v1 sin pareja.

## Documentos con regresiones objetivas

Solo 8 documentos tienen al menos una regresión; el informe completa la lista
de diez con los dos mayores cambios neutrales.

| doc_id | Documento | Regresión |
|---|---|---|
| `06139556` | REMAC 5 DIMAR (.md) | chunks cortos 8,2→13,9 %; cuasi-dup. 131→245 |
| `b0006c94` | Reglamento de playas de Turbo (100 % OCR) | cuasi-dup. 1→44 |
| `873661fb` | AP Miguel Ángel Enciso | cuasi-dup. 0→25 |
| `8767ea35` | AP Inversiones E y D | cuasi-dup. 0→20 |
| `0c26a7cb` | AP Rodrigo Martínez Silva | cuasi-dup. 10→21 |
| `e820f079` | Decreto 1120/2013 UAC (100 % OCR) | cuasi-dup. 0→8 |
| `98cdaeff` | CE 2009 José Palencia | cuasi-dup. 0→5 |
| `735e943c` | CE 2011 José Caballero | cuasi-dup. 0→2 |

`quality_report.md` muestra extractos v1 y v2 lado a lado para los cinco
primeros.

Qué hacer con ellos:

1. REMAC 5 es Markdown de origen: revisar si las líneas «Página N» y la cabecera
   «REGLAMENTO MARÍTIMO COLOMBIANO / REMAC» repetida por página deben
   eliminarse en la limpieza.
2. Turbo y el Decreto 1120 son escaneados: revisar el OCR página a página y
   decidir si conviene un texto digital alternativo.
3. Las acciones populares (Enciso, Inversiones E y D, Martínez Silva):
   inspeccionar los pares cuasi-duplicados en `silver/<doc_id>.jsonl` para
   saber si son encabezados repetidos o texto realmente reiterado (citas,
   transcripciones de la demanda).

## Banderas por documento (v2 solo)

Total sobre 55 documentos × 36 métricas: 1.370 verdes, 187 amarillas, 114 rojas
y 199 no medidas.

| Métrica | Rojo | Amarillo | Observación |
|---|---:|---:|---|
| `ocr_pct` | 19 | 0 | 19 documentos son escaneados al 100 %; indica dependencia de OCR, no error |
| `metadata_conflicts` | 20 | 0 | campos `sala` (17), `magistrado_ponente` (5), `radicado` (4) |
| `near_duplicates` | 18 | 7 | ver sección anterior |
| `metadata_present` / `metadata_absent` | 16 | 38 | sesgada: ver limitaciones |
| `review_queue_entries` | 16 | 39 | consecuencia de lo anterior |
| `structure_coverage_pct` | 3 | 17 | |
| `sections_detected` | 2 | 0 | |
| `removed_pct` | 2 | 14 | limpieza que quita >30 % del texto |
| `alphabetic_pct` | 1 | 0 | Decreto 1120 (OCR) |
| `repeated_corner_lines` | 1 | 16 | |

No medidas: `embedding_dimension`, `invalid_vectors` y `chunks_without_vector`
(la corrida usó `--fake-embeddings`), y `ocr_confidence` en documentos sin OCR.

Documentos con más banderas rojas:

1. `e820f079`, Decreto 1120/2013 UAC: 8 rojas (OCR, alfabético bajo, sin
   secciones, metadatos).
2. `b0006c94`, reglamento de Turbo: 5 rojas.
3. Ocho decretos únicos y códigos escaneados (`1c5b6f4a`, `1d4aab7f`,
   `726fdd46`, `78af35fe`, `907021ed`, `a22960ee`, `a863f489`) y `4b3572e3`:
   4 rojas cada uno, casi todas por OCR y metadatos.

Hallazgo concreto de metadatos: en una sentencia del Consejo de Estado el
regex tomó como magistrado ponente «. Dr. Gustavo Aponte Santos, en cita.»,
que es una cita de un concepto anterior, y en otro documento la cabecera de
plantilla mostró «Decreto 2324/1984 — DIRECCION GENERAL MARITIMA» como norma
principal porque era la primera norma citada. Los conflictos de `sala` vienen
de frases como «Sala a decidir el recurso…» que el regex acepta como nombre de
sala.

## Limitaciones de estas métricas

- Las reglas de metadatos son las mismas para jurisprudencia y normativa, así
  que un decreto aparece con `radicado`, `sala` o `magistrado_ponente` ausentes
  aunque no le apliquen. Las banderas de metadatos de normativa exageran el
  problema.
- `ocr_pct` mide cuánto OCR se usó, no cuántos errores tiene.
  `ocr_confidence` es la media de Tesseract, no una tasa de error verificada.
- Los cuasi-duplicados usan SimHash con distancia de Hamming ≤ 3 sobre
  64 bits. Detectan similitud textual, no repetición jurídica relevante.
- Los caracteres «extra» de v2 pueden ser texto útil o ruido (encabezados
  repetidos, OCR). La métrica no los distingue.
- El emparejamiento v1/v2 es por nombre de archivo normalizado. Un renombrado
  en v1 aparecería como «sin pareja».
- Nada de esto mide la calidad de recuperación ni de respuesta del RAG.
