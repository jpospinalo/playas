# Plan de corrección — Enrutamiento de consultas jurídicas costeras

## 1. Objetivo

Corregir los falsos negativos y falsos positivos confirmados en la clasificación
de alcance del RAG, sin modificar el funcionamiento de autenticación, API,
recuperación híbrida, generación, citas, frontend, infraestructura ni datos.

El defecto confirmado ocurre antes de recuperar documentos. Las dos consultas
entregadas por el equipo jurídico se clasifican actualmente como
`out_of_scope`, aunque pertenecen al ámbito admitido y el respaldo local contiene
documentos pertinentes.

Este plan busca que:

- una consulta jurídica relacionada con playas, mar, embarcaciones, pesca,
  contaminación, actividades náuticas, permisos, autoridades o derechos pueda
  llegar a recuperación aunque esté formulada como una narración ciudadana;
- una consulta creativa, comercial o recreativa sin intención jurídica continúe
  fuera del alcance aunque mencione una playa, el mar o un kayak;
- el comportamiento actual que ya funciona se conserve y quede protegido por
  pruebas de regresión.

## 2. Restricciones obligatorias

1. Trabajar sobre la rama `v2` y comprobar primero que el árbol de trabajo no
   contenga cambios ajenos.
2. No hacer commit ni push salvo autorización expresa del usuario.
3. Conservar HTTP. No añadir HTTPS obligatorio, HSTS ni cookies `Secure`.
4. No modificar AWS Academy, Ollama, ChromaDB, colección, embeddings ni máquinas.
5. No reindexar documentos ni modificar ingesta, capas GOLD o respaldos.
6. No cambiar BM25, búsqueda vectorial, RRF, pesos, `k`, `k_candidates`, filtros
   estructurales ni metadatos.
7. No cambiar el prompt de generación jurídica, la política de citas ni los
   mensajes de evidencia insuficiente en esta fase.
8. No modificar el frontend, contratos HTTP, esquemas de respuesta, base de
   datos, autenticación, rate limiting, CORS, `MemorySaver` o infraestructura.
9. No introducir dependencias nuevas ni un framework adicional de pruebas.
10. No crear una lista extensa de municipios, playas o lugares de Colombia como
    sustituto de la clasificación semántica.
11. No registrar preguntas, nombres, correos, tokens, IP ni contenido del usuario
    en nuevos logs.
12. Si las pruebas requieren cambiar algo fuera de los archivos autorizados en
    este documento, detenerse y solicitar aprobación.

## 3. Archivos autorizados en la primera implementación

Obligatorios:

- `backend/rag/core/query_enricher.py`
- `tests/unit/test_query_analysis.py`

Solo si se necesita demostrar el enrutamiento completo sin servicios externos:

- `tests/unit/test_agent_graph.py`

Opcionalmente, para documentar la prueba desplegada sin cambiar código:

- `docs/SMOKE_TESTS.md`
- `tests/integration/test_api_smoke.py`

No modificar otros archivos en esta fase.

## 4. Diagnóstico que la implementación debe preservar

### 4.1 Falsos negativos confirmados

Las consultas completas siguientes deben clasificarse como `in_scope`:

#### Caso A — pescador, contaminación y embarcación abandonada

> Soy pescador artesanal y vivo con mi familia de lo que gano en el mar. Hace
> varios meses una embarcación quedó abandonada cerca del lugar donde trabajo.
> Cada vez hay más combustible y residuos en el agua, y tengo miedo de que la
> contaminación afecte la zona donde pesco. Ya he presentado quejas, pero nadie
> me da una solución. No tengo dinero para pagar un abogado. ¿Qué puedo hacer
> para que la autoridad actúe y retire la embarcación antes de que el problema
> empeore?

#### Caso B — competencia de kayak y autorización pendiente

