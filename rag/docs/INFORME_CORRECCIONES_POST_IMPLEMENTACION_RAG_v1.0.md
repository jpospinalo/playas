# Informe final — Plan de correcciones posteriores a la implementación del módulo RAG v1.0

**Fecha:** 2026-08-27
**Rama:** `v2` (única rama usada, por instrucción explícita del usuario)
**Commit inicial (línea base, C0):** `82b55af` — "docs(rag): informe final del implementador (§15/§16 del plan T0–T4)"
**Commit final:** `bb4065f` — "C10: retirar código y config muerta demostrable (balance_by_doc_type, QUERY_ENRICHMENT_HYDE, DEFAULT_K*)"
**Commits nuevos de este plan:** 10 (uno por entrega, `341e275`..`bb4065f`)
**Estado del repo:** `v2` queda 31 commits por delante de `origin/v2`. **Ningún `git push` fue realizado en ningún momento de esta ejecución** — instrucción explícita del usuario: el push lo hace él manualmente.
**Sincronización:** los 10 commits se transfirieron a la máquina del usuario (`~/Desktop/playas/playas`, rama `v2`) mediante un bundle de git (`git bundle create` → `SendUserFile` → `device_commit_files` → `git fetch`/`merge --ff-only` en la máquina del usuario). El merge fue fast-forward puro (`82b55af..bb4065f`), sin conflictos ni cambios locales que resolver. Ambos lados (sandbox y máquina del usuario) están en el mismo commit `bb4065f`.

---

## 1. Resumen ejecutivo

Se ejecutaron las 10 entregas (C1–C10) del "Plan de correcciones posteriores a la implementación del módulo RAG v1.0", cada una con TDD estricto: test que reproduce el defecto (rojo, confirmado por la razón esperada) → arreglo mínimo → pruebas objetivo en verde → suite completa + `ruff check` + `ruff format --check` + `mypy` en verde → revisión de diff para confirmar que no hay cambios fuera de alcance → commit independiente. **Ninguna entrega se agrupó con otra.**

**Las 10 entregas se completaron.** Ninguna quedó detenida ni diferida — no se presentó ninguna de las condiciones de parada del §8 del plan (cambio de prompts/clasificación, banco de 21 preguntas, contrato público/SSE, significado de `context_tokens`, acceso a infraestructura real, reindexación, actualización de dependencias compartidas, debilitamiento de una expectativa funcional, cambio de topología del grafo, o cambios locales detectados en archivos que el plan necesitaba tocar).

Todas las restricciones del §2 del plan se respetaron: solo rama `v2`; sin push; sin cambiar HTTP a HTTPS ni exigir certificados; sin acceso a AWS/Chroma/Ollama reales; sin scripts contra hosts remotos; sin crear/borrar/recrear colecciones de Chroma; sin reindexar; sin cambiar modelos de embeddings, dimensiones ni formato de vectores; sin modificar `rag/core/prompts.py`; sin modificar las reglas/regex/señales/precedencia del clasificador en `query_enricher.py`; sin modificar el banco de 21 preguntas ni debilitar sus expectativas; sin cambiar pesos BM25/vector, RRF, `k`, `k_candidates`, filtros `doc_type`, reglas de citación ni respuestas de abstención; sin cambiar nodos/aristas/rutas de LangGraph; sin cambiar campos/tipos/nombres/códigos HTTP ni estructura pública de `/api/query` y `/api/query/stream`; `RAG_BACKPRESSURE_MODE=off` se mantiene por defecto; `OllamaReranker` se conserva; sin actualizar dependencias de LangChain/RAGAS/Chroma/Ollama; `ingesta/` no se tocó.

---

## 2. Tabla de estado

