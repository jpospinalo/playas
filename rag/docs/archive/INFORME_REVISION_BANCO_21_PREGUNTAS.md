# Informe — Revisión posterior con el banco completo de 21 preguntas jurídicas

Fecha: 2026-08-21
Rama: `v2` (sin commit ni push)
Archivo base de esta ronda: `PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md` (fase anterior) +
brief "Revisión posterior con el banco completo de preguntas jurídicas" (esta ronda)

## 1. Verificación inicial

Antes de tocar nada se confirmó el estado exacto dejado por la corrección anterior:

```
## v2...origin/v2
 M rag/backend/rag/core/query_enricher.py
 M rag/tests/unit/test_agent_graph.py
 M rag/tests/unit/test_query_analysis.py
?? rag/INFORME_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
?? rag/PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
```

`git log --oneline -3`: `9c5893c fix: restaurar permiso de ejecución de deploy.sh` /
`1ffc7c6 infra: agilizar el arranque de la EC2 de ChromaDB` / `2218ba4 update: deploy.sh`.
No había cambios sueltos fuera de lo dejado por la corrección anterior. Se ejecutó la
batería de pruebas existente antes de editar nada: **118 tests pasaron**, Ruff y MyPy
limpios — línea base confirmada y sin nada pendiente por corregir fuera del alcance de
esta revisión.

## 2. Resultado individual de las 21 preguntas

Las 21 preguntas se incorporaron **verbatim** (sin resumir ni parafrasear) como casos
parametrizados en `tests/unit/test_query_analysis.py::test_banco_21_preguntas_juridicas_llegan_a_in_scope`.
Para cada una se verificó con el clasificador real (`_fallback`, sin LLM, sin Ollama/ChromaDB):
ruta `in_scope`, al menos un `doc_type` seleccionado, ruta distinta de `conversation` y de
`needs_clarification`, y preservación verbatim del texto original en `standalone_question`.

| # | Caso | Ruta obtenida | ¿Fallaba antes de esta revisión? |
|---|------|---------------|-----------------------------------|
| 1 | Apartamento en El Rodadero, motos acuáticas y parasailing | `in_scope` | No |
| 2 | Club náutico con muelle flotante, concesión marítima | `in_scope` | No |
| 3 | Hotel con malla y guardia que restringe acceso público | `in_scope` | No |
| 4 | Familia que alquila carpas y quiere instalar infraestructura semipermanente | `in_scope` | No |
| 5 | JAC organiza festival de playa para 2.000 personas | `in_scope` | No |
| 6 | Pescador artesanal en Playa Taganga, proyecto turístico | `in_scope` | No |
| 7 | Vendedora informal en Playa Cristal, temor a multa | `in_scope` | No |
| 8 | Residente de El Rodadero, club de playa privado | `in_scope` | No |
| 9 | Comunidad indígena en La Guajira, consulta previa | `in_scope` | No |
| 10 | Joven que quiere montar proyecto turístico en Playa Blanca (Cartagena) | `in_scope` | No |
| 11 | Empresa de eventos, boda en la playa, permiso del hotel | `in_scope` | No |
| 12 | Campeonato de fútbol playa, infraestructura por un mes | `in_scope` | No |
| 13 | Hotel en Bocagrande, diligencia formal de entrega del área | `in_scope` | No |
| 14 | Empresa de competencias de kayak, inicio antes de autorización | `in_scope` | No |
| 15 | Renovación automática de un permiso temporal de playa | `in_scope` | No |
| 16 | Restaurante sobre arena junto al mar, ¿dueño de la playa? | `in_scope` | **Sí** — `needs_clarification` |
| 17 | Lancha hundida heredada, retiro por parte de DIMAR | `in_scope` | No |
| 18 | Vendedor en Playa Los Cocos, prohibición durante conciertos | `in_scope` | No |
| 19 | Residente cerca de Playa Los Cocos, ruido y basura de conciertos | `in_scope` | No |
| 20 | Pescador artesanal, embarcación abandonada que contamina | `in_scope` | No |
| 21 | Residente de Pozos Colorados, erosión costera que amenaza su vivienda | `in_scope` | No |

