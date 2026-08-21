# Informe — Corrección general del clasificador de alcance

Fecha: 2026-08-21
Rama: `v2` (sin commit ni push, sin reindexación)
Base: implementación vigente al cierre de la ronda anterior
("Corrección posterior mínima — defectos #1 a #5").

## 1. Qué cambió: de parches puntuales a una política general

Las tres rondas anteriores fueron correcciones incrementales sobre el mismo
clasificador determinista: cada una agregaba o ajustaba palabras sueltas en
un par de expresiones regulares grandes (`_COASTAL_RE`, `_LEGAL_RE`,
`_OFF_TOPIC_RE`) para resolver casos concretos. Esta ronda **reescribe la
organización interna del clasificador**, no solo agrega más palabras.
`_fallback()` y `_apply_domain_guard()` ahora se apoyan en siete familias de
señal, cada una implementada como una función pequeña y con nombre propio,
en vez de una lista creciente de alternativas dentro de dos regex gigantes:

1. **Contexto costero explícito** (`_has_explicit_coastal_signal`): playa,
   costa, litoral, mar, bahía, bajamar, aguas marítimas, terrenos de
   bajamar, DIMAR, Capitanía de Puerto, acceso al mar, bienes de uso
   público, El Rodadero (única excepción de lugar admitida).
2. **Actividad acuática/marítima ambigua** (`_has_ambiguous_aquatic_signal`):
   pesca, pescador, embarcación, nave, buque, kayak, surf, moto acuática,
   parasailing, muelle, deporte/actividad náutica. Ninguna de estas prueba
   por sí sola conexión costera.
3. **Contexto interior o ajeno** (`_has_inland_or_unrelated_context`): lago,
   laguna, represa, embalse, río, piscina, "espacial" — neutraliza la
   familia 2 cuando aparece junto a ella.
4. **Intención jurídica o regulatoria** (`_has_legal_signal`): compuesta de
   nueve subfamilias pequeñas (permisos/autorización, requisitos/trámites/
   plazos, prohibición/legalidad, competencia de autoridad, quejas/riesgo/
   incumplimiento, acceso/propiedad/ocupación, sanciones/obligaciones,
   participación/protección/derechos, referencia normativa) más el modal de
   posibilidad/obligación combinado con un verbo de actividad.
5. **Solicitud inequívocamente ajena** (`_has_unambiguous_off_topic_intent`):
   once subfamilias acción+objeto (crear contenido visual, escribir
   contenido creativo, programar, clima, deportes, geografía general,
   recomendar hoteles, precios de inmuebles, recetas, entrenar/aprender por
   ocio, comprar por ocio). Fuerza `out_of_scope` sin excepción.
6. **Conversación o meta-pregunta** (`_is_meta_question`): sin cambios de
   fondo respecto a la ronda anterior.
7. **Seguimiento que hereda contexto** (`_inherit_context_from_history`):
   distingue marcadores anafóricos "fuertes" (también, eso, lo mismo,
   mencionado, aplicaría) de un marcador "débil" (una "y" inicial genérica)
   para decidir si se hereda solo el contexto costero o también la
   intención jurídica del historial combinado.

`_has_coastal_signal()` combina las familias 1-3; `_apply_domain_guard()` no
mantiene ninguna copia propia de estas señales — llama exactamente a las
mismas funciones que `_fallback()`. El resultado es una reducción neta de
duplicación: antes existían dos expresiones regulares independientes con
listas de palabras que se solapaban parcialmente (una en `_fallback`, el
"off-topic blando" que se evaluaba distinto en el guard); ahora hay una sola
fuente de verdad por familia.

## 2. Cómo se resolvieron los principios obligatorios del enunciado

**Ninguna condición específica para las 21 preguntas.** El archivo de
producción no contiene ningún texto completo, nombre de persona, playa ni
ciudad de las 21 preguntas. Las 21 siguen pasando porque activan las mismas
familias generales (p. ej. "playa" → familia 1, "permiso"/"autorización" →
familia 4), no porque exista una rama de código dedicada a ellas.

**Sin regex gigante ni duplicación entre `_fallback()` y
`_apply_domain_guard()`.** Cada familia es una expresión regular pequeña
(2-6 alternativas) con un nombre y una función propia; la familia 4 tiene
nueve subfamilias en vez de una lista plana de 25+ alternativas. El guard
llama a `_has_unambiguous_off_topic_intent()` y a `_fallback()` (que a su
vez usa `_has_coastal_signal()`/`_has_legal_signal()`); no vuelve a
compilar ni a repetir ninguna de esas señales.

