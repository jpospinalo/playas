# Registro de evaluaciones de ATLAS

Generado por `evaluation/registro.py` desde `evaluation/registro/evaluaciones.csv`.

| fecha | version_sistema | etiqueta | modelo_generador | juez | casos | respondidas | correctas | respaldo_enricher | hit_at_4 | context_recall | faithfulness | factual_f1 | answer_accuracy | latencia_media_s | costo_generacion_usd |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-10-08 | 4c2186e | linea-base | gpt-5-nano (OpenAI, sistema actual) | gpt-5-nano | 66 | 65 | 51 | n/d | 0.55 | 0.80 | 0.87 | 0.70 | 0.72 | 60.7 | 0.2263 |
| 2026-10-14 | 4c2186e | gemma4-e2b | gemma4:e2b (local, Ollama, sin costo) | gpt-5-nano | 66 | 65 | 32 | 0 | 0.57 | 0.82 | 0.83 | 0.41 | 0.59 | 18.9 | 0.0000 |
| 2026-11-01 | 4c2186e | corpus-congelado | gpt-5-nano (OpenAI, sistema actual) | gpt-5-nano | 66 | 65 | 52 | 0 | 0.53 | 0.85 | 0.88 | 0.66 | 0.73 | 39.0 | 0.2198 |
| 2026-11-01 | 4c2186e | claude-sonnet-aws-prueba | claude-sonnet-5-5 (PRUEBA en AWS, sin OpenAI, no comparable) | claude-haiku-5-5 | 66 | 65 | 14 | 0 | 0.52 | 0.39 | 0.63 | 0.30 | 0.22 | 26.1 | 0.0000 |
