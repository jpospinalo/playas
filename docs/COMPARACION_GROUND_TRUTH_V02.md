# ATLAS — comparación con el ground truth jurídico v0.2

Fecha: 22 de octubre de 2026, America/Bogota (artefactos con timestamps UTC del 23 de octubre). Rama local `feat/evaluacion-ground-truth-v02`, desde `feat/ingesta-normalizacion` @ `2c9d6be`. Sin push, PR, merge ni acceso a producción. El informe queda **sin commit**.

## Resultado principal

**v2b mejora descriptivamente a v1 en esta muestra jurídica**: hit@4 de Julian 0,65517 frente a 0,56897 (+5 casos de 58) y MRR 0,62490 frente a 0,55637. Sin embargo, sus IC95 pareados incluyen cero para hit@4 y MRR; **no está demostrada una mejora concluyente ni equivalencia estadística**. El top-4 efectivo mejora solo de 35/58 a 37/58. v2a presenta un resultado mixto: aumenta hit@4, pero empeora MRR. No se infiere calidad de respuestas desde estas métricas.

La compuerta v1 reproduce los tres promedios publicados al redondear. Dos cifras auxiliares **no se reprodujeron**: REMAC/Decreto 2324 resultó 1/18, frente al 2/18 publicado; concentración del top-4, 21/66 frente a 20/66. Se conservan estas discrepancias y no se calibra el sistema para ocultarlas.

## 1. Procedencia, condiciones iguales y diferencias

| Elemento | Condición comprobada |
| --- | --- |
| Código de Julian | 6ab886ac85b6b9c69950eaa4a1da6842836b8d8f; copia sin merge de rag/evaluation, rag/tests/unit y rag/docs; 103 archivos originales comprobados, salvo conversión LF/CRLF |
| Base de ingesta | 2c9d6bef4bcc004543a35432b6f9893135a99e7f; legal-metadata-2; snapshots finales v2a_r2/v2b_r2 |
| Código del complemento | bb803723e8fae89fee26944e53c89bb52061c9df; solo evaluation/ground_truth_v02; no modifica el evaluador original |
| Core y main | rag/backend/rag/core idéntico a main f16586f5c4b69e09ac3ef2e3f7863fd65e415816; origin/main también f16586f |
| Dataset | 66 preguntas originales; 58 con documento esperado; JSON y Excel originales de Julian |
| source_sha256 (campo del JSON) | dddbde03c04823e18149d524df3ec3315ba7f8f23a8d0989cee245eb4a6b67a1; corresponde al Excel, verificado contra su contenido |
| SHA256 JSON en Windows | 0f7c60b3f3c931d12b65171a9033faa3b34366440203a31fe5baffc3b347c615; CRLF del checkout |
| SHA256 JSON del objeto Git | edb4ecdaa7655a3505025c159eae471fcb2088be9442187870b35b951dbf8225; diferencia de finales de línea, no de casos |
| Recuperación | get_ensemble_retriever; BM25 0,3/vector 0,7; RRF c=160; k=4/candidates=8 y k=20/candidates=20 |
| Pregunta y filtros | Original literal, sin reescritura ni doc_type; title exacto en NFC con same_title |
| Embeddings | embeddinggemma:latest; 768 dimensiones; digest 85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1 |
| Ollama | 0.40.8; endpoint de embeddings del core intacto; sin modelo generador |
| Chroma | Imagen chromadb/chroma:1.3.5 sha256:111a6bd768be19721f5b4e88567d0e1d1f5c2ab5161129e711c0a431e667b128; endpoint get_version reporta 1.0.0; cliente Python 1.5.9 |
| Librerías de medición | Python 3.12.15 Windows; NumPy 2.4.6; rank-bm25 0.2.2; langchain-chroma 1.1.0 |
| Infraestructura | Solo Chroma/Ollama propios del sandbox 679786170402, us-east-1; cálculo del evaluador en Windows local; ninguna EC2 temporal creada |
| Diferencias deliberadas | Colección/UUID/conteo y contenido de cada ingesta. Paridad de metadatos solo en nuevas v2a/v2b; no se transfirió enriquecimiento LLM de v1 |
| Lo no verificado de Julian | Versiones completas de sus librerías/servidor y resultados crudos por caso de la corrida publicada no disponibles; no se afirma igualdad del entorno binario |

La comprobación automática de igualdad de configuraciones entre las tres corridas excluye únicamente colección, UUID y conteo. Evidencias: `evaluation/ground_truth_v02/results/{v1,v2a,v2b}.json`, `provenance.json`, `runtime_versions.json` y `comparison.json`.

### Diferencia de definición encontrada en el evaluador

