# Fiabilidad del bronce de `ingest.offline` frente a una referencia OCR

> **U no es la verdad.** U es una transcripción automática SIN verificar,
> hecha con Unlimited-OCR mediante una conversión MLX no oficial (bf16). Toda
> cifra contra U es **fidelidad frente a U**. Solo la adjudicación humana
> permite hablar de error real. **Nada de esto está validado por abogados.**

Material y código: `ingesta/benchmarks/ocr_referencia/`. Las rutas de este
documento son relativas a esa carpeta. El zip de U, los PDFs y las capas
generadas están en `entrada/` y `trabajo/`, fuera de git.

## Resumen

| | Resultado |
|---|---|
| **Validez de U** | Fiable como vara en texto corrido: error de palabra estimado del 0,54 % (IC95 0,31–1,23 %) en 24 páginas revisadas visualmente por dos revisores ciegos. Menos fiable en tablas incrustadas como imagen y en llamadas de nota. 7 páginas excluidas por bucles. |
| **Defecto encontrado en el pipeline** | El TSV de Tesseract se leía con comillas CSV: una palabra que empieza por `"` se tragaba las filas siguientes, que acababan en el bronce como coordenadas y confianzas. Afectaba a 31 de 304 páginas OCR en 9 documentos. **Corregido** (commit `8df8a96`). |
| **Fidelidad frente a U tras la corrección** | Páginas digitales: CER 1,06 % (IC95 0,63–1,61). Páginas OCR: CER 1,84 % (IC95 0,81–3,36), antes 21,60 %. |
| **Bronce del profesor** | Solo comparable por documento (Markdown sin páginas). CER 12,03 % frente a U, recall crítico 61 %. |
| **Repetibilidad** | 159 de 159 archivos de bronce idénticos byte a byte entre dos corridas con cachés vacías. |
| **Alerta para documentos nuevos** | Confianza OCR media por página ≤ 95 → revisión humana. AUC 0,885 para CER > 3 %. |

## 1. Validación de la referencia U (FASE 1)

Integridad (`resultados/integridad.json`, `resultados/verificacion.json`):

- **Coinciden con mapping:** los SHA256 y el número de páginas de los 54 PDFs de `data/documents/raw`.
- **Archivos 1 a 1:** hay un `.md` y un `.raw.txt` por cada documento.
- **Recuento de páginas:** marcadores de página completos y consecutivos; 1.224 páginas procesadas más 70 del duplicado de Carrero dan 1.294.
- **Duplicado:** el texto de Carrero es idéntico al de su original y se cuenta una sola vez.
- **Única discrepancia:** queda una marca `<|det|>` residual en el `.md` de las normas de playas de Cartagena (`5beb`), página 33. Esa página ya está excluida.
- **No incluidos en U:** los 2 `.md` de normativa de `raw`, que no son PDF.

**Páginas excluidas** (`resultados/paginas_excluidas.csv`): son las 7 que alcanzaron el tope de tokens y quedaron marcadas como `repeticion`. En las 7 se confirmó un bucle por n-gramas.

| Documento | Páginas |
|---|---|
| AP Felipe José Campo (`ce3c`) | 1 |
| CE 2da NYR 2009-164 FEPEP (`e806`) | 29 |
| Normas base de playas de Cartagena (`5beb`) | 31–35 |

El detector de n-gramas y líneas repetidas no encontró más bucles.

**U frente a la capa de texto del PDF** (918 páginas digitales, `resultados/u_vs_capa_texto.csv`):

- **Global:** CER 2,54 % y WER 3,55 %. La mediana por página es 0,66 %.
- **Tablas:** en las páginas con tabla el CER sube al 12,68 %.
- **No mide solo errores de U.** La capa de texto también falla:
  - pega las llamadas de nota a los números;
  - emite viñetas como U+F0B7;
  - lee las tablas por columnas;
  - un documento (AP Gabriel Antonio Carrero, 29 páginas) es un escaneo con una capa OCR incrustada de baja calidad («lev», «ia», «tas»).
- **Sospechosas:** 16 páginas (`resultados/u_sospechosas.csv`).

