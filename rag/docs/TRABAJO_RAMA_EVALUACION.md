# ATLAS — Trabajo de la rama de evaluación y recuperación

| | |
|---|---|
| **Autor** | Julian Esteban Rincón Rodríguez |
| **Periodo** | 2026-10-08 → 2026-11-21 |
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
| 2026-11-16 | **Resolución documental de `corpus`** | Fusión de los commits de `corpus` del 2026-11-15 y 16 (hasta 3260bba: REMAC 5 en alcance, radicados parciales, orden de recuperación del predio, instancia verificada, plazos y remisiones citados, citas JSON/SSE, hidratación en frío); convivencia con la multiconsulta; compatibilidad comprobada con la rama de ingesta y su evaluación de nivel 0 |
| 2026-11-21 | **Contexto normativo verificado de `corpus`** | Fusión de `corpus` hasta 5665e4f (admisión normativa, aclaración ante «ese plan», citas por norma fuente, contexto normativo verificado, sesiones entre pestañas, cierre SSE, siglas en el enriquecimiento); convive con la multiconsulta, la jerarquía normativa y el tope por norma |
| 2026-11-21 | **Mantenimiento adaptativo** | Parámetros de recuperación por entorno, listas fijas contrastadas con la capa gold, métricas «antes/después» y `scripts/integrar_corpus.sh` para el próximo update; Python 3.12 fijado; trazas de la multiconsulta |

## 3. Cambios por componente

### Evaluación (`rag/evaluation/`)

| Archivo | Qué aporta |
|---|---|
| `ground_truth_v02.py`, `data/legal-ground-truth-v0.2.json` | Ground truth v0.2 desde el Excel del equipo jurídico, con tipo de pregunta y documentos esperados |
| `generation_cache.py` | Caché de generación reanudable: una corrida interrumpida no se repite ni se paga dos veces |
| `metricas_sin_llm.py`, `data/linea-base-sin-llm-v0.2.json` | Métricas fijas sin LLM (recuperación, citas, fuga territorial, evidencia insuficiente) con IC 95 % y línea base versionada |
| `baseline_report.py`, `registro.py`, `registro/evaluaciones.csv` | Reporte consolidado y registro versionado de cada corrida |
| `indexar_gold_local.py` | Indexa el Gold A en un ChromaDB local para medir sin tocar AWS |
| `metricas_sin_llm.py` (2026-11-21) | Cada reporte guarda colección, modelo de embeddings y parámetros de recuperación, y avisa si la referencia es de otro corpus; `--linea-base` acepta el reporte de otra corrida (antes/después) y `--fallar-si-regresion` sale con 1; la clase del documento esperado sale del `doc_type` de la capa gold |

### Recuperación (`rag/backend/rag/core/`)

