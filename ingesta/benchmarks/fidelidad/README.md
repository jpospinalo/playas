# Fidelidad del bronce frente al PDF

Todo se ejecuta localmente, sin AWS, servicios LLM, Chroma, embeddings ni red.
En la preparación anterior se intentó instalar Tesseract con Chocolatey; esta
revisión no intenta conexiones ni instalaciones.
No se cambió de rama, no se modificó `data/` ni la configuración sparse, y no se
hicieron commits ni push. La fase ciega terminó: esta revisión lee las
transcripciones existentes C1/C2 y ejecuta `--fuentes S A V C1 C2`.
Se conservan las fuentes, las imágenes, `estructura.csv`, `seleccion.json` y
`resultados/desacuerdos_con_propuesta.csv`. Se usa `--sin-recortes` para regenerar
los resultados sin modificar las imágenes.

## Fuentes y procedencia

`seleccion.json` fija cuatro documentos y 18 páginas, con numeración desde uno.
`preparar_fuentes.py` comprueba el SHA-256 y la ruta contra el mapa de
originales. No recorre originales ajenos a la selección. El script y la lógica
pura de alineación (`anclas.py`) están fuera de `trabajo/`, que está ignorado por
Git y solo contiene insumos y salidas locales. Los tests importan `anclas.py`
sin cargar el extractor ni necesitar esos archivos locales.

Desde la raíz del repo, la preparación se ejecuta con:

```sh
python -B ingesta/benchmarks/fidelidad/preparar_fuentes.py --pdftotext pdftotext
```

La raíz de las salidas sigue siendo este benchmark; el mapa y los originales
se buscan en `trabajo/mapa_originales.json` y `trabajo/originales/`. En Windows,
`--pdftotext` puede indicar la ruta al ejecutable de Poppler.

- **S:** importa exclusivamente `ingest.offline.extract.read_document`, la función
  que invoca `LayerStore.process` al producir bronce. No importa el orquestador de
  sync ni ejecuta capas posteriores. Guarda el texto y la metainformación con el
  mismo contenido y selección de campos del bloque de bronce de `layers.py` en
  `trabajo/capas_fidelidad/bronze/<sha256>.txt` y `.extraction.json`. El texto se
  divide por `\n\f\n`. Los documentos digitales se extraen completos, pero solo se
  exportan las páginas seleccionadas a `fuentes/S/`. No se aplica `clean_pages`,
  que corresponde a una etapa posterior.
- **A:** `pdftotext -enc UTF-8 -f N -l N original -`, sin `-layout`. A conserva su
  salida UTF-8, incluido el separador de página; la normalización elimina este.
  Las páginas sin capa de texto están marcadas explícitamente como `no aplica`.
  Un archivo vacío cuyo estado sea `disponible` sí se evalúa como hipótesis vacía.
- **A2:** `pdfplumber.pages[N-1].extract_text()`, solo apoyo; no vota en consenso.
- **V:** `git ls-tree -r -z HEAD data/documents/bronze` y `git cat-file blob SHA`.
  La búsqueda de rutas usa NFC porque los nombres versionados están en NFD. Cada
  `procedencia.json` registra la ruta real y el blob. El texto se conserva en NFC.
  Se buscan dos n-gramas únicos de seis palabras de los extremos de S y de A; se
  elige la alternativa que deja menos palabras fuera. Se toleran hasta 35 tokens
  de encabezado/pie distintos, se exige orden y una extensión relativa entre 0,45
  y 2,2. Los cortes se hacen en las anclas, sin extender párrafos entre páginas.
  Los tokens alfanuméricos se usan solo para encontrar anclas: el tramo guardado
  conserva su puntuación y Markdown. Los offsets son caracteres del documento NFC.
  Los bordes anteriores/posteriores a las anclas pueden quedar fuera; se registra
  cuántas palabras del PDF quedan fuera. Por tanto, la cobertura es una alineación
  parcial por página y sus diferencias de borde deben revisarse.
  Si faltan anclas o hay solapamiento, se guarda `documento.txt` y se marca
  `solo_documento`; ese documento completo no se compara como si fuera una página.