> Tengo una empresa que organiza competencias de kayak en El Rodadero (Santa
> Marta). Presenté la solicitud para realizar un campeonato internacional dentro
> de dos semanas, pero la respuesta de la autoridad todavía no ha llegado. Los
> patrocinadores ya hicieron publicidad y muchos deportistas vienen desde otras
> ciudades, por lo que estoy pensando en realizar el evento mientras recibo la
> respuesta. ¿Puedo iniciar la actividad mientras deciden mi solicitud o debo
> esperar la autorización?

El problema actual se produce por tres razones:

- el fallback no reconoce expresiones como `mar`, `embarcación`,
  `contaminación`, `kayak` o `autorización` como señales combinadas;
- `pescadores?` no reconoce correctamente el singular `pescador`;
- `_apply_domain_guard()` reemplaza un resultado semántico `in_scope` del LLM
  cuando la heurística limitada devuelve `out_of_scope`.

### 4.2 Otros falsos negativos confirmados

También deben ser `in_scope`:

- `¿Quién debe retirar una nave abandonada que contamina el mar?`
- `¿Puedo programar una competencia turística en una playa si la autoridad no responde?`
- `¿Se puede cocinar y vender pescado en una playa sin permiso?`
- `¿Qué haces si un hotel cierra el acceso público a una playa?`
- `¿Puedo practicar surf en El Rodadero?`
- `¿Quién autoriza deportes náuticos en Santa Marta?`
- `¿La contaminación de una bahía vulnera derechos colectivos?`

`programar` y `cocinar` no pueden seguir siendo vetos absolutos: esas palabras
pueden aparecer en preguntas jurídicas sobre actividades realizadas en playas.
La expresión de capacidades tampoco debe convertir `¿Qué haces si...?` en una
pregunta sobre el asistente.

### 4.3 Falsos positivos confirmados

Estas consultas deben ser `out_of_scope`, incluso si contienen términos
costeros:

- `Escribe un poema sobre una playa.`
- `Genera una imagen de una playa al atardecer.`
- `Recomiéndame hoteles cerca de una playa.`
- `¿Dónde puedo comprar un kayak barato?`
- `¿Cómo entrenar para una competencia de kayak?`

La sola presencia de `playa`, `mar`, `kayak` o un lugar costero no debe forzar
`in_scope`.

## 5. Diseño mínimo requerido

No resolver el problema añadiendo palabras indiscriminadamente a una única
expresión regular. Separar las señales por intención mediante funciones pequeñas
y puras, manteniendo la implementación dentro de `query_enricher.py`.

### 5.1 Conversación/meta-preguntas

La detección de capacidades debe aplicarse únicamente cuando toda la consulta es
una meta-pregunta breve sobre el sistema, por ejemplo:

- `¿Qué puedes hacer?`
- `¿Cómo funcionas?`
- `¿Cuáles son tus capacidades?`

No debe activarse cuando la frase forma parte de un supuesto jurídico:

- `¿Qué haces si un hotel cierra el acceso a una playa?`
- `¿Cómo ayudas a exigir que una autoridad retire una embarcación?`

Anclar la expresión al inicio y al final o implementar una función equivalente
que compruebe la intención completa. Conservar sin cambios los saludos y
despedidas simples.

### 5.2 Señales de contexto costero o marítimo

Reconocer familias morfológicas, no solo palabras exactas. Como mínimo:

- playa, costa, litoral, bajamar, bahía, mar y aguas marítimas;
- embarcación, nave, buque y artefacto naval;
- DIMAR y Capitanía de Puerto;
- pesca, pescador, pescadora, pescadores y pesca artesanal;
- kayak, surf y deportes/actividades náuticas;
- contaminación marina, derrame, combustible, hidrocarburos y residuos cuando
  estén conectados con una señal marítima;
- El Rodadero puede ser una señal auxiliar, pero no debe mantenerse una lista
  extensa de lugares ni aceptarse `Santa Marta` por sí sola.

