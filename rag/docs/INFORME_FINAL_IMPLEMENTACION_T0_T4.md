# Informe final del implementador — Plan técnico inmediato del módulo RAG v1.3

**Fecha:** 2026-08-27
**Rama:** `v2` (todos los cambios, pasados y futuros de esta implementación, viven aquí — instrucción explícita del usuario)
**Estado del repo:** 21 commits locales por delante de `origin/v2` en el momento de cerrar este informe (el commit extra frente a la cifra citada más abajo en el cuerpo del informe es este mismo documento). **Ningún push realizado** — el usuario indicó explícitamente que el push lo haría manualmente él mismo ("Por ahora no hagas push solo commits. El push lo haré manual").
**Alcance ejecutado:** T0 → T4.3, más este informe. T4.2 quedó **parcial** (el import roto se corrigió, pero la incompatibilidad `ragas`/`langchain-community` sigue sin resolver — ver §4.3). T3.3 y T3.4 quedaron **detenidos deliberadamente** (ver §3).

> **Corrección (C9, plan de correcciones posteriores v1.0):** esta sección y las
> §1, §5 y §6 originales contaban "16 entregas" con "14 completadas" y
> reportaban T4.2 como completa sin matiz. El conteo correcto es **19
> entregas** (T0 · T1.1–T1.3 · T2.1–T2.5 · T3.1–T3.7 · T4.1–T4.3 = 1+3+5+7+3)
> con **17 completadas** (19 − T3.3 − T3.4 pendientes) — la cifra "16/14"
> original no coincidía con su propia lista de etiquetas. Además, T4.2 solo
> resolvió el `ModuleNotFoundError` de los scripts de evaluación; la
> incompatibilidad real de dependencias (`ragas`/`langchain-community`,
> documentada en §4.3) sigue sin resolverse, así que T4.2 se marca **parcial**,
> no completa. El conteo de commits ("20 por delante de `origin/v2`") tampoco
> incluía el commit del informe mismo — con él, eran 21. Los valores
> corregidos se aplican también más abajo, en el cuerpo original del informe.

---

## 1. Resumen ejecutivo

Se implementó el plan técnico v1.3 sobre el módulo `rag/` del repositorio `playas`, entrega por entrega, con TDD estricto (test que reproduce el defecto → arreglo → suite completa en verde) y un commit independiente por entrega. Cada commit pasó, antes de considerarse cerrado:

- Suite completa de tests unitarios (`pytest tests/unit/`) en verde.
- `ruff check` y `ruff format --check` en verde sobre los archivos tocados (y, en las entregas de limpieza de T4, sobre el árbol completo).
- `mypy` en verde sobre los módulos de `core/`/`api/` tocados (y, desde T4.1, sobre todo `backend/rag/`).
- El banco de 21 preguntas (`tests/unit/test_query_analysis.py::BANCO_21_PREGUNTAS`) intacto — nunca se tocaron sus expectativas ni su contenido.
- Sin cambios a prompts, lógica de clasificación, umbrales de evidencia/citación, contratos públicos de la API, LangGraph (su estructura de nodos/aristas) ni al frontend.
- Sin escritura real en Chroma, sin acceso a infraestructura real (AWS/Ollama en producción), sin reindexación de datos.

De las **19 entregas** del plan (T0, T1.1–T1.3, T2.1–T2.5, T3.1–T3.7, T4.1–T4.3 = 1+3+5+7+3), **17 se completaron** y **1 quedó parcial (T4.2**, por la incompatibilidad de dependencias documentada en §4.3, no por decisión de alcance). **T3.3 y T3.4 quedaron pendientes por decisión explícita del usuario**, tras detectarse un conflicto genuino de diseño que el propio plan identifica como condición de parada (§3).

---

## 2. Entregas completadas

### T0 — Preparación, línea base y prueba de carga segura
- `bd07a6a` — Endurecimiento de `scripts/load_test.py`: sin URL de producción hardcodeada (ahora `--url` es obligatorio), confirmación explícita para apuntar a un host remoto (escribir el host exacto), credencial JWT obligatoria (`RAG_LOAD_TEST_TOKEN` o `--token`, con `--allow-unauthenticated` para el caso excepcional), y corrección de la etiqueta "primer token" (el backend no hace streaming incremental real — se renombró a "primera fracción de respuesta").