Estado de esta ejecución:

| Documento | V alineado por página | V solo_documento |
| --- | --- | --- |
| sentencia | 1, 2, 9, 16, 24, 31 | ninguna |
| escaneado | ninguna | 1, 2 |
| tablas | 3, 4, 5, 6 | 1, 7 |
| norma | 5 | 1, 3, 7 |

S tiene 16 páginas digitales disponibles y dos OCR pendientes. A y A2 tienen 16
páginas con texto y dos `no aplica`. V tiene 11 páginas alineadas y siete
`solo_documento`, con los motivos en `fuentes/V/paginas.json`.
C1 y C2 tienen las 18 páginas disponibles cada una.

**Tesseract pendiente.** Se intentó `choco install tesseract --yes --no-progress
--limit-output ... --params="/Languages:spa"`. Chocolatey terminó con código 1 e
informó exactamente:

```text
Unable to load the service index for source https://community.chocolatey.org/api/v2/.
Intento de acceso a un socket no permitido por sus permisos de acceso 104.18.20.76:443
```

El registro íntegro, incluido el aviso de sesión sin elevación y el fallo final
de instalación, está en `trabajo/instalacion/intento.txt` y se reproduce en
`fuentes/S/paginas.json`. No se intentó otro OCR ni otra instalación tras el fallo.
La presencia de `spa` se comprobará con `tesseract --list-langs` al regenerar S.

## Normalización exacta

Se aplica la misma función a S, A, V, C1 y C2:

1. NFC, minúsculas y conversión CRLF/CR a LF.
2. Se elimina el guion ASCII y el salto de línea entre **letras**, con espacios
   horizontales opcionales. No se unen guiones entre números ni guiones internos.
3. FF se convierte a salto. Se eliminan líneas completas `Página N`, `Pág. N`,
   `Page N`, con la variante `de/of/N`, además de `<!-- page N -->` y `[[página N]]`.
   También se eliminan `página N de M` y `page N of M` en **cualquier posición**,
   por ejemplo junto a la URL de un pie de navegador. Esta regla figura en
   `REGLAS` y se aplica a todas las fuentes.
   **No** se eliminan líneas que contienen solo dígitos, pies ni encabezados
   repetidos: podrían contener datos críticos.
4. Se eliminan imágenes Markdown `![alt](ruta)` y etiquetas HTML `<img ...>`;
   los `#` de encabezados al inicio de línea; los delimitadores de negrita `**`
   y `__`; las líneas completas de separadores de tabla con tres o más guiones
   y alineadores `:`, por ejemplo `|---|:---:|`.
5. La barra `|` se sustituye por espacio como separador de celdas, también en
   encabezados literales como `Colombia | SUIN Juriscol`.
6. Cada racha de dígitos en superíndice se convierte en un número aparte precedido
   de espacio: `2008³` pasa a `2008 3` y `nota¹²` a `nota 12`. No se aplica NFKC,
   para conservar las ligaduras.
7. Se conservan enlaces, cursivas, puntuación, dígitos y tildes. Se colapsa todo
   espacio Unicode a un espacio y se recortan extremos.

Solo desaparece la puntuación que forma parte de las construcciones anteriores.
No se usa limpieza específica de una fuente. Las celdas del CSV ya contienen
fragmentos normalizados y no se vuelven a normalizar al adjudicar: un fragmento
como `page 3` puede ser contenido legítimo dentro de una línea del original.

## Métricas, consenso e intervalos