Corregir expresamente la familia de `pescador` con una construcción equivalente
a `pescador(?:a|es|as)?`.

### 5.3 Señales jurídicas o procedimentales

Reconocer, entre otras, las familias de:

- permiso, autorización, licencia, solicitud y concesión;
- autoridad, competencia, queja, omisión y actuación;
- derecho, obligación, prohibición, sanción y norma;
- procedimiento, plazo, retiro y medida urgente/cautelar;
- formulaciones de posibilidad u obligación (`puede`, `debe`, `quién puede`)
  únicamente cuando estén acompañadas de una actividad o contexto del dominio.

No clasificar una consulta como jurídica por la sola palabra `puedo` o `debo`.

### 5.4 Señales explícitamente ajenas

Mantener reglas deterministas para intenciones inequívocamente ajenas, pero
formularlas por intención completa y no mediante verbos ambiguos aislados.

Ejemplos que deben seguir fuera:

- capitales o geografía general;
- recetas o instrucciones culinarias sin pregunta regulatoria costera;
- programación de software/API, no `programar un evento`;
- resultados deportivos;
- escritura de poemas, generación de imágenes o chistes;
- compras, recomendaciones hoteleras o entrenamiento deportivo sin intención
  normativa o jurídica.

Una señal ajena no debe ganar automáticamente cuando existe una combinación
clara de contexto costero y propósito regulatorio. Por ejemplo, `cocinar y vender
en una playa sin permiso` es una pregunta sobre actividad económica regulada, no
una solicitud de receta.

### 5.5 Política de fallback

El fallback debe ser autónomo y seguro cuando el enriquecimiento está desactivado,
el proveedor falla o el JSON no puede validarse:

1. saludo/meta-pregunta completa → `conversation`;
2. intención inequívocamente ajena sin propósito jurídico costero →
   `out_of_scope`;
3. contexto costero/marítimo + intención jurídica, procedimental, ambiental o
   de actividad regulada → `in_scope`;
4. término relacionado (pesca, turismo, permiso, derecho) sin conexión costera
   suficiente → `needs_clarification`;
5. ausencia de cualquier señal pertinente → `out_of_scope`.

Los casos A y B deben ser `in_scope` directamente en `_fallback()`. Esto es
obligatorio para que sigan funcionando si el LLM de enriquecimiento no está
disponible.

### 5.6 Política de `_apply_domain_guard`

Reemplazar la precedencia absoluta actual por estas reglas:

1. Una conversación/meta-pregunta completa puede forzar `conversation`.
2. Una intención explícitamente ajena y sin propósito jurídico costero puede
   forzar `out_of_scope`.
3. Una clasificación heurística de alta confianza `in_scope` puede corregir un
   falso negativo del modelo y conservar el comportamiento protector actual.
4. La mera ausencia de coincidencias heurísticas no puede convertir un
   `in_scope` semántico del LLM en `out_of_scope`.
5. La mera aparición de `playa` o `mar` no puede convertir una clasificación
   semántica `out_of_scope` en `in_scope` si no existe intención jurídica.
6. Cuando se fuerce `in_scope`, conservar `standalone_question` y
   `expanded_query` del resultado semántico si son válidos, y usar ambos tipos
   documentales solo cuando el resultado no proporcione `doc_types`.

No cambiar el esquema `EnrichedQuery` ni añadir nuevas rutas.

## 6. Implementación por fases

### Fase 0 — Línea base y protección del alcance

Antes de editar:

```bash
git status --short --branch
git diff --check
uv run pytest tests/unit -q
uv run ruff check backend tests
uv run mypy backend/rag
cd frontend
npx tsc --noEmit
npx eslint .
```

Registrar resultados y volver a la raíz `rag/`. No ejecutar pruebas contra AWS
sin URL y token proporcionados expresamente.

### Fase 1 — Pruebas de regresión antes del código

Añadir primero pruebas que fallen con el código actual.

