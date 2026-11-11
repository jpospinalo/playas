# Fiabilidad por documento

Estado: **COMPLETO**. PDF únicos: 53/53; MD: 2. Calibración: 64/64.

## Regla del veredicto

e_U = 0,0054 (error por palabra estimado de U; IC95 0,31–0,88 %). CER = bronce total, suma de ediciones / suma de caracteres de referencia. Verde: CER + e_U < 1 % (CER < 0,46 %). No distinguible de U: 0,46 % ≤ CER < 1,54 %; la ventana [CER − e_U, CER + e_U] toca el umbral de 1 %. Amarillo: 1,54 % ≤ CER ≤ 3 %. Rojo: CER > 3 %.

Cobertura gold de silver < 99 % o perdida_silver_otra > 5 % → rojo. perdida_silver_otra > 2 % o recall crítico < 90 % → como mínimo amarillo. La pérdida de mobiliario institucional y paginación no degrada el veredicto; la pérdida total se conserva para trazabilidad. Son umbrales operativos solicitados: e_U mide palabras y no identifica un IC del CER verdadero. Se conserva el veredicto automático; si estado_auditoria = aplicada, veredicto_final parte del veredicto_auditado bronce/U y reaplica las puertas silver/gold. Una evaluación automática incompleta indica sin evaluar. La auditoría cambia la atribución y el veredicto, no las métricas frente a U.

## Método

Desde ingesta/: `python -I -B benchmarks/ocr_referencia/fiabilidad.py --capas trabajo/corridas/runA/pdf/capas`. Para runB: `--capas trabajo/corridas/runB/pdf/capas`. md/capas hermana se detecta automáticamente; --capas-md permite indicarla. Las rutas relativas parten de benchmarks/ocr_referencia/. CSV y JSON expresan las tasas como fracciones de 0 a 1.

Modo contenido de metricas.py para todas las fuentes. CER/WER documentales y por estrato suman ediciones y denominadores por página; recuperación/precisión conservan multiplicidad. Críticos se comparan por página (categorías solapadas); orden = LCS de n-gramas de orden_lectura. IC95 percentil, bootstrap de páginas dentro de documento/estrato, 2000 repeticiones, semilla 20261110. ic_amplio = sí con menos de 10 páginas evaluables; un IC de una sola página es degenerado. Ausencia de denominador = n/d.

Las siete páginas excluidas de U no participan en ninguna métrica con U ni en las muestras de líneas eliminadas. Cobertura gold, integridad de cuerpos y cortes usan el documento completo, sin U. Los contadores de confianza usan todas las páginas OCR; sensibilidad y precisión usan únicamente las evaluables frente a U. Una confianza ausente no alerta y cuenta como fallo si su CER > 3 %. La media de confianza pondera páginas por igual.

