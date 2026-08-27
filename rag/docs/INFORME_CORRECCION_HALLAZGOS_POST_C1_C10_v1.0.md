# Informe de corrección de hallazgos posteriores a C1–C10 — v1.0

Ejecución del "Plan de corrección de hallazgos posteriores a C1–C10 — v1.0"
(`rag/docs/PLAN_CORRECCION_HALLAZGOS_VERIFICACION_POST_C1_C10_v1.0.md`),
producto de una revisión independiente sobre el estado `dd3b560`. Este
informe es nuevo y no reescribe el histórico de C1–C10
(`INFORME_CORRECCIONES_POST_IMPLEMENTACION_RAG_v1.0.md`).

## 1. Rama, commit inicial y commit final

- Rama: `v2` (única rama tocada).
- Commit inicial real al empezar esta ejecución: `85f8c43` (`dd3b560` —el
  commit inicial que asumía el plan— más dos commits de depuración del
  repo, ajenos a este plan y ya aplicados antes de que se entregara el
  documento del plan).
- Commit final: `e36d1aa`.
- No se hizo `push` en ningún momento.

## 2. Tabla H1–H4

| Entrega | Estado | Commit |
|---|---|---|
| H1 — fuga de recursos SSE | Aplicada | `6be63e5` |
| H2 — doble formateo del prompt | Aplicada | `1527737` |
| H3 — archivos `.env` temporales sin limpiar | Aplicada | `78701e7` |
| H4 — HyDE huérfano en Terraform + docs de CI | Aplicada | `e36d1aa` |

Las cuatro entregas se completaron; ninguna se detuvo. Cada una en un
commit independiente, en el orden del plan.

## 3. Archivos modificados por entrega

- **H1**: `rag/backend/rag/api/main.py`,
  `rag/tests/unit/test_query_stream_endpoint.py`.
- **H2**: `rag/backend/rag/core/agent.py`,
  `rag/backend/rag/core/observability.py` (solo docstring),
  `rag/tests/unit/test_agent_observability.py`.
- **H3**: `rag/tests/unit/test_config_env_resolution.py` (único archivo
  esperado por el plan; sin cambios en `backend/rag/`).
- **H4**: `rag/infrastructure/variables.tf`, `rag/infrastructure/ecs.tf`,
  `CLAUDE.md`, `rag/docs/AGENTS.md`.

## 4. Prueba roja y resultado verde (H1–H3)

- **H1** — `test_asgi_send_failure_before_first_event_releases_all_resources`:
  roja antes del fix (`assert backpressure_double.in_flight == 0` fallaba
  con `1 == 0`, lock también retenido); verde después.
- **H2** — `test_generate_node_formats_the_prompt_only_once`: roja antes del
  fix (`el prompt se formateó 2 veces, se esperaba 1`); verde después.
- **H3** — `test_minimal_env_does_not_leak_env_files_into_the_system_tmp_root`:
  roja antes del fix (`archivos .env nuevos en la raíz del tmp del sistema:
  {...}`); verde después.

## 5. Reproducción del fallo SSE antes y después (H1)

**Antes** (con el código previo a H1, ejercitando el ciclo ASGI real —
`response(scope, receive, send)` con `send` que falla al recibir
`http.response.start`, antes de que `body_iterator` se itere una sola vez):

```
assert backpressure_double.in_flight == 0
AssertionError: assert 1 == 0
```

Lock de conversación tampoco liberado (seguía en `locks._entries`).

**Después**: el mismo escenario deja `backpressure_double.in_flight == 0`,
`locks._entries == {}`, `ACTIVE_QUERIES.count == 0`, y confirma que el grafo
nunca llegó a ejecutarse (`graph_started is False`).

## 6. Confirmación de cierre de lock/slot/contador antes del primer evento

Cubierto por la prueba de la sección 5, más las 5 pruebas de regresión ya
existentes en `test_query_stream_endpoint.py` (excepción en `astream`,
cancelación tras iniciar el iterador, dos turnos concurrentes del mismo
hilo, hilos distintos en paralelo, finalización normal) — las 6 en verde
tras H1.

## 7. Confirmación de un único formateo y una única llamada LLM (H2)

`test_generate_node_formats_the_prompt_only_once` instrumenta tanto
`ChatPromptTemplate.format_messages` (síncrono) como `aformat_messages`
(asíncrono, el camino real que usa `chain.ainvoke` vía LCEL) y confirma
`calls["n"] == 1` tras el fix. Además confirma que los mensajes
efectivamente recibidos por el LLM (capturados en `_agenerate`) son
idénticos, contenido por contenido, a los usados para calcular
`full_context_chars`. La prueba preexistente
`test_full_context_size_precision_does_not_add_a_second_llm_call` sigue en
verde (una sola llamada al LLM, sin cambios).

## 8. Confirmación de limpieza automática de temporales (H3)

Antes del fix: 189 archivos `.env` de 0 bytes acumulados directamente en la
raíz del directorio temporal del sistema (`/tmp`) durante esta sesión de
trabajo, ninguno borrado por el código de pruebas. Después del fix: una
corrida completa de `test_config_env_resolution.py` (27 pruebas) no agrega
ningún archivo nuevo a la raíz del sistema (`before == after == 0`,
verificado explícitamente); los archivos ahora viven dentro del `tmp_path`
que administra `pytest` por prueba.