En `tests/unit/test_query_analysis.py`:

1. parametrizar los dos casos completos del equipo jurídico y los siete falsos
   negativos adicionales;
2. verificar que `_fallback()` devuelve `in_scope` y selecciona al menos un tipo
   documental;
3. parametrizar los cinco falsos positivos y verificar `out_of_scope`;
4. probar las meta-preguntas breves que deben seguir como `conversation`;
5. probar que `¿Qué haces si...?` y `¿Cómo ayudas a...?` no son
   `conversation` cuando contienen un supuesto jurídico costero;
6. simular salida del LLM `in_scope` para los dos casos completos y comprobar
   que `_apply_domain_guard()` o `_parse_json_response()` no la veta;
7. simular salida del LLM `out_of_scope` para poema/imagen/hoteles con playa y
   comprobar que la heurística no la convierte en `in_scope`;
8. conservar todas las pruebas actuales de capital de Francia, receta,
   programación de API, fútbol, turismo ambiguo e historial.

En `tests/unit/test_agent_graph.py`, añadir como máximo:

- un caso completo legítimo cuyo analizador devuelva `in_scope`, verificando que
  se invoca el retriever exactamente una vez;
- un caso creativo con palabra `playa`, verificando que no se invoca el
  retriever.

Usar retriever y LLM falsos como las pruebas existentes; no conectar con
ChromaDB u Ollama.

Ejecutar solo las pruebas nuevas y confirmar que fallan por las razones
esperadas antes de modificar producción.

### Fase 2 — Corrección mínima del clasificador

Modificar únicamente `query_enricher.py` siguiendo el diseño de la sección 5.

Requisitos de calidad:

- expresiones compiladas una sola vez a nivel de módulo;
- funciones pequeñas, con nombres que describan intención;
- sin duplicar las listas de señales entre fallback y guard;
- sin llamadas de red, geocodificación, consultas a Chroma o al LLM adicionales;
- sin capturar ni registrar la pregunta;
- sin aumentar el número de llamadas al modelo;
- mantener los límites de 4.000 caracteres y 45 palabras;
- mantener `doc_types` y los cuatro nombres de ruta actuales.

### Fase 3 — Validación automática completa

Ejecutar:

```bash
uv run pytest tests/unit -q
uv run ruff check backend tests
uv run mypy backend/rag
git diff --check
cd frontend
npx tsc --noEmit
npx eslint .
npm run build
```

La compilación puede requerir acceso a Google Fonts. Si falla únicamente por
`next/font` y el entorno bloquea la red, documentarlo; no modificar fuentes ni
layout para ocultar la limitación.

Luego revisar:

```bash
git diff --stat
git diff -- backend/rag/core/query_enricher.py tests/unit/test_query_analysis.py tests/unit/test_agent_graph.py
git status --short --branch
```

No debe aparecer ningún archivo no autorizado.

### Fase 4 — Prueba funcional controlada

No ejecutarla contra AWS sin autorización/credenciales. Cuando el usuario la
realice, usar conversaciones nuevas salvo el seguimiento indicado.

| Nº | Pregunta | Resultado esperado |
|---:|---|---|
| 1 | Caso completo del pescador | No rechazar ni pedir conexión costera; buscar evidencia y mostrar fuentes. |
| 2 | Caso completo del kayak | No rechazar; buscar normativa pertinente y mostrar fuentes. |
| 3 | `¿Puedo programar una competencia turística en una playa si la autoridad todavía no ha dado la autorización?` | `in_scope`, con recuperación. |
| 4 | `Escribe un poema sobre una playa.` | `out_of_scope`, sin fuentes. |
| 5 | `¿Dónde puedo comprar un kayak barato?` | `out_of_scope`, sin fuentes. |
| 6 | `Según la normativa y la jurisprudencia, ¿qué competencias tiene DIMAR frente a embarcaciones abandonadas que amenazan el ambiente marino?` | `in_scope`; revisar pertinencia y tipos de fuentes, sin exigir aún una cuota artificial. |
| 7 | Después del caso 1: `¿Y una persona que no puede pagar abogado qué mecanismo puede utilizar para pedir una actuación urgente?` | Mantener el contexto costero y recuperar evidencia. |