**Generalización verificada, no solo las 21.** Se añadió una matriz general
(sección 4 de este informe) con paráfrasis nuevas —no las 21 preguntas— que
ejercitan las mismas familias con vocabulario y estructura de frase
distintos, incluyendo dos bugs de acentuación reales que esta verificación
destapó y corrigió (ver sección 3).

## 3. Hallazgos corregidos durante la verificación (no exigidos
   explícitamente por el enunciado, pero necesarios para que la
   generalización funcionara)

Al construir la matriz de generalización con paráfrasis reales en español,
aparecieron dos defectos de acentuación en la familia 5 (solicitud
inequívocamente ajena) que las rondas anteriores no habían ejercitado:

- **Formas imperativas con pronombre enclítico.** "Dibújame una
  ilustración..." y "Compón una canción..." no coincidían con los patrones
  `dibuj\w*`/`compon\w*` porque el español desplaza el acento ortográfico al
  añadir un pronombre enclítico ("dibuja" → "dibújame"; "compón" ya lleva
  acento incluso sin pronombre, por ser palabra aguda terminada en "n"). Se
  corrigió generalizando los patrones de verbo a `dib[uú]j\w*`,
  `comp[oó]n\w*`, `escr[ií]b\w*`, `red[aá]ct\w*`, `inv[eé]nt\w*`,
  `cr[eé]a\w*` y `progr[aá]ma\w*` en las tres subfamilias de contenido
  creativo/programación.
- **`recomi[eé]ndame\s+hoteles?` no reconocía "un hotel" en singular.** La
  expresión `hoteles?` significa literalmente "hotele" + "s" opcional
  (nunca "hotel" + "es" opcional), un defecto heredado de una ronda
  anterior. Se corrigió a `hotel(?:es)?`.

Ambos se descubrieron y corrigieron ANTES de escribir las pruebas
definitivas (se usó un script de verificación desechable, eliminado antes
de esta entrega), evitando así construir la matriz de pruebas alrededor de
un comportamiento roto.

## 4. Pruebas generales añadidas (`tests/unit/test_query_analysis.py`)

No se duplicó ninguna de las 21 preguntas ni de los controles de rondas
anteriores; todo lo siguiente usa redacciones nuevas:

- **Matriz positiva** (`test_general_positive_matrix_reaches_in_scope`, 14
  casos): paráfrasis de permisos/derechos/autoridades/obligaciones,
  actividades económicas y ambientales en playas, preguntas breves y un
  caso narrativo, y actividad acuática ambigua (kayak) acompañada de
  contexto marítimo explícito (bahía).