Silver: pérdida = |(U ∩ bronce) − (U ∩ bronce ∩ silver)| / |U ∩ bronce|; ruido = |silver − U| / |silver|, con multiconjuntos documentales sobre páginas evaluables. La pérdida total permanece en silver_perdida (alias perdida_silver). perdida_silver_mobiliario atribuye primero las ocurrencias perdidas que caben en las palabras de fragmentos efectivamente eliminados según offset_map dentro de líneas del bronce verificadas como mobiliario. Las ocurrencias conservadas no exoneran palabras iguales eliminadas del cuerpo. perdida_silver_otra es el resto. Ambas tasas usan |U ∩ bronce| y suman la pérdida total, sin contar dos veces palabras repetidas entre mobiliario y contenido. Silver se pagina usando cleaned.pages. El CER de tablas incluye la página completa; recall de celdas compara el multiconjunto del texto td/th dentro de table con toda la página del bronce.
Las claves de cleaned.removed_furniture_keys son solo candidatos. Se acepta una línea si su clave independiente (dígitos → #, minúsculas, espacios colapsados) aparece entre las tres primeras o tres últimas líneas no vacías en al menos tres páginas y el 30 % de todas las páginas del documento, y no contiene marcadores jurídicos (artículo, art., parágrafo, considerando, resuelve, decreta, capítulo, título, numeral, literal). También se acepta un folio de margen: «Página N de M», o un número aislado solo si su valor menos el número de página da un desplazamiento constante observado en al menos dos páginas (secuencia de paginación); un importe aislado no se exonera. Los candidatos rechazados se contabilizan en perdida_silver_otra. Las páginas excluidas de U se controlan sin U: su pérdida bronce→silver no mobiliario aplica los mismos umbrales (2 %/5 %) y, si no se puede evaluar, impide el verde.

offset_map asocia los separadores insertados a un carácter fuente (por ejemplo, la D de Departamento al inicio de página). Por eso el complemento de los offsets puede mostrar un fragmento eliminado sin su primera letra: es un artefacto del mapa, no pérdida adicional de contenido. El mobiliario se clasifica sobre la línea completa original, antes de recortar fragmentos. silver_lineas_eliminadas.md selecciona los cinco documentos con mayor perdida_silver_otra y lista además todos los candidatos rechazados.

Gold: cobertura declarada = unión de [clean_start, clean_end) sobre silver (gold_cobertura_silver, alias gold_cobertura_declarada_silver); cobertura efectiva = unión solo de cuerpos con cabecera válida y texto idéntico al intervalo de silver (gold_cobertura_efectiva_silver). El recall U usa el TEXTO real de los cuerpos, quitando la cabecera válida y deduplicando solapes por offsets solo si el cuerpo coincide. Los discrepantes aportan su texto real completo; si cruzan páginas excluidas, se omiten del recall porque no hay un mapa fiable para recortarlos. Cualquier discrepancia o cabecera inválida impone rojo incluso tras aplicar la auditoría bronce/U. Los huecos mayores incluyen blancos. Duplicados exactos = copias sobrantes de cuerpos idénticos. Cuasi-duplicados = pares no adyacentes (|i−j|>1, orden por offsets) con Jaccard ≥ 0,9 entre conjuntos de shingles de cinco palabras normalizadas; menos de cinco palabras no forma shingles. Puede incluir pares exactos. Cortes = posiciones únicas de inicio/fin de cuerpo dentro de números (incluye punto/coma) o entre Artículo/Art. y su número.

Motivo principal: primero la degradación que eleva el color (gold, silver, críticos); en otro caso tablas si concentra más de la mitad de ediciones, o el estrato digital/OCR con más ediciones. La tabla muestra los peores documentos primero. El CSV contiene todos los estratos, denominadores e intervalos. Detalle por página: trabajo/fiabilidad/paginas.csv.

## PDF, del peor al mejor

| Documento | Conjunto | Págs. | CER total | CER OCR | Pérdida silver otra | Gold declarada | Gold efectiva | Veredicto automático | Veredicto final | Causa (auditoría) | Motivo |
|---|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| por_medio_del_cual_se_implementa_el_reglamento_de_playas_del_distrito_portuario__d6b7 | validación | 25 | 7.04 % | 7.04 % | 0.08 % | 99.94 % | 99.94 % | rojo | rojo | pipeline | tablas: CER 7.04 % |
| por_medio_de_la_cual_se_reglamenta_el_area_de_playa_en_el_balneario_turistico_el_9c01 | validación | 7 | 5.92 % | 5.92 % | 0.00 % | 99.93 % | 99.93 % | rojo | rojo | pipeline | CER OCR: 5.92 % |
| por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb | ajuste | 35 | 5.54 % | 5.54 % | 0.00 % | 99.90 % | 99.90 % | rojo | rojo | pipeline | CER OCR: 5.54 % |
| ap_gerardo_antenor_lemus_orozco_vs_distrito_de_santa_mata_y_otros_7c8c | ajuste | 39 | 4.24 % | n/d | 0.01 % | 99.84 % | 99.84 % | rojo | rojo | ambos | CER digital: 4.24 % |
| taa_2da_rd_2015_281_xxxx_vs_dpto_antioquia_responsabilidad_del_estado_98ef | ajuste | 35 | 3.89 % | n/d | 0.23 % | 99.83 % | 99.83 % | rojo | rojo | pipeline | tablas: CER 40.46 % |
| ce_2da_ap_2021_041_edgar_stephengs_vs_archipielago_san_andres_desarrollo_urbanis_0b8f | ajuste | 51 | 3.12 % | n/d | 0.02 % | 99.79 % | 99.79 % | rojo | rojo |  | CER digital: 3.12 % |
| ce_2da_ap_2016_328_ricardo_cabrales_vs_mun_covenas_playa_uso_publico_37b2 | validación | 28 | 1.91 % | n/d | 0.01 % | 99.80 % | 99.80 % | amarillo | amarillo |  | CER digital: 1.91 % |
| ce_2da_nyr_2009_164_fepep_vs_dimar_playa_uso_urbanistico_e806 | ajuste | 42 | 1.79 % | n/d | 0.00 % | 99.80 % | 99.80 % | amarillo | amarillo |  | CER digital: 1.79 % |
| ce_2da_ap_2017_103_personeria_vs_distrito_cartagena_desembocadura_afb0 | ajuste | 33 | 1.70 % | n/d | 0.00 % | 99.93 % | 99.93 % | amarillo | amarillo |  | CER digital: 1.70 % |
| por_el_cual_se_reglamentan_las_unidades_ambientales_costeras_uac_y_las_comisione_e828 | validación | 2 | 0.83 % | 0.83 % | 0.13 % | 99.96 % | 99.96 % | amarillo | amarillo |  | recall crítico: 87.50 % |
| ce_consulta_2010_071_minambiente_bienes_de_uso_publico_1d4e | validación | 31 | 0.67 % | 0.67 % | 0.18 % | 99.93 % | 99.93 % | amarillo | amarillo |  | recall crítico: 86.07 % |
| por_el_cual_se_reglamenta_el_manejo_del_espacio_publico_en_los_planes_de_ordenam_d195 | validación | 3 | 0.29 % | 0.29 % | 0.15 % | 99.96 % | 99.96 % | amarillo | amarillo |  | recall crítico: 87.30 % |
| por_el_cual_se_dictan_normas_sobre_la_prevencion_de_la_contaminacion_del_medio_m_c9b9 | validación | 4 | 0.21 % | n/d | 0.00 % | 99.85 % | 99.85 % | amarillo | amarillo |  | recall crítico: 82.46 % |
| por_el_cual_se_reglamenta_parcialmente_la_ley_47_del_19_de_febrero_de_1993_3e80 | ajuste | 1 | 0.17 % | n/d | 0.00 % | 100.00 % | 100.00 % | amarillo | amarillo |  | recall crítico: 87.50 % |
| ce_2da_ap_2010_028_radley_bent_vs_dimar_danos_ambientales_embarcaciones_ba1e | ajuste | 31 | 0.14 % | n/d | 0.05 % | 99.93 % | 99.93 % | amarillo | amarillo |  | recall crítico: 88.94 % |
| ce_consulta_1990_horacio_serpa_uso_publico_playa_00a7 | validación | 10 | 0.10 % | n/d | 0.00 % | 99.81 % | 99.81 % | amarillo | amarillo |  | recall crítico: 84.36 % |
| por_el_cual_se_reglamenta_parcialmente_el_articulo_noveno_de_la_ley_10_de_1978_922e | ajuste | 3 | 8.52 % | n/d | 0.00 % | 100.00 % | 100.00 % | rojo | no distinguible de U | U y métrica | tablas: CER 8.03 % |
| ce_2da_ap_2015_550_angela_munoz_vs_dpto_cordoba_bienes_de_uso_publico_bcec | ajuste | 27 | 1.45 % | n/d | 0.04 % | 99.79 % | 99.79 % | no distinguible de U | no distinguible de U |  | CER digital: 1.45 % |
| por_medio_del_cual_se_expide_el_decreto_unico_reglamentario_del_sector_ambiente__f508 | validación | 8 | 1.24 % | 1.24 % | 0.14 % | 99.96 % | 99.96 % | no distinguible de U | no distinguible de U |  | CER OCR: 1.24 % |
| ap_procuraduria_general_de_la_ancion_vs_coorpamag_y_otros_9523 | validación | 71 | 1.17 % | n/d | 0.04 % | 99.74 % | 99.74 % | no distinguible de U | no distinguible de U |  | CER digital: 1.17 % |
| por_medio_del_cual_se_expide_el_decreto_unico_reglamentario_del_sector_comercio__38da | ajuste | 5 | 1.08 % | 1.08 % | 0.11 % | 99.97 % | 99.97 % | no distinguible de U | no distinguible de U |  | CER OCR: 1.08 % |
| ap_rodrigo_martinez_silva_vs_minambiente_y_otros_19a7 | validación | 81 | 1.08 % | 1.08 % | 0.20 % | 99.93 % | 99.93 % | no distinguible de U | no distinguible de U |  | CER OCR: 1.08 % |
| por_medio_del_cual_se_reglamenta_el_uso_zonificacion_y_horario_de_las_playas_con_8351 | validación | 16 | 0.98 % | 0.98 % | 0.12 % | 99.95 % | 99.95 % | no distinguible de U | no distinguible de U |  | CER OCR: 0.98 % |
| por_el_cual_se_aprueba_el_ajuste_y_la_modificacion_a_la_planta_de_personal_de_em_cc7b | validación | 7 | 0.98 % | n/d | 0.00 % | 99.93 % | 99.93 % | no distinguible de U | no distinguible de U |  | CER digital: 0.98 % |
| por_medio_del_cual_se_expide_el_decreto_unico_reglamentario_del_sector_vivienda__404e | ajuste | 4 | 0.85 % | 0.85 % | 0.10 % | 99.97 % | 99.97 % | no distinguible de U | no distinguible de U |  | CER OCR: 0.85 % |
| ap_inversiones_e_y_d_s_a_s_vs_dimar_y_otros_a7c0 | ajuste | 33 | 0.80 % | 0.80 % | 0.21 % | 99.92 % | 99.92 % | no distinguible de U | no distinguible de U |  | CER OCR: 0.80 % |
| ap_carlos_alberto_zuniga_mejia_y_otros_vs_dimar_y_otros_d512 | ajuste | 28 | 0.78 % | n/d | 0.00 % | 99.82 % | 99.82 % | no distinguible de U | no distinguible de U |  | tablas: CER 5.57 % |
| por_el_cual_adiciona_al_titulo_4_de_la_parte_2_del_libro_2_del_decreto_1076_de_2_be8f | validación | 5 | 0.68 % | n/d | 0.03 % | 99.83 % | 99.83 % | no distinguible de U | no distinguible de U |  | CER digital: 0.68 % |
| por_el_cual_se_reglamenta_el_funcionamiento_de_los_comites_locales_para_la_organ_cb33 | ajuste | 4 | 0.60 % | n/d | 0.00 % | 99.84 % | 99.84 % | no distinguible de U | no distinguible de U |  | CER digital: 0.60 % |
| ap_gabriel_antonio_carrero_vs_dimar_y_otros_a44a | validación | 29 | 0.58 % | n/d | 0.00 % | 99.91 % | 99.91 % | no distinguible de U | no distinguible de U |  | CER digital: 0.58 % |
| por_el_cual_se_expide_el_codigo_de_comercio_05d5 | validación | 3 | 0.48 % | 0.48 % | 0.00 % | 99.93 % | 99.93 % | no distinguible de U | no distinguible de U |  | CER OCR: 0.48 % |
| cc_tu_039_2024_modesto_manjarrez_vs_autopistas_del_caribe_consulta_previa_via_d92b | validación | 111 | 0.42 % | 0.00 % | 0.02 % | 99.80 % | 99.80 % | verde | verde |  |  |
| ce_2da_ap_2011_178_jose_caballero_vs_distrito_cartagena_venta_inmueble_valor_cul_092f | validación | 41 | 0.41 % | n/d | 0.00 % | 99.89 % | 99.89 % | verde | verde |  |  |
| ap_felipe_jose_campo_fernandez_vs_corpamag_y_otros_ce3c | validación | 57 | 0.39 % | n/d | 0.01 % | 99.82 % | 99.82 % | verde | verde |  |  |
| ap_miguel_angel_enciso_vs_distrito_y_otros_ffab | ajuste | 29 | 0.37 % | 0.37 % | 0.13 % | 99.91 % | 99.91 % | verde | verde |  |  |
| ce_2da_nyr_1999_503_inversiones_mercedes_vs_dimar_concesiones_uso_playa_f07f | validación | 18 | 0.30 % | n/d | 0.00 % | 99.89 % | 99.89 % | verde | verde |  |  |
| ce_1era_ns_2009_603_jose_palencia_vs_mindefensa_resolucion_pilotos_embargaciones_99fd | validación | 35 | 0.29 % | n/d | 0.00 % | 99.95 % | 99.95 % | verde | verde |  |  |
| por_medio_del_cual_se_reglamenta_el_tramite_de_solicitud_de_concesiones_para_el__1ee0 | validación | 3 | 0.27 % | 0.27 % | 0.10 % | 99.97 % | 99.97 % | verde | verde |  |  |
| por_el_cual_se_dicta_el_codigo_nacional_de_recursos_naturales_renovables_y_de_pr_2880 | ajuste | 6 | 0.23 % | 0.23 % | 0.16 % | 99.95 % | 99.95 % | verde | verde |  |  |
| ce_2da_ap_2011_842_gabriel_carrero_vs_dimar_erosion_costera_93f6 | validación | 70 | 0.20 % | n/d | 0.00 % | 99.87 % | 99.87 % | verde | verde |  |  |
| ce_2da_nyr_1998_102_flury_valencia_vs_mindefensa_uso_urbanistico_playa_ba43 | validación | 21 | 0.19 % | n/d | 0.00 % | 99.95 % | 99.95 % | verde | verde |  |  |
| por_el_cual_se_reglamentan_las_disposiciones_sobre_licencias_urbanisticas_recono_e4a6 | validación | 2 | 0.18 % | 0.18 % | 1.79 % | 99.98 % | 99.98 % | verde | verde |  |  |
| ce_consulta_2005_168_mindefensa_bienes_de_uso_publico_ea75 | validación | 35 | 0.17 % | n/d | 0.00 % | 99.80 % | 99.80 % | verde | verde |  |  |
| por_el_cual_se_reglamenta_el_funcionamiento_de_los_comites_locales_para_la_organ_c8e5 | ajuste | 6 | 0.13 % | n/d | 0.00 % | 99.85 % | 99.85 % | verde | verde |  |  |
| ap_gieseken_cuello_cia_s_en_c_vs_dimar_y_otros_a4be | validación | 42 | 0.13 % | n/d | 0.21 % | 99.90 % | 99.90 % | verde | verde |  |  |
| ce_2da_nyr_1994_993_inversiones_araujo_vs_capitania_puerto_cartagena_urbanismo_p_86ff | ajuste | 19 | 0.12 % | 0.00 % | 0.00 % | 99.95 % | 99.95 % | verde | verde |  |  |
| por_el_cual_se_dictan_normas_para_simplificar_suprimir_y_reformar_tramites_proce_5f39 | ajuste | 3 | 0.10 % | 0.10 % | 0.10 % | 99.97 % | 99.97 % | verde | verde |  |  |
| por_el_cual_se_modifica_el_articulo_16_del_decreto_3888_del_10_de_octubre_de_200_0be7 | ajuste | 1 | 0.09 % | n/d | 0.00 % | 100.00 % | 100.00 % | verde | verde |  |  |
| por_medio_del_cual_se_expide_el_decreto_unico_reglamentario_del_sector_transport_1cd3 | validación | 6 | 0.06 % | 0.06 % | 0.19 % | 99.94 % | 99.94 % | verde | verde |  |  |
| por_el_cual_se_reglamenta_el_servicio_publico_de_transporte_maritimo_cdf2 | validación | 4 | 0.04 % | n/d | 0.00 % | 99.90 % | 99.90 % | verde | verde |  |  |
| por_el_cual_se_reglamenta_la_ley_13_de_1990_15e7 | validación | 4 | 0.03 % | n/d | 0.00 % | 99.85 % | 99.85 % | verde | verde |  |  |
| por_el_cual_se_reglamenta_la_habilitacion_y_la_prestacion_del_servicio_publico_d_aeb1 | validación | 3 | 0.02 % | n/d | 0.21 % | 99.88 % | 99.88 % | verde | verde |  |  |
| por_el_cual_se_reorganiza_la_direccion_general_maritima_y_portuaria_0fec | validación | 7 | 0.01 % | n/d | 0.00 % | 99.91 % | 99.91 % | verde | verde |  |  |

## Resumen por conjunto y categoría

Validación = cifras limpias del conjunto fijado. Ajuste es exploratorio. Media/mediana ponderan documentos por igual; agregado suma ediciones/denominadores.

Colores: V = verde, U = no distinguible de U, A = amarillo, R = rojo.

Total V / U / A / R / sin evaluar: finales 22 / 15 / 10 / 6 / 0; automáticos 22 / 14 / 10 / 7 / 0.

| Conjunto / categoría | Docs. | CER agregado | CER media | CER mediana | WER agregado | Colores finales V / U / A / R / sin evaluar | Colores automáticos V / U / A / R / sin evaluar |
|---|---:|---:|---:|---:|---:|---|---|
| ajuste | 21 | 2.03 % | 1.70 % | 0.80 % | 2.88 % | 6 / 7 / 4 / 4 / 0 | 6 / 6 / 4 / 5 / 0 |
| ajuste / jurisprudencia | 11 | 1.95 % | 1.67 % | 1.45 % | 2.63 % | 2 / 3 / 3 / 3 / 0 | 2 / 3 / 3 / 3 / 0 |
| ajuste / normativa | 10 | 2.49 % | 1.73 % | 0.41 % | 4.29 % | 4 / 4 / 1 / 1 / 0 | 4 / 3 / 1 / 2 / 0 |
| validacion | 32 | 0.87 % | 0.85 % | 0.34 % | 1.94 % | 16 / 8 / 6 / 2 / 0 | 16 / 8 / 6 / 2 / 0 |
| validacion / jurisprudencia | 15 | 0.59 % | 0.53 % | 0.39 % | 1.63 % | 9 / 3 / 3 / 0 / 0 | 9 / 3 / 3 / 0 / 0 |
| validacion / normativa | 17 | 2.46 % | 1.13 % | 0.29 % | 3.71 % | 7 / 5 / 3 / 2 / 0 | 7 / 5 / 3 / 2 / 0 |

Las medias y medianas de las demás métricas y los agregados por estrato están en resumen.json.

## Auditoría visual ciega de los 6 peores

Se seleccionaron los seis documentos con mayor CER automático y, por documento, las 6 páginas evaluables con más ediciones (o todas si había menos de seis). Se comparó la imagen de cada página a 200 dpi con los textos X/Y. Los rangos impares se asignaron al auditor A = Claude y los pares al auditor B = Codex. Ambos trabajaron independientes y sin ver la clave. La asignación X/Y fue aleatoria con semilla 20261110. Limitación: el formato de U —tablas HTML, párrafos en una línea— delata la fuente, así que la ceguera es parcial. La adjudicación por documento recoge las observaciones de ambos auditores y conserva las métricas automáticas.
Solo se aplica si coinciden los SHA256 actuales de U, bronce y gold, la evaluación está completa y la cobertura gold es evaluable. estado_auditoria explica cada rechazo. La revisión sustituye solo el componente bronce/U; después se vuelven a imponer las puertas de pérdida silver, cobertura gold e integridad de cuerpos y cabeceras.

Evidencias: [auditoria_revision_A_claude.tsv](auditoria_revision_A_claude.tsv), [auditoria_revision_B_codex.tsv](auditoria_revision_B_codex.tsv), [auditoria_clave.csv](auditoria_clave.csv) y [veredictos adjudicados](auditoria_veredictos.csv).

### por_el_cual_se_reglamenta_parcialmente_el_articulo_noveno_de_la_ley_10_de_1978_922e

| Veredicto automático → final | Estado | Causa | Justificación |
|---|---|---|---|
| rojo → no distinguible de U | aplicada | U y métrica | Las 3 páginas: el bronce reproduce fielmente la capa de texto (coordenadas correctas). El CER viene de U (en p2 suprime toda una columna de longitudes; escribe suin-juriscopal), de la ambigüedad º/° (unificarla baja el CER de 8,52 % a 7,23 %) y de mobiliario web de SUIN (etiquetas de iconos, letras espaciadas). Sin errores del pipeline en texto jurídico. |

### por_medio_del_cual_se_implementa_el_reglamento_de_playas_del_distrito_portuario__d6b7

| Veredicto automático → final | Estado | Causa | Justificación |
|---|---|---|---|
| rojo → rojo | aplicada | pipeline | OCR: omite el Parágrafo 2° completo (p15), lee ° como %, * o dígito ('Artículo 22' por 'Artículo 2º'), pierde tablas de horarios y coordenadas, folio 'Página 29 de 25'. U también desplaza filas de tablas, pero el error dominante es del pipeline. |

### por_medio_de_la_cual_se_reglamenta_el_area_de_playa_en_el_balneario_turistico_el_9c01

| Veredicto automático → final | Estado | Causa | Justificación |
|---|---|---|---|
| rojo → rojo | aplicada | pipeline | OCR: número de decreto manuscrito y fecha sellada ilegibles en todas las páginas ('(2) J', 'MO MAR', 'M9 MAR'), firmantes perdidos, 'PARÁGRAPO', ° como * o comillas. U también es inconsistente con el número manuscrito (0715/275/075). |

### por_medio_del_cual_se_expiden_las_normas_bases_para_la_reglamentacion_de_las_act_5beb

| Veredicto automático → final | Estado | Causa | Justificación |
|---|---|---|---|
| rojo → rojo | aplicada | pipeline | OCR: tablas de tramos aplanadas mezclando columnas, sellos convertidos en basura ('34 DIC' por '31 DIC'), palabras mutiladas en artículos ('deberá'→'rá', 'las isla de'→'20 de'), pérdida de tildes, '868,32' por '865,3'. |

### ap_gerardo_antenor_lemus_orozco_vs_distrito_de_santa_mata_y_otros_7c8c

| Veredicto automático → final | Estado | Causa | Justificación |
|---|---|---|---|
| rojo → rojo | aplicada | ambos | Digital: el pipeline pega las llamadas de nota a palabras y cifras ('200244' = año 2002 + nota 44) y omite texto dentro de imágenes (rótulos de fotos de inspección); U añade en cada página el membrete/firma leído de una imagen con nombres deformados. Mixta; se mantiene rojo porque los errores del pipeline afectan cifras. |

### taa_2da_rd_2015_281_xxxx_vs_dpto_antioquia_responsabilidad_del_estado_98ef

| Veredicto automático → final | Estado | Causa | Justificación |
|---|---|---|---|
| rojo → rojo | aplicada | pipeline | Digital con tablas incrustadas como imagen escaneada: el pipeline no hace OCR de imágenes dentro de páginas digitales y pierde parentescos, importes y totales (p3, p4). U recupera las tablas con errores (desplaza filas, inventa nombres, cédula). El resto de páginas es equivalente. |

## Sensibilidad º/°

Fuente: [sensibilidad_grado.json](sensibilidad_grado.json). Se unifican º y ° solo para este análisis; no modifica las métricas principales.

CER corpus: 1.260591 % → 1.255315 %; reducción de 0.0053 pp.

Documentos con cambio absoluto > 0,05 puntos porcentuales:

| Documento | CER | CER º/° unificado | Reducción (pp) |
|---|---:|---:|---:|
| ce_1era_ns_2009_603_jose_palencia_vs_mindefensa_resolucion_pilotos_embargaciones_99fd | 0.29 % | 0.23 % | 0.0598 |
| por_el_cual_se_reglamenta_parcialmente_el_articulo_noveno_de_la_ley_10_de_1978_922e | 8.52 % | 7.23 % | 1.2906 |
| por_el_cual_se_reglamenta_parcialmente_la_ley_47_del_19_de_febrero_de_1993_3e80 | 0.17 % | 0.10 % | 0.0672 |

## Repetibilidad

Fuentes: [hashes_runA.txt](../../trabajo/corridas/hashes_runA.txt) y [hashes_runB.txt](../../trabajo/corridas/hashes_runB.txt), manifiestos sha256sum de todos los archivos de capas de ambas corridas. Se comparan SHA256 por ruta relativa, independientemente del orden de las líneas. Una ruta ausente cuenta como distinta. Resultado completo: [repetibilidad.json](repetibilidad.json).

Archivos: 550; idénticos: 550; distintos: 0.

| Tipo / etapa | Archivos | Idénticos | Distintos |
|---|---:|---:|---:|
| bronze | 220 | 220 | 0 |
| silver | 220 | 220 | 0 |
| gold | 110 | 110 | 0 |
| pdf | 530 | 530 | 0 |
| md | 20 | 20 | 0 |
| pdf / bronze | 212 | 212 | 0 |
| pdf / silver | 212 | 212 | 0 |
| pdf / gold | 106 | 106 | 0 |
| md / bronze | 8 | 8 | 0 |
| md / silver | 8 | 8 | 0 |
| md / gold | 4 | 4 | 0 |

Las capas de runB no se descargaron y la EC2 ya se terminó; se omite la ejecución con --capas runB. Los 550 hashes coinciden por ruta: según estos manifiestos las capas son byte-idénticas y los CSV de métricas serían idénticos (salvo rutas). Es una inferencia de los hashes, no una segunda ejecución del comparador.

## Documentos MD — SIN referencia de OCR

Pérdida de caracteres = (longitud bronce − longitud silver) / longitud bronce. Identidad se comprueba sobre bytes contra un original local con SHA256 coincidente o nombre unívoco; si falta se indica n/d. No se presupone identidad por el doc_id.

| Documento | Bronce idéntico | Cambio | Pérdida caracteres | Gold declarada | Gold efectiva | Chunks cortos | Duplicados / cuasi | Cortes número / artículo | Cuerpos distintos |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| normativa/Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103).md | sí | idéntico | 3.40 % | 99.83 % | 99.83 % | 76 | 0 / 0 | 0 / 0 | 0 |
| normativa/decreto-2324-de-1984.md | sí | idéntico | 2.39 % | 99.87 % | 99.87 % | 0 | 0 / 0 | 0 / 0 | 0 |

## Anomalías y disponibilidad

```json
{
  "capas_faltantes": {},
  "paginas_sin_u": {},
  "cuerpos_discrepantes": {},
  "cobertura_gold_menor_99": {},
  "md_sin_original_local": [],
  "md_capas_faltantes": {},
  "md_doc_id_distinto_del_sha256_original": [],
  "numero_md_distinto_de_dos": null
}
```