Para cada caso registrar:

- respuesta completa;
- si apareció la etapa `Buscando evidencia…`;
- títulos y tipos de fuentes;
- si apareció alguno de los mensajes: fuera de ámbito, aclaración, evidencia
  insuficiente o citas no verificables;
- `query_route` y `enriched_query` desde la respuesta de red, si el evaluador
  puede consultarlos, sin añadir UI nueva.

La evaluación jurídica de exactitud y suficiencia corresponde al equipo
jurídico; esta fase técnica solo verifica enrutamiento, recuperación, citas y
ausencia de regresiones.

## 7. Criterios de aceptación

El cambio se aprueba únicamente si se cumplen todos:

1. Las dos preguntas completas son `in_scope` con el LLM disponible y mediante
   `_fallback()`.
2. Los otros falsos negativos confirmados son `in_scope`.
3. Los falsos positivos creativos, comerciales o recreativos son
   `out_of_scope`.
4. Las meta-preguntas breves siguen siendo `conversation`.
5. Las consultas relacionadas pero realmente ambiguas siguen usando
   `needs_clarification`.
6. Capital de Francia, recetas, programación de software, fútbol y hoteles sin
   propósito jurídico continúan fuera.
7. Solo `in_scope` llega a recuperación.
8. El enriquecimiento conserva la pregunta original y no inventa normas,
   autoridades o hechos.
9. Todas las pruebas anteriores y nuevas pasan.
10. No cambian contratos API, frontend, recuperación, generación, citas, datos,
    infraestructura ni configuración de servicios.
11. No se hizo reindexación, commit ni push.

## 8. Hallazgos que NO deben corregirse en este mismo cambio

Durante el diagnóstico surgieron riesgos que requieren evidencia funcional. No
mezclarlos con la corrección del clasificador:

1. **Formato de citas:** el validador rechaza formatos distintos de `[docN]`.
   Solo abrir una corrección separada si la prueba desplegada devuelve
   repetidamente `no fue posible producir una respuesta verificable` pese a
   recuperar fuentes.
2. **Balance normativa/jurisprudencia:** existe `balance_by_doc_type()`, pero no
   está conectado obligatoriamente. No activarlo sin comprobar que consultas
   mixtas están perdiendo un tipo documental y sin evaluar el efecto sobre
   relevancia.
3. **Degradación BM25/vector:** no cambiar tolerancia a fallos en esta fase. Si
   aparecen errores 500 por caída de un sub-retriever, preparar un plan separado.
4. **Visualización de `query_route` y `enriched_query`:** el backend ya los
   entrega. No añadir controles de depuración al frontend en esta corrección.

Separar estos temas evita que una solución de clasificación cambie al mismo
tiempo la recuperación o la respuesta jurídica.

## 9. Entrega requerida de la IA implementadora

Al finalizar, entregar un informe con:

1. causa corregida y política final de precedencia;
2. archivos modificados;
3. lista de pruebas nuevas y qué regresión cubre cada una;
4. resultados completos de pytest, Ruff, MyPy, TypeScript, ESLint y build;
5. tabla de casos funcionales ejecutados y no ejecutados;
6. cualquier validación bloqueada y motivo exacto;
7. `git diff --stat` y `git status --short --branch` finales;
8. confirmación de que no se modificaron componentes fuera de alcance;
9. confirmación de que no hubo reindexación, commit ni push.

Si cualquier prueba obliga a modificar recuperación, citas, prompts de
generación, frontend, infraestructura o datos, detenerse y solicitar una nueva
autorización en lugar de ampliar el cambio silenciosamente.
