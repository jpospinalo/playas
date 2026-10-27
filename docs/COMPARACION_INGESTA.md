# Comparación de ingesta ATLAS — esquema corregido

**Ejecución completada el 22 de octubre de 2026. Dataset sintético, no validado por abogados.**

Se mide recuperación relativa, no corrección jurídica. Informe sin commit; main y producción intactos.

**Resultado:** v2a es la mejor variante offline, pero no iguala v1: MRR@4 de 0,4604 frente a 0,7208; v2b obtiene 0,3854. La diferencia v2a−v1 tiene IC95% [−0,3938; −0,1375]. No se recomienda sustituir v1 con estos índices. El cierre de recursos está verificado al final del informe.

## Alcance y método

Se reutilizaron los 56 documentos fuente y la preparación existente, sin repetir
la fase 0. No se consultó producción, no se modificó main ni se publicaron ramas.
Las claves de proveedores permanecen vacías: **0 llamadas a LLM/APIs con cuota**.
La única API de cálculo usada es Ollama propio para embeddings locales/sandbox.

Dataset congelado: 40 preguntas (24 de contenido, 10 de identidad y 6
multidocumento), procedentes de 24 documentos. Las citas de referencia se
verificaron programáticamente en el texto fuente normalizado a NFC. Los
21 casos anteriores se conservaron aparte. SHA256 del dataset:
`d1f6d6de57729f31dd6951c067a6e4acb28e8fda19b3f81cca75aca857352973`.
No se ajustarán preguntas tras observar las métricas v2.

El harness llama al recuperador del backend (BM25 + vectorial), con pregunta
cruda, k=4 y candidatos=8, sin análisis ni generación LLM. Solo cambia la
colección. Configuración:
`d7a6e9cb156f31bbf4d474ea6e224200e7a37ddf6b8076f40500ccaeb885042f`.
Las consultas comparten la misma caché de vectores, excluida de Git.

RAGAS instalado: 0.4.3; existen y se ejecutan `NonLLMContextRecall` y
`NonLLMContextPrecisionWithReference` (RapidFuzz/Levenshtein, umbral 0,5).
No se usan métricas con juez LLM. Las principales son hit@4 y MRR@4 por
documento; las métricas textuales dependen del tamaño y formato del chunk.
Un acierto de pasaje exige la cita tras NFC/espacios y el documento esperado.

## Variantes

| Variante | Tratamiento |
|---|---|
| v1 | Snapshot inmutable, 5.888 vectores de 768 dimensiones; colección física `atlas_v1` porque Chroma rechaza el nombre de dos caracteres `v1`. |
| v2a | Extracción/OCR, limpieza, metadatos por reglas y cabecera; splitter legacy de 1.000 caracteres con solapamiento 200. |
| v2b | Mismo tratamiento, chunking por estructura jurídica con presupuesto aproximado de 1.024 tokens (bytes UTF-8/3). |

Ambas v2 son colecciones nuevas. La selección preespecificada usa la media de
MRR documental; en empate gana v2a por menor complejidad. Nivel 1 omitido para
evitar coste y cuota. No se construye v1x: no se aísla causalmente el efecto del
enriquecimiento LLM del resto de cambios de extracción/normalización.

Las variantes principales usan legal-metadata-2: colecciones físicas v2a_r2 y v2b_r2, etiquetadas v2a/v2b en las tablas. La primera iteración con metadatos defectuosos se conserva aparte en prototype_metadata1/.

Los 56 archivos contienen 55 hashes únicos. Dos nombres de una sentencia son copias byte a byte; source_aliases.json congela su equivalencia por SHA256. Se repitió v1 con esta misma regla antes de evaluar v2, sin cambiar preguntas ni citas. El cambio queda incluido en el hash de configuración.

### Cambios implementados

- ING-09: importador con salida de error, batch positivo, dos intentos y reconciliación.
- ING-11: NFC y eliminación de controles/NUL, también al cruzar CSV.
- ING-02: identidad, ponente, radicado y referencias extraídos antes de limpiar; evidencia, confianza, ausencias, conflictos y correcciones manuales.
- ING-08: modelo/digest fijo, dimensión y finitud validadas, lotes, caché y checksums.
- ING-01/04: identidad por contenido, OCR local cacheado, originales y offsets; manifiesto SQLite y add/sync incremental con upsert y retirada de chunks obsoletos. Gates solo informativos salvo --enforce.
- Las entradas Bash/Make habituales usan ahora el CLI offline y vacían claves; no inician S3, enriquecimiento ni API de serving. Los módulos históricos quedan para invocación explícita.

Guía y comandos: [INGESTA.md](INGESTA.md).

## Resultados nivel 0