Las 21 preguntas alcanzan el recuperador (route `in_scope` ⇒ `retrieve_forced` en el grafo)
y conservan el texto original completo tanto en `standalone_question` como en el
`question` del estado — ninguna se "resuelve" con una conclusión jurídica fabricada; eso
depende del corpus real, no de esta capa de clasificación (ver sección 6).

Adicionalmente se verificó, para las 21, que `_apply_domain_guard()` no convierte una
clasificación `in_scope` del modelo en ninguna otra ruta (`test_banco_21_preguntas_domain_guard_no_las_convierte_a_out_of_scope`).

## 3. Diagnóstico previo a cualquier cambio de producción

Con la implementación de la corrección anterior **sin modificar**, solo la pregunta
**#16** ("¿Eso significa que también soy dueño de la playa?") fallaba (`needs_clarification`
en lugar de `in_scope`), porque `dueño/propiedad/dominio` no formaban parte de `_LEGAL_RE`.

Antes de tocar producción se probaron además oraciones sintéticas mínimas (no las 21, ni
listas de lugares) para verificar que cada categoría de concepto exigida en la sección 4
del plan estuviera cubierta por **combinaciones** de señal costera + señal jurídica, y no
solo de forma accidental por otras palabras coincidentes en las 21 preguntas reales. Esto
reveló 4 vacíos adicionales genuinos, no evidenciados por las 21 preguntas tal como están
redactadas pero sí reproducibles con la misma categoría de concepto redactada de otra
forma:

- "motos acuáticas" / "parasailing" / "muelle (flotante)" sin otra palabra costera ya
  cubierta.
- el adjetivo "costero/a" en solitario (solo estaba cubierto el sustantivo "costa(s)" y la
  frase "zona costera").

Se descartó deliberadamente ampliar la señal costera a la palabra suelta "arena" (una
prueba con "multa a vendedor informal" usando solo "arena" en vez de "playa/mar" se
mantiene, correctamente, en `needs_clarification`): ninguna de las 21 preguntas depende de
"arena" sola, y agregarla ampliaría el alcance más allá de lo que el plan permite
("no conviertas cada expresión... en una regla que acepte cualquier consulta").

## 4. Cambios de producción realizados y justificación

Único archivo de producción modificado: `backend/rag/core/query_enricher.py`. Se
reutilizaron las mismas familias de señales ya existentes (`_COASTAL_RE`, `_LEGAL_RE`,
`_OFF_TOPIC_RE`); no se creó ninguna condición específica de una sola pregunta ni una
expresión regular gigante nueva.

1. **`_COASTAL_RE`**: se generalizó `costas?` a `costas?|coster[oa]s?` (cubre el adjetivo
   "costero/a" suelto; antes solo cubría el sustantivo), se eliminó la frase redundante
   `zona(?:s)?\s+costeras?` (ya queda subsumida por `coster[oa]s?`), y se agregó
   `motos?\s+acu[aá]ticas?|parasailing|muelles?(?:\s+flotantes?)?` — necesario para la
   pregunta #1 (motos acuáticas/parasailing) y para la #2 (muelle flotante), y para la
   protección de regresión de la sección 4 del plan.
2. **`_LEGAL_RE`**: se agregó `multa\w*` (pregunta #7, vendedora informal con temor a
   multa) y `dueñ\w*|propietari\w*|propiedad\w*|dominio\w*` (pregunta #16, concesiones/
   acceso público/propiedad de playas). No se reincorporó `competenc\w*` como raíz suelta
   — se mantiene deliberadamente excluida porque colisiona con "competencia" en sentido
   deportivo (fase anterior).
3. **`_OFF_TOPIC_RE`**: se agregó `aprender\w*\s+a\s+(?:usar|manejar|montar|navegar)\w*` y
   `precios?\s+de\s+(?:los\s+)?inmuebles?`, exclusivamente para sostener dos de los seis
   pares de control de falsos positivos exigidos en la sección 5 del plan (aprender a usar
   un kayak vs. autorizar una competencia de kayak; precios de inmuebles turísticos vs.
   derechos sobre un lote frente al mar).