| Entrega | Estado | Commit |
|---|---|---|
| C1 — Orden y autoridad de configuración (`DATABASE_URL`/`JWT_ALGORITHM`/`JWT_EXPIRE_MINUTES`) | ✅ Completada | `341e275` |
| C2 — Hermeticidad de `test_config_env_resolution.py` frente a un `.env` real | ✅ Completada | `ac6ba81` |
| C3 — Ciclo de vida de `ConversationLockRegistry` | ✅ Completada | `ccc9d71` |
| C4 — Orden lock-antes-que-backpressure en `/api/query` y `/api/query/stream` | ✅ Completada | `5bf4749` |
| C5 — Cobertura real del endpoint SSE (concurrencia/errores/cancelación) | ✅ Completada | `e66fc7b` |
| C6 — Salir del bucle de reintentos de `vectorstore.py` tras éxito | ✅ Completada | `b703aa2` |
| C7 — Romper dependencia invertida `core.generator` → `api.main` | ✅ Completada | `0fcb779` |
| C8 — Precisar `log_full_context_size` sin tocar la API pública | ✅ Completada | `ff3c362` |
| C9 — Coherencia (readiness/.env.example/SCRIPTS.md/CI/informe previo) | ✅ Completada | `2e8c880` |
| C10 — Retirar código/config muerta demostrable | ✅ Completada | `bb4065f` |

Ninguna entrega quedó **detenida** ni **diferida**.

---

## 3. Detalle por entrega

### C1 — Orden y autoridad de configuración

**Defecto:** `api/database.py` y `api/auth.py` leían `DATABASE_URL`/`JWT_ALGORITHM`/`JWT_EXPIRE_MINUTES` con `os.getenv()` a nivel de módulo. `api/rate_limit.py` importa `api/auth.py` (que importa `api/database.py`) antes de importar `rag.config` — si algo dispara esa cadena antes de que `rag.config` ya se hubiera importado (como ocurre en el punto de entrada real, `rag.api.main`), esos valores quedaban fijados al `os.environ` de ese momento, sin el `.env` resuelto por `RAG_ENV_FILE`.

**Test rojo:** `tests/unit/test_config_import_order.py` (nuevo) — importa `rag.api.main` en un subproceso limpio con `RAG_ENV_FILE` apuntando a un `.env` temporal con valores no-default. Confirmado en rojo: `DATABASE_URL` resolvía al default de sqlite en vez del valor del `.env`; `JWT_ALGORITHM`/`JWT_EXPIRE_MINUTES` resolvían a `'HS256'`/`'10080'` en vez de `'HS512'`/`'42'`. (`REGISTER_ENABLED` se verificó NO estar realmente roto — se centralizó de todos modos, por consistencia, con equivalencia demostrada por el mismo test.)

**Fix:** `database.py`, `auth.py` y `routes/auth.py` ahora importan estas constantes desde `rag.config` (que ya centraliza la resolución de `.env`) en vez de leer `os.getenv()` directamente. `JWT_SECRET_KEY` se deja fuera a propósito: ya se lee de forma perezosa dentro de una función, evaluada por request, no al importar.

**Test verde:** los 5 tests de `test_config_import_order.py` pasan.

**Archivos:** `api/auth.py`, `api/database.py`, `api/routes/auth.py`, `config.py`, `tests/unit/test_config_import_order.py` (nuevo).

---

### C2 — Hermeticidad de `test_config_env_resolution.py`

**Defecto:** `_minimal_env()` no fijaba `RAG_ENV_FILE` a un archivo vacío propio — si un desarrollador tenía un `rag/.env` real con sus propios valores, la resolución de `config.py` (que busca `.env` en el cwd o en la raíz del workspace cuando `RAG_ENV_FILE` no está definida) podía leerlo por accidente, contaminando el resultado del test.

**Test rojo:** se creó temporalmente un `rag/.env` real en el sandbox (nunca antes presente, gitignorado, borrado antes de commitear) con valores marcadores distintivos (`CHROMA_COLLECTION=contaminacion_primaria`, etc.). Confirmado en rojo: 4 tests fallaron por leer esos valores contaminantes en vez de los que el test esperaba.