Cada celda contiene **media / mediana**.

| Categoría (N) | Métrica | v1 | v2a | v2b |
|---|---|---:|---:|---:|
| Todas (40) | Hit documental@4 | 0,750000 / 1,000000 | 0,550000 / 1,000000 | 0,475000 / 0,000000 |
| Todas (40) | MRR documental@4 | 0,720833 / 1,000000 | 0,460417 / 0,333333 | 0,385417 / 0,000000 |
| Todas (40) | Recall documental@4 | 0,712500 / 1,000000 | 0,525000 / 0,750000 | 0,450000 / 0,000000 |
| Todas (40) | Hit pasaje@4 | 0,100000 / 0,000000 | 0,200000 / 0,000000 | 0,250000 / 0,000000 |
| Todas (40) | MRR pasaje@4 | 0,070833 / 0,000000 | 0,181250 / 0,000000 | 0,204167 / 0,000000 |
| Todas (40) | RAGAS recall sin LLM | 0,025000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| Todas (40) | RAGAS precision sin LLM | 0,008333 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| contenido (24) | Hit documental@4 | 0,666667 / 1,000000 | 0,458333 / 0,000000 | 0,458333 / 0,000000 |
| contenido (24) | MRR documental@4 | 0,638889 / 1,000000 | 0,350694 / 0,000000 | 0,388889 / 0,000000 |
| contenido (24) | Recall documental@4 | 0,666667 / 1,000000 | 0,458333 / 0,000000 | 0,458333 / 0,000000 |
| contenido (24) | Hit pasaje@4 | 0,125000 / 0,000000 | 0,083333 / 0,000000 | 0,208333 / 0,000000 |
| contenido (24) | MRR pasaje@4 | 0,097222 / 0,000000 | 0,052083 / 0,000000 | 0,159722 / 0,000000 |
| contenido (24) | RAGAS recall sin LLM | 0,041667 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| contenido (24) | RAGAS precision sin LLM | 0,013889 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| identidad (10) | Hit documental@4 | 1,000000 / 1,000000 | 0,900000 / 1,000000 | 0,500000 / 0,500000 |
| identidad (10) | MRR documental@4 | 1,000000 / 1,000000 | 0,850000 / 1,000000 | 0,450000 / 0,250000 |
| identidad (10) | Recall documental@4 | 1,000000 / 1,000000 | 0,900000 / 1,000000 | 0,500000 / 0,500000 |
| identidad (10) | Hit pasaje@4 | 0,100000 / 0,000000 | 0,600000 / 1,000000 | 0,500000 / 0,500000 |
| identidad (10) | MRR pasaje@4 | 0,050000 / 0,000000 | 0,600000 / 1,000000 | 0,433333 / 0,166667 |
| identidad (10) | RAGAS recall sin LLM | 0,000000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| identidad (10) | RAGAS precision sin LLM | 0,000000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| multi_documento (6) | Hit documental@4 | 0,666667 / 1,000000 | 0,333333 / 0,000000 | 0,500000 / 0,500000 |
| multi_documento (6) | MRR documental@4 | 0,583333 / 0,750000 | 0,250000 / 0,000000 | 0,263889 / 0,125000 |
| multi_documento (6) | Recall documental@4 | 0,416667 / 0,500000 | 0,166667 / 0,000000 | 0,333333 / 0,250000 |
| multi_documento (6) | Hit pasaje@4 | 0,000000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| multi_documento (6) | MRR pasaje@4 | 0,000000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| multi_documento (6) | RAGAS recall sin LLM | 0,000000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |
| multi_documento (6) | RAGAS precision sin LLM | 0,000000 / 0,000000 | 0,000000 / 0,000000 | 0,000000 / 0,000000 |

Selección preespecificada: **v2a**, por MRR documental (v2a=0,460417, v2b=0,385417), antes de cualquier nivel 1. No se ejecutó nivel 1.

## Deltas pareados e incertidumbre

Bootstrap por pregunta: 5.000 remuestras, semilla 20261021, IC95%. Un intervalo que contiene cero se considera no concluyente. No se estima ruido de juez: no hubo juez LLM.