No se tocó `_apply_domain_guard()`, la precedencia del `_fallback()`, el enriquecimiento
LLM, la generación, las citaciones ni ningún componente fuera de estas tres expresiones
regulares.

## 5. Política de prompt de enriquecimiento (sección 6 del plan)

No se modificó preventivamente el prompt de enriquecimiento. En este entorno no hay
credenciales de Ollama/AWS disponibles, por lo que no es posible ejecutar el
enriquecimiento real por LLM para inspeccionar `standalone_question`/`expanded_query`
generados por el modelo sobre las 21 preguntas (la misma limitación documentada como
"Fase 4 AWS" en el informe de la corrección anterior).

Lo que sí se pudo verificar exhaustivamente en este entorno es el camino determinista
(`_fallback()`, usado cuando `ENRICHMENT_ENABLED=False` o cuando el LLM falla): por
construcción, `_fallback()` asigna `standalone_question = expanded_query = pregunta
original sin modificar` (recortada a 45 palabras solo en `expanded_query`, nunca en
`standalone_question`). Esto se verificó explícitamente en la prueba nueva
`test_long_narrative_case_reaches_retriever_with_full_question_preserved` (ver sección 7):
no se pierde ni se inventa ningún hecho, nombre, lugar, cifra, duración o restricción en
esta ruta, porque el texto no se reescribe — se preserva verbatim.

**No se detectó ningún fallo sistémico del prompt que requiera autorización para
modificarlo**, porque el prompt de enriquecimiento LLM no pudo ejercitarse en este
entorno; la verificación completa de esa ruta (con Ollama real) queda pendiente de
autorización y credenciales, tal como en la ronda anterior.

## 6. Preguntas que llegan al recuperador pero podrían tener evidencia insuficiente

Distinto de un error de clasificación: **ninguna de las 21 preguntas es ahora un error de
enrutamiento** (todas llegan a `in_scope` y al recuperador). Si el corpus real (ChromaDB en
producción) no tiene jurisprudencia o normativa suficiente para alguna de ellas — por
ejemplo, sobre erosión costera en Pozos Colorados específicamente, o sobre el caso
puntual de una lancha heredada hundida — eso es un asunto de **cobertura del corpus**, no
de este clasificador, y no puede evaluarse en este entorno porque no hay acceso autorizado
a la instancia real de ChromaDB/AWS. Esa verificación queda para el equipo jurídico contra
el sistema en producción.

## 7. Pruebas nuevas agregadas

En `tests/unit/test_query_analysis.py`:

- 21 constantes verbatim con las preguntas completas del banco (`CASO_21_01…CASO_21_21`;
  `CASO_21_20` reutiliza `CASO_PESCADOR`, ya existente e idéntico byte a byte; el resto son
  literales nuevos para no resumir ni sustituir el texto).
- `test_banco_21_preguntas_juridicas_llegan_a_in_scope` (21 casos parametrizados): ruta
  `in_scope`, `doc_types` no vacío, ruta distinta de `conversation`/`needs_clarification`,
  preservación verbatim de la pregunta original.
- `test_banco_21_preguntas_domain_guard_no_las_convierte_a_out_of_scope` (21 casos): el
  guard no revierte un `in_scope` semántico del modelo para ninguna de las 21.
- `test_seis_pares_control_falsos_positivos_intencion_legal_vs_recreativa` (6 pares):
  boda con contexto de playa vs. boda sin contexto costero; campeonato de fútbol playa vs.
  resultado de fútbol; hotel que restringe acceso vs. recomendación de hotel; autorizar una
  competencia de kayak vs. aprender a usar un kayak; vender comida en playa sin permiso vs.
  receta de cocina; derechos sobre un lote frente al mar vs. precios de inmuebles
  turísticos.
- `test_scope_fallback_accepts_additional_concept_signals` (4 casos sintéticos, no
  pertenecientes a las 21 ni a los 6 pares): motos acuáticas, parasailing, muelle
  flotante y "costero" como adjetivo suelto — protección de regresión para las señales
  agregadas a `_COASTAL_RE`, evitando depender únicamente de que las 21 preguntas
  reales las contengan.