**Fix:** `_minimal_env()` genera un `.env` vacío temporal propio (`tempfile.mkstemp`) y lo asigna a `RAG_ENV_FILE` por defecto, garantizando que ningún `.env` real del desarrollador pueda influir en el resultado salvo que el test lo pida explícitamente.

**Test verde:** los 4 tests afectados pasan, con y sin un `rag/.env` real presente en disco.

**Archivos:** `tests/unit/test_config_env_resolution.py`.

---

### C3 — Ciclo de vida de `ConversationLockRegistry`

**Defecto:** `lock_for()` entregaba el `asyncio.Lock` crudo desde un `defaultdict` que nunca eliminaba claves — el registro crecía con el total histórico de conversaciones distintas procesadas por el proceso, nunca se reducía, pese a que su propio docstring afirmaba lo contrario.

**Test rojo:** la clase `ConversationLockRegistry` original no exponía `_entries`/`hold()`/`_reserve()`/`_release()` — un test escrito contra la API nueva fallaba con `AttributeError` al no existir esos métodos, confirmando la ausencia estructural del ciclo de vida.

**Fix:** se reemplaza `lock_for()` por `hold(key)`, un `@asynccontextmanager` que cuenta referencias (titular + quienes esperan) bajo un lock de registro de corta duración (nunca retenido durante un `await` de negocio) y elimina la entrada del diccionario en cuanto el conteo llega a cero, con comparación por identidad para evitar una carrera con una entrada reemplazada.

**Test verde:** 3 tests preexistentes (T3.5, sin cambios de comportamiento) + 3 tests nuevos (registro vacío tras 200 claves secuenciales; limpieza tras excepción dentro de `hold()`; limpieza tras cancelar una tarea que esperaba el lock) — los 6 pasan.

**Archivos:** `api/conversation_lock.py` (reescritura completa), `api/main.py` (adapta la llamada de `lock_for()` a `hold()`), `tests/unit/test_conversation_lock.py`.

---

### C4 — Orden lock-antes-que-backpressure

**Defecto:** ambos endpoints adquirían primero el slot global de backpressure y solo después esperaban el lock de su conversación. Una segunda solicitud de una conversación con un turno ya en curso reservaba un slot global solo por esperar su propio lock — sin hacer ningún trabajo real — restándole capacidad a conversaciones independientes.

**Test rojo:** `test_lock_before_backpressure.py` (nuevo), con capacidad global = 2 y un retriever deliberadamente bloqueado por un `asyncio.Event` de la prueba: una segunda consulta de la misma conversación A, seguida de una consulta de una conversación B independiente. Confirmado en rojo: B recibía `HTTPException(503)` aunque solo había un turno real en proceso.

**Fix:** en `/api/query` y `/api/query/stream`, el lock de conversación se adquiere primero y el slot de backpressure después, consistentemente en ambos endpoints (evita también un riesgo de deadlock por orden inconsistente). Si backpressure rechaza tras adquirir el lock, la salida del `async with` (o el `except BaseException` del `AsyncExitStack` en el endpoint SSE) lo libera de inmediato.

**Test verde:** los 3 tests de `test_lock_before_backpressure.py` pasan (equidad para `/api/query`, liberación inmediata del lock ante rechazo, y equidad para `/api/query/stream`).

**Archivos:** `api/main.py`, `tests/unit/test_lock_before_backpressure.py` (nuevo).

---

### C5 — Cobertura real del endpoint SSE

**Defecto:** `test_main_backpressure.py` afirmaba en su docstring cubrir el wiring de `ConcurrencyBackpressure` en **ambos** endpoints, pero ninguna de sus pruebas llamaba jamás a `query_stream` — solo a `query`.

**Test rojo:** no aplica un "defecto" de comportamiento (el código ya era correcto desde T3.5/T3.6/C3/C4) — es un hueco de cobertura. Se confirmó por inspección directa del archivo que ningún test ejercitaba `/api/query/stream`.

