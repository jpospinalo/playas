# Comparación local de fuentes y fiabilidad

Ejecutar desde la raíz del repositorio, sin red ni servicios externos:

```powershell
& ingesta/benchmarks/fidelidad/trabajo/venv/Scripts/python.exe -I -B ingesta/benchmarks/ocr_referencia/comparar_fuentes.py --calibrar
& ingesta/benchmarks/fidelidad/trabajo/venv/Scripts/python.exe -I -B ingesta/benchmarks/ocr_referencia/comparar_fuentes.py
& ingesta/benchmarks/fidelidad/trabajo/venv/Scripts/python.exe -I -B ingesta/benchmarks/ocr_referencia/calcular_desacuerdos.py
```

La calibración se ejecuta también al inicio de la corrida completa. Contiene
ocho textos sintéticos con seis clases de contenido crítico, las tres dosis de
sustitución y el borrado de números, en ambos modos: **64 comprobaciones de
métricas y 12 controles de repetición**. Un fallo detiene la interpretación.

## Normalización y dirección de las comparaciones

Todas las fuentes reciben exactamente la misma función. `estricto` conserva
las distinciones tipográficas anteriores y añade la eliminación de las
envolturas LaTeX `\( [^{N}] \)` y `\( [N] \)`, conservando N aparte. `contenido`
además equipara comillas dobles tipográficas y angulares con las rectas,
comillas simples tipográficas con apóstrofo, rayas en/em con guion ASCII y
elipsis con tres puntos. Se aplica también después de decodificar entidades
HTML. No borra puntuación textual, dígitos ni tildes. Los prefijos de línea `>`,
`-`, `+` y `*` ante dígitos o signos numéricos se conservan. En estricto solo
se retira una cita `> ` ante texto no numérico o una viñeta `- ` / `* ` ante
letra; `+ ` se admite como viñeta únicamente en contenido. Ambas representaciones
se entregan siempre; contenido es principal para reducir discrepancias que
solo reflejan convenciones de edición o transcripción. No repara errores
ortográficos, números ni ligaduras.

En `S_mio_vs_U`, S_mio es hipótesis y U es referencia operativa. En
`S_prof_vs_U`, S_prof es hipótesis. En `S_mio_vs_S_prof`, S_prof es referencia.
En el control `capa_vs_U`, la capa PDF es hipótesis: **esta dirección es la
inversa de la FASE 1**, por lo que los denominadores de CER/WER cambian.

Los criterios de normalización, Levenshtein exacto, multiconjuntos, LCS de
trigramas, críticos regex y ruido se detallan en README.md. Los críticos se
entregan por categoría, con recall bidireccional y faltantes/extras que
conservan multiplicidad. El recall crítico global suma categorías solapadas;
no es proporción de citas jurídicas únicas. El ruido no modifica CER/WER.
En S_prof, sin páginas, los candidatos a encabezado/pie son líneas normalizadas
de hasta 250 caracteres que aparecen al menos tres veces: no se afirma su
posición. Puede incluir texto repetido del cuerpo; es menos preciso que el
criterio de primera/última línea de las fuentes paginadas. Los agregados de
ruido conservan conteos por clase y las 50 palabras más frecuentes; las listas
completas permanecen en los CSV por página/documento.

## Selección y comparabilidad

Se leen únicamente U y sus metadatos, los bronces de las dos corridas de
S_mio y los originales PDF permitidos. No se abren carpetas ni resultados
de revisión visual. No se ejecuta ningún contenido del corpus. La biblioteca
común se carga por ruta de código propia, nunca desde entrada.

S_prof se obtiene con `git ls-tree -r -z origin/corpus data/documents/bronze`
y `git cat-file blob <objeto>`. Se exige la revisión `517c399`; no se hace
checkout ni se escribe en `data/`. El emparejamiento usa la ruta esperada
por categoría y nombre del PDF con extensión `.md`, tras NFC, preservando
espacios. Se registra la ruta original de Git y su objeto. Los Markdown
sin correspondencia con U quedan fuera; no se empareja por similitud de texto.

`duplicado_de` se elimina antes de calcular. S_mio se divide por `\n\f\n`;
U se alinea por sus marcadores numéricos, sin desplazar páginas. Se omiten
las exclusiones de `resultados/paginas_excluidas.csv` en ambos lados.

