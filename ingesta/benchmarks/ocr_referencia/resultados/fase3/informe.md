# FASES 3 y 4

Cifra principal: contenido. Estricto controla diferencias tipográficas. U sigue siendo referencia automática sin verificar.

S_prof solo se compara por documento completo, sin reconstruir páginas. Digital/OCR documental exige pureza; los mixtos están separados. Se omiten de S_prof los tres documentos con páginas U excluidas y se ofrece S_mio en ese mismo subconjunto.

| Comparación | Nivel/conjunto | Estrato | Unidades | CER contenido | WER contenido | CER estricto | WER estricto | Recall crítico | Recall inverso | LCS | IC95 CER documentos | Semáforo | Escenario U |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| S_mio_vs_U | pagina/paginas_elegibles | total | 1217 | 6.28% | 11.85% | 6.36% | 12.18% | 93.82% | 39.18% | 95.59% | 2.43%–11.02% | rojo | 5.05%–7.51% |
| S_mio_vs_U | pagina/paginas_elegibles | digital | 918 | 1.06% | 1.90% | 1.15% | 2.18% | 94.25% | 98.48% | 96.85% | 0.61%–1.63% | amarillo | 0.00%–2.29% |
| S_mio_vs_U | pagina/paginas_elegibles | OCR | 299 | 21.60% | 41.38% | 21.69% | 41.85% | 92.49% | 13.65% | 91.84% | 9.18%–29.60% | rojo | 20.37%–22.83% |
| S_mio_vs_U | pagina/paginas_elegibles | jurisprudencia | 1045 | 5.28% | 10.01% | 5.38% | 10.36% | 94.20% | 43.61% | 96.07% | 1.30%–11.06% | rojo | 4.05%–6.51% |
| S_mio_vs_U | pagina/paginas_elegibles | normativa | 172 | 11.86% | 22.51% | 11.90% | 22.75% | 91.59% | 24.40% | 92.82% | 1.83%–23.59% | rojo | 10.63%–13.09% |
| S_mio_vs_U | pagina/paginas_elegibles | con_tabla | 54 | 25.70% | 45.37% | 25.81% | 45.80% | 80.04% | 17.28% | 84.84% | 5.46%–33.97% | rojo | 24.47%–26.93% |
| S_mio_vs_U | pagina/paginas_elegibles | sin_tabla | 1163 | 5.39% | 10.38% | 5.48% | 10.71% | 94.67% | 41.97% | 96.06% | 1.65%–10.52% | rojo | 4.16%–6.62% |
| S_mio_vs_U | pagina/paginas_elegibles | capa_OCR_incrustada | 29 | 0.58% | 2.74% | 0.60% | 2.88% | 93.04% | 96.05% | 93.48% | 0.58%–0.58% | verde | 0.00%–1.81% |
| S_mio_vs_U | pagina/paginas_elegibles | capa_ge80 | 918 | 1.06% | 1.90% | 1.15% | 2.18% | 94.25% | 98.48% | 96.85% | 0.61%–1.63% | amarillo | 0.00%–2.29% |
| S_mio_vs_U | pagina/paginas_elegibles | capa_lt80 | 299 | 21.60% | 41.38% | 21.69% | 41.85% | 92.49% | 13.65% | 91.84% | 9.18%–29.60% | rojo | 20.37%–22.83% |
| capa_vs_U | pagina/paginas_elegibles | total | 918 | 2.44% | 3.24% | 2.53% | 3.53% | 94.25% | 98.48% | 96.22% | 1.38%–3.79% | amarillo | — |
| capa_vs_U | pagina/paginas_elegibles | digital | 918 | 2.44% | 3.24% | 2.53% | 3.53% | 94.25% | 98.48% | 96.22% | 1.38%–3.79% | amarillo | — |
| capa_vs_U | pagina/paginas_elegibles | jurisprudencia | 869 | 2.44% | 3.26% | 2.54% | 3.55% | 94.42% | 98.43% | 96.23% | 1.25%–3.80% | amarillo | — |
| capa_vs_U | pagina/paginas_elegibles | normativa | 49 | 2.30% | 2.89% | 2.32% | 2.97% | 91.49% | 99.30% | 95.84% | 0.53%–4.73% | amarillo | — |
| capa_vs_U | pagina/paginas_elegibles | con_tabla | 22 | 11.42% | 11.69% | 11.63% | 12.35% | 76.80% | 98.93% | 86.14% | 4.27%–21.29% | rojo | — |
| capa_vs_U | pagina/paginas_elegibles | sin_tabla | 896 | 2.26% | 3.08% | 2.34% | 3.36% | 94.99% | 98.46% | 96.41% | 1.18%–3.61% | amarillo | — |
| capa_vs_U | pagina/paginas_elegibles | capa_OCR_incrustada | 29 | 6.26% | 8.88% | 6.28% | 9.02% | 93.04% | 95.71% | 90.95% | 6.26%–6.26% | rojo | — |
| capa_vs_U | pagina/paginas_elegibles | capa_ge80 | 918 | 2.44% | 3.24% | 2.53% | 3.53% | 94.25% | 98.48% | 96.22% | 1.38%–3.79% | amarillo | — |
| S_mio_vs_U | documento/paginas_elegibles | total | 53 | 6.26% | 11.84% | 6.34% | 12.17% | 94.78% | 39.58% | 95.45% | 2.42%–10.99% | rojo | 5.03%–7.49% |
| S_mio_vs_U | documento/paginas_elegibles | digital | 32 | 1.19% | 2.02% | 1.29% | 2.35% | 93.70% | 98.37% | 96.49% | 0.69%–1.72% | amarillo | 0.00%–2.42% |
| S_mio_vs_U | documento/paginas_elegibles | OCR | 19 | 21.53% | 41.33% | 21.61% | 41.80% | 96.31% | 14.22% | 91.64% | 10.01%–30.22% | rojo | 20.30%–22.76% |
| S_mio_vs_U | documento/paginas_elegibles | mixto | 2 | 0.39% | 1.20% | 0.41% | 1.28% | 99.29% | 99.71% | 98.06% | 0.12%–0.42% | verde | 0.00%–1.62% |
| S_mio_vs_U | documento/paginas_elegibles | jurisprudencia | 26 | 5.28% | 10.01% | 5.38% | 10.36% | 95.03% | 43.99% | 95.94% | 1.30%–11.05% | rojo | 4.05%–6.51% |
| S_mio_vs_U | documento/paginas_elegibles | normativa | 27 | 11.74% | 22.42% | 11.79% | 22.66% | 93.38% | 24.88% | 92.60% | 1.83%–23.41% | rojo | 10.51%–12.97% |
| S_mio_vs_U | documento/paginas_elegibles | con_tabla | 13 | 12.54% | 23.11% | 12.65% | 23.53% | 93.52% | 26.84% | 93.15% | 2.64%–22.85% | rojo | 11.31%–13.77% |
| S_mio_vs_U | documento/paginas_elegibles | sin_tabla | 40 | 2.54% | 5.19% | 2.61% | 5.47% | 95.74% | 60.94% | 96.80% | 0.81%–5.32% | amarillo | 1.31%–3.77% |
| S_mio_vs_U | documento/paginas_elegibles | capa_OCR_incrustada | 1 | 0.58% | 2.74% | 0.60% | 2.88% | 93.39% | 96.41% | 93.49% | 0.58%–0.58% | verde | 0.00%–1.81% |
| S_mio_vs_U | documento/documentos_completos_comparables | total | 50 | 6.72% | 12.75% | 6.80% | 13.09% | 95.07% | 36.86% | 95.47% | 2.39%–12.08% | rojo | 5.49%–7.95% |
| S_mio_vs_U | documento/documentos_completos_comparables | digital | 30 | 1.21% | 2.05% | 1.31% | 2.37% | 93.69% | 98.39% | 96.42% | 0.64%–1.85% | amarillo | 0.00%–2.44% |
| S_mio_vs_U | documento/documentos_completos_comparables | OCR | 18 | 22.76% | 43.90% | 22.85% | 44.39% | 97.04% | 13.64% | 91.96% | 10.57%–31.08% | rojo | 21.53%–23.99% |
| S_mio_vs_U | documento/documentos_completos_comparables | mixto | 2 | 0.39% | 1.20% | 0.41% | 1.28% | 99.29% | 99.71% | 98.06% | 0.12%–0.42% | verde | 0.00%–1.62% |
| S_mio_vs_U | documento/documentos_completos_comparables | jurisprudencia | 24 | 5.71% | 10.81% | 5.80% | 11.16% | 95.19% | 41.03% | 95.83% | 1.34%–11.52% | rojo | 4.48%–6.94% |
| S_mio_vs_U | documento/documentos_completos_comparables | normativa | 26 | 12.60% | 24.41% | 12.64% | 24.67% | 94.35% | 23.34% | 93.30% | 0.98%–24.85% | rojo | 11.37%–13.83% |
| S_mio_vs_U | documento/documentos_completos_comparables | con_tabla | 12 | 12.90% | 23.87% | 13.01% | 24.32% | 93.83% | 26.30% | 93.43% | 2.66%–23.91% | rojo | 11.67%–14.13% |
| S_mio_vs_U | documento/documentos_completos_comparables | sin_tabla | 38 | 2.75% | 5.65% | 2.82% | 5.92% | 96.16% | 56.50% | 96.78% | 0.86%–6.04% | amarillo | 1.52%–3.98% |
| S_mio_vs_U | documento/documentos_completos_comparables | capa_OCR_incrustada | 1 | 0.58% | 2.74% | 0.60% | 2.88% | 93.39% | 96.41% | 93.49% | 0.58%–0.58% | verde | 0.00%–1.81% |
| S_prof_vs_U | documento/documentos_completos_comparables | total | 50 | 12.03% | 13.15% | 12.10% | 13.36% | 61.27% | 98.09% | 84.30% | 9.00%–16.23% | rojo | 10.80%–13.26% |
| S_prof_vs_U | documento/documentos_completos_comparables | digital | 30 | 10.47% | 11.60% | 10.55% | 11.78% | 60.34% | 98.03% | 85.73% | 8.62%–12.81% | rojo | 9.24%–11.70% |
| S_prof_vs_U | documento/documentos_completos_comparables | OCR | 18 | 20.87% | 21.48% | 20.91% | 21.76% | 52.38% | 97.50% | 76.31% | 13.08%–39.51% | rojo | 19.64%–22.10% |
| S_prof_vs_U | documento/documentos_completos_comparables | mixto | 2 | 1.44% | 3.66% | 1.50% | 3.88% | 94.57% | 99.36% | 93.67% | 1.31%–1.45% | amarillo | 0.21%–2.67% |
| S_prof_vs_U | documento/documentos_completos_comparables | jurisprudencia | 24 | 7.82% | 9.13% | 7.90% | 9.36% | 63.73% | 98.20% | 88.15% | 5.66%–9.99% | rojo | 6.59%–9.05% |
| S_prof_vs_U | documento/documentos_completos_comparables | normativa | 26 | 36.47% | 37.26% | 36.49% | 37.33% | 47.37% | 97.28% | 61.18% | 24.28%–52.95% | rojo | 35.24%–37.70% |
| S_prof_vs_U | documento/documentos_completos_comparables | con_tabla | 12 | 12.65% | 13.51% | 12.74% | 13.78% | 56.02% | 97.60% | 83.66% | 9.32%–18.71% | rojo | 11.42%–13.88% |
| S_prof_vs_U | documento/documentos_completos_comparables | sin_tabla | 38 | 11.63% | 12.92% | 11.68% | 13.09% | 65.92% | 98.47% | 84.71% | 7.83%–18.58% | rojo | 10.40%–12.86% |
| S_prof_vs_U | documento/documentos_completos_comparables | capa_OCR_incrustada | 1 | 5.82% | 8.79% | 5.86% | 8.87% | 72.87% | 96.10% | 87.40% | 5.82%–5.82% | rojo | 4.59%–7.05% |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | total | 50 | 19.16% | 25.95% | 19.21% | 26.22% | 96.58% | 23.39% | 92.88% | 12.82%–27.60% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | digital | 30 | 10.82% | 11.88% | 10.85% | 12.04% | 96.12% | 62.13% | 93.78% | 8.81%–13.52% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | OCR | 18 | 52.26% | 77.70% | 52.38% | 78.34% | 96.18% | 7.26% | 89.84% | 39.36%–88.03% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | mixto | 2 | 1.17% | 3.42% | 1.22% | 3.64% | 99.47% | 95.08% | 93.89% | 1.17%–1.20% | amarillo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | jurisprudencia | 24 | 12.84% | 18.56% | 12.90% | 18.84% | 96.71% | 27.05% | 93.13% | 7.19%–19.72% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | normativa | 26 | 72.12% | 90.06% | 72.15% | 90.25% | 95.60% | 11.52% | 90.75% | 47.26%–127.22% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | con_tabla | 12 | 25.57% | 37.43% | 25.64% | 37.78% | 95.27% | 15.33% | 91.10% | 15.37%–38.82% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | sin_tabla | 38 | 15.08% | 18.62% | 15.12% | 18.83% | 97.59% | 38.38% | 94.03% | 9.30%–26.39% | rojo | — |
| S_mio_vs_S_prof | documento/documentos_completos_comparables | capa_OCR_incrustada | 1 | 5.63% | 7.15% | 5.66% | 7.21% | 98.39% | 77.02% | 96.09% | 5.63%–5.63% | rojo | — |