- **Seguimientos** (`test_general_follow_up_matrix_inherits_context`, 5
  casos): exactamente los cinco ejemplos de la sección 6 de la revisión
  ("¿Y puedo hacerlo mientras deciden?", "¿Y quién tiene que autorizarlo?",
  "¿Y cuánto tiempo tienen para responder?", "¿También aplica a los
  pescadores?", "¿Qué puedo hacer si no cumplen?"), todos sobre el mismo
  historial de un evento en una playa.
- **Matriz negativa** (`test_general_negative_matrix_stays_out_of_in_scope`,
  14 casos): creación de imagen/canción con verbos distintos a los ya
  cubiertos, programación superficialmente relacionada con DIMAR,
  recomendación de hotel, clima, resultado deportivo, precio de inmueble,
  kayak/muelle/embarcación/nave en un entorno interior explícito (lago,
  embalse, espacial), y tres consultas jurídicas genéricas que solo
  contienen "derecho"/"autoridad"/"permiso" sin ningún contexto costero.
- **Seis pares contrastivos** (`_CONTRASTIVE_PAIRS`, reutilizados por dos
  pruebas): crear imagen de playa / permiso para sesión fotográfica;
  entrenar kayak / autorización para competencia marítima de kayak; pesca
  en un río / pesca artesanal en una playa; muelle en una represa /
  concesión de muelle en una playa; nave espacial / embarcación abandonada
  en el mar; hotel recomendado / hotel que restringe acceso público.
  - `test_general_contrastive_pairs_fallback`: el miembro ajeno/ambiguo
    nunca llega a `in_scope`; el miembro jurídico legítimo siempre llega a
    `in_scope`.
  - `test_general_contrastive_pairs_domain_guard`: simula que el LLM
    devuelve `in_scope` y `out_of_scope` para cada miembro y verifica
    `_apply_domain_guard()` en las dos direcciones. El miembro positivo
    siempre termina en `in_scope` (la heurística corrige el falso negativo
    del modelo). Para el miembro negativo se distinguen dos categorías: los
    tres pares "hard" (solicitud inequívocamente ajena) siempre terminan en
    `out_of_scope`, incluso si el modelo dijo `in_scope`; los tres pares
    "inland" (actividad acuática ambigua en un entorno interior) verifican
    que el guard **conserva el resultado del modelo tal cual** en ambas
    direcciones — la heurística no tiene certeza suficiente ahí, así que no
    debe forzar nada (ni a favor ni en contra), tal como exige la sección 5
    de la revisión.

Total de pruebas nuevas en esta ronda: 45 (261 en la suite completa, antes
216).

## 5. Resultados de validación

```
uv run pytest tests/unit -q
261 passed in ~6s   (216 previos + 45 nuevos, todos en test_query_analysis.py)

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

## 6. Estado final de git en el dispositivo

```
git status --short --branch
## v2...origin/v2
 M rag/backend/rag/core/query_enricher.py
 M rag/tests/unit/test_agent_graph.py
 M rag/tests/unit/test_query_analysis.py
?? rag/INFORME_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md
?? rag/INFORME_CORRECCION_GENERAL_CLASIFICADOR.md
?? rag/INFORME_CORRECCION_POSTERIOR_DEFECTOS_1_A_5.md
?? rag/INFORME_REVISION_BANCO_21_PREGUNTAS.md
?? rag/PLAN_CORRECCION_ENRUTAMIENTO_CONSULTAS_JURIDICAS.md

git diff --stat
 rag/backend/rag/core/query_enricher.py | 501 +++++++++++++++--
 rag/tests/unit/test_agent_graph.py     | 147 +++++
 rag/tests/unit/test_query_analysis.py  | 987 ++++++++++++++++++++++++++++++++-
 3 files changed, 1598 insertions(+), 37 deletions(-)
```

(El diff es acumulado desde el inicio de la primera ronda de corrección,
porque ninguna de las cuatro rondas se ha comprometido con `git commit`.
`query_enricher.py` fue reescrito internamente en esta ronda —501 líneas de
diferencia frente al `HEAD` original— pero su comportamiento externo para
las 21 preguntas y todos los controles previos es idéntico, como confirman
las 261 pruebas.)

## 7. Confirmación de restricciones respetadas

Trabajo realizado sobre el estado actual de `v2`. No se hizo commit ni
push. Se conserva HTTP. No se modificó ningún prompt (ni de enriquecimiento
ni de generación). No se modificó recuperación, BM25, búsqueda vectorial,
RRF, filtros, pesos ni cantidades (`k`/`k_candidates`). No se modificó
frontend, API, autenticación, base de datos ni infraestructura. No se
modificaron AWS Academy, Ollama ni ChromaDB. No se reindexaron documentos.
No se añadieron dependencias. No se registró contenido de consultas en
ningún log nuevo. Los únicos archivos modificados son
`backend/rag/core/query_enricher.py` y `tests/unit/test_query_analysis.py`
(más este informe, sin efecto funcional).

## 8. Resumen

El clasificador de alcance pasó de tres rondas de parches léxicos puntuales
a una política organizada en siete familias reutilizables, con la lógica de
contexto costero, intención jurídica y solicitud ajena compartida entre
`_fallback()` y `_apply_domain_guard()` sin duplicación. Las 21 preguntas
del equipo jurídico se mantienen como banco de regresión y siguen
`in_scope`, pero la cobertura ahora se verifica con una matriz general de
paráfrasis nuevas, seguimientos variados y seis pares contrastivos
probados tanto en el clasificador determinista como en la protección de
dominio con ambas respuestas simuladas del modelo. La verificación de esa
generalización destapó y corrigió dos defectos reales de acentuación en
español que ninguna ronda anterior había ejercitado. 261 pruebas pasan sin
regresiones; Ruff, MyPy, TypeScript, ESLint y `git diff --check` quedan
limpios. No se hizo commit ni push.