`rag/evaluation/retrieval_baseline.py:77` calcula hit@4 como `rank <= 4` del ranking **profundo k=20**, aunque `run()` guarda `top_prod` de la pasada **k=4/candidates=8** por separado. Esas pasadas no tienen por qué ordenar igual. Se ejecutó su código sin cambios: **hit@4 J** conserva la cifra publicada y la compuerta; **hit@4 P** comprueba `same_title` sobre el top-4 efectivo. MRR y hit@20 usan siempre la pasada profunda; doc_recall@4 usa siempre top_prod.

Casos con discrepancia entre ambas definiciones: v1: registro-034, registro-058; v2a: registro-031, registro-061; v2b: registro-006, registro-035, registro-054. No se sustituyó silenciosamente una por otra.

## 2. Recuperación y paridad de metadatos

| Colección medida | Snapshot | Vectores | Dimensión | SHA256 comprimido |
| --- | --- | --- | --- | --- |
| v1/rag_playas | chroma-rag_playas_magdalena-20260731-135720.jsonl.gz | 5888 | 768 | 28b7a3076d1c7ad0aa3ef2a4394e31423cdd5358f691fdc6a6104f7e15712d2d |
| v2a | v2a_r2.jsonl.gz | 5281 | 768 | 2ee27c25c5e27877392275e9607d11f4ce25a06fcbb06353459d74c096580533 |
| v2b | v2b_r2.jsonl.gz | 2366 | 768 | 3bbc31e7a48f0701642558e5aceccd861663eac46b44f2c3ac87fe4087b443f3 |

Los dos manifiestos verificaron checksum comprimido, checksum de registros, IDs únicos, conteo y 768 valores finitos por vector. No se recalculó ningún embedding de documentos. Se midió v1 existente, sin recrearla. Las variantes se importaron como colecciones nuevas `v2a` y `v2b`.

**55/55 fuentes v2 ya tenían title equivalente a v1 en NFC.** Se aplicó la tabla explícita del anexo con title en NFC y el identificador Nº de la misma fuente v1. Se añadieron alias `Corporación←corporacion`, `Magistrado ponente←magistrado_ponente`, `Radicado←radicado`, `section_heading←section_name`; los campos opcionales ausentes quedan vacíos, sin inventar valores ni copiar summary/keywords/entities históricos. `book_title` pertenece a construcción histórica del vectorstore, no a la ruta de recuperación medida; las claves de uso/tokens pertenecen a metadatos LLM, no a documentos. Los alias de encoding son fallbacks y ya existe la clave primaria canónica. El inventario de lecturas con ruta y línea está en `snapshots.json:metadata_reads`.

La actualización usó exclusivamente `collection.update(ids=…, metadatas=…)`; los hashes de textos y vectores leídos del servidor antes/después fueron idénticos en cada variante:

- v2a: `03b1ab3f5f51b6a357a5243291ccd0ba65fab89b593300342871a22f6a964f46`.
- v2b: `d32d710cb099b144826f7c4e2280177064c5dca401e6f29458e5521aabd86f4f`.

**Identidad perdida por deduplicación:** los dos PDFs de Gabriel Carrero son idénticos por bytes en la preparación anterior, pero v1 los presenta con títulos distintos. V2 conserva como fuente primaria `CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.pdf`; desaparece el título `SENTENCIA DE SEGUNDA INSTANCIA 47001-2332-000-2011-08425-02- GABRIEL CARRERO`. No se duplica el documento ni se cambia su identidad según el ground truth. Un hit estricto podría penalizar referencias futuras a ese alias jurídicamente equivalente; requiere una decisión posterior sobre identidad documental, no una corrección ad hoc del evaluador.

**Ninguno de los 66 casos espera ese título:** esta pérdida de alias no penaliza directamente los hit@k de la muestra actual. Evidencias: tabla `source_aliases` y `v1_sources_absent_after_exact_dedup` en snapshots.json; preparación original preservada.

## 3. Compuerta de reproducción de v1

| Métrica | Julian publicado | Reproducción | Diferencia |
| --- | --- | --- | --- |
| hit_at_4 | 0.57 | 0.56897 | -0.00103 |
| hit_at_20 | 0.74 | 0.74138 | 0.00138 |
| mrr | 0.56 | 0.55637 | -0.00363 |

**APROBADA:** diferencias absolutas de hit@4 e hit@20 inferiores a 0,03. Se continuó únicamente después de guardar `v1.json:gate.passed=true`. El hit@4 P de v1 es 35/58 = 0,60345; no sustituye el hit@4 J publicado.

| Control auxiliar | Publicación | Reproducción | Interpretación |
| --- | --- | --- | --- |
| REMAC 5/Decreto 2324 en 18 casos | 2/18 | 1/18 | No coincide; registro-016 es el único hit efectivo de la norma esperada |
| Top-4 de un mismo documento | 20/66 | 21/66 | No coincide; lista de 21 IDs incluida en comparison.json |