### T1 — Estabilidad básica
- `768a6b9` (T1.1) — Eliminado un error 500 determinístico en consultas largas.
- `b9f2428` (T1.2) — Contrato unitario de embeddings verificado con test dedicado.
- `fa438a5` (T1.3) — Salvaguardas en `utils/chroma_count.py` / `utils/chroma_clear.py` (scripts operativos que tocan la colección real) para evitar operaciones destructivas accidentales.

### T2 — Calidad de recuperación y configuración
- `8cc69c3` (T2.1) — Colección vacía ya no produce evidencia ficticia (BM25 sobre corpus vacío).
- `19780f2` (T2.2) — BM25 excluye puntajes exactamente cero (ausencia de señal real, no relevancia marginal).
- `9bbf283` (T2.3) — Inventario y resolución centralizada de variables de entorno en `config.py`, con alias legados preservados.
- `82d7339` (T2.4) — Migración efectiva de `retriever.py`, `vectorstore.py`, `embeddings.py` y los scripts de Chroma a la configuración centralizada (dejó de haber lecturas de `os.getenv` dispersas fuera de `config.py`).
- `af7cc50` (T2.5) — Nuevo endpoint `GET /api/ready` (readiness real: verifica conexión a la base de datos con timeout, distinto de `/api/health` que es solo liveness).

### T3 — Estado, eficiencia y límites (parcial — ver §3 para T3.3/T3.4)
- `103c710` (T3.1) — Módulo `core/observability.py`: `stage_timer` (latencia por etapa del grafo), `log_citation_format_error`, `ActiveQueryTracker` (gauge de consultas activas), `log_retained_conversations` (cuántas conversaciones retiene `MemorySaver`). Regla estricta respetada en todo el módulo y sus llamadores: nunca se loguea texto de la pregunta, contenido de documentos, tokens ni identificadores reales de usuario/conversación — solo conteos y enums cerrados.
- `992969d` (T3.2) — Eliminado un `ThreadPoolExecutor` anidado dentro de `HybridEnsembleRetriever`: la concurrencia entre BM25 y el retriever vectorial ahora se resuelve con una sola capa (`asyncio.gather` + `asyncio.to_thread`), sin cambiar el resultado fusionado (mismo RRF, mismos pesos, mismo `max_results`).
- `c295e32` (T3.3) — **Detenida**, documentada en `rag/docs/T3.3_HISTORIAL_SQL.md` (ver §3).
- `5d1080f` (T3.5) — `ConversationLockRegistry`: un `asyncio.Lock` por `thread_id`, creado bajo demanda. Se **demostró necesario primero**, no se implementó por precaución: un test de interleaving real reprodujo una pérdida silenciosa de mensajes cuando dos turnos concurrentes comparten una misma conversación (`MemorySaver` no serializa escrituras concurrentes al mismo `thread_id`). El fix serializa solo por conversación — conversaciones distintas siguen procesándose en paralelo sin esperarse entre sí (verificado con un test dedicado).
- `8e9047c` (T3.6) — `ConcurrencyBackpressure`: límite de concurrencia global de proceso (no por usuario/IP como el rate limiter existente), mismo idioma `off/observe/enforce` que `SlidingWindowRateLimiter`, responde 503 (no 429, porque es saturación de capacidad del servidor, no abuso de un cliente). Por defecto `off` — sin cambio de comportamiento hasta activarlo explícitamente con `RAG_BACKPRESSURE_MODE`.
- `4eb13d6` (T3.7) — `log_full_context_size`: métrica interna (solo logs, nunca expuesta por la API) del tamaño real del prompt de generación (instrucciones + contexto recuperado + pregunta). Deliberadamente independiente del campo público `context_tokens` (que mide el historial en `state["messages"]`, calculado en `api/main.py`) — probado explícitamente que no lo lee, no lo escribe, y no varía con el tamaño del historial de conversación.