| Comparación | Categoría | Métrica | Δ media | Δ mediana | IC95% |
|---|---|---|---:|---:|---|
| v2a-v1 | Todas | Hit documental@4 | -0,200000 | 0,000000 | [-0,350000; -0,050000] |
| v2a-v1 | Todas | MRR documental@4 | -0,260417 | 0,000000 | [-0,393750; -0,137500] |
| v2a-v1 | Todas | Recall documental@4 | -0,187500 | 0,000000 | [-0,325000; -0,050000] |
| v2a-v1 | Todas | Hit pasaje@4 | 0,100000 | 0,000000 | [-0,050000; 0,250000] |
| v2a-v1 | Todas | MRR pasaje@4 | 0,110417 | 0,000000 | [-0,014583; 0,237500] |
| v2a-v1 | Todas | RAGAS recall sin LLM | -0,025000 | 0,000000 | [-0,075000; 0,000000] |
| v2a-v1 | Todas | RAGAS precision sin LLM | -0,008333 | 0,000000 | [-0,025000; 0,000000] |
| v2a-v1 | contenido | Hit documental@4 | -0,208333 | 0,000000 | [-0,416667; 0,000000] |
| v2a-v1 | contenido | MRR documental@4 | -0,288194 | 0,000000 | [-0,461806; -0,121528] |
| v2a-v1 | contenido | Recall documental@4 | -0,208333 | 0,000000 | [-0,416667; 0,000000] |
| v2a-v1 | contenido | Hit pasaje@4 | -0,041667 | 0,000000 | [-0,208333; 0,083333] |
| v2a-v1 | contenido | MRR pasaje@4 | -0,045139 | 0,000000 | [-0,142361; 0,020833] |
| v2a-v1 | contenido | RAGAS recall sin LLM | -0,041667 | 0,000000 | [-0,125000; 0,000000] |
| v2a-v1 | contenido | RAGAS precision sin LLM | -0,013889 | 0,000000 | [-0,041667; 0,000000] |
| v2a-v1 | identidad | Hit documental@4 | -0,100000 | 0,000000 | [-0,300000; 0,000000] |
| v2a-v1 | identidad | MRR documental@4 | -0,150000 | 0,000000 | [-0,350000; 0,000000] |
| v2a-v1 | identidad | Recall documental@4 | -0,100000 | 0,000000 | [-0,300000; 0,000000] |
| v2a-v1 | identidad | Hit pasaje@4 | 0,500000 | 1,000000 | [0,000000; 0,900000] |
| v2a-v1 | identidad | MRR pasaje@4 | 0,550000 | 1,000000 | [0,200000; 0,900000] |
| v2a-v1 | identidad | RAGAS recall sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2a-v1 | identidad | RAGAS precision sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2a-v1 | multi_documento | Hit documental@4 | -0,333333 | 0,000000 | [-0,666667; 0,000000] |
| v2a-v1 | multi_documento | MRR documental@4 | -0,333333 | 0,000000 | [-0,666667; 0,000000] |
| v2a-v1 | multi_documento | Recall documental@4 | -0,250000 | 0,000000 | [-0,583333; 0,000000] |
| v2a-v1 | multi_documento | Hit pasaje@4 | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2a-v1 | multi_documento | MRR pasaje@4 | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2a-v1 | multi_documento | RAGAS recall sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2a-v1 | multi_documento | RAGAS precision sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2b-v1 | Todas | Hit documental@4 | -0,275000 | 0,000000 | [-0,450000; -0,100000] |
| v2b-v1 | Todas | MRR documental@4 | -0,335417 | 0,000000 | [-0,502083; -0,170833] |
| v2b-v1 | Todas | Recall documental@4 | -0,262500 | 0,000000 | [-0,437500; -0,100000] |
| v2b-v1 | Todas | Hit pasaje@4 | 0,150000 | 0,000000 | [0,025000; 0,275000] |
| v2b-v1 | Todas | MRR pasaje@4 | 0,133333 | 0,000000 | [0,033333; 0,250000] |
| v2b-v1 | Todas | RAGAS recall sin LLM | -0,025000 | 0,000000 | [-0,075000; 0,000000] |
| v2b-v1 | Todas | RAGAS precision sin LLM | -0,008333 | 0,000000 | [-0,025000; 0,000000] |
| v2b-v1 | contenido | Hit documental@4 | -0,208333 | 0,000000 | [-0,416667; 0,041667] |
| v2b-v1 | contenido | MRR documental@4 | -0,250000 | 0,000000 | [-0,444444; -0,062500] |
| v2b-v1 | contenido | Recall documental@4 | -0,208333 | 0,000000 | [-0,416667; 0,041667] |
| v2b-v1 | contenido | Hit pasaje@4 | 0,083333 | 0,000000 | [0,000000; 0,208333] |
| v2b-v1 | contenido | MRR pasaje@4 | 0,062500 | 0,000000 | [0,000000; 0,166667] |
| v2b-v1 | contenido | RAGAS recall sin LLM | -0,041667 | 0,000000 | [-0,125000; 0,000000] |
| v2b-v1 | contenido | RAGAS precision sin LLM | -0,013889 | 0,000000 | [-0,041667; 0,000000] |
| v2b-v1 | identidad | Hit documental@4 | -0,500000 | -0,500000 | [-0,800000; -0,200000] |
| v2b-v1 | identidad | MRR documental@4 | -0,550000 | -0,750000 | [-0,850000; -0,250000] |
| v2b-v1 | identidad | Recall documental@4 | -0,500000 | -0,500000 | [-0,800000; -0,200000] |
| v2b-v1 | identidad | Hit pasaje@4 | 0,400000 | 0,500000 | [0,000000; 0,800000] |
| v2b-v1 | identidad | MRR pasaje@4 | 0,383333 | 0,166667 | [0,050000; 0,733333] |
| v2b-v1 | identidad | RAGAS recall sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2b-v1 | identidad | RAGAS precision sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2b-v1 | multi_documento | Hit documental@4 | -0,166667 | 0,000000 | [-0,666667; 0,333333] |
| v2b-v1 | multi_documento | MRR documental@4 | -0,319444 | -0,458333 | [-0,819444; 0,291667] |
| v2b-v1 | multi_documento | Recall documental@4 | -0,083333 | 0,000000 | [-0,333333; 0,166667] |
| v2b-v1 | multi_documento | Hit pasaje@4 | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2b-v1 | multi_documento | MRR pasaje@4 | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2b-v1 | multi_documento | RAGAS recall sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |
| v2b-v1 | multi_documento | RAGAS precision sin LLM | 0,000000 | 0,000000 | [0,000000; 0,000000] |

