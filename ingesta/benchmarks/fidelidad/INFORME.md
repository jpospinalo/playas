# Fidelidad del bronce v2 frente al PDF original

> **Nada de esto está validado por abogados.** Ninguna fuente LLM es verdad
> absoluta: las cifras «por consenso» son **PROVISIONALES**. Solo la cifra que
> salga de `calcular_error_real.py` tras la adjudicación humana podrá llamarse
> «error real medido sobre una muestra».

## Qué se midió

Se comparó el bronce de `ingest.offline` (**S**) con otras cuatro fuentes,
página a página:

| Fuente | Qué es | Independencia respecto a S |
|---|---|---|
| **A** | `pdftotext` (sin `-layout`) | Lee la misma capa de texto del PDF: comparte sus errores |
| **V** | Bronce v1 (Markdown de Docling), solo lectura | Otro extractor; sin marcas de página, alineado por anclas |
| **C1** | Transcripción ciega de Claude desde la imagen | Visual |
| **C2** | Transcripción ciega de Codex desde la imagen | Visual |

**Muestra:** 4 documentos y 18 páginas, renderizadas a 200 dpi (`seleccion.json`).

| Documento | Tipo | Páginas |
|---|---|---|
| Sentencia CE 2010-00028 (Radley Bent) | digital | 1, 2, 9, 16, 24, 31 |
| Decreto 1120/2013 (UAC) | escaneado (OCR) | 1, 2 |
| Decreto 5058/2009 (planta de personal) | digital con tablas | 1, 3, 4, 5, 6, 7 |
| Decreto 2324/1984 (DIMAR) | digital | 1, 3, 5, 7 |

**El escaneado queda PENDIENTE para S.** Esta máquina no tiene Tesseract:
Chocolatey falló dentro del sandbox de Codex («Intento de acceso a un socket no
permitido») y el instalador de UB-Mannheim requiere elevación (UAC). C1, C2 y
V de esas dos páginas existen; entre sí, C1 y C2 difieren un 0,29 % de CER.

Cómo se calculó:
- **Normalización** idéntica para todas las fuentes: NFC; minúsculas; espacios
  colapsados; guiones de fin de línea unidos; marcadores de página
  («Página N de M») quitados; marcado Markdown de V quitado; `|` como
  separador de celdas; superíndices como número aparte. La lista completa está
  en el README.
- **CER** = distancia de edición entre caracteres ÷ caracteres de la
  referencia; **WER**, lo mismo entre palabras.
- **Recuperación y precisión** de palabras como multiconjunto, sin orden.
- **Intervalos al 95 %:** bootstrap sobre páginas (2000 remuestreos, semilla
  fija). Con 4–6 páginas por documento son muy amplios.
- **Calibración:** se inyectaron sustituciones al 0,5 %, 1 % y 3 % y el
  comparador recuperó 0,499 %, 1,003 % y 3,011 %. Al borrar números, el recall
  crítico baja a 0/437. 64/64 comprobaciones correctas.

## 1. Métricas por documento (páginas digitales)

S como hipótesis frente a cada fuente como referencia. El semáforo usa tus
umbrales (CER < 1 % verde, 1–3 % amarillo, > 3 % rojo; no son un estándar)
sobre las referencias **visuales** C1 y C2. Las diferencias frente a A y V se
explican aparte.

| Documento | Págs. | CER vs A | CER vs V | CER vs C1 [IC95] | CER vs C2 [IC95] | WER vs C1 / C2 | Recup. / precisión vs C1 | Recall crítico vs C1 | Semáforo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Sentencia | 6 | 0,19 % | 2,77 % | 0,13 % [0,00–0,30] | 0,33 % [0,02–0,74] | 1,12 % / 1,36 % | 98,9 % / 99,2 % | **83,5 %** | 🟢 CER · 🔴 datos críticos |
| Tablas | 6 | 16,71 % | 10,23 % (4 p.) | 0,91 % [0,00–4,32] | 0,99 % [0,00–4,66] | 0,78 % / 0,87 % | 99,2 % / 100 % | 100 % | 🟢 |
| Norma | 4 | 0,00 % | 0,00 % (1 p.) | 0,00 % | 0,01 % | 0,00 % / 0,08 % | 100 % / 100 % | 100 % | 🟢 |
| **Total digital** | **16** | 4,10 % [0,48–9,78] | 4,43 % [2,36–7,32] (11 p.) | **0,28 % [0,00–0,89]** | **0,39 % [0,02–1,08]** | 0,70 % / 0,86 % | 99,3 % / 99,6 % | 95,3 % | 🟢 |
| Escaneado (OCR) | 2 | — | — | — | — | — | — | — | ⏳ PENDIENTE |