| Archivo | Cambio | Por qué |
|---|---|---|
| `retriever.py` | Tokenizador español para BM25 (minúsculas, tildes, plurales ligeros y palabras vacías) | BM25 no emparejaba «concesión» con «concesiones» |
| `retriever.py` | Fusión RRF con c=2 y pesos 0,8 BM25 / 0,2 vectores | En este corpus jurídico el término exacto pesa más que la similitud semántica |
| `retriever.py` (`afuse_queries`), `agent.py` | Se buscan y fusionan la pregunta original, una versión autosuficiente y una enriquecida | Una sola reformulación perdía documentos que la pregunta original sí encontraba |
| `retriever.py` | Máximo un fragmento por sentencia | Una sentencia larga ocupaba los 4 lugares y dejaba fuera la norma |
| `territorio.py` (nuevo) | Prioridad territorial | Evita traer normas locales de otra ciudad |
| `retriever.py` | Jerarquía normativa (`CUPOS_NORMATIVA=1`) | Reserva un lugar para la norma (REMAC 5, Decreto 2324) antes que la jurisprudencia |
| `agent.py` (fusión con `corpus`) | Con radicado verificado se usa la consulta compuesta y la selección verificada de `corpus`; el resto, `afuse_queries` | La resolución documental elige los fragmentos de una sola sentencia; las demás preguntas conservan la recuperación multiconsulta |
| `config.py`, `retriever.py` (2026-11-21) | `RRF_C`, pesos, cupos de normativa y topes por sentencia y por norma se leen de `RAG_*` con los valores medidos por defecto | Re-medirlos tras un update del corpus sin tocar código (ver [§9](#9-cómo-reproducir)) |
| `retriever.py` (`afuse_queries`, 2026-11-21) | Abre su propia ejecución de recuperador y pasa callbacks hijos a cada búsqueda | La multiconsulta queda en las trazas igual que `ainvoke` |
| `tools.py` (fusión con `corpus`) | Con identidad verificada se omite también la línea «Radicado» de la metadata | Mismo objetivo que `corpus`: no reintroducir radicados históricos en el contexto |

### Respuesta (`agent.py`, `prompts.py`, `domain_scope.py`)

- El prompt prohíbe nombrar normas que no estén en el contexto y ordena norma → jurisprudencia (reglas 4 y 5; las reglas 6 a 9 vienen de `corpus`).
- Respuestas guiadas sin recuperación: el saludo y las preguntas vagas reciben ejemplos y los datos que faltan (lugar, actividad, autoridad), en vez de una negativa.
- `_tidy_answer` limpia restos de plantilla en la respuesta.

### API (`rag/backend/rag/api/`)

- `auth.py`: `get_current_user` cierra la sesión tras leer el perfil. Antes retenía una conexión durante toda la consulta (LLM incluido) y con más de 15 consultas simultáneas el pool se agotaba (500 a los 30 s).
- `database.py`: `init_db` agrega las columnas opcionales nuevas del modelo a tablas existentes. Sin esto, `users.user_type` (registro con tipo de usuario) rompía el login en bases ya desplegadas.

### Mantenimiento

- `scripts/integrar_corpus.sh`: integra el próximo update de `corpus` y reporta diferencias (ver [§9](#9-cómo-reproducir)).
- `tests/unit/test_recuperacion_adaptativa.py`: los parámetros por entorno y una prueba que recorre la capa gold y exige que toda norma de ámbito local (distrito, municipio, balneario…) tenga lugar en `territorio.LUGARES`. Si Juan agrega la norma de una ciudad nueva, la prueba dice qué añadir en vez de que la prioridad territorial la ignore en silencio.
- `.python-version` (3.12) en `rag/` e `ingesta/`, como CI y las imágenes Docker: con 3.14 fallan 27 pruebas de `test_chroma_snapshot_export.py`.
- `test_corpus_deploy_contract.py`: los dobles de `git` y `python` ya no dependen del shebang, que no admite rutas con espacios.

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
| La resolución documental queda como la deja `corpus` (apagada por defecto) | Su activación en despliegue la decide el equipo; aquí solo se verificó que convive con la recuperación de la rama |
| Se protege con una prueba de contrato lo que la ingesta y el nivel 0 usan del RAG | Otros módulos del repositorio importan el retriever directamente; un cambio de firma los rompería sin aviso |
| Parámetros por entorno, sin auto-ajuste | Cambiar la recuperación sigue siendo una decisión medida; el entorno solo evita tocar código para medir y aplicar el cambio |
| Comparar antes contra después de cada update, no contra cifras fijas | La línea base versionada es de otro corpus y otra caché; antes y después en la misma sesión de ChromaDB aíslan el efecto del update (y el ruido de HNSW entre reinicios) |
| Las listas que dependen del corpus se prueban contra la capa gold | Fallan con un mensaje que dice qué añadir cuando el corpus cambia, en vez de degradar la recuperación sin aviso |

## 6. Verificación

- Suite (2026-11-21, `scripts/integrar_corpus.sh --solo-verificar`): **1679 pruebas de backend**, **322 de frontend** y **1360 de ingesta** (11 omitidas) más 2 contratos entre etapas; ruff, formato, mypy, lint, tsc y build sin errores. También en una ruta con espacios.
- Mantenimiento adaptativo (2026-11-21): métricas sin LLM idénticas a las del 19-nov con la caché de gemma4 (`acierto_doc_4` 0,741, `acierto_doc_4_multi` 0,776, `acierto_doc_4_grafo` 0,684, fuga territorial 0, referencias sin respaldo 1 de 65, fuga de plantilla 0). API local con gemma4: `tests/integration` 3/3, conversación guiada 8/8 escenarios (aclaración en el primer turno y 4 fuentes en el segundo; el saludo solo recibe la guía) y SSE hasta `[DONE]`. El ciclo de integración se probó en una copia aparte con un update simulado que bajaba los cupos de normativa a 0: el script fusionó, la suite falló en la prueba del valor por defecto, y las métricas antes/después marcaron `acierto_doc_4` 0,741 → 0,724 (peor en margen) con el aviso de parámetros distintos.
- Fusión con `corpus` hasta `5665e4f` (2026-11-21): la selección de contexto normativo verificado va antes del híbrido y, si no selecciona, recupera la multiconsulta de esta rama; la aclaración pide el plan o la norma sin perder los tres datos y los ejemplos; los sub-recuperadores reciben los callbacks de corpus sin perder `_gather_cancelling`. La fusión automática había movido la guarda de sesión de `signIn` a `signUp` en `AuthProvider`; se restauró en ambos. Métricas sin LLM idénticas a las del tope por norma (0,741 / 0,776 / 0,684, fuga 0). API local con gemma4: `tests/integration` 3/3, conversación guiada 8/8 escenarios y SSE hasta `[DONE]`. Suite: 1658 de backend, 322 de frontend.
- Fusión con `corpus` hasta `b4346fc` (2026-11-19): consultas a Chroma acotadas, borrado de conversaciones coordinado con las consultas activas y embeddings cancelables. La recuperación multiconsulta de esta rama adopta la misma cancelación (`_gather_cancelling`).
- Tope de un fragmento por norma (2026-11-19): ruta de producción `acierto_doc_4` 0,741 → 0,776 con la caché nueva de gemma4; `acierto_doc_4_grafo` 0,561 → 0,684; `fuga_plantilla` 0,215 → 0; referencias sin respaldo 3 → 1 de 65; jurisprudencia y fuga territorial sin cambio. Suite: 1409 pruebas de backend.
- Fusión con `corpus` (2026-11-16): recuperación idéntica a la de la rama (0,741, fuga 0); API de punta a punta 15/15 con la resolución encendida; infraestructura validada en un emulador local de AWS (con la opción apagada, la tarea lleva `REGISTER_ENABLED`; encendida, además las dos variables de procedencia). Preguntas de radicado reales: 6 de 8 resueltas con cita textual y 2 controles rechazados.
- Compatibilidad con la rama de ingesta (fusión de prueba, no versionada): las funciones del RAG que usa siguen intactas y su nivel 0 mejora con el retriever de esta rama (`document_hit@4` 0,725 → 0,975).
- Carga sin LLM: ~6.000 peticiones, hasta 200 simultáneas, **0 errores 5xx**; memoria estable.
- QA con LLM: validación (11/11), entradas hostiles e inyección de prompt (9/9 sin 500 ni fuga del prompt), streaming, concurrencia 4 y 8 sin errores; con 25 simultáneas, 0 errores 500 y 504 limpio al tiempo máximo.
- Sistema completo tras fusionar `main`: base existente migrada sin perder datos; registro, correo duplicado (409), login, `/auth/me` y usuarios antiguos correctos.

## 7. Limitaciones conocidas

1. **Multas y sanciones:** responden «evidencia insuficiente» por falta de cobertura en el corpus, no por el código.
2. **Preguntas de secuencia o trámite:** la respuesta omite etapas (8 casos; cifra orientativa).
3. **Falso fuera de alcance:** el caso 046 se clasifica como `out_of_scope`.
4. **Normativa:** llega en 8 de 18 casos; REMAC 5 todavía queda fuera en parte de las preguntas.
5. **Territorio:** «Playa Blanca» se asigna solo a Cartagena (también existe en Santa Marta).
6. **Resolución documental:** solo se activa con la forma «¿qué ordenó/resolvió/decidió en … instancia … en el radicado …?»; 2 de 8 preguntas reales no se resuelven aunque el radicado se encuentra.
7. **Carga en despliegue:** con `RAG_BACKPRESSURE_MODE=off`, las consultas que exceden la capacidad esperan hasta 280 s; activar `enforce` responde 503 de inmediato.

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

### Correr todo

Python 3.12 (`.python-version`), uv y Bun. Desde la raíz del repo, en la rama de integración y con el árbol limpio:

```bash
scripts/integrar_corpus.sh --solo-verificar   # rag, frontend, ingesta y métricas sin LLM
scripts/integrar_corpus.sh --solo-verificar --sin-metricas   # sin ChromaDB ni Ollama
```

Pasos sueltos: `cd rag && UV_FROZEN=1 make quality` (ruff, formato, mypy, pytest, lint, tsc, vitest y build) y, en `ingesta/`, `make lint format-check test test-integration`. Las métricas sin LLM necesitan un ChromaDB con el Gold A (`CHROMA_HOST`, `CHROMA_PORT`; la colección por defecto es la publicada en `scripts/corpus_release.sh`) y Ollama con `embeddinggemma` (`OLLAMA_BASE_URL`). La caché de generación para las métricas de la ruta de producción es `CACHE_METRICAS` o la más reciente de `rag/evaluation/results/`.

### Integrar el próximo update de `corpus`

```bash
export CHROMA_HOST=localhost CHROMA_PORT=8001 OLLAMA_BASE_URL=http://localhost:11434
scripts/integrar_corpus.sh
```

1. Descarga `origin/corpus` y lista los commits nuevos y los archivos que cambian ambos lados (donde hay que mirar la fusión: hoy `agent.py`, `retriever.py`, `prompts.py`).
2. Guarda la rama en `respaldo-local/integracion-antes-corpus-<fecha>` y mide las métricas sin LLM **antes**.
3. Fusiona (`merge: corpus hasta <commit>`). Si hay conflictos se detiene y los lista: resolverlos, hacer commit y volver a correr con `--solo-verificar` (o `git merge --abort`).
4. Corre rag, frontend e ingesta, y mide las métricas **después** contra las de antes, en la misma sesión de ChromaDB. Cualquier `REGRESIÓN` hace salir con 1; los casos que cambian están en el reporte `.md`.
5. Si el update publica otra colección Gold (`CORPUS_RELEASE_COLLECTION`), avisa: hay que restaurarla en el ChromaDB local ([`data/chroma-releases/README.md`](../../data/chroma-releases/README.md)) y volver a medir.

No hace push ni toca `main` ni `corpus`. Lo que queda a mano: revisar los conflictos, decidir si una regresión se acepta y, si se acepta un cambio de comportamiento, `--guardar-linea-base` y actualizar las cifras de este documento.

### Qué es configurable

| Variable | Defecto | Qué controla |
|---|---:|---|
| `RAG_RRF_C` | 2 | Constante de la fusión RRF |
| `RAG_BM25_WEIGHT` / `RAG_VECTOR_WEIGHT` | 0,8 / 0,2 | Peso de cada lista en la fusión |
| `RAG_CUPOS_NORMATIVA` | 1 | Puestos del top-k reservados a normas aplicables |
| `RAG_FRAGMENTOS_POR_SENTENCIA` | 1 | Fragmentos por sentencia antes del recorte (0 = sin tope) |
| `RAG_FRAGMENTOS_POR_NORMA` | 1 | Fragmentos por norma antes del recorte (0 = sin tope) |

Los valores por defecto son los medidos sobre el ground truth v0.2 (la medición de cada uno está junto a su uso en `core/retriever.py`). Un valor inválido detiene el arranque nombrando la variable. Para re-medir uno: `RAG_CUPOS_NORMATIVA=2 uv run python -m evaluation.metricas_sin_llm --tag cupos2 --linea-base evaluation/results/metricas-sin-llm-v0.2-<referencia>.json` desde `rag/`. `k` y `k_candidates` siguen llegando por la API (4 y 8).

Lo que no es configurable pero se contrasta con el corpus en las pruebas: los lugares de las normas locales (`core/territorio.py`), el tipo de los documentos esperados del ground truth (capa gold) y los títulos que mapea el ground truth. Las frases de la métrica `fuga_plantilla` ya se derivan del prompt.

### Cifras vigentes (2026-11-21)

| Indicador | Valor |
|---|---:|
| `acierto_doc_4` (pregunta original) | 0,741 |
| `acierto_doc_4_multi` (ruta de producción, caché gemma4) | 0,776 |
| `acierto_doc_4_grafo` | 0,684 |
| Fuga territorial | 0 |
| Respuestas con referencias sin respaldo | 1 de 65 |
| Pruebas: backend / frontend / ingesta | 1679 / 322 / 1360 |

### Más detalle

- Métricas sin LLM, línea base y comparación: [`evaluation/README.md`](../evaluation/README.md).
- Comandos de evaluación, Gold local y modelos locales: [`SCRIPTS.md`](SCRIPTS.md#evaluación-del-rag).
- Arquitectura de la recuperación actual: [`ARCHITECTURE.md`](ARCHITECTURE.md).
