# ATLAS — Línea base de calidad sobre el ground truth jurídico v0.2

| | |
|---|---|
| **Autor** | Julian Esteban Rincón Rodríguez |
| **Fecha de la corrida** | 2026-10-08 |
| **Rama** | `julian-rincon/evaluacion-ragas-linea-base` |
| **Sistema evaluado** | `main` @ `f16586f`, tal como está desplegado en AWS (sin ningún cambio) |
| **Dataset** | `evaluation/data/legal-ground-truth-v0.2.json`: 66 casos del equipo jurídico |
| **Revisores** | Juan Pablo Ospina López, Camilo |

> **Objetivo** (acordado en la reunión del 2026-10-08): establecer el estado actual de ATLAS frente al ground truth validado por el equipo jurídico e identificar en qué tipos de pregunta falla más, evaluando por separado la **recuperación** y la **generación**. **No se calibró nada:** las hipótesis de la §8 son propuestas para discutir.

## Índice

1. [Resumen](#1-resumen)
2. [Cómo se midió](#2-cómo-se-midió)
3. [Cómo leer las métricas](#3-cómo-leer-las-métricas)
4. [Recuperación: ¿llega el documento correcto?](#4-recuperación-llega-el-documento-correcto)
5. [Comportamiento del sistema](#5-comportamiento-del-sistema)
6. [Calidad de las respuestas](#6-calidad-de-las-respuestas)
7. [Ejemplos concretos](#7-ejemplos-concretos)
8. [Hipótesis de calibración (no aplicadas)](#8-hipótesis-de-calibración-no-aplicadas)
9. [Hallazgos sobre los datos](#9-hallazgos-sobre-los-datos)
10. [Confiabilidad de la medición](#10-confiabilidad-de-la-medición)
11. [Costo y reproducibilidad](#11-costo-y-reproducibilidad)
12. [Decisiones que necesitamos](#12-decisiones-que-necesitamos)

---

## 1. Resumen

1. **Las respuestas son fieles a sus fuentes.** La fidelidad (*faithfulness*) es **0,87**: ATLAS casi no afirma cosas que no estén en los fragmentos que recibe. No se detectaron casos de alucinación.
2. **Se parecen a las del equipo jurídico en un ~70%.** Factual Correctness: precisión 0,72 y cobertura 0,70. Answer Accuracy: 0,72. El juez clasificó **51 de 65** respuestas como correctas, **8** con falla de recuperación y **6** incompletas o demasiado generales.
3. **El punto débil es la recuperación del documento exacto, sobre todo de la normativa.** El documento que señala el equipo jurídico llega al modelo en el **57%** de los casos. El **REMAC 5** y el **Decreto 2324 de 1984** llegan en solo **2 de 18** preguntas que los necesitan. El sistema suele compensar con otros documentos que dicen algo parecido (context recall de 0,80), pero cuando el detalle solo está en el REMAC, la respuesta sale incompleta.
4. **Los tipos más débiles son "Secuencia, trámite u orden jurídico"** (F1 factual 0,54, precisión 0,51) y **"Comparación jurídica"** (Answer Accuracy 0,54). Los trámites paso a paso son justamente lo que más necesita un usuario de playa.
5. **Experiencia de uso:** cada respuesta tarda **~61 s** de media, y 1 de 66 preguntas pertinentes fue rechazada como "fuera del ámbito".

## 2. Cómo se midió

Se midió el sistema **tal como está desplegado**, con el grafo real de producción. Las fases que no requieren un LLM se hicieron primero, para gastar presupuesto solo donde era necesario.

| Fase | Qué se hizo | Costo LLM | Módulo |
|---|---|---|---|
| 0 | El Excel v0.2 se convirtió en un JSON versionado y validado: 66 casos (filas con pregunta y respuesta), 6 tipos de pregunta normalizados, bandera `revisado` y documento esperado mapeado **por título** (ver D1 en la §9) | Ninguno | `ground_truth_v02.py` |
| 1 | Recuperación con el retriever de producción y la pregunta original: ¿el documento esperado está en el top-4? ¿Y en el top-20? | Ninguno | `retrieval_baseline.py` |
| 2 | El **grafo real**, una vez por pregunta, guardando respuesta, fragmentos, ruta, consulta reescrita, tokens y latencia en una caché reutilizable | 0,23 USD | `generation_cache.py` |
| 3 | Piloto de 3 casos: costo real por caso y revisión manual de que el juez califica con sentido en español jurídico | 0,02 USD | `ragas_v02.py` |
| 4 | Métricas RAGAS (`ragas.metrics.collections`, v0.4.3) sobre la caché. Juez: **gpt-5-nano** (`reasoning_effort=low`). Embeddings: `embeddinggemma` del Ollama del proyecto | ≈0,43 USD | `ragas_v02.py` |
| 5 | Tablas consolidadas | Ninguno | `baseline_report.py` |

**Configuración del sistema medido** (verificada en la tarea ECS desplegada):
- Modelo `gpt-5-nano`, con reescritura de la consulta activa.
- Búsqueda híbrida BM25 (peso 0,3) + vectores (peso 0,7) con fusión RRF.
- `k = 4` fragmentos por pregunta. El reranker existe en el código, pero no participa en el flujo desplegado.
- ChromaDB `rag_playas` con 5.888 fragmentos, idéntica a la capa gold de `data/documents/`.

## 3. Cómo leer las métricas

Todas van de 0 a 1 (más alto es mejor). Las de RAGAS usan un **LLM juez**: parte cada texto en afirmaciones simples y verifica cada una contra otro texto.

| Métrica | Pregunta que responde | Cómo se calcula |
|---|---|---|
| **hit@4 / hit@20** | ¿El documento que señala el equipo jurídico llega entre los 4 fragmentos que recibe el modelo? ¿Y entre los 20 primeros candidatos? | Sin LLM: casos con el documento en el top-k ÷ casos |
| **MRR** | ¿En qué posición aparece el documento correcto? | Sin LLM: promedio de 1/posición (1 = siempre primero) |
| **Context recall** | ¿Lo que dice la respuesta jurídica está en los fragmentos recuperados? | Afirmaciones de la referencia respaldadas por los fragmentos ÷ total |
| **Context precision** | ¿Los fragmentos útiles quedan arriba en el ranking? | Precisión promedio ponderada por posición |
| **Faithfulness** | ¿La respuesta se apega a los fragmentos, o inventa? | Afirmaciones de la respuesta respaldadas por los fragmentos ÷ total |
| **Factual precisión / cobertura / F1** | ¿Coincide con la respuesta jurídica? | Precisión: lo que dice ATLAS que también dice la referencia. Cobertura: lo que dice la referencia que ATLAS también dice. F1: media armónica de ambas |
| **Answer accuracy** | Calificación global de exactitud frente a la referencia | Dos jueces califican 0, 2 o 4 y se promedia |

**Diagnóstico por caso** (umbral 0,5), en este orden:

| Si… | Diagnóstico | Qué se calibraría |
|---|---|---|
| context recall < 0,5 | **Falla de recuperación:** la evidencia no llegó | Partición en fragmentos, BM25, pesos, `k`, filtros |
| faithfulness < 0,5 | **Alucinación:** el modelo no se apega al contexto | Prompt, instrucciones de citación |
| cobertura factual < 0,5 | **Incompleta o demasiado general** | Prompt: especificidad, pasos, jerarquía |
| ninguna de las anteriores | **Correcta** | — |

---

## 4. Recuperación: ¿llega el documento correcto?

58 de los 66 casos tienen documento esperado.

| Tipo | n | hit@4 | hit@20 | MRR |
|---|---:|---:|---:|---:|
| **Todos** | **58** | **0,57** | **0,74** | **0,56** |
| 1. Extracción puntual | 2 | 1,00 | 1,00 | 1,00 |
| 2. Síntesis dentro de un documento | 7 | 0,71 | 0,86 | 0,72 |
| 3. Cruce entre documentos | 5 | 0,40 | 0,60 | 0,44 |
| 4. Comparación jurídica | 7 | 0,71 | 0,86 | 0,74 |
| 5. Aplicación normativa o jurisprudencial | 29 | 0,52 | 0,69 | 0,49 |
| 6. Secuencia, trámite u orden jurídico | 8 | 0,50 | 0,75 | 0,46 |

**Lectura:**
- **La normativa casi no se recupera.** De 18 preguntas cuyo documento esperado es el REMAC 5 o el Decreto 2324, el documento llegó al modelo en **2**. En su lugar llegan reglamentos locales de playas (Santa Marta, Cartagena), decretos únicos y sentencias del Consejo de Estado. El REMAC 5 es el documento más grande del corpus (572 fragmentos) y sí está segmentado por artículos: el problema no es la segmentación, sino que sus fragmentos compiten con muchos otros de vocabulario parecido y no alcanzan el top-4.
- **La diferencia entre casos revisados y no revisados la explica la normativa, no la revisión.** Los revisados tienen hit@4 de 0,11 y los no revisados de 0,79, pero **18 de los 19 casos revisados son preguntas de normativa.**
- **La reescritura de la pregunta con el LLM no mejora la recuperación.** Con la consulta reescrita (la recuperación real del grafo, fase 2) el hit@4 es el mismo: 0,56 frente a 0,56. Gana en 2 casos y pierde en otros 2.
- **Hay poca diversidad.** En **20 de 66** preguntas, los 4 fragmentos vienen del **mismo** documento. En preguntas de cruce entre documentos (hit@4 de 0,40), eso deja fuera al segundo documento.
- El documento correcto **sí aparece en el top-20 en el 74%** de los casos: muchas veces está cerca y queda fuera por el corte en 4.

## 5. Comportamiento del sistema

El grafo solo busca en el corpus si primero clasifica la pregunta como "dentro del ámbito". Si no, devuelve una respuesta fija. Por eso se registró la ruta de cada caso, y las respuestas fijas se reportan aparte y no se califican con RAGAS.

| | Resultado |
|---|---|
| Preguntas clasificadas "dentro del ámbito" | **65 / 66** |
| Respuestas generadas | 65 (ninguna respuesta fija de "sin evidencia" ni de "citas inválidas") |
| Rechazada como "fuera del ámbito" | 1: registro 046 (ver §7.4) |
| Latencia por pregunta | media **61 s**, rango de 10 a 117 s |
| Tokens de salida por pregunta | ~8.200, en su mayoría razonamiento interno de gpt-5-nano |
| Errores | 0 |

## 6. Calidad de las respuestas

Sobre los 65 casos respondidos.

| Tipo | n | Context recall | Context precision | Faithfulness | Factual precisión | Factual cobertura | Factual F1 | Answer accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Todos** | **65** | **0,80** | **0,94** | **0,87** | **0,72** | **0,70** | **0,70** | **0,72** |
| 1. Extracción puntual | 2 | 0,50 | 1,00 | 0,33 | 0,00 | 0,00 | 0,00 | 0,25 |
| 2. Síntesis dentro de un documento | 7 | 0,93 | 0,86 | 0,96 | 0,78 | 0,71 | 0,74 | 0,75 |
| 3. Cruce entre documentos | 5 | 0,67 | 1,00 | 0,92 | 0,79 | 0,66 | 0,72 | 0,65 |
| 4. Comparación jurídica | 7 | 0,63 | 0,79 | 0,88 | 0,76 | 0,74 | 0,74 | **0,54** |
| 5. Aplicación normativa o jurisprudencial | 36 | 0,86 | 0,99 | 0,87 | 0,77 | 0,76 | 0,75 | 0,83 |
| 6. Secuencia, trámite u orden jurídico | 8 | 0,69 | 0,83 | 0,89 | **0,51** | **0,60** | **0,54** | 0,56 |

| Diagnóstico | Casos | Cuáles |
|---|---:|---|
| Correcta | 51 | — |
| Falla de recuperación | 8 | 003, 008, 014, 033, 035, 061, 062, 065 |
| Incompleta o demasiado general | 6 | 012, 024, 032, 047, 051, 055 |
| Alucinación | 0 | — |

**Lectura:**
- **No hay alucinación sistemática.** Cuando el contexto es bueno, el modelo se apega a él.
- **"Secuencia y trámite" es el tipo más débil en contenido.** Las respuestas omiten pasos o los mezclan (precisión 0,51). En "Comparación jurídica", Answer Accuracy da 0,54.
- **"Extracción puntual" tiene solo 2 casos.** Uno es un error real de ATLAS (§7.2) y el otro, un cero falso del juez (§10). No permite conclusiones.
- **Context recall (0,80) es mucho mayor que el acierto del documento exacto (0,57).** El juez encuentra el contenido de la respuesta jurídica en *otros* documentos recuperados. Para preguntas generales eso basta. Cuando la respuesta depende de un procedimiento que solo está en el REMAC 5, no (§7.1). Por eso conviene definir con el equipo jurídico **qué fuente debe citarse** (§12).

## 7. Ejemplos concretos

### 7.1 Falla de recuperación: el trámite del REMAC 5 (registro 003, tipo 6)

*Pregunta:* unos socios quieren un club náutico con muelle flotante en Santa Marta. ¿Basta con la concesión ante la Capitanía de Puerto?

- **Equipo jurídico:** describe el procedimiento del **REMAC 5** en etapas: solicitud con memoria georreferenciada, **certificaciones de siete entidades** (Alcaldía, MinTransporte, MinComercio, MinCultura, ICANH, Consulta Previa y verificación de antecedentes), archivo si alguna es desfavorable y **30 días hábiles de publicidad**.
- **ATLAS:** responde con el procedimiento del **Decreto 2324 de 1984 (art. 169)** y una sentencia, porque el REMAC 5 no llegó entre sus 4 fragmentos. La respuesta está bien citada, pero **omite las etapas vigentes.**
- **Métricas:** context recall 0,25, answer accuracy 0,50 → *falla de recuperación*.

### 7.2 Error de dato: radicado equivocado (registro 062, tipo 1)

*Pregunta:* ¿cuál es el número de radicación de la sentencia de segunda instancia del cerramiento de la playa Los Cocos?

- **Equipo jurídico:** `47-001-3333-005-2010-00684-01` (caso Lemus Orozco).
- **ATLAS:** `47001-2332-000-2011-08425-02`. Es el radicado de **otro** proceso (la segunda instancia del caso Carrero), con cita a un fragmento.
- **Métricas:** faithfulness 0, answer accuracy 0. Para un abogado o un actor popular, este error es grave.

### 7.3 Respuesta correcta (registro 002, tipo 2)

*Pregunta:* motos acuáticas y parasailing cerca de bañistas en El Rodadero. ¿DIMAR fija zonas?

- ATLAS coincide con el equipo jurídico: hay zonas de deportes náuticos delimitadas con boyas, DIMAR ejerce el control y se puede acudir a la Capitanía. Cita el reglamento de playas de Santa Marta en lugar del Decreto 2324 que señaló el equipo jurídico.
- **Métricas:** context recall 1,0, faithfulness 1,0, factual F1 0,94.

### 7.4 Pregunta pertinente rechazada (registro 046)

*Pregunta:* "Mi licencia de construcción fue suspendida por una medida cautelar… ¿ese tiempo se descuenta de la vigencia?". Proviene del caso Lemus Orozco (muro en playa Los Cocos).

- ATLAS respondió **"La consulta está fuera del ámbito…"**, porque la pregunta no menciona la playa. Es un **falso negativo** del clasificador de alcance: un usuario real recibiría esa respuesta ante una pregunta pertinente.

## 8. Hipótesis de calibración (no aplicadas)

Ordenadas por impacto esperado. Cada una se probaría en su propia rama, midiendo antes y después con este mismo procedimiento.

| # | Hipótesis | Evidencia | Qué se mediría |
|---|---|---|---|
| C1 | **Recuperar mejor la normativa nacional (REMAC 5, Decreto 2324).** Opciones a comparar: normalizar BM25 (mayúsculas, tildes, puntuación), dar más peso a BM25 en preguntas de trámite, incluir título y artículo en el texto indexado y revisar el filtro por tipo de documento. Aparte, seccionar por artículo los 9 decretos y códigos que hoy no lo están (D5) | Normativa hit@4: 2/18; caso 003 | hit@4 de normativa, context recall del tipo 6 |
| C2 | **Más diversidad de documentos en el top-k:** tope de fragmentos por documento, o subir `k` o `k_candidates` | 20/66 con los 4 fragmentos del mismo documento; hit@20 = 0,74 frente a hit@4 = 0,57 | hit@4 de cruce y comparación, costo por pregunta |
| C3 | **Instrucciones específicas para trámites:** pedir los pasos enumerados y completos, con la norma que los rige | Tipo 6: precisión 0,51, F1 0,54 | Factual F1 del tipo 6 |
| C4 | **Jerarquía normativa en el prompt:** priorizar la norma vigente (REMAC) sobre la anterior (Decreto 2324) y sobre la jurisprudencia | Caso 003 | Rúbrica de jerarquía |
| C5 | **Clasificador de alcance menos estricto** con preguntas sobre licencias u obras costeras que no dicen "playa" | Caso 046 | Falsos negativos en el set |
| C6 | **Latencia:** probar un `reasoning_effort` más bajo en la generación | 61 s de media | Latencia, costo y que la calidad no baje |
| C7 | Normalizar títulos y texto a NFC en la ingesta | D2 | — |

## 9. Hallazgos sobre los datos

Encontrados al preparar la medición. **Ninguno se ha corregido**; se presentan para decidir con el equipo.

| # | Hallazgo | Impacto |
|---|---|---|
| D1 | **La numeración SM-XX del Excel del ground truth no coincide con la del corpus.** El CSV de metadatos, `ingesta/docs/archivos-indexados.md` y el metadato `Nº` de los fragmentos dicen SM-01 = *Procuraduría vs Corpamag*, SM-04 = *Lemus Orozco* y SM-09 = *Gabriel Carrero*; la lista del Excel dice SM-01 = *Lemus Orozco*, SM-05 = *Gabriel Carrero* y SM-09 = *Procuraduría*, entre otros | Si se cruza por código, la evaluación queda mal, y si ATLAS muestra "SM-xx" a un usuario, puede citar otro documento. La evaluación cruza **por título**, con una tabla explícita en `ground_truth_v02.py` |
| D2 | **Parte del corpus tiene los títulos en Unicode NFD** (la tilde separada de la letra, típico de archivos creados en macOS): 6 de las 9 sentencias SM | Se ven iguales pero el código los distingue. La evaluación compara en NFC; conviene normalizar en la ingesta (C7) |
| D3 | **La taxonomía de tipos del Excel (6 tipos) no coincide** con la nombrada en la reunión (localización, extracción, síntesis, relación causal, juicio de valor). Además, el Excel trae etiquetas con variantes (mayúsculas, tildes, el tipo 6 partido en dos celdas) | Este reporte usa los 6 tipos del Excel, normalizados |
| D4 | **39 de los 66 casos no tienen revisor**; 8 no tienen documento esperado | Los resultados por revisión se reportan aparte (§4) |
| D5 | **Artefactos de procesamiento en la capa gold** (no de la fuente jurídica): 245 fragmentos de menos de 150 caracteres (46 son solo un "."), 166 filas sueltas de tabla, 343 duplicados exactos y 9 decretos o códigos extensos sin segmentar por artículo | La fusión ya descarta los fragmentos sin texto, pero no las filas de tabla ni los duplicados, que pueden ocupar lugares del top-4. Cualquier ajuste conservaría el 100% del contenido jurídico |
| D6 | **No hay preguntas "fuera del corpus"** (la hoja existe en el Excel pero está vacía) | No se puede medir si ATLAS reconoce cuándo no tiene información |

## 10. Confiabilidad de la medición

- **El juez varía caso por caso.** Se repitió Factual Correctness dos veces más en los dos casos con cero:
  - registro 032: 0 → 0,36 → 0,40;
  - registro 014: 0 → 0,15 → 0.

  El 032 es una respuesta correcta que el juez calificó mal la primera vez. **Los promedios por grupo son útiles; la nota de un caso aislado no es concluyente.** Para comparar calibraciones conviene repetir cada corrida 2–3 veces o subir el `reasoning_effort` del juez.
- **El juez es algo indulgente al partir en afirmaciones.** Con la configuración por defecto las afirmaciones son gruesas: en el caso 003 dio cobertura 0,65 a una respuesta que omite la mayoría de las etapas. Answer Accuracy (0,50 en ese caso) es más estricta.
- **Métricas que se interpretan con cautela:** Response Relevancy (0,60) compara la pregunta, que son relatos largos, con preguntas cortas que el juez reconstruye desde la respuesta, así que tiende a quedar baja aunque la respuesta sea pertinente. Semantic Similarity (0,72) mide parecido de tema, no exactitud jurídica. Por eso no se usan en el diagnóstico.
- **hit@k es estricto:** si ATLAS responde bien con otro documento válido, cuenta como fallo (por ejemplo, el caso 002).
- **Valores faltantes:** 3 de 585 (cortes de conexión con Ollama). Los promedios los excluyen.
- **Tamaño de muestra:** los tipos 1, 3 y 4 tienen entre 2 y 7 casos, así que sus promedios son orientativos.
- **Juez y evaluado son el mismo modelo** (gpt-5-nano), por ser el modelo autorizado para el proyecto. Puede haber algo de indulgencia.

## 11. Costo y reproducibilidad

| Concepto | Costo estimado (OpenAI, gpt-5-nano) |
|---|---:|
| Generación: 66 preguntas con el grafo real | 0,23 USD |
| Juez RAGAS: 65 casos (≈0,0066 USD por caso) | ≈0,43 USD |
| Repetición de control (§10) | 0,01 USD |
| **Total** | **≈0,67 USD** |

- Las fases 0, 1 y 5 no usan LLM, y los embeddings los calcula el Ollama del proyecto.
- Los comandos están en [`SCRIPTS.md` § Línea base](SCRIPTS.md#línea-base-sobre-legal-ground-truth-v02). La generación y el juez escriben caso a caso y se pueden reanudar.
- Los resultados crudos (`evaluation/results/`) no se versionan, porque se regeneran con los comandos. Cada reporte registra el commit, el hash del dataset y el modelo.
- Las corridas posteriores a esta línea base, como la comparación con un modelo local, quedan en el [registro de evaluaciones](REGISTRO_EVALUACIONES.md) y en el [informe para el equipo jurídico](INFORME_EVALUACION_ATLAS.md#5-comparación-con-un-modelo-local).
- El código nuevo tiene 54 pruebas unitarias. La suite de `rag/` queda en 815 pruebas en verde, sin cambios en el backend, el frontend ni las dependencias.

## 12. Decisiones que necesitamos

1. **¿Qué fuente debe citar ATLAS** cuando el contenido está tanto en el REMAC 5 como en un reglamento local o en una sentencia? ¿La vigente de mayor jerarquía?
2. ¿Cuál numeración SM-XX es la oficial: la del corpus o la del Excel (D1)?
3. ¿Qué taxonomía de tipos se usa para reportar (D3)?
4. ¿Priorizamos **C1** (recuperación de normativa) y **C3** (trámites) antes de la demostración de noviembre?
5. ¿El equipo jurídico puede revisar los 14 casos no correctos de la §6 para confirmar el diagnóstico del juez?
6. ¿Puede el equipo jurídico aportar **preguntas fuera del corpus** (D6)?