S_prof no tiene marcadores: **no hay comparación paginada ni estratificación
por página digital/OCR para esa fuente**. Para impedir que las páginas U
retiradas aparezcan como falsas inserciones de S_prof, se omiten íntegros los
tres documentos afectados en las comparaciones con S_prof. Se ofrece S_mio
frente a U en ese mismo conjunto de documentos completos, además de S_mio
frente a U sobre todas las páginas elegibles. Las cifras documentales exactas
se calculan sobre concatenaciones, sin promediar CER por página: pueden diferir
del cociente de las ediciones paginadas por la alineación entre páginas.

Tipo de página: OCR solo si su número figura en `ocr_pages`; digital en caso
contrario. Se conserva aparte `caracteres_capa_texto_pdf` y los estratos
`capa_ge80`/`capa_lt80`. Las 29 páginas de Carrero (`a44a`) llevan
`capa_ocr_incrustada=true`, aunque la ruta de extracción diga digital.
Un documento es digital u OCR solo cuando todas sus páginas elegibles son de
ese tipo; en otro caso es mixto. `con_tabla` por página exige `<table>` en U;
por documento significa **alguna** página con tabla, no el texto aislado de
las tablas. El control de capa se limita a páginas con >=80 caracteres según
los metadatos de U.

## Agregación e incertidumbre

Se informan cocientes micro, LCS/total de n-gramas y críticos comunes/totales.
Los IC95 percentil usan 2.000 remuestreos con reemplazo, semilla 27102026,
por página y por documento completo. Los agregados documentales solo admiten
bootstrap documental; no se fabrica un IC por página de S_prof. Numeradores
y denominadores permanecen juntos. Los denominadores vacíos quedan nulos.
El semáforo CER es verde <1%, amarillo de 1 a 3% inclusive y rojo >3%.

La sensibilidad al error de U muestra la fórmula solicitada para e_U=0,24%
y e_U=1,23%, su envolvente `[max(0,CER_obs−0,0123), CER_obs+0,0123]` y la
fracción máxima de discrepancia compatible con cada presupuesto de error
`min(1,e_U/CER_obs)`. No se obliga a atribuir a U esa fracción.

**Advertencia dimensional:** la desigualdad triangular requiere distancias
de caracteres y denominadores compatibles. El rango facilitado por el usuario
es error de **palabra**: no constituye una cota válida del error de caracteres
ni da el CER real respecto a una referencia perfecta de longitud desconocida.
Por ello estos intervalos se etiquetan como escenarios hipotéticos, separados
de los IC bootstrap. No se han abierto revisiones visuales para verificarlos.

## Repetibilidad y alertas

Se comparan SHA256 de todos los `.txt`, `.extraction.json` y `.quality.json`
de las dos corridas, también fuera de U. Se enumeran archivos ausentes,
campos JSON distintos y páginas de texto distintas. Los manifiestos no forman
parte de esa comprobación solicitada.

En las páginas OCR de S_mio se estudian confianza y caracteres por página,
además de medidas y banderas documentales de calidad. A nivel documento se
usan documentos con al menos una página OCR elegible; la confianza es la media
de las páginas OCR medidas y el CER abarca todo el documento elegible. No se
mezcla una confianza ausente con cero.

Spearman usa rangos medios en empates. AUC da medio crédito a empates; mayor
riesgo corresponde a menor confianza/caracteres o a la dirección declarada en
calidad. Se define página/documento malo con CER contenido >3% y >5% por
separado. Se ofrecen Youden y un umbral con sensibilidad observada >=0,9,
con sensibilidad, especificidad e IC bootstrap de AUC, Spearman y umbrales.
Se remuestrean documentos completos también en el análisis paginado, evitando
tratar como independientes las medidas documentales repetidas. Se cuenta
cuántas réplicas tienen las dos clases. AUC sin dos clases y correlaciones
constantes quedan nulas; un predictor constante no recibe umbral útil.

Son umbrales **exploratorios dentro de muestra**, sin validación externa ni
garantía de sensibilidad futura. Los IC no corrigen el optimismo de selección.

## Causas