**Revisión visual ciega** (`trabajo/revision_visual_*.tsv`): dos revisores LLM revisaron muestras de 12 páginas cada uno, a 200 dpi y con 6 digitales y 6 escaneadas por muestra. Ninguno vio la muestra ni el resultado del otro, y ninguno vio el bronce del pipeline. Las páginas de Claude se eligieron por cobertura (tablas, sellos, notas); las de Codex al azar con semilla 20261109. Sin contar marcado LaTeX, comillas ni puntos suspensivos:

| Muestra | Páginas | Palabras | Errores de U | Críticos | Tasa (IC95 bootstrap por página) |
|---|---:|---:|---:|---:|---:|
| Global | 24 | 11.407 | 62 | 7 | **0,54 %** (0,31–0,88) |
| Digitales | 12 | 5.745 | 39 | 6 | 0,68 % (0,30–1,24) |
| Escaneadas | 12 | 5.662 | 23 | 1 | 0,41 % (0,13–0,78) |

Errores típicos de U:

- palabras «corregidas» por el modelo («resultas» → «resultados», «oponible» → «opinable», «fáctico» → «práctico»);
- dígitos perdidos en números largos (un número predial de 29 dígitos con 28);
- «Artículo 3o» leído como «Artículo 30»;
- llamadas de nota envueltas en marcado LaTeX;
- **tablas escaneadas incrustadas en páginas digitales:** en una de ellas inventó filas y desplazó valores. Es el caso peor (12 errores en una página).

**Veredicto de la FASE 1:**

- **Usable como referencia:** texto corrido, digital o escaneado, con un error estimado del 0,3–1,2 % de palabras.
- **Usar con cautela:** tablas, sobre todo si son imágenes, y llamadas de nota.
- **Excluidas:** las 7 páginas con bucle.

## 2. Lo que cambió el profesor (FASE 2)

`git fetch --all --prune` con todas las ramas remotas como referencias de seguimiento, sin cambiar la configuración del clon. El trabajo del profesor (Juan, jpospinalo) está en **`origin/corpus` @ `517c399`** (8 nov.), que diverge de `origin/main` (11 commits por delante y 10 por detrás). `main` (`813b6aa`) incorpora 56 de sus commits. La rama `juan-felipe` es de otra persona (Juan Felipe Hurtado).

Cambios desde `f16586f`:

- **`data/documents`:** no tocó `raw`. Cambió 36 archivos de bronze, 39 de silver y 55 de gold. Son correcciones manuales verificadas: cifras, metadatos, resúmenes, palabras partidas, ponentes y la restauración de la Ley 28.
- **`ingesta/`:** 32 archivos. Hay contratos de prueba nuevos (secciones, normativa, tablas, catálogo local) y `utils/audit_local_corpus.py`. El código del pipeline Docling/LLM cambió poco: conserva el contexto de tablas de normativa y los encabezados y referencias.
- **docs:** `data/CORPUS_CATALOG.md`, `data/README.md`, `DOCUMENT_SECTIONS.md` y `SCRIPTS.md`.
- **Formato de su bronce:** Markdown de Docling, uno por documento y **sin marcas de página**. Por eso solo se compara con U a nivel de documento, por secuencia de palabras, que es menos preciso.

**Integración con `feat/ingesta-medallion-escalabilidad`:** una simulación de merge (`git merge-tree`) da conflictos en 6 archivos: `.gitignore`, `CLAUDE.md`, `data/import_to_chromadb.py`, `ingesta/docs/SCRIPTS.md` y los dos `ingesta/scripts/run*_pipeline.sh`. Las capas de datos no chocan, porque mi pipeline escribe en `data/documents-v2/`. Propuesta, sin ejecutar: **merge de `origin/corpus` en una rama nueva salida de la mía**, resolviendo a mano esos 6 archivos (sus scripts de entrada frente a los que delegan en `ingest.offline`). No conviene rebase, porque mi rama ya está publicada. Queda pendiente de tu confirmación.

## 3. Fidelidad frente a U (FASES 3 y 4)