## Deltas por pregunta

Δ respecto a v1. Los siete deltas por pregunta están en [comparison.json](../evaluation/ragas/results/comparison.json); aquí se muestran las métricas principales.

| ID | Categoría | Δ hit v2a | Δ MRR v2a | Δ hit v2b | Δ MRR v2b |
|---|---|---:|---:|---:|---:|
| atlas-001 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-002 | contenido | -1,000000 | -1,000000 | -1,000000 | -1,000000 |
| atlas-003 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-004 | contenido | 0,000000 | -0,500000 | -1,000000 | -1,000000 |
| atlas-005 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-006 | contenido | 0,000000 | -0,750000 | 0,000000 | -0,666667 |
| atlas-007 | contenido | -1,000000 | -1,000000 | -1,000000 | -1,000000 |
| atlas-008 | contenido | 0,000000 | 0,000000 | -1,000000 | -1,000000 |
| atlas-009 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-010 | contenido | 1,000000 | 0,333333 | 1,000000 | 0,500000 |
| atlas-011 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-012 | contenido | -1,000000 | -0,333333 | -1,000000 | -0,333333 |
| atlas-013 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-014 | contenido | -1,000000 | -1,000000 | -1,000000 | -1,000000 |
| atlas-015 | contenido | 0,000000 | 0,000000 | 1,000000 | 0,500000 |
| atlas-016 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-017 | contenido | 0,000000 | -0,666667 | 0,000000 | 0,000000 |
| atlas-018 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-019 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-020 | contenido | -1,000000 | -1,000000 | -1,000000 | -1,000000 |
| atlas-021 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-022 | contenido | -1,000000 | -1,000000 | 0,000000 | 0,000000 |
| atlas-023 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-024 | contenido | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-025 | identidad | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-026 | identidad | 0,000000 | 0,000000 | -1,000000 | -1,000000 |
| atlas-027 | identidad | 0,000000 | -0,500000 | -1,000000 | -1,000000 |
| atlas-028 | identidad | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-029 | identidad | -1,000000 | -1,000000 | -1,000000 | -1,000000 |
| atlas-030 | identidad | 0,000000 | 0,000000 | 0,000000 | -0,500000 |
| atlas-031 | identidad | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-032 | identidad | 0,000000 | 0,000000 | -1,000000 | -1,000000 |
| atlas-033 | identidad | 0,000000 | 0,000000 | 0,000000 | 0,000000 |
| atlas-034 | identidad | 0,000000 | 0,000000 | -1,000000 | -1,000000 |
| atlas-035 | multi_documento | 0,000000 | 0,000000 | -1,000000 | -1,000000 |
| atlas-036 | multi_documento | 0,000000 | 0,000000 | 0,000000 | -0,250000 |
| atlas-037 | multi_documento | -1,000000 | -1,000000 | 0,000000 | -0,666667 |
| atlas-038 | multi_documento | -1,000000 | -1,000000 | -1,000000 | -1,000000 |
| atlas-039 | multi_documento | 0,000000 | 0,000000 | 1,000000 | 1,000000 |
| atlas-040 | multi_documento | 0,000000 | 0,000000 | 0,000000 | 0,000000 |

## Diez peores preguntas por variante