`metricas_paginas.csv` contiene todos los pares ordenados de fuentes disponibles:
`fuente` es la hipótesis y `referencia` el denominador. A2 no participa. Se emiten
ambas direcciones porque CER, WER y recuperación dependen de la referencia.
CER y WER usan Levenshtein propio exacto (vectores de bits para la distancia;
programación dinámica para alinear palabras). Precisión y recuperación comparan
multiconjuntos de palabras. Un denominador vacío produce `null`, no cero.

El resumen agrega mediante cocientes de sumas, por documento y tipo de página y
para TODOS los documentos, siempre separando digital/OCR. El bootstrap usa
2.000 remuestreos **de páginas** con reemplazo, semilla 27102026 y percentiles
interpolados 2,5 y 97,5. Con una sola página el intervalo degenera; la muestra
pequeña no justifica generalizar al corpus. Las páginas ausentes, pendientes,
`no aplica` o `solo_documento` se documentan y se excluyen, sin imputar métricas
OCR. Una extracción disponible vacía participa en pares, críticos y consenso:
frente a una referencia no vacía tiene CER = WER = 1.

`criticos.csv` calcula recall de S respecto de cada otra fuente disponible,
por categoría: números (incluidos decimales), fechas numéricas y escritas,
radicados separados o compactos, Artículo/Art., Ley y Decreto con número/año.
Compara apariciones, no conjuntos. `faltantes` son ocurrencias de la referencia
que no están en S; `extras_o_cambiados` son ocurrencias de S sin correspondencia
exacta. No se afirma que un extra sea necesariamente el sustituto de un faltante.
Las categorías se solapan (un número puede pertenecer también a una fecha).

El consenso alinea cada otra fuente con S, y de forma simétrica con V. La unión
de intervalos de palabras superpuestos define segmentos de discrepancia. En cada
segmento se proyecta la lectura de todas las fuentes disponibles. Se cuenta el
apoyo al objetivo y se agrupan las lecturas alternativas **exactamente iguales**.
Se omiten fuentes ausentes, sin considerarlas votos vacíos; un borrado de una
fuente presente sí cuenta como lectura vacía. Las fuentes `solo_documento` no
votan en esa página, aunque exista un archivo de texto anterior.

- `respaldado`: al menos una fuente coincide con el objetivo y no hay consenso contrario.
- `contradicho_por_consenso`: hay consenso contrario y ninguna fuente lo respalda.
- `en_disputa`: hay simultáneamente respaldo y consenso contrario.
- `indeterminado`: no hay respaldo ni consenso contrario.

Un consenso contrario requiere dos o más lecturas iguales distintas del objetivo.
La lectura concordante debe ser no vacía, o el grupo debe incluir al menos una
fuente visual C1/C2. Dos vacíos de A/V no bastan para contradecir a S; se aplica
la misma regla al objetivo V. El JSON conserva los conteos de apoyo y de consenso
contrario. Para S votan A/V/C1/C2 y para V votan S/A/C1/C2.
Este acuerdo es **PROVISIONAL**, no una verdad verificada: los extractores pueden
compartir errores y la alineación de V es parcial. El porcentaje usa caracteres
del objetivo normalizado entre todos sus caracteres disponibles. Se informan dos
variantes: solo `contradicho_por_consenso` (`porcentaje_PROVISIONAL`) y la suma de
`contradicho_por_consenso` + `en_disputa` (`porcentaje_con_disputa_PROVISIONAL`).
Los insertos de longitud cero no aportan caracteres al numerador;
quedan visibles en los segmentos y en CER/WER. También se ofrecen porcentajes
por página y separados para digital/OCR.

Resultados **PROVISIONALES** de esta revisión (sin adjudicación humana):

| Objetivo | Caracteres disponibles | Solo contradicho | Contradicho + en disputa |
| --- | ---: | ---: | ---: |
| S | 27.619 (16 páginas digitales) | 16 / 27.619 = 0,057931 % | 75 / 27.619 = 0,271552 % |
| V | 20.295 (11 páginas digitales) | 166 / 20.295 = 0,817935 % | 183 / 20.295 = 0,901700 % |