En `tests/unit/test_agent_graph.py`:

- `test_long_narrative_case_reaches_retriever_with_full_question_preserved`: usa la
  pregunta #1 del banco (>45 palabras) con el clasificador real
  (`ENRICHMENT_ENABLED=False`). Verifica: el recuperador se invoca exactamente una vez; la
  consulta enviada al recuperador contiene la pregunta original completa; `enriched_query`
  respeta el tope de 45 palabras (confirmando que el recorte sí ocurre); y la pregunta
  original permanece disponible sin modificar en el estado final para la generación.

No se amplió el límite de 45 palabras de `expanded_query` — la prueba demuestra que no
hace falta, porque la pregunta original ya llega completa al recuperador por otra vía
(`state["question"]`/`standalone_question`).

## 8. Resultados de validación

```
uv run pytest tests/unit -q
171 passed in 5.19s   (118 previos + 53 nuevos: 1 en test_agent_graph.py, 52 en test_query_analysis.py)

uv run ruff check backend tests
All checks passed!

uv run mypy backend/rag
Success: no issues found in 25 source files

frontend: bun install && ./node_modules/.bin/tsc --noEmit
sin errores

frontend: ./node_modules/.bin/eslint .
sin errores

frontend: npm run build
Falla únicamente por bloqueo de red hacia fonts.googleapis.com (Geist Mono, Inter) —
limitación de red de este entorno, no relacionada con los cambios de esta revisión;
el frontend no fue modificado en esta ronda.
```

## 9. Estado de git en el dispositivo (posterior a esta ronda)

```
git status --short --branch
## v2...origin/v2
 M rag/backend/rag/core/query_enricher.py
 M rag/tests/unit/test_agent_graph.py
 M rag/tests/unit/test_query_analysis.py
?? rag/INFORME_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
?? rag/INFORME_REVISION_BANCO_21_PREGUNTAS.md
?? rag/PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md

git diff --stat
 rag/backend/rag/core/query_enricher.py | 206 ++++++++++++---
 rag/tests/unit/test_agent_graph.py     | 147 +++++++++++
 rag/tests/unit/test_query_analysis.py  | 449 ++++++++++++++++++++++++++++++++-
 3 files changed, 769 insertions(+), 33 deletions(-)
```

(El diff acumula la corrección anterior y esta revisión, porque ninguna de las dos rondas
se ha comprometido con `git commit` — sigue exactamente igual que como se dejó, ahora con
las tres ediciones adicionales de esta ronda encima.)

## 10. Confirmación de restricciones respetadas

No se realizó ningún cambio de infraestructura, AWS Academy, Ollama, ChromaDB, máquinas,
reindexación, documentos, embeddings, colección, backup ni capa GOLD. No se modificó
BM25/búsqueda vectorial/RRF/pesos/filtros/`k`/`k_candidates`, ni el contrato de la API, el
frontend, autenticación, CORS ni base de datos. No se modificó el prompt de generación
jurídica ni la política de citaciones. No se agregaron dependencias nuevas. No se hizo
`git commit` ni `git push` — el repositorio queda igual que al inicio de esta ronda, solo
con los tres archivos editados y este informe agregado, todos sin confirmar.

## 11. Resumen

Antes de esta revisión, de las 21 preguntas del banco solo la #16 fallaba el enrutamiento
(quedaba en `needs_clarification`). Con tres adiciones mínimas y localizadas a
`_COASTAL_RE`, `_LEGAL_RE` y `_OFF_TOPIC_RE` — reutilizando las mismas familias de señales
ya implementadas, sin listas de lugares ni condiciones ad-hoc por pregunta — las 21 llegan
ahora a `in_scope` y alcanzan el recuperador, se preserva el texto original completo, los
controles de falsos positivos existentes y los seis pares nuevos se mantienen correctos, y
la batería completa de pruebas (171) pasa sin regresiones. No se identificó ningún fallo
sistémico del prompt de enriquecimiento que requiriera autorización para modificarlo (esa
ruta LLM no es ejercitable en este entorno). No se realizó commit ni push.