Orden: MRR documental ascendente, luego MRR de pasaje e ID; los empates no implican diferencias de gravedad jurídica.

### v1

| ID | Pregunta | MRR documento | MRR pasaje |
|---|---|---:|---:|
| atlas-003 | Según el documento «AP  Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-005 | Según el documento «AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-010 | Según el documento «decreto-2324-de-1984», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-011 | Según el documento «SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-013 | Según el documento «CE 2da AP 2017 103 Personeria VS Distrito Cartagena Desembocadura», ¿qué se señala sobre los bienes de uso público? | 0,000000 | 0,000000 |
| atlas-015 | Según el documento «CE 2da NYR 1999 503 Inversiones Mercedes VS Dimar Concesiones Uso Playa», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-019 | Según el documento «CE 2da NYR 1998 102 Flury Valencia VS MinDefensa Uso Urbanistico Playa», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-021 | Según el documento «AP Felipe José Campo Fernández VS Corpamag y otros», ¿qué se señala sobre los bienes de uso público? | 0,000000 | 0,000000 |
| atlas-039 | ¿Qué indican «decreto-2324-de-1984» y «Por el cual se dictan normas sobre la prevención de la contaminación del medio marino y otras disposiciones» acerca del uso de playas y zonas costeras? Distingue lo que dice cada documento. | 0,000000 | 0,000000 |
| atlas-040 | ¿Qué indican «Por el cual se dictan normas sobre la prevención de la contaminación del medio marino y otras disposiciones» y «CE 2da AP 2017 103 Personeria VS Distrito Cartagena Desembocadura» acerca del uso de playas y zonas costeras? Distingue lo que dice cada documento. | 0,000000 | 0,000000 |

### v2a

| ID | Pregunta | MRR documento | MRR pasaje |
|---|---|---:|---:|
| atlas-002 | Según el documento «Por el cual se reglamenta el servicio público de transporte marítimo», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |
| atlas-003 | Según el documento «AP  Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-005 | Según el documento «AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-007 | Según el documento «AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros», ¿qué se señala sobre los bienes de uso público? | 0,000000 | 0,000000 |
| atlas-011 | Según el documento «SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-012 | Según el documento «Por el cual se dictan normas sobre la prevención de la contaminación del medio marino y otras disposiciones», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |
| atlas-013 | Según el documento «CE 2da AP 2017 103 Personeria VS Distrito Cartagena Desembocadura», ¿qué se señala sobre los bienes de uso público? | 0,000000 | 0,000000 |
| atlas-014 | Según el documento «Por el cual se reglamenta la Ley 13 de 1990», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |
| atlas-015 | Según el documento «CE 2da NYR 1999 503 Inversiones Mercedes VS Dimar Concesiones Uso Playa», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-019 | Según el documento «CE 2da NYR 1998 102 Flury Valencia VS MinDefensa Uso Urbanistico Playa», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |

### v2b

| ID | Pregunta | MRR documento | MRR pasaje |
|---|---|---:|---:|
| atlas-002 | Según el documento «Por el cual se reglamenta el servicio público de transporte marítimo», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |
| atlas-003 | Según el documento «AP  Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-004 | Según el documento «Por el cual se reglamenta el funcionamiento de los Comités Locales para la  organización de las Playas de que trata el artículo 12 de la Ley 1558 de 2012», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-005 | Según el documento «AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS», ¿qué se señala sobre el uso de las playas? | 0,000000 | 0,000000 |
| atlas-007 | Según el documento «AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros», ¿qué se señala sobre los bienes de uso público? | 0,000000 | 0,000000 |
| atlas-008 | Según el documento «Por el cual se aprueba el ajuste y la modificación a la planta de personal de Empleados Públicos del Ministerio de Defensa Nacional - Dirección General Marítima y se dictan otras disposiciones», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |
| atlas-011 | Según el documento «SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO», ¿qué se señala sobre las concesiones en zonas costeras? | 0,000000 | 0,000000 |
| atlas-012 | Según el documento «Por el cual se dictan normas sobre la prevención de la contaminación del medio marino y otras disposiciones», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |
| atlas-013 | Según el documento «CE 2da AP 2017 103 Personeria VS Distrito Cartagena Desembocadura», ¿qué se señala sobre los bienes de uso público? | 0,000000 | 0,000000 |
| atlas-014 | Según el documento «Por el cual se reglamenta la Ley 13 de 1990», ¿qué se señala sobre las competencias de la autoridad marítima? | 0,000000 | 0,000000 |

## Cobertura de metadatos