No se dispone de los resultados crudos auxiliares de Julian para atribuir la diferencia a cohorte, desempates, ANN u otra condición. **Causa no verificada.** Las cifras globales y por tipo reproducen su tabla al redondear; la compuerta solicitada no condicionaba la continuación a esos dos controles auxiliares.

## 4. Nivel 0 — resultados globales

| Colección | n | hit@4 J | hit@4 P | hit@20 | MRR | doc_recall@4 |
| --- | --- | --- | --- | --- | --- | --- |
| v1 | 58 | 0.56897 | 0.60345 | 0.74138 | 0.55637 | 0.53448 |
| v2a | 58 | 0.62069 | 0.62069 | 0.79310 | 0.52034 | 0.56897 |
| v2b | 58 | 0.65517 | 0.63793 | 0.81034 | 0.62490 | 0.59483 |

### Por tipo de pregunta

| Tipo | Colección | n | hit@4 J | hit@4 P | hit@20 | MRR | doc_recall@4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Extracción puntual | v1 | 2 | 1.00000 | 1.00000 | 1.00000 | 1.00000 | 1.00000 |
| 1. Extracción puntual | v2a | 2 | 1.00000 | 1.00000 | 1.00000 | 1.00000 | 1.00000 |
| 1. Extracción puntual | v2b | 2 | 1.00000 | 1.00000 | 1.00000 | 1.00000 | 1.00000 |
| 2. Síntesis dentro de un documento | v1 | 7 | 0.71429 | 0.71429 | 0.85714 | 0.72269 | 0.64286 |
| 2. Síntesis dentro de un documento | v2a | 7 | 0.71429 | 0.71429 | 0.85714 | 0.62925 | 0.64286 |
| 2. Síntesis dentro de un documento | v2b | 7 | 0.85714 | 0.85714 | 0.85714 | 0.85714 | 0.78571 |
| 3. Cruce entre documentos | v1 | 5 | 0.40000 | 0.60000 | 0.60000 | 0.44000 | 0.40000 |
| 3. Cruce entre documentos | v2a | 5 | 0.60000 | 0.60000 | 0.80000 | 0.46176 | 0.40000 |
| 3. Cruce entre documentos | v2b | 5 | 0.60000 | 0.60000 | 0.80000 | 0.62222 | 0.40000 |
| 4. Comparación jurídica | v1 | 7 | 0.71429 | 0.85714 | 0.85714 | 0.73810 | 0.50000 |
| 4. Comparación jurídica | v2a | 7 | 0.71429 | 0.71429 | 1.00000 | 0.49286 | 0.50000 |
| 4. Comparación jurídica | v2b | 7 | 0.85714 | 0.71429 | 1.00000 | 0.72180 | 0.57143 |
| 5. Aplicación normativa o jurisprudencial | v1 | 29 | 0.51724 | 0.51724 | 0.68966 | 0.48976 | 0.51724 |
| 5. Aplicación normativa o jurisprudencial | v2a | 29 | 0.55172 | 0.51724 | 0.68966 | 0.43733 | 0.51724 |
| 5. Aplicación normativa o jurisprudencial | v2b | 29 | 0.51724 | 0.55172 | 0.68966 | 0.51680 | 0.55172 |
| 6. Secuencia, trámite u orden jurídico | v1 | 8 | 0.50000 | 0.50000 | 0.75000 | 0.45511 | 0.50000 |
| 6. Secuencia, trámite u orden jurídico | v2a | 8 | 0.62500 | 0.75000 | 0.87500 | 0.66667 | 0.75000 |
| 6. Secuencia, trámite u orden jurídico | v2b | 8 | 0.75000 | 0.62500 | 1.00000 | 0.63661 | 0.62500 |

### Por revisión

| revisado | Colección | n | hit@4 J | hit@4 P | hit@20 | MRR | doc_recall@4 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| True | v1 | 19 | 0.10526 | 0.10526 | 0.36842 | 0.10620 | 0.10526 |
| True | v2a | 19 | 0.21053 | 0.21053 | 0.42105 | 0.19777 | 0.21053 |
| True | v2b | 19 | 0.21053 | 0.15789 | 0.47368 | 0.21639 | 0.15789 |
| False | v1 | 39 | 0.79487 | 0.84615 | 0.92308 | 0.77568 | 0.74359 |
| False | v2a | 39 | 0.82051 | 0.82051 | 0.97436 | 0.67749 | 0.74359 |
| False | v2b | 39 | 0.87179 | 0.87179 | 0.97436 | 0.82391 | 0.80769 |

Hay 27 casos revisados y 39 sin revisor entre los 66. En las métricas de relevancia quedan 19 revisados y 39 no revisados: los otros 8 revisados no tienen documento esperado. La revisión está muy asociada con la cohorte normativa; no puede interpretarse la diferencia como efecto causal del revisor.

### Normativa nacional y diversidad