**Fix:** cobertura pura, sin cambios de producción. `test_main_backpressure.py` gana las dos pruebas que su propio docstring ya afirmaba tener (503 antes de construir el stream en modo enforce; comportamiento inalterado en modo off). `test_query_stream_endpoint.py` (nuevo) cubre: mismo hilo sin intercalado (checkpoint final con ambos turnos completos), hilos distintos en paralelo, excepción real en `graph.astream` → evento SSE de error existente + liberación de lock/slot/contador, cancelación de la tarea que consume el iterador a mitad de stream → misma liberación, y finalización normal con el formato de eventos exacto (`status* → token* → sources → [DONE]`, claves de cada tipo).

**Test verde:** los 7 tests nuevos/extendidos pasan.

**Archivos:** `tests/unit/test_main_backpressure.py`, `tests/unit/test_query_stream_endpoint.py` (nuevo). **Ningún archivo de producción tocado.**

---

### C6 — Bucle de reintentos de `vectorstore.py`

**Defecto:** `for attempt in range(MAX_RETRIES): try: ... except Exception: ...` en `build_or_load_vectorstore()` nunca hacía `break` tras un intento exitoso — solo salía del `for` al agotar los 3 intentos. Un batch exitoso en el primer intento se re-embebía (Ollama) y se reenviaba (`collection.add`) hasta 2 veces más, en silencio.

**Test rojo:** `test_vectorstore_retry.py` (nuevo), con dobles locales de Chroma/Ollama (sin red real). Confirmado en rojo: éxito en el primer intento → 3 llamadas a embed y a add (se esperaba 1).

**Fix:** se añade la cláusula `else` de `try/except` (se ejecuta solo cuando el `try` no lanzó, nunca durante un reintento) con un único `break` — el único punto de salida por éxito.

**Test verde:** éxito en el primer intento → exactamente 1 llamada a cada uno; 2 fallos + éxito al tercer intento → exactamente 3 llamadas, recuperación correcta; fallo persistente → `RuntimeError` tras exactamente `MAX_RETRIES` intentos. Los 3 tests pasan.

**Archivos:** `core/vectorstore.py`, `tests/unit/test_vectorstore_retry.py` (nuevo).

---

### C7 — Dependencia invertida `core.generator` → `api.main`

**Defecto:** `rag.core.generator` (adaptador explícitamente pensado para uso offline, sin servidor) importaba `_extract_answer_from_state` desde `rag.api.main` — forzando la carga completa de FastAPI, todos los routers y la base de datos async solo por una función pura.

**Test rojo:** `test_generator_no_api_dependency.py` (nuevo) — `import rag.core.generator` en un subproceso limpio. Confirmado en rojo: `'rag.api.main' in sys.modules` y `'fastapi' in sys.modules` daban `True`.

**Fix:** la función se mueve a `rag.core.agent` como `extract_answer_from_state` (pública, tipada, misma implementación); tanto `api.main` (con alias `_extract_answer_from_state` para no tocar sus dos sitios de llamada) como `core.generator` la importan desde ahí.

**Test verde:** ambos tests del archivo nuevo pasan; los 3 tests preexistentes de `test_core_generator.py` (comportamiento de `generate_answer`) siguen en verde sin cambios.

**Archivos:** `api/main.py`, `core/agent.py`, `core/generator.py`, `tests/unit/test_generator_no_api_dependency.py` (nuevo).

---

### C8 — Precisión de `log_full_context_size`

**Defecto:** la métrica interna T3.7 aproximaba el tamaño sumando `len(BASE_INSTRUCTIONS) + len(context) + len(question)` por separado — ignorando todo el texto literal del propio `ChatPromptTemplate` (etiquetas `<context>`/`<question>`, recordatorio de citación, y en el caso sin system role el envoltorio `"INSTRUCCIONES:\n...\n\n"`).

