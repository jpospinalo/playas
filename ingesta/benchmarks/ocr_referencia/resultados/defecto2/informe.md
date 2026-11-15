# Defecto 2: «º/°» leído como dígito o símbolo en escaneados (FASE 2, Linux real)

Medido frente a U (OCR de referencia, no transcripción humana) en las 304 páginas OCR
del corpus (21 documentos), con la división fija ajuste/validación (semilla 20261110).
OCR real con Tesseract 5.3.4 en EC2 Linux; mismo armado de texto que `extract._ocr`
(`variantes_ocr.py`). «Páginas bajas» = 91 páginas OCR con confianza ≤ 95 en runA; en
las variantes «_bajas» solo esas páginas se re-OCR y el resto queda como el bronce base.

| Variante | Ajuste CER | Ajuste recall crítico | Validación CER | Validación recall crítico | Validación núm./año |
|---|---:|---:|---:|---:|---:|
| base (fast spa, zoom 2) | 1,65 % | 93,32 % | 1,94 % | 91,29 % | 90,54 % |
| tessdata_best, todas | 1,64 % | 93,65 % | 1,94 % | 90,67 % | 89,69 % |
| tessdata_best, bajas | 1,65 % | 93,32 % | 1,95 % | 90,51 % | 89,62 % |
| tessdata_best + zoom 3, bajas | 1,60 % | 93,65 % | 1,85 % | 91,52 % | 90,82 % |
| fast + zoom 3, bajas | 1,63 % | 93,61 % | 1,83 % | 91,87 % | 91,27 % |
| fast + Otsu, bajas | 1,77 % | 92,93 % | 1,96 % | 90,28 % | 89,54 % |

Diferencia pareada (bootstrap por documento, 2000 réplicas) de la mejor variante,
zoom 3 en páginas bajas, frente a la base en VALIDACIÓN: ΔCER −0,10 pp, IC95 [−0,23,
+0,07]; Δrecall crítico +0,58 pp, IC95 [−0,12, +2,10]. El intervalo incluye cero: **no
es una mejora clara** y no se adopta. tessdata_best no mejora (empeora el recall
crítico en validación) y es ~3 veces más lento (2.458 s frente a ~830 s para 304
páginas). Otsu empeora.

Síntoma específico (encabezados de artículo/parágrafo con un símbolo pegado al número,
detector `signals.secuencia_articulos`): Turbo 14 (base) → 12 (tessdata_best) / 14–15
(resto); El Rodadero 2 → 2; Cartagena 1 → 1. Ninguna variante corrige el «°».

**Decisión: no se adopta ninguna variante; el extractor no cambia.** El detector de
anomalías de secuencia se conserva como señal (registrada en la ficha de cada documento).
La política ya envía a revisión los escaneados rojos (Turbo, El Rodadero, Cartagena) por
la fracción de páginas con confianza baja.

Incidencia del experimento: la primera corrida con `--tessdata-dir` dio texto vacío
porque ese directorio no tenía `configs/tsv`; `variantes_ocr.py` ahora falla con un
mensaje claro en ese caso. Nada está validado por abogados.