S y V no tienen páginas OCR disponibles: sus porcentajes OCR son nulos.

## Revisión humana y error verificado

`desacuerdos.csv` contiene hasta 150 desacuerdos, con estas prioridades:

- **a:** todos los segmentos S contradichos, en disputa o indeterminados.
- **b:** los restantes segmentos S donde C1 o C2 discrepan de S.
- **c:** contenido crítico, primero objetivo S y luego V.
- **d:** los restantes segmentos V contradichos o en disputa.
- **e:** el resto.

Dentro de cada nivel el orden es estable por documento, página y posición, con
la precedencia S/V indicada en c. Se agrupan segmentos del mismo objetivo y página
separados por hasta tres palabras, incluyendo el texto intermedio. También se
fusionan los solapes en cualquier fuente, incluidos los de objetivos distintos,
para conservar los segmentos prioritarios sin duplicar rangos. La fila agrupada
hereda `objetivo`, `clase` y `prioridad` del miembro de mayor prioridad; el JSON
conserva cada segmento original para calcular porcentajes y verificar cobertura.
Las columnas anteriores se mantienen y se añaden `clase` y `prioridad`.

Si a+b superan las 150 filas agrupadas, se prioriza S según ese orden y se informa
el exceso y los segmentos sin cubrir en `metricas_resumen.json` y en la salida
del comando. La revisión actual tiene **87 desacuerdos**: a=18, b=5, c=40, d=23,
e=1. No hay exceso de a+b. Están cubiertos los **2/2 segmentos S contradichos y
17/17 en disputa**; no hay segmentos S indeterminados.

Se añaden 20 controles aleatorios de ventanas
disjuntas de hasta 12 palabras donde coinciden todas las fuentes **solicitadas**;
todas deben estar presentes. Si faltan fuentes o ventanas suficientes, se informa
el conteo disponible, sin fabricar controles. La semilla es fija. Se filtran contra
los rangos ocupados de **todas** las fuentes de los desacuerdos y de otros controles,
también cuando el texto repetido produce proyecciones diferentes. Esta ejecución
mantiene **20 controles** y 107 filas en total. La aceptación estructural por
`calcular_error_real.evaluar` se verificó con adjudicaciones temporales en memoria,
sin guardar adjudicaciones ni presentar esas lecturas como verdad verificada.

`rangos` contiene índices de palabras normalizadas [inicio, fin) por fuente;
`fuentes_presentes` distingue ausencia de una lectura legítimamente vacía.
Se alinean estas palabras con coordenadas PyMuPDF y se recorta todo el intervalo,
con 35 puntos de contexto vertical y ancho de página completo. Para OCR se
prepara el TSV repitiendo exactamente el comando, imagen 2x, spa y psm=3 del
pipeline, sin modificarlo. Si la correspondencia del segmento con las coordenadas
no alcanza 70 %, se guarda la página completa y se indica en `localizacion`.
Esta revisión no regenera recortes: `recorte` queda vacío y `localizacion` indica
`no generado`. Las imágenes anteriores se conservan y no se vinculan a los nuevos IDs.

Completar `quien_acierta` con S/A/V/C1/C2 o `ninguna`. Si es `ninguna`, `nota`
debe contener únicamente la lectura correcta; `[VACÍO]` indica que no hay texto.
La corrección manual se normaliza con `fragmento=True`: conserva el contenido que
las reglas de marcadores o separadores de línea completa podrían borrar. Las
celdas de las fuentes se usan literalmente como texto ya normalizado, tanto para
las métricas como para comprobar errores en los controles.
Las celdas de las fuentes no deben editarse. Conservar una copia del CSV antes de
volver a ejecutar `comparar.py`, que regenera las salidas y deja la revisión vacía.