Se usa la normalización «contenido» como cifra principal: NFC y minúsculas; comillas, rayas y puntos suspensivos unificados; tablas HTML aplanadas a texto de celdas; marcado LaTeX de las notas quitado. La «estricta» se reporta como control y difiere menos de 0,1 puntos en todo. La calibración pasa (64 de 64): las sustituciones inyectadas al 0,5, 1 y 3 % se recuperan como 0,50, 1,00 y 3,01 %.

### Por página, S_mio frente a U

Semáforo según tus referencias: CER < 1 % verde, 1–3 % amarillo, > 3 % rojo.

| Estrato | Páginas | CER antes | **CER después** | IC95 doc. (después) | WER después | Recall crítico | Orden (LCS) | Semáforo |
|---|---:|---:|---:|---|---:|---:|---:|---|
| Digital | 918 | 1,06 % | **1,06 %** | 0,63–1,61 | 1,90 % | 94,3 % | 96,9 % | 🟡 |
| OCR | 299 | 21,60 % | **1,84 %** | 0,81–3,36 | 3,31 % | 92,0 % | — | 🟡 |
| Con tabla | 54 | 25,70 % | ver nota | — | — | 80,0 % | 84,8 % | 🔴 |
| Capa OCR incrustada (Carrero) | 29 | 0,58 % | 0,58 % | — | 2,73 % | 93,0 % | 93,5 % | 🟢 |

«Antes» es el bronce con el defecto del TSV (`run1`); «después», el bronce corregido (`run3`). Las páginas digitales no cambian. Los estratos «con tabla» y orden de lectura se calcularon sobre `run1`. En la tabla de documentos de la FASE 3 (`resultados/fase3/informe.md`), el bronce plano tiene un CER del 12,90 % en documentos con tabla, porque pierde la estructura de filas y columnas.

### Rango que considera el error de U

Si U tuviera un error de palabra e_U entre el 0,31 % y el 1,23 %, la cota CER_obs ± e_U da estos rangos para S_mio después de la corrección. Es una sensibilidad, no una cota garantizada, porque mezcla error de palabra con CER.

| Estrato | CER frente a U | Si U fuera perfecta | Con e_U del 1,23 % |
|---|---:|---:|---:|
| Digital | 1,06 % | 1,06 % | 0,00–2,29 % |
| OCR | 1,84 % | 1,84 % | 0,61–3,07 % |

Las 30 adjudicaciones ciegas confirman que una parte de la discrepancia es de U (ver 4.6).

### Por documento: S_mio frente a S_prof

50 documentos completos, comparables en ambas fuentes. S_mio es el bronce con el defecto (`run1`).

| Fuente | Estrato | CER | WER | Recall crítico | Orden (LCS) | Semáforo |
|---|---|---:|---:|---:|---:|---|
| S_mio | digital (30) | 1,21 % (0,64–1,85) | 2,05 % | 93,7 % | 96,4 % | 🟡 |
| S_mio | OCR (18) | 22,76 % → ≈1,9 % tras la corrección | — | 97,0 % | 92,0 % | 🔴 → 🟡 |
| S_prof | digital (30) | 10,47 % (8,60–12,79) | 11,55 % | 60,3 % | 85,8 % | 🔴 |
| S_prof | OCR (18) | 20,87 % (13,05–39,49) | 21,43 % | 52,4 % | 76,4 % | 🔴 |

El Markdown del profesor:

- **pierde números:** recall crítico del 60 %. Docling descarta encabezados, pies, numeración y parte de las notas;
- **reordena bloques:** su orden de lectura (LCS) es más bajo;
- **en normativa se aleja mucho:** CER del 36 %.

Parte de esa diferencia es intencional, porque Docling limpia el documento. No es directamente un error, pero sí una pérdida de fidelidad frente a la página.

## 4. Pruebas de fiabilidad (FASE 4)

**4.3 Repetibilidad.** Dos corridas completas del bronce, cada una con su caché vacía: los 159 archivos (`.txt`, `.extraction.json`, `.quality.json`) son idénticos byte a byte (`resultados/fase3/repetibilidad.json`). Una tercera corrida con la corrección del TSV solo cambia los 9 documentos afectados.