| Colección | Cohorte normativa n | hit@4 J cohorte | Norma esperada en top-4 P | Top-4 del mismo documento / 66 |
| --- | --- | --- | --- | --- |
| v1 | 18 | 0.05556 | 1/18 | 21/66 |
| v2a | 18 | 0.16667 | 3/18 | 18/66 |
| v2b | 18 | 0.16667 | 2/18 | 19/66 |

Hits efectivos de REMAC/Decreto: v1: registro-016; v2a: registro-003, registro-014, registro-016; v2b: registro-003, registro-016. v2b tiene 3/18 en la definición profunda J, pero solo 2/18 en el top-4 efectivo. v2a recupera 3/18 normas, aun siendo inferior en MRR global.

## 5. Comparación pareada

Unidad de remuestreo: pregunta con documento esperado, n=58. Bootstrap pareado de 10.000 muestras, semilla 20261022; IC95 percentil. McNemar binomial exacto bilateral para hit@4, sin ajuste por múltiples comparaciones. Gana/pierde/empata se refiere al valor de cada métrica, no a una calificación jurídica. El archivo `paired_cases.csv` y los arreglos `paired.*.*.*.cases` conservan la comparación de cada caso.

| Vs v1 | Métrica | Δ media | IC95 Δ | Gana | Pierde | Empata | p McNemar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| v2a | hit_at_4_julian | 0.05172 | [-0.05172, 0.15517] | 6 | 3 | 49 | 0.50781 |
| v2a | hit_at_4_prod | 0.01724 | [-0.06897, 0.10345] | 4 | 3 | 51 | 1.00000 |
| v2a | hit_at_20 | 0.05172 | [-0.01724, 0.12069] | 4 | 1 | 53 | — |
| v2a | mrr | -0.03603 | [-0.11124, 0.03813] | 13 | 10 | 35 | — |
| v2a | doc_recall_at_4 | 0.03448 | [-0.05172, 0.12069] | 5 | 3 | 50 | — |
| v2b | hit_at_4_julian | 0.08621 | [-0.01724, 0.18966] | 7 | 2 | 49 | 0.17969 |
| v2b | hit_at_4_prod | 0.03448 | [-0.05172, 0.12069] | 4 | 2 | 52 | 0.68750 |
| v2b | hit_at_20 | 0.06897 | [0.01724, 0.13793] | 4 | 0 | 54 | — |
| v2b | mrr | 0.06852 | [-0.00118, 0.14692] | 13 | 5 | 40 | — |
| v2b | doc_recall_at_4 | 0.06034 | [-0.01724, 0.14655] | 6 | 2 | 50 | — |

### Comparación pareada por revisión

| Revisado | Vs v1 | Métrica | n | Δ media | IC95 Δ | G/P/E | p McNemar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| True | v2a | hit_at_4_julian | 19 | 0.10526 | [0.00000, 0.26316] | 2/0/17 | 0.50000 |
| True | v2a | hit_at_4_prod | 19 | 0.10526 | [0.00000, 0.26316] | 2/0/17 | 0.50000 |
| True | v2a | mrr | 19 | 0.09157 | [0.00661, 0.21842] | 6/1/12 | — |
| True | v2b | hit_at_4_julian | 19 | 0.10526 | [0.00000, 0.26316] | 2/0/17 | 0.50000 |
| True | v2b | hit_at_4_prod | 19 | 0.05263 | [0.00000, 0.15789] | 1/0/18 | 1.00000 |
| True | v2b | mrr | 19 | 0.11019 | [0.00574, 0.25419] | 6/1/12 | — |
| False | v2a | hit_at_4_julian | 39 | 0.02564 | [-0.10256, 0.15385] | 4/3/32 | 1.00000 |
| False | v2a | hit_at_4_prod | 39 | -0.02564 | [-0.12821, 0.07692] | 2/3/34 | 1.00000 |
| False | v2a | mrr | 39 | -0.09820 | [-0.19144, -0.01251] | 7/9/23 | — |
| False | v2b | hit_at_4_julian | 39 | 0.07692 | [-0.05128, 0.20513] | 5/2/32 | 0.45312 |
| False | v2b | hit_at_4_prod | 39 | 0.02564 | [-0.07692, 0.12821] | 3/2/34 | 1.00000 |
| False | v2b | mrr | 39 | 0.04823 | [-0.03470, 0.14251] | 7/4/28 | — |

**Lectura:** v2b gana 7 y pierde 2 casos con hit@4 J (49 empates); con el top-4 efectivo gana 4 y pierde 2 (52 empates). Su IC95 de MRR incluye ligeramente cero. El IC bootstrap de hit@20 es positivo, pero es un resultado secundario con solo cuatro ganancias y sin pérdidas; no convierte automáticamente el hit@4 principal en significativo. En v2a hay ganancias de alcance, pero peores primeras posiciones: ΔMRR negativo.