`calcular_error_real.py` reconstruye las referencias de los segmentos adjudicados,
evalúa todas las fuentes presentes, suma las distancias **por segmento** y agrupa
por página para bootstrap e IC de fidelidad `1 - CER`. Informa CER/WER, fidelidad
condicional a la muestra revisada y tasa de líneas de control con error por
fuente. Rechaza valores inválidos, fuentes ausentes, `ninguna` sin lectura y rangos
superpuestos. Por defecto exige el CSV completado; el modo parcial es explícito.
No presenta el resto de la página como verificado ni extrapola al corpus: los
desacuerdos son una muestra deliberadamente sesgada por las prioridades anteriores.
CER puede ser mayor que uno y, en consecuencia, fidelidad puede ser negativa.
No se ha calculado error humano real porque aún no hay adjudicaciones.

## Calibración y comandos

`--calibrar` usa como referencias sin alterar las 16 páginas digitales de A e
inyecta sustituciones en posiciones distintas al 0,5 %, 1 % y 3 %, con redondeo
al carácter entero más próximo. El símbolo reservado U+FFFD garantiza que cada
posición elegida cambia. Se admite una tolerancia de dos caracteres por página,
incluido el efecto del colapso de espacios. También se borran todos los dígitos:
el recall de cada categoría presente debe caer a cero. La calibración falla con
código distinto de cero si cualquiera de las comprobaciones falla.

Esta ejecución pasó 64 comprobaciones: 48 de sustitución y 16 de borrado. El
borrado dejó cero recuperaciones de 437 ocurrencias críticas (categorías
superpuestas). `resultados/calibracion.json` contiene tasas, redondeos y resumen
micro; los tests también usan referencias sintéticas y una implementación lenta
independiente para contrastar Levenshtein.

El CER micro recuperado fue 0,499692 %, 1,003005 % y 3,005395 % respectivamente,
con 138, 277 y 830 sustituciones sobre 27.617 caracteres. Pasaron **101 tests**
(44 casos adicionales respecto de los 57 existentes), `ruff check` y
`ruff format --check` sobre los tres archivos Python autorizados.
Las salidas contienen 284 filas de métricas, 354 filas de críticos, 693 segmentos
de consenso y 107 filas de revisión (87 desacuerdos y 20 controles).

Desde la raíz del repositorio, PowerShell:

```powershell
$b = 'C:/Users/Migue/Desktop/playas/ingesta/benchmarks/fidelidad'
$py = "$b/trabajo/venv/Scripts/python.exe"
$env:PYTHONDONTWRITEBYTECODE = '1'

# Fuentes existentes; fase ciega terminada. No modificar imágenes.
& $py -B "$b/comparar.py" --fuentes S A V C1 C2 --sin-recortes
& $py -B "$b/comparar.py" --fuentes S A V C1 C2 --calibrar

# Después de completar y guardar una copia del CSV adjudicado.
& $py -B "$b/calcular_error_real.py" "$b/resultados/desacuerdos_revisados.csv"

# Tests y formato, sin cachés ni bytecode fuera de las rutas autorizadas.
$tmpFidelidad = Join-Path $env:TEMP ('fidelidad-' + [guid]::NewGuid().ToString('N'))
& ingesta/.venv/Scripts/python.exe -B -m pytest ingesta/tests/unit/test_fidelidad.py --basetemp=$tmpFidelidad -p no:cacheprovider
$archivos = @("$b/anclas.py", "$b/preparar_fuentes.py", "$b/comparar.py", "$b/calcular_error_real.py", "ingesta/tests/unit/test_fidelidad.py")
& ingesta/.venv/Scripts/python.exe -B -m ruff check --no-cache $archivos
& ingesta/.venv/Scripts/python.exe -B -m ruff format --check --no-cache $archivos
```

Los scripts de comparación no requieren nuevas dependencias. Para generar
recortes se utiliza PyMuPDF ya instalado; la preparación usa también pdfplumber.
`--sin-recortes` permite calcular métricas sin el renderizado.