**Test rojo:** `test_agent_observability.py` (extendido) compara el valor logueado contra una referencia calculada formateando el mismo `ChatPromptTemplate` (`prompt.format_messages(...)`, templating local, sin red). Confirmado en rojo: 3906 vs 4145 caracteres esperados (con system role), 3908 vs 4164 (sin system role).

**Fix:** `generate_node` formatea el mismo `ChatPromptTemplate` que ya construye y cuenta los caracteres de los mensajes ya formateados — sin una segunda llamada al LLM, sin tocar `context_tokens`/`context_limit`, sin modificar `prompts.py`.

**Test verde:** ambas pruebas de precisión pasan exactamente; se añaden pruebas confirmando que no se añade una segunda llamada al LLM y que el texto de pregunta/documentos sigue sin aparecer en el log.

**Archivos:** `core/agent.py`, `tests/unit/test_agent_observability.py`.

---

### C9 — Coherencia (documentación/configuración)

No aplica TDD (son correcciones de documentación/configuración, no de comportamiento):

- Docstring de `/api/ready`: documenta que ninguno de los tres chequeos llama a Chroma/Ollama en el momento de la consulta — reflejan estado tomado una sola vez en el `lifespan` de arranque. Sin cambio de JSON, código HTTP ni lógica.
- `.env.example`: añade `RAG_BACKPRESSURE_MODE`/`RAG_BACKPRESSURE_MAX_CONCURRENT` (antes ausentes), documenta `RAG_ENV_FILE` (sin inventar una ruta real), aclara la sección del reranker sin inventar una URL.
- `docs/SCRIPTS.md`: corrige el ejemplo de `chroma_clear.py` (`--collection` es obligatorio, `--execute` es obligatorio para borrar de verdad — el ejemplo anterior habría fallado con argparse) y añade `--url` (obligatorio) al ejemplo de `load_test.py` en la tabla resumen.
- `.github/workflows/ci.yml`: añade `v2` a los triggers de push (rama de integración activa confirmada: `origin/v2` existe, el último merge a `main` fue un PR desde `v2`).
- `rag/docs/INFORME_FINAL_IMPLEMENTACION_T0_T4.md`: corrige el conteo de entregas (era "16/14", no coincidía con su propia lista de etiquetas — son 19 entregas, 17 completas + T4.2 parcial), el conteo de commits (20 → 21, faltaba contar el commit del informe mismo), y marca T4.2 como parcial (el `ModuleNotFoundError` se corrigió, pero la incompatibilidad `ragas`/`langchain-community` documentada en su propia §4.3 sigue sin resolverse). Corrección con nota visible, no reescritura silenciosa.

**Archivos:** `.github/workflows/ci.yml`, `rag/.env.example`, `api/main.py` (solo docstring), `docs/INFORME_FINAL_IMPLEMENTACION_T0_T4.md`, `docs/SCRIPTS.md`.

---

### C10 — Retirar código/config muerta demostrable

**Verificación de "código muerto" (búsqueda global inmediatamente antes de eliminar):**
- `balance_by_doc_type()` (`core/retriever.py`) — único consumidor en todo el repo: `tests/unit/test_retriever_balance.py`, dedicado exclusivamente a probarla. Sin caller real en `api/`, `core/` ni `evaluation/`.
- `QUERY_ENRICHMENT_HYDE` (`config.py`) — sin ningún lector en todo el repo.
- `DEFAULT_K` / `DEFAULT_K_CANDIDATES` (`config.py`) — sin ningún consumidor; el `k`/`k_candidates` reales vienen del `QueryRequest` de la API y de los defaults inline de `agent.py::retrieve_forced_node`.

**Test rojo:** `test_retriever_no_dead_code.py` (extendido) y `test_config_no_dead_code.py` (nuevo) — `hasattr(módulo, nombre)` daba `True` para los cuatro símbolos antes de eliminarlos.

