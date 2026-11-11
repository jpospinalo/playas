# FASE 1: U frente a la capa de texto

U es OCR automático sin verificar. La capa de texto es otra extracción imperfecta; estas discrepancias no estiman por sí solas el error frente al PDF visible.

Integridad: DISCREPANCIAS. Véase integridad.json.

Excluidas como NO CONFIABLES: 7. Véase paginas_excluidas.csv.

Cocientes micro; IC95 percentil, 2.000 remuestreos, semilla 27102026. Se excluyen duplicados y páginas no confiables.

| Estrato | Páginas | Documentos | CER | WER | Recuperación | Precisión | IC CER páginas | IC WER páginas | IC CER documentos | IC WER documentos |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| total | 918 | 34 | 2.54% | 3.55% | 98.92% | 98.11% | 2.28%–2.79% | 3.28%–3.81% | 1.46%–3.91% | 2.46%–4.93% |
| jurisprudencia | 869 | 22 | 2.55% | 3.58% | 98.94% | 98.08% | 2.29%–2.83% | 3.32%–3.87% | 1.33%–3.93% | 2.36%–4.95% |
| normativa | 49 | 12 | 2.32% | 2.96% | 98.45% | 98.67% | 1.51%–3.36% | 1.98%–4.13% | 0.54%–4.76% | 0.98%–5.27% |
| sin_tabla | 896 | 34 | 2.36% | 3.37% | 98.95% | 98.27% | 2.14%–2.57% | 3.15%–3.59% | 1.25%–3.73% | 2.28%–4.73% |
| jurisprudencia_sin_tabla | 853 | 22 | 2.39% | 3.41% | 98.95% | 98.24% | 2.18%–2.61% | 3.19%–3.64% | 1.17%–3.80% | 2.21%–4.80% |
| normativa_sin_tabla | 43 | 12 | 1.56% | 2.44% | 98.83% | 99.01% | 0.91%–2.28% | 1.53%–3.34% | 0.42%–3.07% | 0.76%–4.23% |
| con_tabla | 22 | 8 | 12.68% | 13.44% | 97.13% | 89.75% | 5.72%–22.91% | 6.20%–24.09% | 4.49%–25.24% | 4.59%–27.53% |
| jurisprudencia_con_tabla | 16 | 6 | 13.03% | 14.48% | 97.91% | 88.71% | 4.45%–26.10% | 5.96%–27.85% | 2.71%–30.13% | 4.03%–32.80% |
| normativa_con_tabla | 6 | 2 | 11.24% | 9.15% | 93.87% | 94.57% | 8.17%–15.64% | 3.05%–17.59% | 9.24%–15.34% | 3.38%–22.49% |

Sospechosas sin duplicados: 16; de ellas incluidas en agregados: 14.

## Diez peores páginas incluidas, por CER descendente

| Slug | Página | CER | WER | Recuperación | Precisión | LCS |
|---|---:|---:|---:|---:|---:|---:|
| taa_2da_rd_2015_281_xxxx_vs_dpto_antioquia_responsabilidad_del_estado_98ef | 3 | 170.65% | 170.83% | 95.83% | 42.40% | 67.02% |
| taa_2da_rd_2015_281_xxxx_vs_dpto_antioquia_responsabilidad_del_estado_98ef | 4 | 134.26% | 131.40% | 94.21% | 50.89% | 62.18% |
| ap_felipe_jose_campo_fernandez_vs_corpamag_y_otros_ce3c | 33 | 130.08% | 214.29% | 100.00% | 31.82% | 100.00% |
| ce_2da_ap_2021_041_edgar_stephengs_vs_archipielago_san_andres_desarrollo_urbanis_0b8f | 44 | 71.47% | 69.55% | 98.96% | 58.73% | 96.17% |
| por_el_cual_se_aprueba_el_ajuste_y_la_modificacion_a_la_planta_de_personal_de_em_cc7b | 1 | 49.47% | 35.14% | 97.30% | 83.72% | 82.86% |
| ce_2da_ap_2021_041_edgar_stephengs_vs_archipielago_san_andres_desarrollo_urbanis_0b8f | 51 | 47.80% | 53.10% | 67.26% | 95.00% | 49.55% |
| ce_2da_ap_2017_103_personeria_vs_distrito_cartagena_desembocadura_afb0 | 33 | 46.12% | 51.11% | 100.00% | 93.75% | 65.91% |
| por_el_cual_se_aprueba_el_ajuste_y_la_modificacion_a_la_planta_de_personal_de_em_cc7b | 7 | 43.67% | 18.42% | 97.37% | 97.37% | 83.33% |
| ce_2da_nyr_2009_164_fepep_vs_dimar_playa_uso_urbanistico_e806 | 42 | 39.96% | 45.67% | 70.87% | 95.74% | 56.80% |
| ap_gerardo_antenor_lemus_orozco_vs_distrito_de_santa_mata_y_otros_7c8c | 33 | 35.77% | 32.00% | 98.67% | 75.51% | 90.41% |

## Páginas excluidas

- `ap_felipe_jose_campo_fernandez_vs_corpamag_y_otros_ce3c`, página 1: tope_alcanzado;repeticion;ngramas_repetidos.
- `ce_2da_nyr_2009_164_fepep_vs_dimar_playa_uso_urbanistico_e806`, página 29: tope_alcanzado;repeticion;ngramas_repetidos.
- `por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb`, página 31: tope_alcanzado;repeticion;ngramas_repetidos.
- `por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb`, página 32: tope_alcanzado;repeticion;ngramas_repetidos.
- `por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb`, página 33: tope_alcanzado;repeticion;ngramas_repetidos.
- `por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb`, página 34: tope_alcanzado;repeticion;ngramas_repetidos.
- `por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb`, página 35: tope_alcanzado;repeticion;ngramas_repetidos.

## Límites

Los umbrales son señales de triaje, no validación visual. Notas pegadas a números, viñetas U+F0B7, columnas de tablas y orden interno del PDF pueden aumentar CER/WER o reducir LCS. Precisión baja indica discrepancia, sin atribuir automáticamente invención a U. Las páginas con menos de 80 caracteres de capa no están evaluadas por estas métricas. Los IC cuantifican remuestreo del corpus observado; no eliminan sesgos compartidos por las fuentes.
