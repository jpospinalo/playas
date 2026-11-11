# Calibración de la política del intake (FASE 4)

Etiqueta: veredicto por documento frente a U (fidelidad frente a otro OCR, no error real). Aceptar =
`aceptado` o `aceptado_con_advertencias`. Umbrales elegidos SOLO con los 21 documentos de AJUSTE
(rejilla en `calibrar_politica.py`): 0 rojos aceptados y, además, robustez: cada rojo debe caer por
una señal de su propio defecto aunque se quite la puerta de identidad. A igualdad, menor carga humana y
política menos estricta. VALIDACIÓN (32) no interviene en la elección.

**Con 53 documentos (6 rojos) las conclusiones son frágiles.** Nada está validado por abogados.

## Independencia de la validación (leer antes que las cifras)

El resultado de 0 rojos aceptados en VALIDACIÓN **no es una confirmación independiente**:

- la regla de seguridad OCR (≤ 50 % de páginas con confianza ≤ 95) procede de la recomendación de la
  fase anterior, calculada con todas las páginas OCR, incluidas las de validación;
- las señales (tablas-imagen, clasificación por encabezado, mínimo por página de 70) se diseñaron
  mirando los 53 documentos;
- la calibración ingenua, sin esas decisiones, aceptaba un rojo de validación.

Este conjunto es de DESARROLLO. Para confirmar la política hay que congelarla (versión 1 de
`config/intake_policy.yaml`) y evaluarla con documentos nuevos e independientes, etiquetados del mismo
modo, antes de usar estas cifras como garantía.

## Umbrales elegidos

```json
{
 "ocr_confianza_media_minima": 0,
 "ocr_confianza_pagina_minima": 70,
 "ocr_fraccion_paginas_bajas_maxima": 0.5,
 "simbolos_sospechosos_maximos": 1000,
 "anomalias_secuencia_maximas": 1000,
 "tablas_imagen_maximas": 1,
 "tablas_imagen_caracteres_maximos": 1500,
 "caida_texto_paginas_maximas": 1000
}
```

Reglas de seguridad que la calibración no relaja: `ocr_fraccion_paginas_bajas_maxima` ≤ 0,5 y
`ocr_confianza_pagina_minima` ≥ 70 (defecto grave: una página ilegible no se diluye entre páginas
buenas; valor redondo, no ajustado). La primera se fijó
tras ver la recomendación de la fase anterior (umbral de página ≤ 95, calculado con todas las páginas
OCR, incluidas las de validación): por eso las cifras de validación son algo optimistas.

## AJUSTE (21)

| Veredicto frente a U | aceptado | con advertencias | revisión humana | rechazado |
|---|---:|---:|---:|---:|
| verde | 2 | 3 | 1 | 0 |
| no distinguible de U | 4 | 3 | 0 | 0 |
| amarillo | 2 | 0 | 2 | 0 |
| rojo | 0 | 0 | 4 | 0 |

- Rojos aceptados (falsa aceptación): **0 de 4**.
- Carga humana: 1 de 13 verdes y no distinguibles van a revisión.
- Amarillos aceptados: 2 de 4.

## VALIDACIÓN (32)

| Veredicto frente a U | aceptado | con advertencias | revisión humana | rechazado |
|---|---:|---:|---:|---:|
| verde | 7 | 4 | 5 | 0 |
| no distinguible de U | 5 | 2 | 1 | 0 |
| amarillo | 4 | 1 | 1 | 0 |
| rojo | 0 | 0 | 2 | 0 |

- Rojos aceptados (falsa aceptación): **0 de 2**.
- Carga humana: 6 de 24 verdes y no distinguibles van a revisión.
- Amarillos aceptados: 5 de 6.

## Calibración ingenua (descartada)

