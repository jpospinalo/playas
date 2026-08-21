# Informe — Corrección posterior mínima (defectos #1 a #5)

Fecha: 2026-08-21
Rama: `v2` (sin commit ni push, sin reindexación)
Base: implementación vigente al cierre de la ronda anterior
("Revisión posterior con el banco completo de preguntas jurídicas").

## 1. Alcance de esta ronda

Se corrigieron únicamente los cinco defectos confirmados, reutilizando las
mismas familias de señales ya existentes (`_COASTAL_RE`, `_LEGAL_RE`,
`_OFF_TOPIC_RE`, `_CAPABILITIES_RE`, `_ACTIVITY_PERMISSION_RE`). No se
revirtió nada del trabajo anterior, no se tocó retrieval, generación,
citaciones, prompts de generación, frontend, API, datos ni infraestructura.
Único archivo de producción modificado: `backend/rag/core/query_enricher.py`.

## 2. Cambios por defecto

**Defecto #1 — intenciones inequívocamente ajenas no deben ganar por mencionar
términos jurídicos costeros.** Se dividió el antiguo `_OFF_TOPIC_RE` en dos
regex: `_UNAMBIGUOUS_OFF_TOPIC_RE` (generar imágenes, poemas, programar
software/código) y `_OFF_TOPIC_RE` (señales "blandas": receta/cocinar,
comprar, entrenar, aprender a usar, precios de inmuebles, recomendar
hoteles, capital de, resultado de fútbol, etc., que sí pueden ceder ante una
combinación costera+jurídica). `_fallback()` ahora evalúa la señal
inequívoca ANTES que nada (incluso antes del saludo/meta-pregunta) y fuerza
`out_of_scope` sin excepción. `_apply_domain_guard()` hereda este
comportamiento sin cambios propios: como la heurística ya no es `in_scope`
para estos casos, la regla existente ("intención ajena sin combinación
fuerza out_of_scope, aunque el modelo diga in_scope") ahora también cubre
las intenciones inequívocas, y de paso nunca convierte un `out_of_scope`
correcto del modelo en `in_scope`.

**Defecto #2 — reevaluar la intención jurídica tras heredar contexto
costero del historial.** Al heredar `coastal = True` desde el historial, se
recalcula `legal = _has_legal_signal(clean_question, coastal=True)`. Antes,
`legal` quedaba fijado con `coastal=False`, lo que impedía que
`_ACTIVITY_PERMISSION_RE` (que solo cuenta con contexto costero ya
confirmado) reconociera un seguimiento como "¿Y puedo realizar el evento
mientras deciden?".

**Defecto #3 — restringir `norma\w*`.** Se sustituyó por
`normas?|normativ\w*`, que reconoce "norma", "normas", "normativa",
"normativo" y "normatividad", pero ya no "normal" ni "normalmente" (el
límite de palabra `\b...\b` impide que cualquiera de las dos ramas se
extienda dentro de esas palabras).

**Defecto #4 — no tratar automáticamente nave/kayak/moto acuática/muelle
como contexto costero en entornos ajenos.** Estos cuatro términos se
movieron de `_COASTAL_RE` a una nueva `_AMBIGUOUS_COASTAL_RE`. Se agregó
`_INLAND_OR_UNRELATED_CONTEXT_RE` (lago, represa, río, piscina, espacial).
`_has_coastal_signal()` ahora solo cuenta un término ambiguo como costero
si la consulta NO contiene también una de esas palabras de entorno; un
término inequívocamente costero (playa, mar, DIMAR, etc.) sigue contando
siempre. No se agregó ninguna lista de lugares.

**Defecto #5 — restaurar "¿Cómo ayudas?" / "¿Cómo me ayudas?" como
`conversation`.** Se agregó la alternativa `c[oó]mo\s+(?:me\s+)?ayudas` a
`_CAPABILITIES_RE`. El anclaje `^...$` que ya tenía el regex sigue evitando
que dispare sobre un supuesto jurídico más largo que empiece igual (p. ej.
"¿Cómo ayudas a exigir que retiren una embarcación?").

## 3. Pruebas nuevas agregadas (`tests/unit/test_query_analysis.py`)

- `test_scope_fallback_rejects_unambiguous_off_topic_even_with_legal_coastal_terms`
  (4 casos): poema/imagen/programar software con normativa/permisos/DIMAR ⇒
  `out_of_scope`, `doc_types == []`.
- `test_domain_guard_does_not_let_model_force_in_scope_for_unambiguous_off_topic`
  (2 casos): simula al LLM devolviendo `in_scope` para esos mismos casos;
  el guard debe corregir a `out_of_scope`.
- `test_domain_guard_does_not_flip_a_correct_model_out_of_scope_to_in_scope`
  (2 casos): simula al LLM acertando con `out_of_scope`; el guard no debe
  convertirlo en `in_scope`.
- `test_follow_up_after_coastal_history_reevaluates_legal_intent`: caso
  exacto del defecto #2 ("¿Y puedo realizar el evento mientras deciden?"
  tras historial de evento en playa) ⇒ `in_scope`.