La mejor v2 por la regla fijada (hit@4 J, luego MRR) es **v2b**; también lidera entre v2 en hit@4 P. La variante no se seleccionó mirando resultados del nivel 1, que no se ejecutó.

## 6. Integridad, validación y cierre

v1 no recibió operaciones create/upsert/update/delete en esta fase. Conserva su UUID y 5.888 IDs. Frente al snapshot, todos los textos y metadatos son idénticos. El hash de números serializados de vectores **no es literalmente igual**: diferencia absoluta máxima 1.9999999989472883e-08 en 554888 componentes. Compatible con diferencias de representación numérica, pero **la causa no está verificada** y no se afirma identidad binaria. No se restauró ni corrigió v1. Evidencia: `v1_integrity.json`.

| Validación | Resultado |
| --- | --- |
| Pruebas de Julian | 71/71 aprobadas; fixtures gold originales recuperados por SHA, nombres cortos locales por límite de rutas Windows; no se versionaron |
| Pruebas estadísticas nuevas | 5/5 aprobadas; NFC exacto, diferencia de definiciones, McNemar, bootstrap y emparejamiento por ID |
| Suite RAG completa | 840 aprobadas/2 fallidas inicialmente. RapidFuzz 3.14.3 declarado pero ausente localmente fue instalado; ese test pasó al repetir |
| Fallo pendiente | test_query_timeouts.py::test_stream_survives_several_stages_that_together_exceed_a_total_budget falló en sus dos intentos en Windows; timeout 0,1s, esperaba 3 eventos y recibió 0/1. Causa específica no verificada. No se modificó backend ni se certifica suite completa verde |
| Ruff | check de rag/evaluation y rag/tests/unit aprobado; check y format --check del complemento aprobados |
| Checksums y paridad | Snapshots, 768 componentes finitos, títulos NFC y hashes texto/vector antes/después de actualización de metadatos aprobados |
| LLM y embeddings | 0 llamadas LLM; 0 embeddings nuevos de documentos. Solo embeddings de preguntas mediante el endpoint del core |
| Cierre de colecciones | Retiradas solo v2a/v2b creadas en esta ejecución, con UUID y marca de experimento comprobados; queda rag_playas con 5.888 |
| Cierre AWS | STS679786170402; ambas EC2 vectoriales stopped; no se creó EC2 temporal, no cambios IAM, no terraform destroy, mlflow2 excluida |

Las credenciales iniciales expiraron: se detuvo AWS hasta que el usuario proporcionó reemplazo y se actualizó default mediante el mecanismo previamente autorizado, sin mostrar claves ni transferirlas a EC2. Los resultados y snapshots privados permiten retomar; `docs/ingesta-progress.md` permanece excluido de Git.

## 7. Opcionales omitidos y limitaciones

- **Nivel 1 omitido:** no hay clave OpenAI ya configurada en entorno/env/tfvars inspeccionados. No se usó Gemini, otro generador ni otro juez. No hay generación, métricas RAGAS de respuestas ni repetición 2×10 del juez. El esquema opcional con gpt-5-nano como generador y juez podría tener sesgo por compartir modelo; aquí no se aplicó y no se midió ese sesgo.
- **v2a_t omitida:** no se creó una variante posterior con título indexado ni se recalcularon sus miles de vectores. No se prueba C1 ni se atribuye una mejora al título en el texto.
- **Muestra limitada:** n=58 para relevancia; 39/66 sin revisor; varios casos comparten documento. El bootstrap por pregunta no modela explícitamente dependencia por documento. Grupos de n=2–8 tienen gran incertidumbre.
- **Criterio estricto:** title NFC exacto no evalúa equivalencia jurídica ni pertinencia de un pasaje; la deduplicación puede perder alias relevantes. doc_recall cuenta documentos esperados, no afirmaciones legales.
- **Una ejecución por colección:** no se cuantificó ruido de ANN ni variación entre versiones de librerías; no hay pruebas de carga ni conclusión sobre latencia de producción.
- **No equivalencia demostrada:** IC que incluyen cero no prueban empate; resultados secundarios no ajustados por múltiples comparaciones. Las dos discrepancias auxiliares publicadas y el fallo unitario pendiente quedan abiertos.

**Conclusión y siguiente decisión:** v2b mejora los estimadores globales observados con preguntas del equipo jurídico y es la candidata a una revisión posterior, pero la ganancia del top-4 efectivo es pequeña y su incertidumbre impide afirmar superioridad general. v2a empeora MRR pese a recuperar más casos. No se recomienda sustituir automáticamente v1 basándose únicamente en esta muestra. Queda pendiente decidir una identidad canónica que preserve alias de documentos duplicados, reconciliar los controles auxiliares con los crudos de Julian y evaluar respuestas cuando exista la clave OpenAI requerida. Ninguno de esos cambios se aplicó aquí.