Presencia de un valor, no exactitud. La confianza es heurística, no una probabilidad calibrada. Denominadores: fuentes distintas en el snapshot y hashes de contenido en R2; la copia exacta explica 27 jurisprudencias frente a 26 contenidos únicos. Los aliases del snapshot se mapearon por campo; no se interpretó Nº/SM-xx como número de sentencia ni doc_type como tipo jurídico específico.

| Grupo | Campo | v1 presentes / docs | v2a presentes / docs | v2b presentes / docs |
|---|---|---:|---:|---:|
| Todas | tipo_documento | 0/56 | 53/55 | 53/55 |
| Todas | corporacion | 9/56 | 44/55 | 44/55 |
| Todas | sala | 0/56 | 21/55 | 21/55 |
| Todas | clase | 0/56 | 19/55 | 19/55 |
| Todas | numero | 0/56 | 35/55 | 35/55 |
| Todas | anio | 0/56 | 46/55 | 46/55 |
| Todas | radicado | 9/56 | 18/55 | 18/55 |
| Todas | fecha_iso | 0/56 | 34/55 | 34/55 |
| Todas | magistrado_ponente | 9/56 | 24/55 | 24/55 |
| Todas | ambito | 0/56 | 44/55 | 44/55 |
| Todas | municipio | 0/56 | 25/55 | 25/55 |
| Todas | normas_citadas | 0/56 | 55/55 | 55/55 |
| jurisprudencia | tipo_documento | 0/27 | 26/26 | 26/26 |
| jurisprudencia | corporacion | 9/27 | 26/26 | 26/26 |
| jurisprudencia | sala | 0/27 | 21/26 | 21/26 |
| jurisprudencia | clase | 0/27 | 18/26 | 18/26 |
| jurisprudencia | numero | 0/27 | 10/26 | 10/26 |
| jurisprudencia | anio | 0/27 | 23/26 | 23/26 |
| jurisprudencia | radicado | 9/27 | 18/26 | 18/26 |
| jurisprudencia | fecha_iso | 0/27 | 23/26 | 23/26 |
| jurisprudencia | magistrado_ponente | 9/27 | 24/26 | 24/26 |
| jurisprudencia | ambito | 0/27 | 26/26 | 26/26 |
| jurisprudencia | municipio | 0/27 | 17/26 | 17/26 |
| jurisprudencia | normas_citadas | 0/27 | 26/26 | 26/26 |
| normativa | tipo_documento | 0/29 | 27/29 | 27/29 |
| normativa | corporacion | 0/29 | 18/29 | 18/29 |
| normativa | sala | 0/29 | 0/29 | 0/29 |
| normativa | clase | 0/29 | 1/29 | 1/29 |
| normativa | numero | 0/29 | 25/29 | 25/29 |
| normativa | anio | 0/29 | 23/29 | 23/29 |
| normativa | radicado | 0/29 | 0/29 | 0/29 |
| normativa | fecha_iso | 0/29 | 11/29 | 11/29 |
| normativa | magistrado_ponente | 0/29 | 0/29 | 0/29 |
| normativa | ambito | 0/29 | 18/29 | 18/29 |
| normativa | municipio | 0/29 | 8/29 | 8/29 |
| normativa | normas_citadas | 0/29 | 29/29 | 29/29 |

## Coste computacional e incrementalidad

No se usa precio de catálogo para inventar una factura AWS. Se miden CPU Python+OCR y latencia de embeddings; **CPU del servicio Ollama queda fuera**, tanto local como remoto. Las variantes comparten cachés y se ejecutaron parcialmente en paralelo: sus tiempos no son una comparación independiente de hardware. v1 se importó de snapshot; su coste histórico de ingesta/LLM no se midió.

| Medición | v2a | v2b |
|---|---:|---:|
| Documentos procesados tras retoma | 47 | 45 |
| Chunks publicados | 5281 | 2366 |
| Embeddings nuevos por escritor | 1753 | 1030 |
| Embeddings nuevos por asistente de caché | 252 | 0 |
| Segundos transcurridos del sync | 2338,254209 | 2006,037935 |
| Segundos CPU Python+OCR dentro del sync | 22,594366 | 9,528094 |
| CPU por documento procesado tras retoma, media / mediana | 0,480731 / 0,366136 | 0,211735 / 0,138915 |
| Segundos de embeddings por escritor | 2270,567388 | 1973,667974 |
| Segundos por chunk nuevo por escritor | 1,295247 | 1,916182 |
| Lotes HTTP a Ollama por escritor | 124 | 78 |
| Embeddings nuevos al repetir sync | 0 | 0 |
| Llamadas a LLM/APIs con cuota | 0 | 0 |

Preextracción compartida: 514,204407 segundos CPU, pagada una sola vez en el prototipo y reutilizada en R2. No hubo asistente para v2b en R2. Las solicitudes registradas por los escritores pueden solaparse con la caché asistida: no se equipara automáticamente número de chunks a vectores nuevos.

