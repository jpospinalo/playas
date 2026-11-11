# Corrección de caché y signos numéricos

Rama: feat/ingesta-fiabilidad-ocr. Sin commits ni push.

La caché contrasta directamente los SHA256 de las fuentes con la procedencia
de la corrida que produjo los CSV. Regenerar informes auxiliares no permite
reutilizar métricas de fuentes modificadas. Se conservan los prefijos ante
dígitos y signos numéricos; estricto retira únicamente citas `> ` ante texto
no numérico y viñetas `- ` / `* ` ante letra.

419 tests aprobados. Ruff check y format --check correctos (13 archivos).
Calibración: 64/64 comprobaciones de métricas y 12/12 controles de bucles, en contenido y estricto.
comparar_fuentes.py ejecutado completo con Python -I -B, sin --reanudar.
Las cuatro corridas de evaluar_fase5.py terminaron con codigo 0 y sin faltantes.

## Fase 5: CER contenido (%)

| Conjunto | Variante | Paginas / docs | Antes | Ahora | Delta (pp) |
|---|---|---:|---:|---:|---:|
| ajuste_ocr | base | 111 / 8 | 17,954833 | 17,954833 | +0.00000000 |
| ajuste_ocr | tsv_fix | 111 / 8 | 1,652260 | 1,652260 | +0.00000000 |
| ajuste_ocr | z2_psm3 | 111 / 8 | 1,652260 | 1,652260 | +0.00000000 |
| ajuste_ocr | z2_psm6 | 111 / 8 | 2,086850 | 2,087191 | +0.00034166 |
| ajuste_ocr | z300dpi_psm3 | 111 / 8 | 2,234104 | 2,234104 | +0.00000000 |
| validacion_ocr | base | 188 / 13 | 23,484347 | 23,485062 | +0.00071464 |
| validacion_ocr | tsv_fix | 188 / 13 | 1,936452 | 1,937319 | +0.00086633 |
| todos_ocr | base | 299 / 21 | 21,604402 | 21,604882 | +0.00048041 |
| todos_ocr | tsv_fix | 299 / 21 | 1,839832 | 1,840404 | +0.00057224 |
| todos_digital | base | 918 / 34 | 1,063418 | 1,063416 | -0.00000168 |
| todos_digital | tsv_fix | 918 / 34 | 1,063418 | 1,063416 | -0.00000168 |

A dos decimales, en fase 5 cambia validación base: 23,48% -> 23,49%. Los demás valores mantienen el redondeo previo.

## Fase 3: CER contenido (%)

| Comparacion | Nivel / conjunto | Estrato | Antes | Ahora | Delta (pp) |
|---|---|---|---:|---:|---:|
| S_mio_vs_U | pagina / paginas_elegibles | total | 6,276058 | 6,276190 | +0.00013259 |
| S_mio_vs_U | pagina / paginas_elegibles | digital | 1,063418 | 1,063416 | -0.00000168 |
| S_mio_vs_U | pagina / paginas_elegibles | OCR | 21,604402 | 21,604882 | +0.00048041 |
| S_prof_vs_U | documento / documentos_completos_comparables | total | 12,011924 | 12,026676 | +0.01475189 |
| S_prof_vs_U | documento / documentos_completos_comparables | digital | 10,454197 | 10,470451 | +0.01625404 |
| S_prof_vs_U | documento / documentos_completos_comparables | OCR | 20,853908 | 20,868554 | +0.01464665 |

## Integridad y procedencia

- Huellas directas en procedencia.json: 53 Markdown U, 159 archivos bronce S_mio y 53 blobs S_prof (objeto Git y SHA256 de bytes).
- comprobar_cache sobre las fuentes actuales devuelve True; las regresiones rechazan U aun regenerando integridad.json y bronces aun regenerando repetibilidad.json.
- 147 archivos protegidos sin cambios por SHA256: entrada completa, muestra revisada, clave, manifiesto, evaluacion y recortes.
- Consistencia verificada: 4270 filas de paginas, 406 documentales y 108 agregados (numeradores, denominadores y cocientes).
- Las adjudicaciones se conservan tambien al recalcular sin --reanudar; la regeneracion explicita de la muestra mantiene su rechazo a sobrescribir notas.

Los logs de pytest y las cinco corridas se encuentran en esta carpeta. Los resultados completos y sus IC estan en ../fase3 y ../fase5.