**4.4 Alertas para documentos nuevos** (bronce corregido, 299 páginas OCR):

| Página mala si | Spearman (confianza, CER) | AUC (IC95 por documento) | Umbral de Youden | Umbral con sensibilidad ≥ 90 % |
|---|---:|---:|---|---|
| CER > 3 % (69 páginas) | −0,685 | **0,885** (0,78–0,96) | confianza ≤ 95,1 → sens. 0,84, esp. 0,84 | ≤ 95,3 → esp. 0,70; revisa 132 de 299 páginas |
| CER > 5 % (37 páginas) | — | 0,872 (0,80–0,97) | ≤ 95,1 → sens. 0,86, esp. 0,76 | ≤ 95,3 → esp. 0,63 |

**Umbral recomendado: enviar a revisión humana las páginas OCR con una confianza media de Tesseract ≤ 95.** Los caracteres por página no predicen nada (AUC ≈ 0,5). Son resultados dentro de muestra y exploratorios, sin un conjunto de prueba independiente. Con el bronce defectuoso la AUC era 0,830.

**4.5 Causas de error** (ediciones repartidas, sobre `run1`):

| Causa | Parte de las ediciones |
|---|---:|
| Orden / columnas (LCS bajo) | 54 % |
| Sin causa asignada | 17 % |
| Tablas | 13 % |
| OCR de baja confianza | 9 % |
| Llamadas de nota pegadas a números | 6 % |
| Viñetas U+F0B7 | < 1 % |

El «orden / columnas» de `run1` era, sobre todo, el defecto del TSV: las filas coladas destrozan el orden. Tras la corrección, las causas restantes son:

1. **tablas:** el bronce plano pierde la estructura y una tabla en imagen queda en manos del OCR;
2. **llamadas de nota pegadas a números** («2008³» → «20083»);
3. **OCR de baja confianza.**

**4.6 Muestra visual adjudicada a ciegas** (`resultados/fase3/desacuerdos.csv`, con la clave aparte): 30 desacuerdos entre S_mio y U, 15 digitales y 15 OCR. Mostré los textos como A/B en orden aleatorio y anoté quién acertaba mirando solo la imagen. Las 15 OCR eran de `run1`, antes de la corrección.

| | Acierta S | Acierta U | Ambos | Ninguno |
|---|---:|---:|---:|---:|
| Digitales (15) | 6 | 3 | 6 | 0 |
| OCR (15) | 0 | 14 | 0 | 1 |

- **En digitales, U se equivoca más que S en los desacuerdos:**
  - U cambia palabras («providencia» → «provincia», «fáctico» → «práctico», «1271» por [27]);
  - S pega llamadas de nota («202285»).
- **En OCR (Tesseract 2019, `run1`) acierta U casi siempre.** Una de esas filas era una fila TSV colada.
- **Agregado sobre los 30:**
  - S erra el 60 % de los segmentos (IC 53–70 %) y U el 23 % (IC 10–37 %);
  - de los errores atribuibles a una sola fuente, el 26 % son de U.

  Es una tasa condicionada a los desacuerdos, no un error global.

## 5. Mejoras del pipeline (FASE 5)

- **Gatillo de la FASE 5:** se cumplían los tres disparadores (OCR > 3 %, digital > 1 %, recall crítico < 99 %).
- **Conjunto de validación:** antes de probar nada fijé, con semilla 20261110 (`division_ajuste_validacion.json`), 21 documentos de **ajuste** y 32 de **validación**, estratificados por presencia de OCR.
- **Experimentos de ajuste:** sobre las 111 páginas OCR del ajuste, todo en Linux, con Tesseract 5.3.4 spa.

| Variante (ajuste, 111 págs.) | CER | WER | Recall crítico | Decisión |
|---|---:|---:|---:|---|
| Base (`run1`) | 17,95 % | 34,08 % | 93,2 % | — |
| **Parseo TSV sin comillas** (zoom 2, `--psm 3`) | **1,65 %** | 3,22 % | 93,3 % | **Aplicada** |
| + `--psm 6` | 2,09 % | 4,13 % | 92,6 % | Descartada: empeora |
| + 300 dpi (zoom 4,17) | 2,23 % | 3,73 % | 94,2 % | Descartada: empeora el CER |