El detalle por cada documento nuevo está en [cpu_por_documento.csv](../evaluation/ragas/results/cpu_por_documento.csv). El warm-up incluye lectura cacheada de documentos que v2a ya había extraído; se contabiliza trabajo observado, no una reconstrucción ideal de coste en frío.

Asistente local de caché para v2a_r2, después de terminar v2b_r2: 252 embeddings nuevos; 12,392001 segundos CPU Python; 277,962472 segundos de latencia y 17 lotes. No publica en Chroma. Estos costes se suman a los del escritor; el CSV incluye su columna separada.

### Repetición, interrupción y coste observado

La primera iteración (esquema 1) encontró 39 coincidencias sospechosas de ponente: MP sin límites de palabra coincidía dentro de competencia, limpieza o cumplieran. Se conservan sus métricas en prototype_metadata1/. No se presentan sus 55 valores como metadatos correctos. Se corrigió el patrón, se agregaron ocho regresiones (ingesta 70 tests aprobados), se subió legal-metadata-2 y se crearon v2a_r2/v2b_r2. La tabla principal corresponde SOLO a esta segunda iteración; v1, dataset y harness permanecen iguales.

El checkpoint del prototipo tenía 7.654 vectores persistidos: 7.651 del corpus y 3 de la prueba incremental real. La segunda iteración añadió 4319 vectores únicos persistidos a esa caché. Antes de reanudar ya había 8.951 (1.297 nuevos de R2). Son conteos de caché, no el número exacto de solicitudes: un lote en vuelo pudo perderse durante el reinicio.

CPU Python+OCR observada del corpus entre prototipo, warm-up y tramo posterior a reanudar: 913,025228 segundos, **límite inferior**. No se recuperaron los contadores de CPU del tramo R2 interrumpido. CPU del servicio Ollama excluida; llamadas LLM/APIs con cuota: 0. Los 511 embeddings del asistente de v2b pertenecen al prototipo; los 252 del asistente de v2a pertenecen a R2.

Durante la interrupción del acceso al sandbox se observó UnauthorizedOperation y luego ExpiredToken del perfil anterior. El usuario reactivó el lab y autorizó actualizar el perfil de forma privada. Los manifiestos SQLite y cachés sobrevivieron al reinicio; se reanudaron sin escritores duplicados. La tabla de coste R2 y su CSV cubren solo el tramo posterior a reanudar. Las celdas CPU vacías de los documentos ya publicados antes de la interrupción significan no medido, nunca cero. La segunda reutiliza caché del prototipo: no es una medición fría independiente.

OCR corpus: 19/19 documentos originalmente con <200 caracteres recuperados; 304 páginas nuevas en total entre escritores y warm-up (188 durante warm-up). Fallos reportados: 0.

- v2a: candidatos a cuarentena si se usara --enforce: 11; gates fallidos: {"schema": 0, "identity": 11, "characters": 0, "ocr": 0, "sections": 0, "size": 0}. Grupos duplicados exactos: 1; pares cercanos: 41; originales borrados: 0.
- v2b: candidatos a cuarentena si se usara --enforce: 11; gates fallidos: {"schema": 0, "identity": 11, "characters": 0, "ocr": 0, "sections": 0, "size": 0}. Grupos duplicados exactos: 1; pares cercanos: 41; originales borrados: 0.

## Evidencia de validación

- La comprobación de etiquetas de R2 encontró cero coincidencias de abreviatura sospechosas en los 55 documentos; REMAC queda con ponente null y razón sin_evidencia. Esto verifica el fallo técnico corregido, no la exactitud jurídica de los demás campos (metadata_label_check_r2.json). Corporación en jurisprudencia pasa de 9/27 fuentes a 26/26 contenidos únicos; la diferencia de denominador se debe a la copia exacta.