## 9. Resultado exacto de pytest, cobertura, Ruff, formato y mypy

Desde `rag/`, sin `.env` del proyecto (`RAG_ENV_FILE` apuntando a un
archivo vacío temporal, sin conexión a servicios externos):

```
uv run pytest tests/unit/ -p no:cacheprovider
======================= 486 passed, 1 warning in ~20s ========================

uv run pytest tests/unit/ --cov=rag --cov-report=term-missing
======================= 486 passed, 2 warnings in ~26s ========================
TOTAL                                      2046    435    79%

uv run ruff check backend/rag/ tests/ evaluation/
All checks passed!

uv run ruff format --check backend/rag/ tests/ evaluation/
72 files already formatted

uv run mypy backend/rag/
Success: no issues found in 28 source files
```

El único warning recurrente (`StarletteDeprecationWarning` sobre `httpx`
con `TestClient`) es preexistente y ajeno a este plan.

486 = 483 (línea base previa) + 1 (H1) + 1 (H2) + 1 (H3). H4 no agregó
pruebas (cambio de Terraform + documentación, sin código Python).

## 10. Resultado de `terraform fmt -check`

No se ejecutó: `terraform` no está instalado en este entorno y, por
restricción explícita del plan, no se instaló. Se revisó a mano que la
alineación de columnas del bloque `environment` en `ecs.tf` sigue siendo
consistente tras eliminar la línea de `QUERY_ENRICHMENT_HYDE` (el nombre
más largo que fija el ancho de columna, `QUERY_ENRICHMENT_ENABLED`, sigue
presente sin cambios).

## 11. Confirmación de que prompts, clasificador, banco jurídico, retrieval, API y SSE no cambiaron

- `rag/backend/rag/core/prompts.py` — sin diff en esta serie de commits.
- `query_enricher.py` (reglas, regex, señales, precedencias) — sin diff.
- Banco jurídico de 21 preguntas — no tocado, no existe en el árbol de
  `rag/backend/rag/`.
- Pesos BM25/vector, RRF, `k`, `k_candidates`, filtros de recuperación,
  topología LangGraph — sin diff (`retriever.py`, la topología de
  `build_graph()` en `agent.py` no cambió, solo el cuerpo interno de
  `generate_node`).
- Reglas de citas/abstención (`_validate_citations`, `_INVALID_CITATIONS_RESPONSE`) — sin diff.
- `context_tokens` — sin diff en `api/main.py::_estimate_context_tokens`; H2
  no lo toca (deriva de `state["messages"]`, no de `full_context_chars`).
- Campos, códigos HTTP y estructura pública de `/api/query` y
  `/api/query/stream`, nombres/orden/forma de los eventos SSE — sin
  cambios; H1 solo envuelve la respuesta en una subclase privada de
  `StreamingResponse` que preserva exactamente el mismo comportamiento
  ASGI observable, y las 6 pruebas de forma de eventos siguen en verde.
- `RAG_BACKPRESSURE_MODE` sigue en `off` por defecto (`.env.example` sin
  diff en esta serie).

## 12. Lista de commits

```
6be63e5 fix(H1): cerrar recursos SSE aunque falle el envío ASGI antes del primer evento
1527737 fix(H2): formatear el prompt de generación una sola vez
78701e7 fix(H3): no dejar archivos .env temporales sueltos tras las pruebas
e36d1aa fix(H4): eliminar QUERY_ENRICHMENT_HYDE huérfano en Terraform, alinear docs de CI con v2
```

(Precedidos, en la misma rama pero fuera del alcance de este plan, por
`69c3a4f` y `85f8c43` — depuración de archivos residuales del repo,
solicitada y aplicada por separado antes de recibir este plan.)

## 13. Confirmación explícita

- No se accedió a AWS, Chroma, Ollama, S3 ni proveedores LLM reales.
- No se ejecutó `terraform init/plan/apply/destroy` ni ningún comando
  contra infraestructura real.
- No se reindexó ningún documento ni se ejecutó el pipeline de ingesta.
- No se actualizó ninguna dependencia ni se modificó `uv.lock`.
- No se hizo `push` en ningún momento; todos los commits quedaron locales
  en `v2` hasta ser sincronizados al equipo del usuario por el mecanismo ya
  establecido (bundle de git), sin publicarlos a `origin`.

## 14. Definición de terminado (§12 del plan)

Todos los criterios de la sección 12 del plan se cumplen: fallo ASGI antes
del primer evento libera todos los recursos SSE; caminos de éxito, error y
cancelación siguen en verde; el prompt se formatea una sola vez y el LLM se
invoca una sola vez; la métrica conserva sus claves (`full_context_chars`,
`full_context_tokens_est`) y su docstring ahora describe con precisión qué
mide; las pruebas de configuración no dejan archivos temporales sueltos;
Terraform ya no presenta HyDE como opción operativa inexistente; la
documentación de CI incluye `v2`; todas las pruebas y controles estáticos
pasan; no se modificó comportamiento jurídico ni contrato público; no hubo
acceso a servicios reales, reindexación, actualización de dependencias ni
push.
