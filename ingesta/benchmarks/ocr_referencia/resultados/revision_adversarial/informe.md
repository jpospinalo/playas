# Revisión adversarial OCR

Rama: `feat/ingesta-fiabilidad-ocr`. Sin commits ni push. Sin modificaciones en `ingesta/ingest/`, `data/` ni `entrada/`.

Validación: **143 tests aprobados** (123 previos y 20 nuevos casos). Ruff check y format --check: 12 archivos correctos. Calibración: 64 comprobaciones de métricas y 12 controles de bucles aprobados, entre contenido y estricto.

La población se fija con `ocr_pages ∪ ocr_failed_pages` del bronce base, menos las exclusiones de U. Los faltantes abortan con listado y exportación de cobertura; `--permitir-faltantes` los evalúa como hipótesis vacías, conservando todas las páginas. Un texto vacío existente sigue siendo texto disponible. Las tasas sin denominador son `null` en JSON y `n/d` en pantalla; sus réplicas bootstrap se omiten. Se rechaza una evaluación sin páginas.

El desguionado se aplica al guion ASCII original antes de equiparar rayas tipográficas. Los tests exigen discrepancia entre `acceso—\nprohibido` y `accesoprohibido`.

## Fase 5

Contenido; porcentajes. Cada celda muestra estimación [IC95 por documento]. Bootstrap: 2000 réplicas, semilla 20261110. Las 2000 réplicas fueron definidas para las tres métricas en todas estas ejecuciones.

| Conjunto | Variante | Páginas / documentos | CER [IC95] | WER [IC95] | Recall crítico [IC95] | Cobertura |
|---|---|---:|---|---|---|---:|
| ajuste_ocr | base | 111 / 8 | 17,95 [2,33; 31,12] | 34,08 [3,98; 59,08] | 93,23 [87,17; 97,48] | 111/111 |
| ajuste_ocr | tsv_fix | 111 / 8 | 1,65 [0,44; 3,73] | 3,22 [1,37; 5,88] | 93,32 [87,13; 97,39] | 111/111 |
| ajuste_ocr | z2_psm3 | 111 / 8 | 1,65 [0,44; 3,73] | 3,22 [1,37; 5,88] | 93,32 [87,13; 97,39] | 111/111 |
| ajuste_ocr | z2_psm6 | 111 / 8 | 2,09 [0,78; 3,99] | 4,13 [1,83; 6,77] | 92,58 [87,64; 96,52] | 111/111 |
| ajuste_ocr | z300dpi_psm3 | 111 / 8 | 2,23 [0,43; 5,37] | 3,73 [1,23; 7,26] | 94,23 [89,15; 98,30] | 111/111 |
| validacion_ocr | base | 188 / 13 | 23,48 [6,44; 34,20] | 45,18 [12,75; 65,77] | 92,10 [87,28; 96,50] | 188/188 |
| validacion_ocr | tsv_fix | 188 / 13 | 1,94 [0,79; 4,22] | 3,36 [2,01; 5,92] | 91,29 [87,00; 96,12] | 188/188 |
| todos_ocr | base | 299 / 21 | 21,60 [10,02; 30,07] | 41,38 [19,38; 57,69] | 92,49 [88,94; 95,36] | 299/299 |
| todos_ocr | tsv_fix | 299 / 21 | 1,84 [0,81; 3,36] | 3,31 [2,06; 5,04] | 92,00 [88,69; 94,99] | 299/299 |
| todos_digital | base | 918 / 34 | 1,06 [0,63; 1,61] | 1,90 [1,49; 2,41] | 94,25 [92,29; 95,88] | 918/918 |
| todos_digital | tsv_fix | 918 / 34 | 1,06 [0,63; 1,61] | 1,90 [1,49; 2,41] | 94,25 [92,29; 95,88] | 918/918 |

Los CER coinciden exactamente con los valores anteriores: ajuste base 17,95 / tsv_fix 1,65 / z2_psm3 1,65 / z2_psm6 2,09 / 300dpi 2,23; validación 23,48 / 1,94; todos OCR 21,60 / 1,84; digital 1,06 para ambas variantes.

En OCR tampoco cambian WER, recall crítico ni IC de CER. En digital el WER pasa de 1,8955719899% a 1,8965737455% (+0,0010017556 puntos porcentuales); el IC de CER pasa de [0,6296944044%; 1,6140094751%] a [0,6298468820%; 1,6140518653%]. CER y recall digital no cambian. Los IC de WER y recall son nuevas exportaciones.

Resultados actuales: `../fase5/ajuste_ocr.json`, `../fase5/validacion_ocr.json`, `../fase5/todos_ocr.json` y `../fase5/todos_digital.json`; cobertura también en archivos `*_cobertura.json`. Los archivos antiguos `ajuste.json` y `validacion.json` se conservan como históricos.

## Ejecuciones

Desde `ingesta/benchmarks/ocr_referencia`, con `../fidelidad/trabajo/venv/Scripts/python.exe -I`:

