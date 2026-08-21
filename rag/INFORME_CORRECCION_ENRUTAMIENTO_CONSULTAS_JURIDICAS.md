# Informe — Corrección de enrutamiento de consultas jurídicas costeras

Implementa `PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md` sobre el
estado actual de la rama `v2` (posterior al commit `9c5893c`). No se hizo
`reset`, `rebase`, `commit --amend` ni `push --force`; no se reescribió
historial. **No se hizo commit ni push de este cambio** — sigue sin
confirmar, a la espera de tu autorización.

## 1. Causa corregida y política final de precedencia

**Causa raíz confirmada** (las tres señaladas en el plan, sección 4.1):

1. El fallback (`_fallback()`) solo reconocía un puñado de palabras exactas
   como señal costera fuerte (`_STRONG_SCOPE_RE`) y, si no coincidían,
   nunca llegaba a considerar la combinación de contexto costero + intención
   jurídica — por eso "mar", "embarcación", "contaminación" o "kayak" en una
   narración ciudadana no bastaban.
2. `pescadores?` no reconocía el singular `pescador` (el caso A usa "Soy
   **pescador** artesanal").
3. `_apply_domain_guard()` reemplazaba *cualquier* resultado semántico
   `in_scope` del LLM en cuanto la heurística limitada devolvía
   `out_of_scope` — sin distinguir si esa heurística tenía una razón
   explícita (intención claramente ajena) o si simplemente no reconocía las
   palabras usadas (silencio, no evidencia en contra).

Durante la implementación apareció además un **cuarto problema, en la
dirección opuesta**, no documentado explícitamente en el diagnóstico
original pero cubierto por los mismos criterios de aceptación: la vieja
`_apply_domain_guard()` también podía forzar `in_scope` sobre un
`out_of_scope` semántico *correcto* del modelo, con solo que la heurística
detectara "playa" como señal fuerte (p. ej. "Escribe un poema sobre una
playa." con el LLM ya respondiendo correctamente `out_of_scope`). La prueba
`test_domain_guard_keeps_creative_or_commercial_out_of_scope_despite_playa`
lo confirma como regresión antes del cambio.

**Política final** (implementada en `query_enricher.py`):

- **Fallback** (`_fallback()`), en orden:
  1. saludo o meta-pregunta completa sobre el asistente → `conversation`
     (ancla la expresión al inicio *y al final* de la pregunta, para no
     disparar cuando "¿Qué haces...?" es apenas el arranque de un supuesto
     jurídico más largo).
  2. intención inequívocamente ajena **sin** combinación costera+jurídica →
     `out_of_scope`.
  3. contexto costero/marítimo **y** intención jurídica, procedimental o de
     actividad regulada → `in_scope`.
  4. una sola señal (costera o jurídica, sin la otra) → `needs_clarification`.
  5. ausencia de cualquier señal pertinente → `out_of_scope`.
- **Guard** (`_apply_domain_guard()`), en orden:
  1. conversación/meta-pregunta completa fuerza `conversation`.
  2. intención explícitamente ajena (heurística) **sin** esa misma
     combinación fuerza `out_of_scope`, incluso si el modelo dijo
     `in_scope`.
  3. una heurística `in_scope` de alta confianza corrige un falso negativo
     del modelo (protección existente).
  4. si ninguna regla anterior aplicó, se conserva el resultado del modelo
     tal cual — el silencio de la heurística ya no se interpreta como
     rechazo.

Por construcción, `_fallback()` nunca marca `in_scope` solo por "playa" o
"mar" (siempre exige también señal jurídica/de actividad), así que la regla
3 del guard nunca puede forzar `in_scope` sobre un `out_of_scope` semántico
del modelo por esa única razón (criterio de aceptación 10 / plan sección
5.6.5).

Las señales se organizaron en tres familias de expresiones compiladas una
sola vez a nivel de módulo (`_COASTAL_RE`, `_LEGAL_RE`, `_OFF_TOPIC_RE`) más
un patrón específico para modales de posibilidad combinados con un verbo de
actividad (`_ACTIVITY_PERMISSION_RE`, p. ej. "puedo practicar surf"), y
cuatro funciones pequeñas y puras (`_is_meta_question`,
`_has_coastal_signal`, `_has_legal_signal`, `_has_off_topic_signal`) que
tanto `_fallback()` como `_apply_domain_guard()` reutilizan — sin duplicar
listas de señales entre ambos, sin llamadas de red ni al LLM adicionales,
sin registrar la pregunta.

## 2. Archivos modificados

Únicamente los autorizados en la sección 3 del plan:

- `backend/rag/core/query_enricher.py` — clasificador (única corrección de
  producción).
- `tests/unit/test_query_analysis.py` — pruebas de regresión del fallback y
  del guard.
- `tests/unit/test_agent_graph.py` — dos pruebas de enrutamiento completo
  con el clasificador real (sin LLM), retriever y LLM de generación
  simulados.

No se tocó ningún otro archivo. No se usaron `docs/SMOKE_TESTS.md` ni
`tests/integration/test_api_smoke.py` (opcionales, no fueron necesarios).

## 3. Pruebas nuevas y regresión que cubre cada una

En `tests/unit/test_query_analysis.py`:

- `test_scope_fallback_accepts_confirmed_false_negatives` (9 casos
  parametrizados: los dos casos completos A/B del equipo jurídico + los 7
  falsos negativos adicionales de la sección 4.2) — cubre el defecto
  original: estas consultas se clasificaban como `out_of_scope` y ahora
  deben ser `in_scope` con al menos un tipo documental.
- `test_scope_fallback_rejects_confirmed_false_positives` (5 casos: poema,
  imagen, hoteles, compra de kayak, entrenamiento de kayak) — cubre que la
  sola presencia de "playa"/"kayak" no fuerce `in_scope`.
- `test_short_meta_questions_about_the_assistant_are_conversation` (3
  casos) — protege que las meta-preguntas breves sigan siendo
  `conversation`.
- `test_legal_question_phrased_like_a_meta_question_is_not_conversation` (2
  casos: "¿Qué haces si...?", "¿Cómo ayudas a...?") — cubre específicamente
  que la forma superficial de meta-pregunta no capture un supuesto jurídico
  completo.
- `test_domain_guard_does_not_veto_a_model_in_scope_for_confirmed_cases` (
  casos A/B) — cubre que el guard no vete un `in_scope` del modelo para los
  dos casos del equipo jurídico.
- `test_domain_guard_keeps_creative_or_commercial_out_of_scope_despite_playa`
  (poema/imagen/hoteles) — cubre el falso positivo antes descrito: un
  `out_of_scope` correcto del modelo no debe convertirse en `in_scope` solo
  porque la heurística ve "playa".
- `test_domain_guard_does_not_flip_model_in_scope_when_heuristic_is_silent`
  — cubre la regla 4 del guard con una pregunta que la heurística no
  reconoce (ni señal costera ni jurídica, ni marcador ajeno): el `in_scope`
  del modelo debe conservarse intacto, incluyendo su `expanded_query`.
- `test_previously_passing_domain_questions_still_pass` — repite de forma
  agrupada las 5 preguntas de dominio y las 4 no relacionadas que ya
  pasaban antes de esta corrección, como regresión explícita.

En `tests/unit/test_agent_graph.py` (con `ENRICHMENT_ENABLED=False`, sin
ChromaDB ni Ollama):

- `test_legitimate_full_case_reaches_retrieval_exactly_once` — el caso
  completo del pescador, con el clasificador real (fallback), debe llegar a
  `in_scope` y el grafo debe invocar el retriever **exactamente una vez**.
- `test_creative_question_with_playa_does_not_reach_retrieval` — "Escribe
  un poema sobre una playa." con el clasificador real debe quedar
  `out_of_scope` y el retriever no debe invocarse en absoluto (el test falla
  si se invoca).

Todas las pruebas anteriores (82 en `tests/unit/` antes de esta corrección,
ahora con las de `test_email_race_conditions.py`/`test_rate_limit.py` de la
ronda previa: 90) se mantienen sin cambios y siguen en verde.

## 4. Resultados de validación

Fase 0 (línea base, antes de tocar código) y Fase 3 (final) dieron el mismo
resultado salvo el conteo de pruebas:

```
uv run pytest tests/unit -q     → línea base: 90 passed | final: 118 passed
uv run ruff check backend tests → All checks passed! (ambas fases)
uv run mypy backend/rag         → Success: no issues found in 25 source files (ambas fases)
git diff --check                → sin errores de espacios en blanco (ambas fases)
cd frontend
npx tsc --noEmit                → sin errores (ambas fases)
npx eslint .                    → sin errores (ambas fases)
npm run build                   → BLOQUEADO por el entorno, igual en ambas fases (ver abajo)
```

`npm run build` falla únicamente por `next/font: Failed to fetch 'Inter' from
Google Fonts` — el entorno de revisión bloquea `fonts.googleapis.com`. Es la
misma limitación ya documentada en correcciones anteriores, no introducida
por este cambio (que además no tocó el frontend en absoluto). No se modificó
ninguna fuente ni el layout para ocultarla.

28 pruebas nuevas (20 en `test_query_analysis.py`, incluyendo las
parametrizadas; 2 en `test_agent_graph.py`) se confirmaron **fallando** por
las razones esperadas contra el código anterior antes de tocar
`query_enricher.py` (Fase 1), y **pasando** después de la corrección
mínima (Fase 2) — incluida la corrección de un ajuste sobre la marcha: el
patrón jurídico `competenc\w*` (pensado para "autoridad competente")
colisionaba con "competencia" en el sentido deportivo ("competencia de
kayak"), lo que hacía que `¿Cómo entrenar para una competencia de kayak?`
saliera `in_scope` por error; se acotó a la frase exacta
`autoridad\s+competente` (ya cubierta también por `autoridad` a secas) y
la prueba pasó.

## 5. Casos funcionales — tabla de la Fase 4

**No se ejecutó ninguno contra AWS**: esta sesión no tiene autorización ni
credenciales/URL+token de un despliegue vivo para esta fase (y en el
momento de esta corrección tampoco hay navegador conectado disponible). Los
7 casos de la tabla del plan quedan pendientes de que tú los ejecutes:

| Nº | Caso | Ejecutado |
|---:|---|---|
| 1 | Caso completo del pescador | No — pendiente de entorno vivo |
| 2 | Caso completo del kayak | No — pendiente de entorno vivo |
| 3 | Competencia turística + autoridad sin responder | No — pendiente de entorno vivo |
| 4 | Poema sobre una playa | No — pendiente de entorno vivo |
| 5 | Comprar un kayak barato | No — pendiente de entorno vivo |
| 6 | Competencias de DIMAR frente a embarcaciones abandonadas | No — pendiente de entorno vivo |
| 7 | Seguimiento sin poder pagar abogado | No — pendiente de entorno vivo |

Los 9 falsos negativos y 5 falsos positivos de las secciones 4.1–4.3 del
plan, y las variantes de meta-pregunta de 5.1, sí quedan verificados
automáticamente contra el clasificador real (fallback) y contra el guard,
como se detalla en la sección 3 de este informe — eso cubre el enrutamiento
determinista; la evaluación jurídica de exactitud/suficiencia de las
respuestas sigue correspondiendo al equipo jurídico contra un entorno vivo.

## 6. Validaciones bloqueadas y motivo

- **Fase 4 (prueba funcional contra AWS)**: bloqueada por falta de
  autorización/credenciales explícitas para esta sesión, tal como exige el
  plan. Motivo exacto: no se proporcionó URL+token, y el plan prohíbe
  ejecutarla sin eso.
- **`npm run build`**: bloqueada por el bloqueo de red a
  `fonts.googleapis.com` en este entorno de revisión (no relacionado con el
  cambio; documentado, no se intentó ocultar).

## 7. `git diff --stat` y `git status --short --branch` finales

```
 rag/backend/rag/core/query_enricher.py | 199 +++++++++++++++++++++++++++------
 rag/tests/unit/test_agent_graph.py     |  73 ++++++++++++
 rag/tests/unit/test_query_analysis.py  | 185 ++++++++++++++++++++++++++++++
 3 files changed, 425 insertions(+), 32 deletions(-)
```

```
## v2...origin/v2
 M rag/backend/rag/core/query_enricher.py
 M rag/tests/unit/test_agent_graph.py
 M rag/tests/unit/test_query_analysis.py
?? rag/PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
?? rag/INFORME_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
```

(El segundo `??` es este mismo informe, escrito después de tomar la captura
de `git diff --stat`.)

## 8. Confirmación: nada tocado fuera de alcance

No se modificó AWS Academy, Ollama, ChromaDB, la colección ni las
máquinas; no se reindexó ni se tocó ingesta, capas GOLD ni respaldos; no se
cambió BM25, búsqueda vectorial, RRF, pesos, `k`, `k_candidates`, filtros
estructurales ni metadatos; no se cambió el prompt de generación jurídica,
la política de citas ni los mensajes de evidencia insuficiente; no se
modificó el frontend, contratos HTTP, esquemas de respuesta, base de datos,
autenticación, rate limiting, CORS, `MemorySaver` ni infraestructura; no se
introdujo ninguna dependencia nueva ni framework adicional de pruebas; no
se creó ninguna lista extensa de municipios/playas (solo "El Rodadero" como
única excepción auxiliar explícita del plan; "Santa Marta" no se incluyó);
no se registró ninguna pregunta, nombre, correo, token ni IP en logs
nuevos. El esquema `EnrichedQuery` no cambió, ni se añadieron rutas nuevas.

Los tres hallazgos de la sección 8 del plan (formato de citas, balance
normativa/jurisprudencia, degradación BM25/vector, visualización de
`query_route`/`enriched_query`) **no se tocaron**, tal como se indicó.

## 9. Confirmación: sin reindexación, commit ni push

No se ejecutó reindexación de ningún tipo. No se ejecutó `git add`, `git
commit` ni `git push` en ningún momento de esta corrección — los 3 archivos
existen solo como cambios sin confirmar en el árbol de trabajo (más el
propio plan y este informe, sin rastrear), listos para que decidas cuándo y
cómo confirmarlos.