**Fix:** se elimina la función y las tres constantes, junto con `test_retriever_balance.py` (que dejó de tener sujeto) y las referencias en `.env.example`. **Explícitamente NO tocados:** `OllamaReranker` (documentado como opcional, uso intencional), `enrich_query()` síncrono, adaptadores de embeddings, funciones de indexado, `QUERY_ENRICHMENT_ENABLED` (sí tiene consumidor real — se prueba explícitamente que sigue expuesta).

**Test verde:** los `hasattr` dan `False` tras la eliminación; el caso positivo de `QUERY_ENRICHMENT_ENABLED` confirma que no se arrastró por error.

**Archivos:** `.env.example`, `config.py`, `core/retriever.py`, `tests/unit/test_config_no_dead_code.py` (nuevo), `tests/unit/test_retriever_balance.py` (eliminado), `tests/unit/test_retriever_no_dead_code.py`.

---

## 4. Verificación final (§7)

Ejecutado sobre el commit final `bb4065f`:

| Verificación | Resultado |
|---|---|
| `pytest tests/unit/` (sin `.env` real) | **483 passed** |
| `pytest tests/unit/` (con un `.env` real presente, valores marcadores) | **483 passed** (idéntico resultado — confirma la hermeticidad de C2 en ambos sentidos) |
| `pytest tests/unit/` — repetido 2 veces más para descartar flakiness | 483 passed en cada corrida |
| `ruff check backend/rag/ tests/ evaluation/` | All checks passed |
| `ruff format --check backend/rag/ tests/ evaluation/` | 72 files already formatted |
| `mypy backend/rag/` | Success: no issues found in 28 source files |
| Liberación de lock/slot/contador tras cancelación SSE | Confirmado — `test_closing_the_iterator_early_releases_all_resources` (C5): tras cancelar la tarea que consume el iterador con el retriever bloqueado, `backpressure.in_flight == 0`, `locks._entries == {}`, `ACTIVE_QUERIES.count == 0` |
| Un batch de vectorización exitoso corre exactamente una vez | Confirmado — `test_successful_batch_is_embedded_and_added_exactly_once` (C6): 1 llamada a embed, 1 llamada a `add()` |
| `rag/core/prompts.py` | Sin diff alguno desde el commit base (`git diff 82b55af..HEAD` vacío) |
| `rag/core/query_enricher.py` (reglas/regex/señales/precedencia del clasificador) | Sin diff alguno desde el commit base |
| `tests/unit/test_query_analysis.py` (banco de 21 preguntas) | Sin diff alguno desde el commit base |
| Topología de LangGraph (`agent.py::build_graph`, nodos/aristas) | Sin diff alguno en las líneas de `add_node`/`add_edge`/`add_conditional_edges`/`.compile(` |
| Contrato de `api/schemas.py` (`QueryRequest`/`QueryResponse`/`SourceGroup`/`SourceFragment`) | Sin diff alguno desde el commit base |
| Decoradores de ruta / `response_model` / `status_code` en `api/main.py` | Sin diff alguno desde el commit base |
| Pesos BM25/vector, RRF, `k_candidates` en `core/retriever.py` | Sin diff alguno (más allá de la eliminación de `balance_by_doc_type` en C10) |
| Defaults de rate-limit/backpressure (`mode="off"`, `max_concurrent=20`) | Sin cambio — verificado en `rate_limit.py` y `config.py` |
| `ingesta/` | Sin ningún archivo tocado (`git diff --stat` vacío) |
| Acceso a infraestructura real (AWS/Chroma/Ollama) | Ninguno — todas las pruebas usan dobles locales (fakes/monkeypatch), sin red real |
| Reindexación de documentos | Ninguna |

### Higiene de git (§7.4)

- Solo se tocaron archivos dentro de `rag/` y el workflow de CI en la raíz (`.github/workflows/ci.yml`, autorizado explícitamente por C9).
- Exactamente **1 commit por entrega** — 10 commits, ninguno agrupa más de una entrega.
- **Ningún `git push`** se ejecutó en ningún momento — ni en el sandbox ni en la máquina del usuario.
- Ningún `.env`, `.venv`, caché, token ni credencial se commiteó — el `.env` temporal creado para reproducir C2 se borró antes de cualquier `git add`/`commit`, y `.env*` está gitignorado salvo `.env.example`.