- **El CER alto frente a A en tablas es culpa de A.** `pdftotext` lee las
  tablas por columnas («5 (Cinco) 2 (Dos) 1 (Uno)… Asesor… Asesor…»). S
  conserva cada fila en su orden. Se comprobó en los recortes.
- **Frente a V, la diferencia viene de v1.** Docling cambia comillas
  tipográficas por rectas y rayas por guiones, y **omite números**: días de
  fechas, llamadas de nota, «DECRETO 2324 DE 1984» de la fuente formal. Su
  recall crítico frente a S es más bajo.
- **El residuo frente a C1/C2 en tablas** sale sobre todo de texto que es
  imagen (logotipos de SUIN y Justicia, icono «DOC»). Las transcripciones lo
  incluyen y un extractor de texto no lo ve, así que no es un error de S.

## 2. Estimación de error por consenso (PROVISIONAL)

Porcentaje de caracteres de cada fuente que caen en segmentos contradichos por
al menos dos fuentes concordantes con texto. Si otra fuente respalda a la vez
al objetivo, el segmento es «en disputa».

| Objetivo | Caracteres | Contradicho | Contradicho + en disputa |
|---|---:|---:|---:|
| **S (bronce v2)** | 27.619 | **0,06 %** (16 car.) | **0,27 %** (75 car.) |
| **V (bronce v1)** | 20.295 | **0,82 %** (166 car.) | **0,90 %** (183 car.) |

Cómo leerlo:
- Los 16 caracteres «contradichos» de S son en realidad un **acierto de S**.
  En «NACIONAL-⏎ARMANDA» el guion es real, pero la regla que une
  «guion + salto de línea» se lo quita a C1 y C2. Es un artefacto de la
  normalización.
- Los errores verdaderos de S están **en disputa**, porque A (misma capa de
  texto) los comparte y los «respalda»:
  - las 7 fechas con la llamada de nota pegada;
  - 7 viñetas emitidas como U+F0B7 (carácter de uso privado) en lugar de «•».
- **Conclusión provisional:** S comete aproximadamente un orden de magnitud
  menos errores que v1. La cifra pasará a ser medida cuando completes la
  adjudicación.

## 3. Estructura (`estructura.csv`, comparando imagen y S)

Sobre las 16 páginas evaluables; el escaneado está pendiente.

| Problema | Páginas | % |
|---|---:|---:|
| Columnas mezcladas | 1 / 16 | 6 % (bloque de firmas a dos columnas, sentencia p. 31) |
| Tablas aplanadas | 0 / 4 con tabla | 0 % (filas conservadas; celdas separadas solo por espacios) |
| Notas al pie perdidas | 0 / 1 con notas | 0 % |
| Llamada de nota pegada al número | 1 / 1 con notas | 100 % (sentencia p. 24) |
| Encabezados o pies que quedaron | 6 / 16 | 38 % (todas del decreto de tablas: cabecera y pie de impresión de SUIN, etiquetas de botones, «A-Z») |

## 4. Datos críticos perdidos o alterados en S

Todos en la sentencia, página 24. La llamada de nota en superíndice queda
pegada al año, así que la fecha deja de ser una fecha válida:

| Correcto (imagen) | S |
|---|---|
| 10 de julio de 2008³ | 10 de julio de **20083** |
| 15 de julio de 2008⁴ | 15 de julio de **20084** |
| 15 de julio de 2008⁵ | 15 de julio de **20085** |
| 22 de julio de 2008⁶ | 22 de julio de **20086** |
| 23 de julio de 2008⁷ | 23 de julio de **20087** |
| 23 de julio de 2008⁸ | 23 de julio de **20088** |
| 8 de octubre de 2008⁹ | 8 de octubre de **20089** |