Sin robustez ni la regla de fracción OCR elige {"ocr_confianza_media_minima": 0, "ocr_confianza_pagina_minima": 70, "ocr_fraccion_paginas_bajas_maxima": 1.0, "simbolos_sospechosos_maximos": 1000, "anomalias_secuencia_maximas": 1000, "tablas_imagen_maximas": 1, "tablas_imagen_caracteres_maximos": 1500, "caida_texto_paginas_maximas": 1000}.
Ajuste: 0 rojos aceptados; validación: **1 de 2**
(acepta Turbo, rojo escaneado): el único rojo escaneado de ajuste caía por la identidad, y la
calibración no tenía motivo para activar ninguna regla de OCR. Se endureció como se describe arriba.

## Cómo cae cada rojo

| Rojo | Conjunto | Tipo | Motivos de la política |
|---|---|---|---|
| Cartagena (normas base) | ajuste | escaneado | 80% de páginas OCR con confianza ≤ 95 (máximo 50%); identidad incompleta: faltan tipo_documento, numero, anio |
| Turbo | validacion | escaneado | 76% de páginas OCR con confianza ≤ 95 (máximo 50%) |
| El Rodadero | validacion | escaneado | 100% de páginas OCR con confianza ≤ 95 (máximo 50%); identidad incompleta: faltan tipo_documento, numero, anio |
| AP Lemus Orozco | ajuste | digital | páginas digitales con imágenes grandes y poco texto (posible tabla-imagen): [32, 33, 34] |
| TAA 2015-281 | ajuste | digital | páginas digitales con imágenes grandes y poco texto (posible tabla-imagen): [3, 4] |
| CE AP 2021-041 Stephengs | ajuste | digital | páginas digitales con imágenes grandes y poco texto (posible tabla-imagen): [22, 33] |

Los tres rojos digitales (sin confianza OCR) se detectan por la señal nueva de páginas digitales con
imágenes grandes y poco texto (tablas o rótulos dentro de imágenes). Los escaneados, por la fracción de
páginas OCR con confianza ≤ 95 (y además por la identidad en El Rodadero y Cartagena).

**Salvedad:** los tres rojos digitales están en AJUSTE; en VALIDACIÓN no hay ningún rojo digital, así
que la señal de tablas-imagen no tiene confirmación independiente. Sus umbrales (≥ 25 % del área, ≤ 1500
caracteres, más de una página) se eligieron viendo esos tres casos.

## Carga humana en validación

| Documento | Veredicto | Motivo |
|---|---|---|
| por_el_cual_se_expide_el_codigo_de_comercio_05d5 | no distinguible de U | identidad incompleta: faltan tipo_documento, numero, anio |
| ap_felipe_jose_campo_fernandez_vs_corpamag_y_otros_ce3c | verde | páginas digitales con imágenes grandes y poco texto (posible tabla-imagen): [33, 36] |
| por_el_cual_se_reglamenta_el_servicio_publico_de_transporte_ | verde | identidad incompleta: faltan tipo_documento, numero, anio |
| por_el_cual_se_reglamenta_la_ley_13_de_1990_15e7 | verde | identidad incompleta: faltan tipo_documento, numero, anio |
| por_el_cual_se_reglamenta_la_habilitacion_y_la_prestacion_de | verde | identidad incompleta: faltan tipo_documento, numero, anio |
| por_el_cual_se_reorganiza_la_direccion_general_maritima_y_po | verde | identidad incompleta: faltan tipo_documento, numero, anio |

Cinco de los seis van a revisión por identidad incompleta: son fragmentos de compilaciones sin el
encabezado de la propia norma. Se resuelven con un archivo lateral de metadatos (override con evidencia).

## Señales medidas pero sin bloqueo

La secuencia de artículos (símbolos pegados, descensos) y la caída de texto no aportaron en ajuste más
allá de las reglas elegidas; quedan registradas en la ficha de cada documento y desactivadas como
bloqueo. El detector de símbolos sí marca a Turbo (14) y El Rodadero (2), pero también a verdes (hasta 6).