- Ingesta corregida: 70 tests aprobados. RAG completo: 770 antes del último ajuste de alias; harness final: 6 después de ese ajuste. Mypy backend: 30 archivos sin errores. Ruff check/format: 47 archivos aprobados; sintaxis Bash aprobada. Evidencia en [local_validation.json](../evaluation/ragas/results/local_validation.json) y results/evidence/. GitHub Actions preparado, no ejecutado (sin push).
- Fixtures: PDF digital y escaneado, homónimos, duplicado exacto, modificación/renombrado/eliminación, gates, offsets, overrides y rechazo de colecciones protegidas. Tests bloquean sockets en el lote con adaptadores y las entradas vacían claves.
- Prueba real incremental del prototipo (smoke_live.json), con lógica incremental sin cambios en R2: dos sincronizaciones sin cambios no generan vectores nuevos; agregar documento calcula solo sus chunks. Importador ING-09 tiene pruebas de fallo visible, reintentos y reconciliación.
- v1 conserva UUID y hash: 4bfaaa3ac9b99e6ee640bbaa135e3c46e96a0040a85a2e6f74e186e76a754c2c; 5.888x768 vectores finitos. Chroma remoto nunca recibió escrituras.
- v2a/v2b: todos los vectores finitos, dimensión 768, conteos reconciliados con exportaciones y checksums verificados (final_integrity.json y manifiestos).
- Snapshot original SHA256: 28b7a3076d1c7ad0aa3ef2a4394e31423cdd5358f691fdc6a6104f7e15712d2d. Dataset y configuración iguales para las tres variantes.
- Réplica Ollama 0.40.8, digest fijado; tres cosenos con el servidor propio: 1,1,1.

## Limitaciones y conclusión

La mejor v2 empeora el MRR documental en este dataset; no alcanza la línea base. Δ=-0,260417, IC95%=[-0,393750; -0,137500]. **No se recomienda sustituir v1 por estas variantes.** El siguiente paso técnico es revisar los errores listados y probar extracción, cabeceras y chunking en otra colección y un holdout independiente; esta fase no ajusta parámetros para perseguir el resultado del dataset congelado.

**¿Justifica su coste el enriquecimiento LLM? No está demostrado.** Este experimento no mide su coste histórico ni ejecuta v1x; no puede atribuir causalmente una diferencia al LLM. La alternativa offline elimina las llamadas de pago por diseño. La decisión para el servicio gratuito debe usar el resultado anterior y la revisión de errores; no se afirma calidad jurídica ni beneficio causal de un proveedor.

N=40, corpus de 24 documentos representados, plantillas que pueden favorecer la identidad documental y ningún abogado. Bootstrap por pregunta, sin agrupar por documento, ni garantía de generalización a consultas reales. Comparaciones múltiples exploratorias sin ajuste.

Cobertura regex no implica precisión. Ámbito/municipio son inferencias; faltantes y conflictos deben revisarse mediante CSV. La prueba compara también extracción y OCR: legacy nuevo procesa texto completo limpio, no las cuatro secciones silver históricas. Los presupuestos son aproximados; el reconocimiento de encabezados es heurístico.

Las métricas de pasaje son sensibles a OCR, desguionado, mayúsculas y longitud. RAGAS textual depende de formato/tamaño; sus valores bajos no significan directamente mala calidad jurídica. Nivel 1 y v1x omitidos; no se generan respuestas ni se evalúan faithfulness/answer_relevancy.

Input histórico de embeddings no reproducido exactamente en dos de tres muestras (cosenos 0,992916 y 0,995983; tercera 1). Aunque el modelo actual coincide por digest, la procedencia exacta del input histórico queda **no verificada**. No se presenta el experimento como una ablación pura.

Escalabilidad: extracción y cálculo por documento, lotes de 16 y cachés SQLite; informes retienen metadatos, no todo el corpus textual. Sigue existiendo límite por tamaño de un documento y no hay transacción distribuida Chroma+SQLite ni escritores concurrentes en una misma colección. El backend mantiene su BM25 en memoria, fuera del alcance de este cambio.

Los 19 documentos originalmente con menos de 200 caracteres no eran elegibles para generar las preguntas congeladas. La recuperación de caracteres por OCR no valida semánticamente ese texto y su beneficio no está representado directamente en este dataset.

## Recursos y cierre

Windows sin WSL/Docker utilizable: ejecución en EC2 temporal propia t3.medium, con Chroma/Ollama locales. El servidor vectorial propio Chroma se detuvo al dejar de usarse. Ollama propio se utilizó solo para embeddings; no se crearon roles ni se tocó mlflow2. Cachés, originales, estados y exportaciones se guardaron fuera de Git.

**Cierre verificado el 22 de octubre a las 12:53 (America/Bogota):** Chroma y Ollama vectoriales en stopped; temporal i-09c723d5f76be14eb en terminated y sin volúmenes temporales restantes. Evidencia: [sandbox_cleanup_final.json](../evaluation/ragas/results/sandbox_cleanup_final.json). No se ejecutó terraform destroy. No se incluye ningún paso de despliegue de producción.

Checkpoint privado final: 219.587.160 bytes, 725 archivos, CRC gzip y presencia de manifiestos/exportaciones verificados. Guardado fuera de Git en `C:/Users/Migue/.codex/visualizations/2026/10/21/01a15fc8-35d2-74f3-8101-c287325b20ea/ingesta-offline-checkpoint.tar.gz`. Los vectores y cachés no se versionan.