### T4 — Simplificación segura
- `1335730` (T4.1a) — Formato mecánico (`ruff format`) de 4 archivos pendientes de una línea base anterior, incluido el archivo del banco de 21 preguntas — se verificó **programáticamente** (comparación byte a byte de las constantes antes/después) que el contenido del banco no cambió, solo se retiraron paréntesis redundantes de sintaxis.
- `bb1d9de` (T4.1b) — `ci.yml` y `tests.yml` ejecutaban exactamente los mismos tests por paquete; se confirmó la duplicación y se fusionaron en `ci.yml` (que además ya encadenaba tests detrás de lint, un comportamiento más correcto), preservando el cache de `uv` y las opciones de cobertura de `tests.yml`. `tests.yml` se eliminó.
- `4f322dc` (T4.1c) — `mypy` habilitado en CI **solo para `rag/`** (0 errores verificados en 28 archivos de `backend/rag/`). **No** se habilitó para `ingesta/`, que tiene 5 errores preexistentes ajenos a este plan (ver §4).
- `6c013be` (T4.2 — **parcial**, ver corrección C9 al inicio del informe) — Los scripts `evaluation/ragas_eval_gemma.py` y `evaluation/ragas_eval_ollama.py` importaban `rag.core.generator.generate_answer`, un módulo que ya no existía (huérfano desde la migración del agente al grafo único de `core/agent.py`) — fallaban con `ModuleNotFoundError` antes de poder ejecutarse. Se restauró `core/generator.py` como adaptador delgado que invoca el mismo `build_graph()` que sirve `/api/query` (sin tocar el grafo), con un `thread_id` efímero por llamada. También se limpiaron comentarios de cabecera obsoletos ("TODO: cambiar a playas, actualmente poe"). `scripts/load_test.py` (ya endurecido en T0) se verificó sin cambios. **Esto corrigió el `ModuleNotFoundError`, pero no deja los scripts de evaluación ejecutables de punta a punta**: la incompatibilidad real de dependencias `ragas`/`langchain-community` (§4.3) sigue sin resolverse, así que esta entrega se marca parcial, no completa.
- `28eca22` (T4.3) — Eliminada `demo()` de `core/retriever.py` (código muerto demostrable: cero llamadores reales, no documentada en ningún script/Makefile/doc mantenido). `OllamaReranker` se **conservó deliberadamente** — ver §4.

---

## 3. T3.3 y T3.4 — detenidos por decisión explícita del usuario

**T3.3** (acotar la ventana de historial SQL que se inyecta al rehidratar una conversación tras un reinicio del servidor) reveló un conflicto genuino durante la investigación, documentado en detalle en [`rag/docs/T3.3_HISTORIAL_SQL.md`](./T3.3_HISTORIAL_SQL.md):

Acotar esa ventana cambiaría, en un caso de borde específico, el valor reportado del campo público `context_tokens` (que se calcula a partir de `state["messages"]`, la misma estructura que alimentaría el acotamiento). Esto entra en conflicto directo con el mandato explícito de T3.7 de no alterar el significado ni el valor de `context_tokens`, y con la prohibición general del plan de tocar contratos públicos de la API sin ambigüedad.

El plan mismo establece como condición de parada para esta entrega: *"detener si no se puede demostrar equivalencia"*. No se pudo demostrar. Se presentaron tres caminos posibles (documentados en el archivo enlazado) y se escaló la decisión al usuario mediante una pregunta directa. El usuario eligió explícitamente: **dejar T3.3 (y T3.4, que depende de su resolución) pendientes, documentar el hallazgo, y continuar con T3.5–T3.7 y T4**, que es exactamente lo que se hizo.

**T3.4** (reducir la autoridad/alcance de `MemorySaver`) no se abordó porque el plan la condiciona al resultado de T3.3.

**Recomendación:** retomar T3.3 solo cuando alguien con autoridad sobre el contrato público de la API decida explícitamente si `context_tokens` puede/debe cambiar de definición, o si el acotamiento del historial SQL debe excluirse deliberadamente del cálculo de `context_tokens` (lo cual es técnicamente posible pero es una decisión de producto/contrato, no una implementación mecánica).

---

## 4. Decisiones de alcance documentadas (no son omisiones)

Estas tres cosas se identificaron durante el trabajo y **deliberadamente no se tocaron**, porque hacerlo habría excedido el alcance autorizado o requerido un juicio de valor que el plan reserva para quien lo apruebe:

1. **`ingesta/` sin mypy en CI.** Tiene 5 errores preexistentes (`boto3`/`botocore` sin stubs de tipos, dos problemas de tipos genuinos en `pdf_to_md/images.py` y `splitter_and_enrich.py`). Es un paquete y un `uv` workspace completamente distinto del módulo RAG — corregirlos habría sido trabajo fuera del plan. Documentado en `CLAUDE.md` y en el propio `ci.yml`.