- `test_legal_regex_still_matches_norma_family` (4 casos) y
  `test_legal_regex_does_not_match_normal_or_normalmente` (2 casos):
  control positivo/negativo del defecto #3.
- `test_scope_fallback_does_not_force_in_scope_for_inland_or_unrelated_context`
  (5 casos): kayak en lago, muelle en represa, nave en río, moto acuática
  en piscina, nave espacial — ninguno debe llegar a `in_scope`.
- `test_short_how_do_you_help_questions_are_conversation` (2 casos) y
  `test_long_legal_question_starting_like_how_do_you_help_is_not_conversation`:
  control positivo/negativo del defecto #5.
- `test_cooking_and_selling_on_a_beach_without_permit_stays_in_scope`:
  control de regresión explícito exigido por esta ronda.
- `test_banco_21_preguntas_siguen_in_scope_tras_la_correccion_posterior`
  (21 casos parametrizados, reutilizando `BANCO_21_PREGUNTAS` ya existente):
  control de no regresión de las 21 preguntas jurídicas.

Total de pruebas nuevas: 45 (216 en la suite completa, antes 171).

## 4. Resultados de validación

```
uv run pytest tests/unit -q
216 passed in 5.28s   (171 previos + 45 nuevos, todos en test_query_analysis.py)

uv run ruff check backend tests
All checks passed!

uv run mypy backend/rag
Success: no issues found in 25 source files

frontend: ./node_modules/.bin/tsc --noEmit
sin errores

frontend: ./node_modules/.bin/eslint .
sin errores

frontend: npm run build
Falla únicamente por bloqueo de red hacia fonts.googleapis.com (Geist Mono,
Inter) — limitación de red de este entorno, no relacionada con esta ronda;
el frontend no fue tocado.

git diff --check (en el repositorio del dispositivo)
(sin salida — sin errores de espacios en blanco), exit code 0
```

## 5. Estado de git en el dispositivo

```
git status --short --branch
## v2...origin/v2
 M rag/backend/rag/core/query_enricher.py
 M rag/tests/unit/test_agent_graph.py
 M rag/tests/unit/test_query_analysis.py
?? rag/INFORME_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
?? rag/INFORME_CORRECCION_POSTERIOR_DEFECTOS_1_A_5.md
?? rag/INFORME_REVISION_BANCO_21_PREGUNTAS.md
?? rag/PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md

git diff --stat
 rag/backend/rag/core/query_enricher.py | 304 ++++++++++++++--
 rag/tests/unit/test_agent_graph.py     | 147 ++++++++
 rag/tests/unit/test_query_analysis.py  | 642 ++++++++++++++++++++++++++++++++-
 3 files changed, 1060 insertions(+), 33 deletions(-)
```

(Acumula las tres rondas anteriores porque ninguna se ha comprometido con
`git commit`. El diff aislado de solo esta ronda para `query_enricher.py`
se entrega por separado en `DIFF_CORRECCION_DEFECTOS_QUERY_ENRICHER.diff`.)

## 6. Confirmación de restricciones respetadas

Las 21 preguntas jurídicas siguen `in_scope` (verificado en la sección 3).
No se modificó ningún prompt (ni de enriquecimiento ni de generación), la
recuperación (BM25/vectorial/RRF/`k`/`k_candidates`/filtros), el frontend,
el contrato de la API, datos, embeddings, colección ni infraestructura. No
se agregaron dependencias. No se hizo `git commit`, `git push` ni
reindexación.

## 7. Resumen

Se corrigieron los cinco defectos confirmados con cambios mínimos y
localizados a las mismas familias de señales ya implementadas: una
partición de `_OFF_TOPIC_RE` en "inequívoca" vs. "blanda" (defecto #1), un
recálculo de la señal jurídica tras heredar contexto del historial (defecto
#2), una restricción de `norma\w*` a `normas?|normativ\w*` (defecto #3),
una nueva partición ambigua/inequívoca para el contexto costero con una
lista corta de entornos interiores (defecto #4, sin lista de lugares), y
una alternativa adicional en `_CAPABILITIES_RE` (defecto #5). Las 21
preguntas jurídicas y todos los controles previos (incluido "cocinar y
vender sin permiso") siguen intactos; 216 pruebas pasan sin regresiones;
Ruff, MyPy, TypeScript, ESLint y `git diff --check` quedan limpios. No se
hizo commit ni push.