No se encontraron otros números, fechas, radicados ni artículos alterados en las
16 páginas digitales. El radicado 88001-23-31-000-2010-00028-01(AP), la
Ley 472 de 1998, el Decreto 2324 de 1984 y los artículos 163–181 coinciden en
todas las fuentes visuales.

## 5. Veredicto

**En páginas digitales, el bronce v2 copia el texto del PDF casi sin errores
(CER ≈ 0,3 % frente a transcripciones hechas desde la imagen) y con menos
errores que v1. Pero pega las llamadas de nota al pie a los números, lo que
alteró 7 fechas en una sola página, y en documentos escaneados todavía no se
ha medido.**

Limitaciones:
- **Tamaño:** 4 documentos de 56 y 16 páginas evaluables; los intervalos son
  amplios.
- **Fuentes LLM:** C1 y C2 no son verdad. Entre sí difieren poco (CER 0,11 %
  en digitales y 0,29 % en el escaneado), pero cada una tiene errores propios:
  C2 leyó «pretendan», «desmplayar» y «armada».
- **Error común no detectable:** si todas las fuentes se equivocan igual, no
  aparece. Las 20 líneas de control que miré coinciden con la imagen.
- **A no es independiente de S:** usa la misma capa de texto, así que comparte
  errores, como las fechas.
- **Normalización:**
  - unir «guion + salto de línea» borra guiones reales al final de línea;
  - quitar `|` borra también la barra literal de «Colombia | SUIN Juriscol».
- **Ceguera de C1 imperfecta:** antes de esta prueba ya había visto fragmentos
  del informe de calidad («Dr. Gustavo Aponte Santos, en cita», el
  encabezado v1 del Decreto 1120 y el artículo 3). Codex verificó con su log
  que C2 solo abrió `seleccion.json` y las imágenes.
- **OCR sin medir.**
- **Sin validación jurídica.**

## 6. Qué te falta hacer

1. **Adjudicar.** Abre `resultados/desacuerdos_con_propuesta.csv` (87
   desacuerdos y 20 controles). Mira el PDF o el recorte de `recorte` y
   escribe en `quien_acierta` una de S, A, V, C1, C2 o `ninguna`; si es
   `ninguna`, pon la lectura correcta en `nota`. La columna
   `propuesta_claude` es solo una sugerencia, con confianza.
2. **Calcular el error real:**
   ```powershell
   $b = 'C:/Users/Migue/Desktop/playas/ingesta/benchmarks/fidelidad'
   & "$b/trabajo/venv/Scripts/python.exe" -B "$b/calcular_error_real.py" "$b/resultados/desacuerdos_con_propuesta.csv"
   ```
   Así lo provisional pasa a «error real medido sobre una muestra».
3. **Medir el escaneado.** Instala Tesseract con español como administrador
   (`winget install UB-Mannheim.TesseractOCR` más `spa.traineddata`).
   Después:
   ```powershell
   $py = "$b/trabajo/venv/Scripts/python.exe"
   & $py -B "$b/trabajo/preparar_fuentes.py"
   & $py -B "$b/comparar.py" --fuentes S A V C1 C2
   ```
4. **Decidir sobre el pipeline**, aparte de esta medición:
   - separar las llamadas de nota al pie de los números en la extracción;
   - mapear U+F0B7 a «•»;
   - quitar la cabecera y el pie de impresión web de SUIN en silver.

## Archivos

- **Muestra y entradas:**
  - `seleccion.json`;
  - `estructura.csv`;
  - `fuentes/{S,A,A2,V,C1,C2}/`.
- **Imágenes (ignoradas por git):** `imagenes/`.
- **Código:**
  - `comparar.py`, `calcular_error_real.py`;
  - `trabajo/preparar_fuentes.py`;
  - pruebas en `ingesta/tests/unit/test_fidelidad.py`.
- **Resultados (`resultados/`):**
  - `metricas_paginas.csv`, `metricas_resumen.json`;
  - `criticos.csv`, `consenso.json`, `calibracion.json`;
  - `desacuerdos.csv`, `desacuerdos_con_propuesta.csv`.
- **Método detallado:** `README.md`.
