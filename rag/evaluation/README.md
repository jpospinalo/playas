# `evaluation/` — Evaluación offline del RAG

Infraestructura offline para medir la calidad de ATLAS. Nunca forma parte de la ruta de servicio: ningún módulo de `api/` o `core/` la importa (ver [`docs/ARCHITECTURE.md` § 10](../docs/ARCHITECTURE.md#10-evaluación-offline-evaluation)).

## Contenido

| Archivo | Qué hace |
|---|---|
| `ground_truth.py` | Carga y valida `data/legal-ground-truth-v0.1.json` (21 casos) |
| `ground_truth_v02.py` | Construye `data/legal-ground-truth-v0.2.json` desde el Excel (66 casos, con tipo, `revisado` y documentos esperados por título) y lo valida |
| `metricas_sin_llm.py` | **Métricas fijas sin LLM** que se corren siempre: recuperación (documento, artículo exacto, diversidad, fuga territorial) y respuesta (citas, referencias sin respaldo) |
| `retrieval_baseline.py` | Línea base, fase 1: recuperación por documento esperado (hit@k, MRR), sin LLM |
| `generation_cache.py` | Línea base, fase 2: grafo real una vez por caso, con ruta, consulta reescrita, tokens y costo, en caché reanudable |
| `ragas_v02.py` | Línea base, fase 4: métricas RAGAS (`collections`) con juez gpt-5-nano sobre la caché |
| `baseline_report.py` | Línea base, fase 5: tablas consolidadas |
| `run_paths.py` | Rutas de resultados por corrida (`--tag`), para comparar modelos sin sobrescribir la línea base |
| `registro.py` | Registro versionado de evaluaciones (`registro/evaluaciones.csv` → `docs/REGISTRO_EVALUACIONES.md`) |
| `registro/evaluaciones.csv` | Registro de cada evaluación: fecha, versión del sistema, modelo, métricas, latencia y costo (versionado) |
| `ragas_common.py` | Lógica compartida: generación con el grafo real, dataset RAGAS, métricas y reporte reproducible |
| `ragas_eval_gemma.py` | Adaptador con juez Gemini/Gemma: `context_precision`, `context_recall`, `faithfulness`, `answer_relevancy` |
| `ragas_eval_ollama.py` | Adaptador con juez Ollama: `answer_relevancy` |
| `citation_coverage.py` | Diagnóstico offline de cobertura de citas en las respuestas |
| `rrf_diagnostic.py` | Diagnóstico offline de la fusión RRF del retriever híbrido |
| `data/legal-ground-truth-v0.1.json` | Dataset jurídico v0.1 (21 casos) |
| `data/legal-ground-truth-v0.2.xlsx` | Dataset jurídico v0.2 construido por el equipo jurídico (fuente) |
| `data/legal-ground-truth-v0.2.json` | Dataset v0.2 versionado, generado por `ground_truth_v02.py` (66 casos) |
| `results/` | Reportes de cada corrida (no versionados, ver `.gitignore`) |

Comandos, variables de entorno y forma del reporte: [`docs/SCRIPTS.md` § Evaluación del RAG](../docs/SCRIPTS.md#evaluación-del-rag).

## Métricas fijas sin LLM

Se corren **siempre** que se cambie la ingesta, el retriever o los prompts
(`make eval-sin-llm`, ~20 s). No usan gpt-5-nano ni ningún otro modelo
generador o juez: 0 tokens, y la misma entrada da exactamente el mismo
resultado. Comparan contra lo que escribió el equipo jurídico en el ground
truth v0.2 (documento esperado, respuesta y `ubicacion_evidencia`).

| Métrica | Qué mide | Cómo leerla |
|---|---|---|
| `acierto_doc_4` | El documento esperado está entre los **4 fragmentos que llegan al modelo** | Más alto es mejor. Es la métrica principal de recuperación |
| `mrr_doc_20` | Inverso de la posición del documento esperado en el top-20 | Sube si el documento correcto se acerca al top-4 aunque aún no entre |
| `articulos_4` | Fracción de los artículos (`5.3.6.2`) y normas con número y año (`Ley 768 de 2002`) que cita el equipo jurídico y que aparecen en el texto de esos 4 fragmentos | Mide si llega el **artículo exacto**, no solo el documento |
| `docs_distintos_4` | Documentos distintos entre los 4 fragmentos (1 a 4) | Muy bajo indica que un solo documento acapara el contexto |
| `fuga_territorial_4` | Fracción de casos donde llega una norma **local** (Cartagena, Santa Marta, Turbo) de un lugar que la pregunta no menciona | Más bajo es mejor. Debería tender a 0 |
| `citas_validas` | El validador de producción acepta las citas `[docN]` de la respuesta | Debe ser 1. Si baja, se rompió el formato de citas |
| `respuestas_con_refs_sin_respaldo` | Respuestas que citan una norma o artículo que no está en ningún fragmento ni en la pregunta | Más bajo es mejor. Es la señal más directa de una referencia inventada |
| `refs_esperadas_en_respuesta` | Fracción de las referencias del equipo jurídico que la respuesta menciona | Más alto es mejor |

Las métricas de respuesta se calculan sobre una caché de
`generation_cache.py` ya existente: no generan respuestas nuevas.

**Qué no miden:** si la respuesta es jurídicamente correcta. Eso solo lo dice
el juez RAGAS (`ragas_v02.py`), que se reserva para los hitos. En la línea base
el juez califica casi igual las respuestas con y sin el documento esperado
(*answer accuracy* 0,71 frente a 0,70), porque otros documentos pueden
respaldar la respuesta. Estas métricas miden otra cosa: si el sistema llega a
las **mismas fuentes** que usa el equipo jurídico.

**Límites:** el cruce es por título y por texto exacto; `articulos_4` y las
referencias solo aplican a los casos que citan artículos jerárquicos o normas
con número y año (39 de 66). Los artículos cortos ("artículo 15") se ignoran
porque son ambiguos entre normas.

### Línea base de estas métricas

Sistema actual (commit `5c92ef5`, ChromaDB 1.3.5 con la colección del repo y
`embeddinggemma` con el mismo digest que en AWS; caché de gpt-5-nano del
2026-10-08):

| Métrica | Valor | Casos |
|---|---|---|
| `acierto_doc_4` | 0,603 | 58 |
| `mrr_doc_20` | 0,556 | 58 |
| `articulos_4` | 0,071 | 39 |
| `docs_distintos_4` | 2,27 | 66 |
| `fuga_territorial_4` | 0,061 (4 casos) | 66 |
| `citas_validas` | 1,000 | 65 |
| `respuestas_con_refs_sin_respaldo` | 0,046 (3 casos) | 65 |
| `refs_esperadas_en_respuesta` | 0,090 | 38 |

`acierto_doc_4` (0,603) es la tasa de los fragmentos que llegan al modelo. El
`hit_at_4` de `retrieval_baseline.py` (0,569) se calcula sobre el ranking de
20 y por eso es distinto.

## Resultados sobre el ground truth v0.2

66 casos construidos por el equipo jurídico; 27 marcados como revisados. Detalle de cada corrida en el [registro de evaluaciones](../docs/REGISTRO_EVALUACIONES.md).

| Indicador | Sistema actual (gpt-5-nano) | Modelo local (gemma4:e2b) |
|---|---|---|
| Respuestas correctas según el juez | **51 de 65** | 32 de 65 |
| Fidelidad a las fuentes (*faithfulness*) | **0,87** | 0,83 |
| Coincidencia con la respuesta jurídica (Factual F1 / Answer Accuracy) | **0,70 / 0,72** | 0,41 / 0,59 |
| Documento esperado entre los fragmentos consultados (hit@4) | 0,55 (normativa nacional 2 de 18) | 0,57 |
| Tipo de pregunta más débil | Secuencia, trámite u orden jurídico (F1 0,54) | — |

- Informe para el equipo jurídico, con la comparación frente al modelo local: **[`docs/INFORME_EVALUACION_ATLAS.md`](../docs/INFORME_EVALUACION_ATLAS.md)**.
- Anexo técnico de la línea base (cómo leer las métricas, hallazgos y propuestas): **[`docs/EVALUACION_LINEA_BASE.md`](../docs/EVALUACION_LINEA_BASE.md)**.
- Comandos: [`docs/SCRIPTS.md` § Línea base](../docs/SCRIPTS.md#línea-base-sobre-legal-ground-truth-v02).