Los JSON conservan ambos modos, todos los IC por página/documento para las ocho métricas y los escenarios e_U=0,24% y 1,23%. La cota CER_obs ± e_U solo es triangular con error de caracteres y denominador común; usar una estimación de error de palabra es una sensibilidad hipotética, no una cota garantizada del CER real.

Repetibilidad: 159/159 archivos idénticos; diferencias: 0.

## Alertas exploratorias

| Nivel | CER malo | Predictor | n | Spearman | AUC | IC95 AUC | Youden | Sensibilidad ≥0,9 |
|---|---|---|---:|---:|---:|---|---|---|
| pagina_OCR | >3.00% | confianza_ocr | 299 | -0.6040544851943412 | 0.8302498670919723 | [0.6679522793921621, 0.9076169008384509] | <=95.06547064079422 (sens. 72.22%, esp. 87.08%) | <=95.74364528636364 (sens. 90.00%, esp. 36.84%) |
| pagina_OCR | >3.00% | chars_per_page | 299 | 0.11646268622560446 | 0.4943115364167996 | [0.2776940723172232, 0.7489930191595402] | <=2003 (sens. 37.78%, esp. 82.30%) | <=6576 (sens. 90.00%, esp. 0.00%) |
| pagina_OCR | >5.00% | confianza_ocr | 299 | -0.6040544851943412 | 0.7800557880055788 | [0.6592606670644315, 0.8742888979119412] | <=94.85311886053412 (sens. 63.33%, esp. 85.36%) | <=95.7438479010239 (sens. 90.00%, esp. 33.05%) |
| pagina_OCR | >5.00% | chars_per_page | 299 | 0.11646268622560446 | 0.3833682008368201 | [0.26572351635617136, 0.6038680807928111] | <=1426 (sens. 15.00%, esp. 97.91%) | <=8848 (sens. 90.00%, esp. 0.00%) |
| documento_con_OCR | >3.00% | confianza_ocr | 21 | -0.43116883116883115 | 0.7962962962962963 | [0.5727272727272728, 0.9636363636363636] | <=95.24345025993392 (sens. 66.67%, esp. 83.33%) | <=95.58939345413896 (sens. 100.00%, esp. 41.67%) |
| documento_con_OCR | >3.00% | chars_per_page | 21 | 0.08311688311688312 | 0.6018518518518519 | [0.32727272727272727, 0.8518518518518519] | <=3489.125 (sens. 88.89%, esp. 50.00%) | <=8286.5 (sens. 100.00%, esp. 0.00%) |
| documento_con_OCR | >5.00% | confianza_ocr | 21 | -0.43116883116883115 | 0.7962962962962963 | [0.5727272727272728, 0.9636363636363636] | <=95.24345025993392 (sens. 66.67%, esp. 83.33%) | <=95.58939345413896 (sens. 100.00%, esp. 41.67%) |
| documento_con_OCR | >5.00% | chars_per_page | 21 | 0.08311688311688312 | 0.6018518518518519 | [0.32727272727272727, 0.8518518518518519] | <=3489.125 (sens. 88.89%, esp. 50.00%) | <=8286.5 (sens. 100.00%, esp. 0.00%) |

