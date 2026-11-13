# ATLAS — Trabajo de la rama de evaluación y recuperación

| | |
|---|---|
| **Autor** | Julian Esteban Rincón Rodríguez |
| **Periodo** | 2026-10-08 → 2026-11-12 |
| **Rama** | `julian-rincon/evaluacion-ragas-linea-base` |
| **Punto de partida** | `main` @ `f16586f` (sistema desplegado en AWS el 2026-10-08) |
| **Revisores** | Juan Pablo Ospina López, Camilo |

> Registro de lo que se hizo en esta rama, por qué y con qué resultado. Describe el estado actual; el detalle de cada cambio está en Git y las cifras completas en [`evaluation/README.md`](../evaluation/README.md#estado-al-2026-11-11-gold-a-corregido-mejoras-de-recuperación-y-qa-sin-juez). Los informes elaborados durante el trabajo se conservan fuera del árbol de fuentes, como pide [`CONTRIBUTING.md`](../../CONTRIBUTING.md#alcance-y-criterios-de-diseño); aquí solo se listan.

## Índice

1. [Resumen](#1-resumen)
2. [Cronología](#2-cronología)
3. [Cambios por componente](#3-cambios-por-componente)
4. [Resultados](#4-resultados)
5. [Decisiones tomadas](#5-decisiones-tomadas)
6. [Verificación](#6-verificación)
7. [Limitaciones conocidas](#7-limitaciones-conocidas)
8. [Informes elaborados](#8-informes-elaborados)
9. [Cómo reproducir](#9-cómo-reproducir)

## 1. Resumen

La rama empezó como la **línea base de calidad** de ATLAS frente al ground truth del equipo jurídico y terminó mejorando la **recuperación**, la **forma de responder** y la **estabilidad de la API**, siempre medido contra esa misma línea base.

| Indicador (66 casos del ground truth v0.2) | Línea base 2026-11-01 | Esta rama |
|---|---:|---:|
| Documento esperado en el top-4 de la búsqueda | 0,586 | **0,741** |
| Documento esperado en los fragmentos que llegan al modelo | 0,53 | **0,75–0,79** |
| Normativa en el top-4 con la pregunta original | 0 de 18 | **8 de 18** |
| Fuga territorial (norma local de otra ciudad) | 0,045 | **0** |
| Respuestas con referencias sin respaldo (generador Claude) | 12,3 % | **3,1 %** |

## 2. Cronología

| Fecha | Etapa | Resultado |
|---|---|---|
| 2026-10-08 → 10-10 | **Línea base RAGAS** sobre `main` sin cambios | Ground truth v0.2 versionado, caché de generación, RAGAS con juez gpt-5-nano y reporte consolidado ([`EVALUACION_LINEA_BASE.md`](EVALUACION_LINEA_BASE.md)) |
| 2026-10-14 → 10-17 | **Registro de evaluaciones** e informe para el equipo jurídico | Cada corrida queda versionada con fecha, versión del sistema, modelo, métricas y costo ([`REGISTRO_EVALUACIONES.md`](REGISTRO_EVALUACIONES.md), [`INFORME_EVALUACION_ATLAS.md`](INFORME_EVALUACION_ATLAS.md)) |
| 2026-10-28 | **Métricas fijas sin LLM** | 0 tokens, deterministas, con IC 95 % y comparación contra la línea base; permiten medir cada cambio sin costo |
| 2026-11-01 | **Línea base sobre el corpus congelado** | Nueva referencia oficial: 52 de 65 correctas; normativa en el contexto 0 de 18 |
| 2026-11-05 → 11-06 | **Mejoras de recuperación y respuesta** | Tokenizador español, fusión ajustada, varias consultas, prioridad territorial, jerarquía normativa, prompt sin normas ausentes, saludo guiado |
| 2026-11-11 | **Gold A corregido + QA completa** | Fusión de `corpus`; ~6.000 peticiones de carga sin errores 5xx; arreglo del agotamiento del pool de conexiones |
| 2026-11-12 | **`main` al día** | Fusión del registro con tipo de usuario; arreglo de la columna `user_type` en bases existentes; comparación de modelos locales |

## 3. Cambios por componente

### Evaluación (`rag/evaluation/`)

| Archivo | Qué aporta |
|---|---|
| `ground_truth_v02.py`, `data/legal-ground-truth-v0.2.json` | Ground truth v0.2 desde el Excel del equipo jurídico, con tipo de pregunta y documentos esperados |
| `generation_cache.py` | Caché de generación reanudable: una corrida interrumpida no se repite ni se paga dos veces |
| `metricas_sin_llm.py`, `data/linea-base-sin-llm-v0.2.json` | Métricas fijas sin LLM (recuperación, citas, fuga territorial, evidencia insuficiente) con IC 95 % y línea base versionada |
| `baseline_report.py`, `registro.py`, `registro/evaluaciones.csv` | Reporte consolidado y registro versionado de cada corrida |
| `indexar_gold_local.py` | Indexa el Gold A en un ChromaDB local para medir sin tocar AWS |

### Recuperación (`rag/backend/rag/core/`)

| Archivo | Cambio | Por qué |
|---|---|---|
| `retriever.py` | Tokenizador español para BM25 (minúsculas, tildes, plurales ligeros y palabras vacías) | BM25 no emparejaba «concesión» con «concesiones» |
| `retriever.py` | Fusión RRF con c=2 y pesos 0,8 BM25 / 0,2 vectores | En este corpus jurídico el término exacto pesa más que la similitud semántica |
| `retriever.py` (`afuse_queries`), `agent.py` | Se buscan y fusionan la pregunta original, una versión autosuficiente y una enriquecida | Una sola reformulación perdía documentos que la pregunta original sí encontraba |
| `retriever.py` | Máximo un fragmento por sentencia | Una sentencia larga ocupaba los 4 lugares y dejaba fuera la norma |
| `territorio.py` (nuevo) | Prioridad territorial | Evita traer normas locales de otra ciudad |
| `retriever.py` | Jerarquía normativa (`CUPOS_NORMATIVA=1`) | Reserva un lugar para la norma (REMAC 5, Decreto 2324) antes que la jurisprudencia |

### Respuesta (`agent.py`, `prompts.py`, `domain_scope.py`)

- El prompt prohíbe nombrar normas que no estén en el contexto y ordena norma → jurisprudencia (reglas 4 y 5; las reglas 6 a 9 vienen de `corpus`).
- Respuestas guiadas sin recuperación: el saludo y las preguntas vagas reciben ejemplos y los datos que faltan (lugar, actividad, autoridad), en vez de una negativa.
- `_tidy_answer` limpia restos de plantilla en la respuesta.

### API (`rag/backend/rag/api/`)

- `auth.py`: `get_current_user` cierra la sesión tras leer el perfil. Antes retenía una conexión durante toda la consulta (LLM incluido) y con más de 15 consultas simultáneas el pool se agotaba (500 a los 30 s).
- `database.py`: `init_db` agrega las columnas opcionales nuevas del modelo a tablas existentes. Sin esto, `users.user_type` (registro con tipo de usuario) rompía el login en bases ya desplegadas.

## 4. Resultados

- **Recuperación:** ver la tabla del [resumen](#1-resumen). La normativa pasó de no llegar nunca al modelo a llegar en 8 de 18 casos.
- **Gold A corregido** (mismo código, mismo modelo): búsqueda idéntica al Gold anterior; las respuestas cambian dentro del ruido del modelo local.
- **k=6 frente a k=4:** más evidencia hacia el modelo (0,754 → 0,786; artículos esperados 0,147 → 0,206) y, con Claude como generador y juez, 16 respuestas correctas frente a 11.
- **Modelos locales para la demo:** gemma4:e4b frente a Qwen 3.5 9B. Qwen cita más normas esperadas (12,9 % frente a 4,6 %), pero responde «evidencia insuficiente» en 30 casos frente a 13.

## 5. Decisiones tomadas

| Decisión | Motivo |
|---|---|
| Medir cada cambio con métricas sin LLM antes que con RAGAS | Son gratuitas y deterministas; RAGAS queda para las corridas oficiales |
| `k=4` sigue como valor por defecto | k=6 mejora la evidencia, pero el cambio de comportamiento lo decide el equipo |
| La demo local sigue con gemma4:e4b | Qwen 3.5 deja más respuestas sin evidencia; no afecta la línea base, que usa gpt-5-nano |
| No se cambió nada de infraestructura ni de AWS | Fuera del alcance de la rama; la recomendación de backpressure queda documentada para quien despliega |
| Cambios en código de `main` (auth, base de datos) solo con prueba que falla antes y pasa después | Son arreglos de fallos reales encontrados en la QA, no cambios de diseño |

## 6. Verificación

- Suite: **1066 pruebas de backend** y **245 de frontend**; ruff, formato y mypy sin errores.
- Carga sin LLM: ~6.000 peticiones, hasta 200 simultáneas, **0 errores 5xx**; memoria estable.
- QA con LLM: validación (11/11), entradas hostiles e inyección de prompt (9/9 sin 500 ni fuga del prompt), streaming, concurrencia 4 y 8 sin errores; con 25 simultáneas, 0 errores 500 y 504 limpio al tiempo máximo.
- Sistema completo tras fusionar `main`: base existente migrada sin perder datos; registro, correo duplicado (409), login, `/auth/me` y usuarios antiguos correctos.

## 7. Limitaciones conocidas

1. **Multas y sanciones:** responden «evidencia insuficiente» por falta de cobertura en el corpus, no por el código.
2. **Preguntas de secuencia o trámite:** la respuesta omite etapas (8 casos; cifra orientativa).
3. **Falso fuera de alcance:** el caso 046 se clasifica como `out_of_scope`.
4. **Normativa:** llega en 8 de 18 casos; REMAC 5 todavía queda fuera en parte de las preguntas.
5. **Territorio:** «Playa Blanca» se asigna solo a Cartagena (también existe en Santa Marta).
6. **Carga en despliegue:** con `RAG_BACKPRESSURE_MODE=off`, las consultas que exceden la capacidad esperan hasta 280 s; activar `enforce` responde 503 de inmediato.

## 8. Informes elaborados

| Fecha | Informe |
|---|---|
| 2026-10-10 | Informe de estudio: línea base de ATLAS con RAGAS |
| 2026-10-14 | Informe de evaluación para el equipo jurídico (versión en el repo: [`INFORME_EVALUACION_ATLAS.md`](INFORME_EVALUACION_ATLAS.md)) |
| 2026-10-20 | Revisión de documentación, código y panel de administración |
| 2026-10-28 | Investigación: conversación guiada |
| 2026-11-01 | Comportamiento con el corpus congelado (línea base) |
| 2026-11-05 | Mejoras de recuperación, demo local y conversación guiada |
| 2026-11-06 | Prueba con Claude y correcciones |
| 2026-11-11 | QA completa antes del lanzamiento (carga, estrés, revisión de código) |

## 9. Cómo reproducir

- Métricas sin LLM, línea base y comparación: [`evaluation/README.md`](../evaluation/README.md).
- Comandos de evaluación, Gold local y modelos locales: [`SCRIPTS.md`](SCRIPTS.md#evaluación-del-rag).
- Arquitectura de la recuperación actual: [`ARCHITECTURE.md`](ARCHITECTURE.md).