Reglas de indicios, que pueden solaparse: confianza <85; orden LCS <0,8 con
recuperación >=0,9; tabla en U; extras de encabezado/pie >=5 palabras y >=20%
de los extras; número de 2–4 dígitos seguido de llamada de 1–2 dígitos en U
fusionados en S; ligaduras U+FB00–FB06 o privados U+E000–F8FF (incluido U+F0B7);
y el documento con capa OCR incrustada. Sin regla aplicable se indica
`sin_causa_reglada`. No se diagnostica causalidad a partir de la correlación.

Se clasifican todas las páginas y se muestran las 15 peores por CER, además
de los cinco peores documentos con sus causas por página. Para conservar el
total de ediciones, cada página reparte sus ediciones a partes iguales entre
sus indicios (1/k). Se entrega además el conteo solapado. No es localización
de cada edición ni estimación causal de su mecanismo.

## Adjudicación ciega

`desacuerdos.csv` contiene 30 segmentos de 30 páginas diferentes, 15 digitales
y 15 OCR, con textos de 3–25 palabras normalizadas en contenido. Se alinean
palabras mediante Levenshtein exacto y se añade contexto. Quince selecciones
priorizan una coincidencia crítica regex en el tramo editado (8 digitales,
7 OCR); las otras quince se toman al azar (7 digitales, 8 OCR) y pueden
incluir críticos por casualidad. Se registran semilla y rangos en el manifiesto.
La selección por página y luego segmento no es una muestra uniforme de todas
las ediciones del corpus.

Tras mezclar los segmentos, A/B se asigna al azar con semilla registrada.
**La tabla de revisión no contiene `quien_es_A` ni etiquetas de fuente en
texto_A/B.** La clave está exclusivamente en `clave_desacuerdos.csv`.
Veredicto y nota se dejan vacíos; la generación se niega a sobrescribirlos si
ya hay adjudicación o notas.

Los recortes PNG están a 200 dpi en `trabajo/recortes_desacuerdos/`, con nombres
opacos D001…D030. Se usa un ancla única de palabras PyMuPDF cerca del segmento
y márgenes de contexto. Si la capa no permite localizarlo de forma unívoca,
se entrega la página completa. El manifiesto registra coordenadas, método,
dimensiones y resolución. No se ejecuta OCR nuevo ni se inventan coordenadas.

`calcular_desacuerdos.py` interpreta A/B como solo esa variante correcta,
`ambos` como ambas correctas y `ninguno` como ambas erróneas. Estima errores
por segmento de S y U, fracciones unilaterales, ambas erróneas/correctas y
fracción de U entre errores atribuidos. Usa IC bootstrap dentro de los
estratos de tipo/prioridad, preservando su composición. Son estimaciones
condicionadas a los desacuerdos adjudicados; no CER/WER global ni estimaciones
de error para los pendientes. Si no hay veredictos, informa pendiente y nulos.

## Salidas

Todo el análisis tabular queda en `resultados/fase3/`: `paginas.csv`,
`documentos.csv`, `resumen.json`, `informe.md`, `calibracion.json`,
`emparejamiento.json`, `procedencia.json`, `repetibilidad.{json,csv}`,
`alertas.{json,csv}`, `causas.json`, `causas_paginas.csv`, `desacuerdos.csv`,
`clave_desacuerdos.csv`, `muestreo_desacuerdos.json` y
`evaluacion_desacuerdos.json`. Los CSV de métricas contienen críticos y ruido
en celdas JSON. Las salidas previas de la FASE 1 no se reinterpretan como
resultados del modo contenido; esta corrida nueva tiene procedencia propia.

`--reanudar` permite volver a calcular ruido, IC y FASE 4 desde los CSV de
distancias completos, sin repetir Levenshtein documental. Verifica la huella
de metricas.py y comparar_fuentes.py, los metadatos de entrada y los SHA256
directos de cada Markdown U, los tres archivos de cada bronce S_mio y cada
blob S_prof usado, guardados en procedencia.json al calcular las métricas.
Regenerar integridad.json o repetibilidad.json no autoriza reutilizar CSV
de fuentes modificadas. Una procedencia antigua sin esas huellas obliga a
recalcular. Requiere una corrida
completa previa y las entradas sin cambios. Los veredictos/notas existentes
siguen protegidos contra sobrescritura, también al recalcular sin `--reanudar`:
se conserva la muestra revisada y sus recortes.
Con `--reanudar --solo-resumen` se conservan alertas, causas y recortes de la
corrida completa verificada; solo se recalculan ruido, agregados e informe.
