# `evaluation/` — Evaluación offline del RAG

Infraestructura offline para medir la calidad de ATLAS. Nunca forma parte de la ruta de servicio: ningún módulo de `api/` o `core/` la importa (ver [`docs/ARCHITECTURE.md` § 10](../docs/ARCHITECTURE.md#10-evaluación-offline-evaluation)).

## Contenido

| Archivo | Qué hace |
|---|---|
| `ground_truth.py` | Carga y valida `data/legal-ground-truth-v0.1.json` (21 casos) |
| `ground_truth_v02.py` | Construye `data/legal-ground-truth-v0.2.json` desde el Excel (66 casos, con tipo, `revisado` y documentos esperados por título) y lo valida |
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