```text
evaluar_fase5.py --conjunto ajuste --variante base=bronce:trabajo/s_mio/run1/capas/bronze --variante tsv_fix=bronce:trabajo/s_mio/run3/capas/bronze --variante z2_psm3=pagina:trabajo/variantes/z2_psm3 --variante z2_psm6=pagina:trabajo/variantes/z2_psm6 --variante z300dpi_psm3=pagina:trabajo/variantes/z4.1667_psm3
evaluar_fase5.py --conjunto validacion --variante base=bronce:trabajo/s_mio/run1/capas/bronze --variante tsv_fix=bronce:trabajo/s_mio/run3/capas/bronze
evaluar_fase5.py --conjunto todos --paginas ocr --variante base=bronce:trabajo/s_mio/run1/capas/bronze --variante tsv_fix=bronce:trabajo/s_mio/run3/capas/bronze
evaluar_fase5.py --conjunto todos --paginas digital --variante base=bronce:trabajo/s_mio/run1/capas/bronze --variante tsv_fix=bronce:trabajo/s_mio/run3/capas/bronze
comparar_fuentes.py --reanudar
```

Tests: `ingesta/.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp C:/Users/Migue/AppData/Local/Temp/pt_ocr2 ingesta/tests/unit/test_ocr_referencia.py`.

## comparar_fuentes.py --reanudar

Ejecución completada con código de salida 0. Se invalidó la caché por el cambio de normalización/clasificación y se recalcularon las distancias de los 53 documentos en ambos modos, 108 agregados y FASE 4. Bootstrap: 2000 réplicas, semilla 27102026; los IC difieren de fase 5 por la semilla y su convención de percentiles.

Contenido; porcentajes e IC95 por documento. Los JSON de fase 3 conservan todos los estratos, ambos modos e IC por página/documento.

| Comparación | Nivel/conjunto/estrato | Unidades | CER [IC95] | WER [IC95] | Recall crítico [IC95] |
|---|---|---:|---|---|---|
| S_mio_vs_U | pagina/paginas_elegibles/total | 1217 | 6,28 [2,43; 11,02] | 11,85 [4,49; 20,97] | 93,82 [92,13; 95,32] |
| S_mio_vs_U | pagina/paginas_elegibles/digital | 918 | 1,06 [0,61; 1,63] | 1,90 [1,48; 2,44] | 94,25 [92,37; 95,96] |
| S_mio_vs_U | pagina/paginas_elegibles/OCR | 299 | 21,60 [9,18; 29,59] | 41,38 [17,35; 56,67] | 92,49 [89,10; 95,27] |
| capa_vs_U | pagina/paginas_elegibles/total | 918 | 2,44 [1,38; 3,79] | 3,24 [2,20; 4,56] | 94,25 [92,37; 95,96] |
| S_mio_vs_U | documento/paginas_elegibles/total | 53 | 6,26 [2,42; 10,99] | 11,84 [4,49; 20,95] | 94,78 [93,20; 96,21] |
| S_mio_vs_U | documento/documentos_completos_comparables/total | 50 | 6,72 [2,39; 12,08] | 12,75 [4,43; 23,07] | 95,07 [93,48; 96,50] |
| S_prof_vs_U | documento/documentos_completos_comparables/total | 50 | 12,01 [8,99; 16,21] | 13,10 [10,31; 17,26] | 61,27 [55,36; 67,91] |
| S_mio_vs_S_prof | documento/documentos_completos_comparables/total | 50 | 19,14 [12,80; 27,58] | 25,91 [16,10; 38,52] | 96,58 [95,34; 97,70] |

Frente a los resultados anteriores, las cifras redondeadas a dos decimales no cambian. Sí cambian algunos valores exactos e IC por la normalización. En los agregados totales de contenido:

| Comparación / nivel / conjunto | CER anterior → actual (%) | WER anterior → actual (%) |
|---|---|---|
| S_mio_vs_U/pagina/paginas_elegibles | 6,27605788 → 6,27605788 | 11,85097923 → 11,85172838 |
| capa_vs_U/pagina/paginas_elegibles | 2,43747516 → 2,43747516 | 3,24092973 → 3,24193148 |
| S_mio_vs_U/documento/paginas_elegibles | 6,25604813 → 6,25604813 | 11,83824369 → 11,83899284 |
| S_mio_vs_U/documento/documentos_completos_comparables | 6,71784891 → 6,71781637 | 12,74867946 → 12,74867946 |
| S_prof_vs_U/documento/documentos_completos_comparables | 12,01192444 → 12,01192444 | 13,09951313 → 13,09951313 |
| S_mio_vs_S_prof/documento/documentos_completos_comparables | 19,14218028 → 19,14228987 | 25,91326536 → 25,91372513 |

El recall crítico de esos agregados totales no cambia. Las diferencias exactas y de IC de los 108 agregados se conservan en `comparacion_fase3.json`.

Se preservaron byte a byte `desacuerdos.csv`, `clave_desacuerdos.csv`, `muestreo_desacuerdos.json` y `evaluacion_desacuerdos.json` (SHA-256 verificados frente al estado anterior). No se regeneraron recortes ni se sobrescribieron las revisiones humanas. Las huellas de código y entradas coinciden con la nueva procedencia.

Repetibilidad: 159/159 archivos idénticos; diferencias: 0.

Verificación estructurada: `verificacion.json`. Comparación antes/después: `comparacion_fase5.json` y `comparacion_fase3.json`. Resúmenes anteriores conservados en `anteriores.json`.