## 8. Artefactos y hashes de corrida

| Corrida | UUID durante medición | SHA256 configuración |
| --- | --- | --- |
| v1 | b569496c-801d-4ad0-a03b-135c3ef74ff2 | 23e847f66bb50fd9da037a24cbb47a1452a003109ace5297635b0f961e92e052 |
| v2a | 0e1115fe-1f7e-4089-8779-4c284fe7e25a | 00a8cb1a82d27f5a33e2b11150a07d451c6c33c371b330172839f5d52a683615 |
| v2b | fbd0de76-7110-49dc-9bc1-9eb492132d66 | 9484848c65d25c40cf915b40ff9947a0fe39e1d0d3fd52744dfa3f002960dd7d |

Configuración estadística SHA256: `19c00a5d3ec8ce87662c2b7ef46c4aea799e6d739a958864d995dce2417253ed`. Los hashes de entradas crudas están en `comparison.json:configuration.input_hashes`. Los snapshots originales y la caché se conservan fuera de Git, en el respaldo privado de la ingesta; los resultados públicos no contienen vectores.

Directorio de evidencia: `evaluation/ground_truth_v02/results/`. Incluye `v1.json`, `v2a.json`, `v2b.json`, `comparison.json`, `paired_cases.csv`, `snapshots.json`, `provenance.json`, `runtime_versions.json`, `v1_integrity.json`, `collections_cleanup.json`, `aws_cleanup.json`, `validation.json` y `validation_commands.md`. Reproducción local/sandbox en `evaluation/ground_truth_v02/README.md`; no hay pasos de despliegue a producción.

## Anexo. Tabla explícita fuente v2 → title de v1 en NFC

Unión por basename de fuente y NFC exactos, sin fuzzy matching; extensiones .pdf/.md se omiten solo para identificar la misma fuente. Esta tabla no amplía same_title. Los 55 valores ya coincidían en NFC antes de la actualización.