2. **`OllamaReranker` conservado en `core/retriever.py`.** A diferencia de `demo()` (que sí se eliminó en T4.3), esta clase está documentada en `CLAUDE.md`/`AGENTS.md` como reranker opcional respaldado por infraestructura Terraform real (un modelo de Ollama aprovisionado para ese fin). Su no-uso en el flujo principal ya estaba comentado como decisión deliberada en `config.py` antes de esta entrega — no se pudo demostrar que fuera código muerto en el mismo sentido que `demo()`, así que se dejó intacta.

3. **Incompatibilidad de dependencias en `ragas`.** Al intentar ejecutar los scripts de `evaluation/` de punta a punta (más allá de la corrección del import roto en T4.2), se encontró que `ragas==0.4.3` falla al importar por una incompatibilidad con `langchain-community==0.4.2` (`ChatVertexAI` se movió/eliminó de `langchain_community.chat_models.vertexai`). Es un problema de versiones preexistente, no introducido por este trabajo, y corregirlo requeriría fijar versiones de dependencias compartidas con el resto del grupo `dev` — una decisión que excede "limpieza de referencias rotas". Queda documentado aquí para que se aborde como su propia tarea si se decide usar esos scripts.

---

## 5. Verificación final

Ejecutado inmediatamente antes de este informe, sobre el estado final de `v2` (commit `28eca22`):

| Verificación | Resultado |
|---|---|
| `pytest tests/unit/` | **455 passed** |
| `ruff check backend/rag/ tests/ evaluation/` | All checks passed |
| `ruff format --check backend/rag/ tests/ evaluation/` | 67 files already formatted |
| `mypy backend/rag/` | Success: no issues found in 28 source files |
| Banco de 21 preguntas | Contenido verificado idéntico byte a byte tras el único cambio que lo tocó (formato) |
| Cambios a prompts/clasificación/LangGraph/contratos públicos/frontend | Ninguno |
| Escrituras/reindexación en Chroma real | Ninguna |
| `git push` | Ninguno realizado — 21 commits locales por delante de `origin/v2` (incluyendo este informe), el usuario hará el push manualmente |

---

## 6. Definición de terminado

- [x] T0, T1.1–T1.3, T2.1–T2.5, T3.1, T3.2, T3.5, T3.6, T3.7, T4.1, T4.3 implementados, cada uno con test rojo→verde propio y commit independiente.
- [~] T4.2 implementada solo parcialmente: corrigió el `ModuleNotFoundError` de los scripts de evaluación, pero la incompatibilidad `ragas`/`langchain-community` (§4.3) sigue sin resolver.
- [x] T3.3/T3.4 detenidos explícitamente por el usuario, con el hallazgo documentado (`T3.3_HISTORIAL_SQL.md`) y no perdido.
- [x] Suite completa, ruff y mypy en verde sobre el estado final de `v2`.
- [x] Banco de 21 preguntas preservado sin cambios de contenido ni de expectativas.
- [x] Ningún contrato público, prompt, umbral de evidencia/citación o nodo de LangGraph modificado.
- [x] Sin acceso a infraestructura real ni escrituras en Chroma.
- [x] Todo el trabajo vive en `v2`, sincronizado también a la máquina del usuario (commit `28eca22` en ambos lados).
- [x] Sin push al remoto — pendiente de que el usuario lo haga manualmente.
- [ ] T3.3/T3.4 — pendientes de una decisión de producto/contrato sobre `context_tokens` para poder retomarse (ver §3).
- [ ] Incompatibilidad `ragas`/`langchain-community` — pendiente si se decide volver a usar `evaluation/ragas_eval_*.py` (ver §4.3).

---

## 7. Próximos pasos sugeridos (no ejecutados — requieren decisión de quien apruebe el plan)

1. Decidir el destino de T3.3/T3.4 (§3): ¿puede `context_tokens` cambiar de definición, o debe el acotamiento de historial excluirse deliberadamente de ese cálculo?
2. Si se van a usar los scripts de `evaluation/` en la práctica, fijar versiones compatibles de `ragas`/`langchain-community` (o downgrade/upgrade coordinado) — trabajo de dependencias, no de este plan.
3. Si en algún momento se decide que `ingesta/` también debe tener mypy en CI, corregir sus 5 errores preexistentes como tarea propia (fuera del módulo RAG).
4. Revisar si `OllamaReranker` sigue teniendo sentido operativo (la infraestructura Terraform que lo respalda existe) o si conviene formalizar su retiro — es una decisión de producto, no de este plan de limpieza.