---

## 5. Trabajo explícitamente diferido (fuera de alcance de este plan)

Según el §6 del plan de correcciones, **no se tocó**:

- T3.3 (acotar ventana de historial SQL) ni T3.4 (reducir autoridad de `MemorySaver`).
- El significado/definición de `context_tokens`.
- Actualización de versiones de RAGAS/LangChain.
- Creación de ground-truths legales para evaluación.
- Migración de `/api/embeddings` a `/api/embed` por lotes.
- Reindexación de documentos.
- Modificación de máquinas/contenedores/modelos de AWS Academy.
- Pruebas de carga contra hosts remotos.
- Cambio de HTTP a HTTPS.
- Recalibración de prompts, clasificador, retrieval o citaciones.
- La incompatibilidad de dependencias `ragas`/`langchain-community` (documentada, no resuelta — ver corrección de T4.2 en C9).

---

## 6. Commits creados

```
341e275 C1: centralizar DATABASE_URL/JWT_ALGORITHM/JWT_EXPIRE_MINUTES en rag.config
ac6ba81 C2: aislar test_config_env_resolution.py de un rag/.env real
ccc9d71 C3: ciclo de vida administrado en ConversationLockRegistry
5bf4749 C4: adquirir el lock de conversación antes que el slot de backpressure
e66fc7b C5: cubrir /api/query/stream con pruebas reales de concurrencia, errores y liberación de recursos
b703aa2 C6: salir del bucle de reintentos de vectorstore.py tras un add() exitoso
0fcb779 C7: mover _extract_answer_from_state de api.main a core.agent (pública)
ff3c362 C8: log_full_context_size mide el prompt de generación realmente formateado
2e8c880 C9: coherencia — readiness, .env.example, SCRIPTS.md, CI y el informe previo
bb4065f C10: retirar código y config muerta demostrable (balance_by_doc_type, QUERY_ENRICHMENT_HYDE, DEFAULT_K*)
```

Todos en `v2`, sincronizados también a la máquina del usuario (`~/Desktop/playas/playas`, fast-forward `82b55af..bb4065f`, sin conflictos).

**Confirmación explícita: no se realizó ningún `git push` durante la ejecución de este plan**, ni desde el sandbox ni desde la máquina del usuario. El push queda pendiente de que el usuario lo haga manualmente, como en la fase anterior.

---

## 7. Definición de terminado (§10)

- [x] Las 10 entregas (C1–C10) implementadas, cada una con test rojo→verde propio (o cobertura confirmada donde no había un defecto de comportamiento — C5, C9) y commit independiente.
- [x] Ninguna entrega agrupada con otra.
- [x] Suite completa (483 tests), ruff y mypy en verde sobre el estado final de `v2`.
- [x] Suite completa en verde con y sin un `.env` real presente.
- [x] Banco de 21 preguntas, `prompts.py` y `query_enricher.py` sin ningún diff desde el commit base.
- [x] Ningún contrato público, código HTTP, campo de `/api/query`/`/api/query/stream`, ni topología de LangGraph modificados.
- [x] Liberación de lock/slot/contador confirmada tras cancelación del stream SSE.
- [x] Un batch de vectorización exitoso confirmado en exactamente 1 intento (embed + add).
- [x] Sin acceso a infraestructura real ni reindexación en ningún punto.
- [x] `ingesta/` sin tocar.
- [x] Todo el trabajo vive en `v2`, sincronizado a la máquina del usuario (commit `bb4065f` en ambos lados).
- [x] Sin push al remoto — pendiente de que el usuario lo haga manualmente.
- [x] Trabajo diferido documentado explícitamente (§5 de este informe), sin quedar como un olvido.