Spearman sobre valores originales; AUC orientada según riesgo definido a priori.
Bootstrap por documento completo (2.000) también para páginas; se informa cuántos remuestreos tienen ambas clases.
Calidad es documental: repetirla por página no genera información independiente.
Youden y sensibilidad>=0,9 se seleccionan y evalúan dentro de muestra. IC exploratorios, sin garantía de rendimiento futuro.
Documentos mixtos: CER documental abarca todas sus páginas elegibles; la confianza resume solo sus páginas OCR.
La confianza no medida y banderas no medidas se omiten, sin convertirlas en cero. Predictores constantes no admiten umbral.

## Causas por ediciones repartidas

| Causa | Ediciones | Fracción |
|---|---:|---:|
| columnas_u_orden | 115882.5 | 54.43% |
| sin_causa_reglada | 35404.0 | 16.63% |
| tablas | 26891.0 | 12.63% |
| OCR_baja_confianza | 18657.5 | 8.76% |
| notas_llamadas_pegadas | 13737.5 | 6.45% |
| ligaduras_o_caracteres_privados | 1846.5 | 0.87% |
| capa_OCR_incrustada | 498.0 | 0.23% |

Por página se reparten sus ediciones entre los indicios presentes con peso 1/k; la suma conserva el total. También se informa conteo solapado. Es distribución descriptiva, no atribución causal de cada edición.

Véase causas.json para las 15 peores páginas y los cinco peores documentos. Los 30 segmentos ciegos se entregan con veredicto y nota vacíos; la clave A/B permanece en archivo separado. No se estiman errores adjudicados hasta completar la revisión.