| Fuente v2 | Title v1 NFC | Nº v1 |
| --- | --- | --- |
| AP  Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros.pdf | AP  Carlos Alberto Zúñiga Mejía y otros VS DIMAR y otros | SM-02 |
| AP Felipe José Campo Fernández VS Corpamag y otros.pdf | AP Felipe José Campo Fernández VS Corpamag y otros | SM-03 |
| AP Gabriel Antonio Carrero VS DIMAR y otros.pdf | AP Gabriel Antonio Carrero VS DIMAR y otros | SM-09 |
| AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Mata y otros.pdf | AP Gerardo Antenor Lemus Orozco VS Distrito de Santa Mata y otros | SM-04 |
| AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros.pdf | AP Gieseken Cuello & Cía. S. en C. VS DIMAR y otros | SM-05 |
| AP Inversiones E y D S.A.S VS DIMAR y otros.pdf | AP Inversiones E y D S.A.S VS DIMAR y otros | SM-07 |
| AP Miguel Ángel Enciso VS Distrito y otros.pdf | AP Miguel Ángel Enciso VS Distrito y otros | SM-08 |
| AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS.pdf | AP PROCURADURÍA GENERAL DE LA ANCIÓN VS COORPAMAG Y OTROS | SM-01 |
| AP Rodrigo Martínez Silva VS Minambiente y otros.pdf | AP Rodrigo Martínez Silva VS Minambiente y otros | SM-06 |
| CC_TU_039_2024_Modesto_Manjarrez_VS_Autopistas_Del_Caribe_Consulta_Previa_Via.pdf | CC TU 039 2024 Modesto Manjarrez VS Autopistas Del Caribe Consulta Previa Via |  |
| CE_1era_NS_2009_603_Jose_Palencia_VS_MinDefensa_Resolución_Pilotos_Embargaciones.pdf | CE 1era NS 2009 603 Jose Palencia VS MinDefensa Resolución Pilotos Embargaciones |  |
| CE_2da_AP_2010_028_Radley_Bent_VS_Dimar_Daños_Ambientales_Embarcaciones.pdf | CE 2da AP 2010 028 Radley Bent VS Dimar Daños Ambientales Embarcaciones |  |
| CE_2da_AP_2011_178_Jose_Caballero_VS_Distrito_Cartagena_Venta_Inmueble_Valor_Cultural.pdf | CE 2da AP 2011 178 Jose Caballero VS Distrito Cartagena Venta Inmueble Valor Cultural |  |
| CE_2da_AP_2011_842_Gabriel_Carrero_VS_Dimar_Erosión_Costera.pdf | CE 2da AP 2011 842 Gabriel Carrero VS Dimar Erosión Costera |  |
| CE_2da_AP_2015_550_Angela_Muñoz_VS_Dpto_Cordoba_Bienes_De_Uso_Publico.pdf | CE 2da AP 2015 550 Angela Muñoz VS Dpto Cordoba Bienes De Uso Publico |  |
| CE_2da_AP_2016_328_Ricardo_Cabrales_VS_Mun_Coveñas_Playa_Uso_Publico.pdf | CE 2da AP 2016 328 Ricardo Cabrales VS Mun Coveñas Playa Uso Publico |  |
| CE_2da_AP_2017_103_Personeria_VS_Distrito_Cartagena_Desembocadura.pdf | CE 2da AP 2017 103 Personeria VS Distrito Cartagena Desembocadura |  |
| CE_2da_AP_2021_041_Edgar_Stephengs_VS_Archipielago_San_Andres_Desarrollo_Urbanistico.pdf | CE 2da AP 2021 041 Edgar Stephengs VS Archipielago San Andres Desarrollo Urbanistico |  |
| CE_2da_NYR_1994_993_Inversiones_Araujo_VS_Capitania_Puerto_Cartagena_Urbanismo_Playa.pdf | CE 2da NYR 1994 993 Inversiones Araujo VS Capitania Puerto Cartagena Urbanismo Playa |  |
| CE_2da_NYR_1998_102_Flury_Valencia_VS_MinDefensa_Uso_Urbanistico_Playa.pdf | CE 2da NYR 1998 102 Flury Valencia VS MinDefensa Uso Urbanistico Playa |  |
| CE_2da_NYR_1999_503_Inversiones_Mercedes_VS_Dimar_Concesiones_Uso_Playa.pdf | CE 2da NYR 1999 503 Inversiones Mercedes VS Dimar Concesiones Uso Playa |  |
| CE_2da_NYR_2009_164_FEPEP_VS_DIMAR_Playa_Uso_Urbanistico.pdf | CE 2da NYR 2009 164 FEPEP VS DIMAR Playa Uso Urbanistico |  |
| CE_Consulta_1990_Horacio_Serpa_Uso_Publico_Playa.pdf | CE Consulta 1990 Horacio Serpa Uso Publico Playa |  |
| CE_Consulta_2005_168_MinDefensa_Bienes_De_Uso_Publico.pdf | CE Consulta 2005 168 MinDefensa Bienes De Uso Publico |  |
| CE_Consulta_2010_071_MinAmbiente_Bienes_De_Uso_Publico.pdf | CE Consulta 2010 071 MinAmbiente Bienes De Uso Publico |  |
| Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la Unidad Ambiental Costera -POMIUAC- Caribe In.pdf | Por el cual adiciona al Título 4 de la Parte 2 del Libro 2 del Decreto 1076 de 2015, un Capítulo 3 en el que se establece el Plan de Ordenación y Manejo Integrado de la Unidad Ambiental Costera -POMIUAC- Caribe In |  |
| Por el cual se aprueba el ajuste y la modificación a la planta de personal de Empleados Públicos del Ministerio de Defensa Nacional - Dirección General Marítima y se dictan otras disposiciones.pdf | Por el cual se aprueba el ajuste y la modificación a la planta de personal de Empleados Públicos del Ministerio de Defensa Nacional - Dirección General Marítima y se dictan otras disposiciones |  |
| Por el cual se dicta el Código Nacional de Recursos Naturales Renovables y de Protección al Medio Ambiente.pdf | Por el cual se dicta el Código Nacional de Recursos Naturales Renovables y de Protección al Medio Ambiente |  |
| Por el cual se dictan normas para simplificar, suprimir y reformar trámites, procesos y procedimientos innecesarios existentes en la administración pública.pdf | Por el cual se dictan normas para simplificar, suprimir y reformar trámites, procesos y procedimientos innecesarios existentes en la administración pública |  |
| Por el cual se dictan normas sobre la prevención de la contaminación del medio marino y otras disposiciones.pdf | Por el cual se dictan normas sobre la prevención de la contaminación del medio marino y otras disposiciones |  |
| Por el cual se expide el Código de Comercio.pdf | Por el cual se expide el Código de Comercio |  |
| Por el cual se modifica el artículo 16 del Decreto 3888 del 10 de octubre de 2007.pdf | Por el cual se modifica el artículo 16 del Decreto 3888 del 10 de octubre de 2007 |  |
| Por el cual se reglamenta el funcionamiento de los Comités Locales para la  organización de las Playas de que trata el artículo 12 de la Ley 1558 de 2012.pdf | Por el cual se reglamenta el funcionamiento de los Comités Locales para la  organización de las Playas de que trata el artículo 12 de la Ley 1558 de 2012 |  |
| Por el cual se reglamenta el funcionamiento de los comités locales para la organización de las playas.pdf | Por el cual se reglamenta el funcionamiento de los comités locales para la organización de las playas |  |
| Por el cual se reglamenta el manejo del espacio público en los planes de ordenamiento territorial.pdf | Por el cual se reglamenta el manejo del espacio público en los planes de ordenamiento territorial |  |
| Por el cual se reglamenta el servicio público de transporte marítimo.pdf | Por el cual se reglamenta el servicio público de transporte marítimo |  |
| Por el cual se reglamenta la Ley 13 de 1990.pdf | Por el cual se reglamenta la Ley 13 de 1990 |  |
| Por el cual se reglamenta la habilitación y la prestación del servicio público de transporte fluvial.pdf | Por el cual se reglamenta la habilitación y la prestación del servicio público de transporte fluvial |  |
| Por el cual se reglamenta parcialmente el artículo noveno de la Ley 10 de 1978..pdf | Por el cual se reglamenta parcialmente el artículo noveno de la Ley 10 de 1978. |  |
| Por el cual se reglamenta parcialmente la Ley 47 del 19 de febrero de 1993.pdf | Por el cual se reglamenta parcialmente la Ley 47 del 19 de febrero de 1993 |  |
| Por el cual se reglamentan las Unidades Ambientales Costeras - UAC- y las comisiones conjuntas, se establecen las reglas de procedimiento y criterios para reglamentar la restricción de ciertas actividades en.pdf | Por el cual se reglamentan las Unidades Ambientales Costeras - UAC- y las comisiones conjuntas, se establecen las reglas de procedimiento y criterios para reglamentar la restricción de ciertas actividades en |  |
| Por el cual se reglamentan las disposiciones sobre licencias urbanísticas, reconocimiento de edificaciones y legalización de asentamientos humanos.pdf | Por el cual se reglamentan las disposiciones sobre licencias urbanísticas, reconocimiento de edificaciones y legalización de asentamientos humanos |  |
| Por el cual se reorganiza la Dirección General Marítima y Portuaria.pdf | Por el cual se reorganiza la Dirección General Marítima y Portuaria |  |
| Por medio de la cual se reglamenta el área de playa en el Balneario Turístico El Rodadero.pdf | Por medio de la cual se reglamenta el área de playa en el Balneario Turístico El Rodadero |  |
| Por medio del cual se expide el Decreto Único Reglamentario del Sector Ambiente y Desarrollo Sostenible.pdf | Por medio del cual se expide el Decreto Único Reglamentario del Sector Ambiente y Desarrollo Sostenible |  |
| Por medio del cual se expide el Decreto Único Reglamentario del Sector Comercio, Industria y Turismo.pdf | Por medio del cual se expide el Decreto Único Reglamentario del Sector Comercio, Industria y Turismo |  |
| Por medio del cual se expide el Decreto Único Reglamentario del Sector Transporte.pdf | Por medio del cual se expide el Decreto Único Reglamentario del Sector Transporte |  |
| Por medio del cual se expide el Decreto Único Reglamentario del Sector Vivienda, Ciudad y Territorio.pdf | Por medio del cual se expide el Decreto Único Reglamentario del Sector Vivienda, Ciudad y Territorio |  |
| Por medio del cual se expiden las normas bases para la reglamentación de las actividades en las playas urbanas y rurales en el Distrito de Cartagena de Indias.pdf | Por medio del cual se expiden las normas bases para la reglamentación de las actividades en las playas urbanas y rurales en el Distrito de Cartagena de Indias |  |
| Por medio del cual se implementa el Reglamento de Playas del Distrito Portuario, Logístico, Industrial, Turístico y Comercial de Turbo – Antioquia.pdf | Por medio del cual se implementa el Reglamento de Playas del Distrito Portuario, Logístico, Industrial, Turístico y Comercial de Turbo – Antioquia |  |
| Por medio del cual se reglamenta el trámite de solicitud de concesiones para el desarrollo de actividades portuarias previstas en las Leyes 1ª de 1991 y 1242 de 2008.pdf | Por medio del cual se reglamenta el trámite de solicitud de concesiones para el desarrollo de actividades portuarias previstas en las Leyes 1ª de 1991 y 1242 de 2008 |  |
| Por medio del cual se reglamenta el uso, zonificación y horario de las playas con vocación turística del Distrito Turístico, Cultural e Histórico de Santa Marta, aptas para la realización de activiades de aprovech.pdf | Por medio del cual se reglamenta el uso, zonificación y horario de las playas con vocación turística del Distrito Turístico, Cultural e Histórico de Santa Marta, aptas para la realización de activiades de aprovech |  |
| Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103).md | Reglamento Maritimo Colombiano REMAC 5-DIMAR (202103) |  |
| TAA_2da_RD_2015_281_XXXX_VS_Dpto_Antioquia_Responsabilidad_Del_Estado.pdf | TAA 2da RD 2015 281 XXXX VS Dpto Antioquia Responsabilidad Del Estado |  |
| decreto-2324-de-1984.md | decreto-2324-de-1984 |  |