**Validación** (32 documentos, 188 páginas OCR, sin tocar durante el ajuste): CER del **23,49 % → 1,94 %** (IC95 por documento 0,79–4,22) y WER del 45,18 % → 3,36 %.

- **Recall crítico:** baja un poco (92,1 → 91,3 %), porque las filas TSV coladas contenían números que coincidían por azar.
- **Commit:** `8df8a96` en `feat/ingesta-fiabilidad-ocr`.
  - Cambio: `quoting=csv.QUOTE_NONE`.
  - Test de regresión: confirmé que falla sin la corrección.
  - Versión: `EXTRACTOR_VERSION` sube a `pymupdf-tesseract-spa-3`, lo que invalida el bronce y las cachés anteriores.
  - Sin push.

No probadas por falta de tiempo y pendientes:

- **Separar las llamadas de nota en superíndice:** con el tamaño y la posición de fuente de PyMuPDF. Es la mejor candidata para el recall crítico digital.
- **Binarización o deskew** y **`--oem`.**
- **Quitar «Página N»:** no afecta al CER, porque la normalización ya lo quita.

## 6. Limitaciones

- U es un OCR LLM sin verificar, y su propio error (≈ 0,5 % de palabras) es comparable al error digital medido de S. **Por debajo de ≈ 1 % de CER, la comparación frente a U no distingue con fiabilidad quién se equivoca.**
- La revisión visual y la adjudicación las hicieron LLM (Claude y Codex), no personas. Son 24 páginas y 30 desacuerdos.
- S_prof no tiene páginas: su comparación es solo documental y pesa más el orden.
- Las alertas y umbrales se eligieron dentro de la muestra.
- **Nada está validado por abogados.**

## Corrida limpia bronze→silver→gold y fiabilidad por documento (10-11-2026)

Medición, sin cambios en `ingest/`. Detalle completo en `benchmarks/ocr_referencia/resultados/fiabilidad/fiabilidad_por_documento.md`.

- **Corrida:** extractor `pymupdf-tesseract-spa-3` (commit 8df8a96), configuración por defecto `legacy`/512, capas y cachés vacías, sin embeddings ni Chroma (`benchmarks/ocr_referencia/capas_completas.py`), en una EC2 temporal t3.large con Tesseract 5.3.4 spa. 53 PDF únicos (1.224 páginas, 304 con OCR; duplicado de Carrero una vez) y 2 .md.
- **Repetibilidad:** dos corridas desde cero, 550/550 archivos de capas byte-idénticos; el bronce PDF también es idéntico al de la corrida `run3` del día anterior.
- **Veredicto final** (regla en el informe; e_U = 0,54 %): 22 verdes, 15 no distinguibles de U, 10 amarillos y 6 rojos. Validación: 16 / 8 / 6 / 2.
- **Silver:** la limpieza retira casi solo mobiliario; la pérdida no atribuible a mobiliario es ≤ 0,21 % salvo un documento de 2 páginas (1,79 %, mobiliario que el criterio conservador no puede verificar).
- **Gold:** cubre 99,7–100 % de silver (los huecos son saltos de línea); 0 cuerpos distintos de silver.
- **Auditoría visual ciega** de los 6 peores (33 páginas: 17 Claude y 16 Codex): 5 se confirman como error del pipeline y 1 (Decreto 1436/1984) pasa a «no distinguible de U».
- **Defectos hallados** (propuestos, no aplicados):
  - el «°» ordinal se lee como %, *, ” o un dígito («Artículo 2º» → «Artículo 22»);
  - Tesseract omite un párrafo junto a una tabla escaneada;
  - en páginas digitales, las tablas incrustadas como imagen no pasan por OCR;
  - las llamadas de nota se pegan a cifras («2002⁴⁴» → «200244»).

Todas las cifras son fidelidad frente a U, una transcripción automática sin verificar. Nada está validado por abogados.
