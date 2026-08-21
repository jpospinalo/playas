# Instrucciones para implementar los hallazgos confirmados de forma segura

## Objetivo

Aplicar únicamente las correcciones confirmadas y accionables del diagnóstico técnico,
preservando el comportamiento que ya funciona en la rama `v2`.

Estas instrucciones fueron contrastadas con el código actual. No deben interpretarse como una
autorización para hacer una reescritura general del proyecto.

## Restricciones obligatorias

La implementación debe respetar lo siguiente:

1. Continuar operando por **HTTP**. No agregar redirecciones a HTTPS, HSTS, cookies que exijan
   HTTPS ni validaciones que bloqueen el protocolo actual.
2. No modificar las máquinas, configuración o servicios de Ollama y ChromaDB en AWS Academy.
3. No reindexar documentos ni modificar colecciones, embeddings o datos almacenados.
4. No modificar infraestructura, Terraform, ECS, ALB, Nginx, red, puertos, DNS o IAM.
5. No introducir migraciones de base de datos.
6. No modificar los prompts, el alcance temático ni el flujo determinista del RAG en este grupo
   de cambios.
7. No cambiar contratos públicos de la API salvo que estas instrucciones lo indiquen
   expresamente. Ninguna corrección aprobada requiere hacerlo.
8. No mostrar secretos, tokens, contraseñas ni valores reales de `.env` en código, pruebas o
   logs.
9. No hacer `commit` ni `push` salvo autorización expresa.
10. Trabajar sobre el directorio actual, incluidos los cambios locales existentes. No descartar,
    sobrescribir ni reformatear cambios no relacionados.

## Evaluación de los hallazgos del informe

| Hallazgo | Veredicto | Acción |
|---|---|---|
| Estado del chat sobrevive al cambio de usuario | Confirmado y prioritario | Implementar ahora |
| `generate-title` no usa el limitador | Confirmado, aunque el frontend actual no lo invoca | Implementar con un limitador independiente, desactivado por defecto |
| Login sin protección contra fuerza bruta | Confirmado | Preparar limitador independiente, `off` por defecto; no activar `enforce` en esta tarea |
| Tool `retrieve` y `ALL_TOOLS` sin uso | Confirmado | Eliminar después de verificar importaciones y actualizar documentación |
| Crecimiento de `MemorySaver` | Riesgo confirmado | No implementar la purga propuesta en este grupo; ver sección aplazada |
| Expiración de sesión mal comunicada | Confirmado | Implementar junto con el aislamiento del chat |
| `rehype-raw` instalado y sin uso | Confirmado | Eliminar dependencia y actualizar el lockfile |
| CORS fijo y `allow_credentials=True` | Parcialmente relevante, sin impacto actual | No cambiar ahora |
| Feedback admin carga todas las filas | Confirmado, prioridad baja | Aplazar; el diseño futuro requiere aprobación independiente |
| Carrera de email duplicado | Confirmado | Capturar `IntegrityError` sin ocultar otros errores de base de datos |
| Chunks puramente estructurales recuperables | Confirmado en el respaldo | Añadir un filtro conservador en tiempo de consulta, sin tocar el índice |
| Duplicados, OCR y metadata desigual del corpus | Confirmado | Documentar para la futura reindexación; no modificar datos ahora |

## Estrategia de implementación

No implementar todo en una sola modificación. Usar este orden y validar completamente después
de cada fase:

1. Aislamiento del estado por usuario y manejo de sesión expirada.
2. Limitadores independientes, reversibles y manejo de carreras de email.
3. Limpieza de código muerto, dependencia sin uso y filtro conservador del retriever.
4. No ejecutar en esta implementación la optimización del panel de feedback; conservarla solo
   como diseño para una tarea futura con aprobación expresa.

Si una fase falla en sus pruebas, corregirla o revertir únicamente esa fase antes de continuar.
No iniciar una fase nueva con la anterior en estado rojo. Crear cambios pequeños y revisables,
sin mezclar formateos generales ni refactors adyacentes.

### Guardas de compatibilidad por fase

- **Fase 1:** solo debe cambiar el comportamiento de sesiones inválidas o del cambio de cuenta.
  Una sesión válida, el streaming y la navegación de conversaciones deben verse igual.
- **Fase 2:** con las nuevas variables ausentes o en `off`, no puede aparecer ningún `429` nuevo
  ni cambiar el resultado de login, títulos o consultas. El modo `off` debe retornar antes de
  adquirir locks, guardar eventos o escribir logs.
- **Fase 3.1 y 3.2:** son limpiezas sin efecto en ejecución. Cualquier cambio visible obliga a
  detener la fase.
- **Fase 3.3:** el único cambio admitido es excluir candidatos sin caracteres alfanuméricos. No
  se permite alterar el orden ni la cantidad cuando todos los candidatos son válidos.
- **Fases aplazadas:** no deben producir ningún archivo modificado.

Antes de aceptar cada fase, comparar los contratos HTTP, mensajes relevantes y muestras de salida
con la línea base. Si aparece una diferencia fuera de estas excepciones, tratarla como regresión.

---

## Fase 0 — Establecer la línea base

Antes de editar:

1. Ejecutar `git status --short --branch` y conservar el listado de cambios previos.
2. No asumir que un archivo modificado pertenece a la nueva tarea.
3. Ejecutar las pruebas actuales:

```bash
uv run pytest tests/unit -q
uv run ruff check backend tests
uv run mypy backend/rag
cd frontend
npx tsc --noEmit
npx eslint .
npm run build
```

La referencia actual es 66 pruebas unitarias aprobadas. Las nuevas pruebas deben aumentar esa
cantidad. Si `next build` falla por descarga de fuentes o binarios, repetirlo en un entorno con
red y distinguir el bloqueo ambiental de un error de código.

No ejecutar pruebas contra AWS sin `RAG_SMOKE_API_URL` y `RAG_SMOKE_TOKEN` proporcionados
expresamente.

---

## Fase 1 — Aislamiento de sesión y expiración del JWT

### 1.1. Separar el límite autenticado del chat

**Hallazgo confirmado:** `useChat` y `useConversations` se montan antes de comprobar el usuario.
Al cerrar sesión, `ChatInterface` no se desmonta y sus mensajes, `conversationId`, referencias y
feedback permanecen en memoria.

**No aplicar literalmente** la sugerencia de añadir `key={user?.user_id}` en
`frontend/app/page.tsx`. Esa página es un componente de servidor que exporta `metadata` y no
dispone de `useAuth`. Convertirla en componente cliente solo para obtener el usuario sería una
regresión arquitectónica innecesaria.

#### Archivos

- `frontend/components/chat/ChatInterface.tsx`
- No es necesario modificar `frontend/app/page.tsx`.

#### Modificación requerida

1. Mantener `ChatInterface` como componente cliente y convertirlo en un límite pequeño de
   autenticación.
2. `ChatInterface` debe ejecutar únicamente `useAuth()`.
3. Si `authLoading` o no existe `user`, debe mostrar el `AuthModal` obligatorio, como ocurre hoy.
4. Extraer el contenido autenticado actual a un componente privado, por ejemplo
   `AuthenticatedChat`.
5. Mover dentro de `AuthenticatedChat`:
   - `useConversations()`;
   - `useChat()`;
   - todos los estados de sidebar, feedback y scroll;
   - el resto de la interfaz autenticada.
6. Cuando exista usuario, renderizar:

```tsx
<AuthenticatedChat key={user.user_id} />
```

7. No pasar mensajes ni identificadores del chat desde el componente exterior.

El cambio de `key` debe desmontar todo el árbol autenticado cuando cambia la cuenta. El cleanup
ya presente en `useChat` abortará una solicitud SSE activa al desmontarse.

#### No hacer

- No limpiar únicamente `messages`; también deben reiniciarse `conversationIdRef`,
  `threadIdRef`, `ratedMessageIds`, `contextPercent` y el `AbortController`.
- No agregar un `useEffect` que omita dependencias para forzar el reset.
- No almacenar mensajes del chat en `localStorage`.
- No recargar la página mediante `window.location.reload()`.

#### Validación manual obligatoria

1. Iniciar sesión como usuario A.
2. Abrir o crear una conversación y comprobar que hay mensajes visibles.
3. Cerrar sesión sin recargar la pestaña.
4. Iniciar sesión como usuario B.
5. Verificar que no aparecen mensajes, fuentes, conversación activa ni feedback del usuario A.
6. Enviar el primer mensaje de B y comprobar que crea una conversación nueva.
7. Repetir el cambio de usuario mientras existe una respuesta en streaming y confirmar que la
   solicitud anterior se aborta y no reaparece contenido después del nuevo login.

### 1.2. Manejar todos los `401` de llamadas autenticadas sin carreras entre sesiones

**Hallazgo confirmado:** el frontend conserva el usuario en React y el token en `localStorage`
cuando una llamada autenticada devuelve `401`. Algunos flujos muestran un error genérico y no
vuelven a presentar el modal de acceso.

#### Diseño recomendado

Usar una única señal de sesión expirada, sin acoplar `frontend/lib/api.ts` directamente al
contexto de React. La señal debe comprobar cuál fue el token usado por la solicitud: una
respuesta tardía de la sesión A nunca puede borrar el token de una sesión B iniciada después.

#### Archivos principales

- `frontend/lib/auth.ts`
- `frontend/lib/api.ts`
- `frontend/components/providers/AuthProvider.tsx`
- `frontend/components/common/AuthModal.tsx`
- `frontend/hooks/useChat.ts`
- `frontend/hooks/useConversations.ts`
- Los componentes administrativos y de conversaciones que todavía hacen `fetch` directo.

#### Modificación requerida

1. En `frontend/lib/auth.ts`, añadir:
   - un nombre constante de evento interno de sesión expirada;
   - retornar `false` inmediatamente si el código se ejecuta sin `window`, antes de acceder a
     `localStorage`;
   - una función como `expireAuthSession(expectedToken, message)` que compare primero
     `getToken()` con el token que utilizó la solicitud;
   - solo si ambos coinciden, ejecutar `clearAuth()` y emitir un `CustomEvent` cuando exista
     `window`;
   - retornar un booleano para que el llamador sepa si realmente invalidó la sesión;
   - el evento debe transportar únicamente un mensaje para el usuario, nunca el token ni datos
     sensibles.
2. Si el token actual es distinto de `expectedToken`, la función debe ignorar el `401`: pertenece
   a una solicitud de una sesión anterior. Esto también hace la operación idempotente cuando
   varias solicitudes del mismo token reciben `401` simultáneamente.
3. `clearAuth()` debe seguir siendo una operación silenciosa. El cierre de sesión manual no debe
   mostrar el aviso de sesión expirada.
4. En `AuthProvider`:
   - escuchar el evento al montar y retirar el listener al desmontar;
   - al recibirlo, hacer `setUser(null)` y guardar un mensaje como
     `"Tu sesión expiró. Inicia sesión nuevamente."`;
   - limpiar ese mensaje después de un login exitoso o de un cierre de sesión manual;
   - exponer el mensaje en el contexto solo si `AuthModal` necesita mostrarlo.
5. Corregir también la validación inicial de `/api/auth/me`:
   - capturar una sola vez el token enviado;
   - antes de aplicar el resultado, comprobar que ese token continúa siendo el actual;
   - con `200`, actualizar el usuario como hoy;
   - con `401`, expirar únicamente ese token;
   - con error de red, respuesta `5xx`, `403` inesperado o JSON inválido, no borrar el token;
   - en esos fallos transitorios, usar `getStoredUser()` como identidad provisional si está
     disponible. El backend seguirá autorizando todas las operaciones y un `401` posterior
     cerrará la sesión correctamente;
   - siempre finalizar `loading`, incluso si no existe usuario almacenado.
6. En `frontend/lib/api.ts`, crear un helper pequeño, por ejemplo
   `throwIfSessionExpired(response, requestToken)`, con responsabilidad única:
   - si el estado no es `401`, retornar sin consumir el cuerpo ni cambiar el comportamiento;
   - si devuelve `401`, llamar a `expireAuthSession(requestToken, ...)` y lanzar un error con un
     mensaje legible;
   - no tratar `403` como sesión expirada;
   - no usar este helper con el `401` normal de `/api/auth/login`, porque allí significa
     credenciales incorrectas.
7. No generalizar en esta fase el manejo de todos los errores ni reemplazar indiscriminadamente
   sus mensajes. Después del helper de `401`, cada función debe conservar el tratamiento actual
   de `403`, `404`, `409`, `422`, `429`, `5xx` y errores de red.
8. En cada llamada autenticada:
   - capturar el token una sola vez antes del `fetch`;
   - usar exactamente ese valor en `Authorization` y al llamar al helper;
   - si no existe token, emitir la señal solo si el estado continúa sin token y devolver el
     mensaje actual de sesión inválida;
   - no volver a leer el token después de recibir la respuesta para asociarla a otra sesión.
9. Hacer que `persistMessage`, creación/carga/edición/eliminación de conversaciones, streaming,
   feedback y llamadas administrativas usen el helper. Preservar si cada flujo actualmente
   muestra, propaga o silencia los errores que no son `401`.
10. En `persistMessage`, no reintentar un `401` ni otro error `4xx`. Conservar el reintento actual
   únicamente para errores transitorios `5xx` o de red.
11. `AuthModal` debe mostrar el aviso de expiración separado del error de credenciales. Después
    de un login correcto debe desaparecer.
12. Al ejecutar `setUser(null)`, el límite implementado en 1.1 desmontará el chat y eliminará su
   estado.

Para localizar todas las llamadas que deben revisarse:

```bash
rg -n "\\bfetch\\(" frontend --glob '!node_modules/**'
```

#### No hacer

- No decodificar el JWT en el navegador para decidir si sigue siendo válido; el backend es la
  autoridad.
- No renovar silenciosamente el JWT: no existe actualmente un contrato de refresh token.
- No introducir cookies ni cambiar el almacenamiento de sesión en esta tarea.
- No incluir el token en `CustomEvent.detail`, mensajes, logs o errores.
- No borrar una sesión nueva como reacción a la respuesta de una solicitud antigua.
- No mostrar el detalle técnico completo del backend.
- No cerrar la sesión por un `403`, `404`, `409`, `422`, `429` o `500`.

#### Casos de aceptación

- Un `401` al crear, guardar, consultar o cargar una conversación elimina el token, desmonta el
  chat y muestra el login obligatorio.
- Un `429` mantiene la sesión y muestra el mensaje de límite.
- Un `403` del panel admin mantiene la sesión.
- Un fallo de red no elimina una sesión que podría seguir siendo válida.
- El login con contraseña incorrecta muestra su error sin emitir el mensaje “sesión expirada”.
- Usuario A inicia una solicitud, cierra sesión e inicia como B; un `401` tardío de la solicitud
  de A no elimina la sesión de B.
- Dos respuestas `401` simultáneas del mismo token producen un solo cambio efectivo de sesión.

#### Pruebas

El frontend aún no tiene infraestructura de pruebas. No agregar Vitest/Jest/Testing Library en
esta misma fase: introducir un framework completo junto con una corrección de seguridad amplía
innecesariamente el riesgo. Ejecutar TypeScript, ESLint, build y los casos manuales anteriores.
La infraestructura de pruebas de componentes puede añadirse después en un cambio separado.

---

## Fase 2 — Limitadores reversibles y carreras de usuario

### 2.1. Proteger `generate-title` con una instancia independiente

**Hallazgo confirmado:** el endpoint llama a un LLM, pero solo depende de
`get_current_user`. La función de frontend `generateConversationTitle` no se usa actualmente,
pero el endpoint sigue expuesto a clientes autenticados.

#### Archivos

- `backend/rag/api/routes/conversations.py`
- `backend/rag/api/rate_limit.py`
- `backend/rag/config.py`
- `.env.example`
- `tests/unit/test_rate_limit.py` o una nueva prueba de dependencias de rutas.

#### Modificación requerida

1. Reutilizar la implementación de ventana deslizante de `rate_limit.py`, pero crear una instancia
   distinta de `query_rate_limiter`. No duplicar el algoritmo.
2. Generalizar el nombre interno a `SlidingWindowRateLimiter` y conservar temporalmente
   `QueryRateLimiter = SlidingWindowRateLimiter` como alias de compatibilidad para imports
   existentes. Generalizar únicamente el detalle del `429` y la etiqueta de log, manteniendo los
   valores actuales como predeterminados para que `query_rate_limiter` no cambie su
   comportamiento.
3. Añadir configuración independiente:
   - `TITLE_RATE_LIMIT_MODE=off`;
   - `TITLE_RATE_LIMIT_REQUESTS=5`;
   - `TITLE_RATE_LIMIT_WINDOW_SECONDS=60`;
   - la misma validación de modo `off | observe | enforce` del limitador existente.
4. Crear `title_rate_limiter` y una dependencia `get_title_user` que primero use
   `get_current_user` y después compruebe el límite con `user["sub"]`.
5. Cambiar solamente la dependencia de `generate_title`:

```python
user: dict = Depends(get_title_user)
```

6. Mantener el resto de endpoints de conversaciones con `get_current_user`; listar, cargar o
   guardar mensajes no llama al LLM y no debe consumir ninguna cuota.
7. No modificar `query_rate_limiter`, `get_query_user` ni las variables `RAG_RATE_LIMIT_*`.

Esta separación evita que una generación de título reduzca la cuota disponible para una consulta
jurídica si `RAG_RATE_LIMIT_MODE` ya estuviera activo en algún entorno. Con el nuevo modo de
títulos en `off` no debe existir ningún cambio observable. No modificar variables de AWS ni
activar `observe` o `enforce` en esta tarea.

#### Pruebas

- Verificar que `generate-title` conserva autenticación y validación de propiedad de la
  conversación.
- Con `TITLE_RATE_LIMIT_MODE=off`, una llamada válida mantiene el mismo resultado.
- Con `enforce` en una instancia aislada de prueba, el exceso produce `429` y `Retry-After`.
- Consumir cuota de títulos no modifica el estado del limitador RAG y viceversa.
- No llamar a un proveedor LLM real desde la prueba; sustituirlo por un fake.

### 2.2. Añadir un limitador independiente para login

**Hallazgo confirmado:** no existe protección local contra intentos repetidos. No reutilizar la
misma instancia del limitador RAG, porque mezclar login y consultas haría que una actividad
bloqueara la otra.

#### Archivos

- `backend/rag/config.py`
- `backend/rag/api/rate_limit.py`
- `backend/rag/api/routes/auth.py`
- `.env.example`
- `tests/unit/test_rate_limit.py`

#### Modificación requerida

1. Reutilizar la misma implementación de ventana deslizante generalizada en 2.1. No duplicar su
   algoritmo ni crear otra clase.
2. Verificar mediante las pruebas existentes que la generalización no alteró el mensaje,
   `Retry-After`, aislamiento por clave ni comportamiento del limitador RAG.
3. Añadir configuración independiente:
   - `AUTH_RATE_LIMIT_MODE`, valor predeterminado `off`;
   - `AUTH_RATE_LIMIT_REQUESTS=10`;
   - `AUTH_RATE_LIMIT_WINDOW_SECONDS=300`;
   - usar la misma validación de `off | observe | enforce` que el limitador RAG.
4. Crear una instancia independiente `login_rate_limiter`.
5. En el endpoint `login`, recibir también el objeto `Request` de FastAPI y comprobar el límite
   antes de ejecutar la consulta y `bcrypt`.
6. Construir una clave opaca a partir de:
   - email ya normalizado;
   - `request.client.host` cuando esté disponible;
   - un valor estable como `"unknown"` si no existe cliente.
7. Hashear esa combinación con SHA-256. No guardar ni registrar el correo o IP sin procesar.
8. Contar todos los intentos, exitosos o fallidos, para no revelar si el usuario existe.
9. Conservar exactamente el mismo `401` genérico para credenciales incorrectas.
10. Documentar en el código que el limitador es local al proceso.

#### Activación

- El código debe quedar en `off` por defecto.
- No activar `enforce` hasta observar el comportamiento real y confirmar cómo llega
  `request.client.host` detrás del proxy actual.
- No modificar ni asumir valores de estas variables en AWS durante esta tarea.
- No confiar directamente en `X-Forwarded-For` dentro de esta tarea: usarlo sin una política de
  proxies confiables permitiría falsificar la clave.

#### Pruebas

- `off` nunca bloquea.
- Las claves de dos emails diferentes están aisladas.
- Las claves del mismo email desde clientes diferentes están aisladas.
- `observe` registra sin bloquear.
- `enforce` devuelve `429` y `Retry-After` después del umbral.
- Los limitadores de login, títulos y consultas no comparten eventos ni bloqueos.
- Los logs y errores nunca contienen email, IP o contraseña.

### 2.3. Traducir correctamente la carrera de email duplicado

**Hallazgo confirmado:** el `SELECT` previo no elimina la carrera entre dos transacciones. La
restricción única protege los datos, pero hoy la segunda solicitud puede terminar como `500`.

#### Archivos

- `backend/rag/api/routes/auth.py`
- `backend/rag/api/routes/admin.py`
- pruebas nuevas para registro y creación administrativa.

#### Modificación requerida

1. Importar `IntegrityError` desde `sqlalchemy.exc`.
2. Envolver únicamente el `session.commit()` que inserta el usuario.
3. Ante `IntegrityError`:
   - ejecutar siempre `await session.rollback()`;
   - volver a consultar el email normalizado;
   - si ahora existe, devolver el mismo `409` que ya usa el flujo normal;
   - si no existe, registrar el error sin información sensible y volver a lanzar la excepción
     original con `raise`, no con `raise exc`.
4. No convertir todo `IntegrityError` de forma incondicional en “email duplicado”, porque podría
   ocultar otra restricción o un defecto del modelo.
5. Mantener los mensajes actuales de cada endpoint para no romper consumidores.

#### Pruebas

- Simular que el `commit` falla por unicidad y que la consulta posterior encuentra el email:
  debe obtenerse `409` y debe haberse ejecutado `rollback`.
- Simular un `IntegrityError` sin email existente: debe propagarse, no enmascararse como `409`.
- Verificar el registro público y la creación admin por separado.

---

## Fase 3 — Limpieza segura y mitigación del corpus sin reindexar

### 3.1. Eliminar la tool de recuperación que ya no se ejecuta

**Hallazgo confirmado:** el grafo actual es determinista y llama directamente a
`get_ensemble_retriever`. No hay `bind_tools`, importadores de `retrieve` ni usos de
`ALL_TOOLS`.

#### Archivos

- `backend/rag/core/tools.py`
- `docs/AGENTS.md`
- cualquier otra documentación encontrada mediante `rg`.

#### Modificación requerida

1. Antes de borrar, repetir:

```bash
rg -n "ALL_TOOLS|from .*tools import .*retrieve|\\bretrieve\\(" backend tests docs
```

2. Eliminar únicamente:
   - la función decorada `@tool retrieve`;
   - `ALL_TOOLS`;
   - imports que queden sin uso: `Annotated`, `ToolMessage`, `InjectedToolCallId`, `tool`,
     `InjectedState`, `Command` y `get_ensemble_retriever`, según corresponda.
3. Conservar sin cambios funcionales:
   - `sanitize_replacement_chars`;
   - `build_context_block`.
4. Reescribir el docstring del módulo para indicar que contiene sanitización y construcción del
   contexto utilizado por el grafo determinista.
5. Actualizar `docs/AGENTS.md`:
   - eliminar la descripción ReAct/tool-calling del agente;
   - documentar `enrich_query → retrieve_forced → generate` para consultas dentro del dominio;
   - documentar la respuesta directa para conversación, aclaración y fuera de alcance;
   - reemplazar referencias obsoletas a Firestore por la base SQL actual.
6. No modificar `llm_factory.py` solo porque mencione soporte de structured output/tool calling;
   ese soporte puede seguir siendo utilizado por proveedores y enriquecimiento estructurado.

#### Pruebas

- `test_generator.py` y `test_context_block_doctype.py` deben seguir pasando.
- Ejecutar toda la suite para demostrar que ningún camino dependía de la tool.

### 3.2. Eliminar `rehype-raw`

**Hallazgo confirmado:** la dependencia está instalada, pero `AssistantBubble` usa solamente
`ReactMarkdown` y `remarkGfm`.

#### Modificación requerida

1. Eliminar `rehype-raw` de `frontend/package.json` usando el gestor del workspace:

```bash
cd frontend
bun remove rehype-raw
```

2. Confirmar que el `bun.lock` del workspace fue actualizado.
3. Verificar mediante `rg` que no existan importaciones.
4. No añadir `rehype-sanitize`: no se necesita mientras el HTML crudo siga deshabilitado.
5. No activar `rehypeRaw` en `ReactMarkdown`.

#### Pruebas

- TypeScript, ESLint y build de producción.
- Renderizar una respuesta que contenga `<script>alert(1)</script>` y comprobar que no se ejecuta
  como HTML.

### 3.3. Filtrar únicamente chunks sin contenido alfanumérico

El respaldo más reciente contiene fragmentos cuyo texto es solo `.`, `|'`, separadores de tabla
o puntuación. Algunos tienen resúmenes enriquecidos que parecen jurídicos, por lo que pueden
entrar en BM25 o búsqueda vectorial aunque no aporten evidencia.

Esta mitigación debe ser deliberadamente conservadora para no eliminar artículos breves,
encabezados útiles ni cláusulas válidas.

#### Archivo

- `backend/rag/core/retriever.py`
- `tests/unit/test_retriever_limit.py` o un archivo nuevo específico.

#### Modificación requerida

1. Crear una función pura, por ejemplo:

```python
def _has_retrievable_content(text: str) -> bool:
    return any(character.isalnum() for character in text)
```

2. En `HybridEnsembleRetriever._get_relevant_documents`, conservar el cálculo RRF actual.
3. Después de ordenar todos los IDs por puntuación, construir el resultado iterativamente:
   - omitir documentos cuyo `page_content` no tenga ningún carácter alfanumérico;
   - seguir recorriendo candidatos para completar `max_results`;
   - detenerse al alcanzar `max_results`.
4. No filtrar por una longitud mínima general.
5. No modificar embeddings, BM25, pesos RRF, `k`, `k_candidates` ni el índice.
6. No deduplicar todavía textos idénticos de fuentes diferentes. En el dominio jurídico, dos
   decisiones pueden citar el mismo párrafo y una deduplicación global podría eliminar evidencia
   de una fuente distinta. La deduplicación documental debe resolverse durante una reindexación
   controlada mediante identificadores jurídicos canónicos.

#### Pruebas

- Si los primeros candidatos son `.`, `|---|` o espacios, deben omitirse y completarse el
  resultado con candidatos válidos posteriores.
- Un texto breve pero válido, como `"Prohíbese pescar."`, debe conservarse.
- El orden relativo de los candidatos válidos no debe cambiar.
- Nunca deben devolverse más de `max_results`.
- Si todos los candidatos son estructurales, el resultado debe ser vacío y el agente debe usar
  su respuesta de ausencia de evidencia.

### 3.4. Herramienta opcional de auditoría del respaldo

No crear esta herramienta en la implementación actual. Si se autoriza en una tarea separada, se
puede añadir, sin afectar producción, un script de solo lectura como
`scripts/audit_chroma_backup.py` que reciba un `.jsonl.gz` y reporte:

- manifiesto y cantidad real;
- conteo por `doc_type`;
- IDs duplicados;
- dimensión y validez de embeddings;
- cobertura de metadata común;
- documentos sin contenido alfanumérico;
- distribución de longitudes;
- duplicados exactos por hash, sin imprimir documentos completos ni host remoto.

Debe usar solo la biblioteca estándar, no conectarse a Chroma y no escribir sobre el respaldo.

---

## Fase 4 — Optimización de feedback administrativo, diseño futuro no autorizado

El problema existe, pero la solución sugerida en el informe —aplicar directamente
`LIMIT/OFFSET` y un `COUNT`— es incompleta. Los filtros de rating se aplican actualmente sobre
columnas JSON en Python y la respuesta incluye distribuciones y promedios sobre **todo** el
conjunto filtrado. Paginar antes de aplicar esos filtros cambiaría el contrato y produciría
estadísticas incorrectas.

No implementar esta fase en la ejecución actual ni junto con seguridad, autenticación o RAG.

Si se aprueba posteriormente, usar un enfoque compatible con SQLite y PostgreSQL:

1. Construir una consulta base con los filtros de fecha.
2. Consultar únicamente `id`, `ratings` y el campo de orden para el universo candidato, no todos
   los modelos ORM con comentarios y textos.
3. Aplicar los filtros JSON actuales sobre esas filas livianas.
4. Calcular `total`, promedios y distribuciones sobre todos los IDs elegibles.
5. Seleccionar los IDs de la página solicitada conservando el orden.
6. Hacer una segunda consulta ORM solo para los IDs de esa página.
7. Restaurar explícitamente el orden de la página si un `WHERE id IN (...)` lo altera.
8. Mantener exactamente `AdminFeedbackResponse` y `AdminMessageFeedbackResponse`.

No introducir expresiones JSON específicas de PostgreSQL mientras las pruebas locales dependan
de SQLite, salvo que se implemente y pruebe una abstracción por dialecto.

Pruebas necesarias:

- más filas que `page_size`;
- filtros de fecha;
- cada combinación de rating mínimo/máximo;
- total, promedios y distribuciones calculados sobre todo el conjunto filtrado;
- página vacía más allá del final;
- mismo resultado en SQLite y PostgreSQL si hay un entorno de integración disponible.

---

## Cambios que no deben implementarse ahora

### Purga o LRU directa de `MemorySaver`

El crecimiento en memoria es un riesgo real, pero la solución del informe no es suficientemente
segura para aplicarla sin diseño adicional:

- `MemorySaver` mantiene `storage`, `writes` y `blobs`; limpiar solo `storage` deja datos
  huérfanos.
- Una tarea periódica podría purgar un hilo mientras una consulta SSE está activa.
- No existe actualmente un registro de hilos activos ni una operación atómica de expulsión.
- Depender de atributos internos de LangGraph crea acoplamiento con una versión concreta.

En esta implementación no modificar `MemorySaver`, no añadir tareas periódicas y no inspeccionar
sus atributos internos ni siquiera para métricas. La observabilidad también debe diseñarse en una
tarea independiente para evitar dependencias accidentales de detalles internos.

Una solución futura deberá ser un cambio independiente y demostrar:

1. eliminación coordinada de `storage`, `writes` y `blobs`;
2. exclusión de hilos con solicitudes activas;
3. sincronización segura;
4. hidratación correcta desde SQL después de expulsar un hilo;
5. límite configurable y desactivable;
6. pruebas de concurrencia y streaming.

Un checkpointer PostgreSQL sigue siendo una alternativa futura, pero necesita dependencia,
tablas/migración y despliegue coordinado; no pertenece al alcance actual.

### CORS

El despliegue actual funciona y usa autenticación Bearer. No se ha demostrado un defecto de CORS
en ese flujo que justifique cambiarlo junto con los hallazgos prioritarios.

No retirar `allow_credentials=True` sin inventariar primero consumidores externos. Si más
adelante se necesita configurar orígenes, añadir `CORS_ALLOWED_ORIGINS` con el valor actual
`http://localhost:3000` como predeterminado y probar explícitamente clientes locales y
desplegados. No usar `*` con credenciales y no introducir HTTPS obligatorio.

### Reindexación, OCR y pipeline de ingesta

No modificar datos ni el proyecto `ingesta` en esta implementación. Para el integrante
responsable de la futura reindexación queda documentado que debe considerar:

- eliminar o unir chunks estructurales antes del enriquecimiento;
- deduplicar por radicado/instancia en jurisprudencia y tipo/número/año en normativa;
- corregir el documento con caracteres `Æ`, `Ø`, `œ` y `æ`;
- normalizar Unicode NFC antes de generar IDs;
- unificar metadata jurídica;
- evaluar el tamaño de chunk con preguntas reales;
- reconstruir una colección limpia en lugar de limitarse a agregar IDs nuevos.

La mitigación 3.3 funciona en tiempo de consulta y no sustituye esa depuración futura.

### Diversidad forzada por fuente

No añadir todavía un máximo rígido de chunks por fuente. Una respuesta jurídica puede necesitar
varios fragmentos consecutivos del mismo artículo o sentencia. Antes de imponer diversidad, crear
un conjunto de evaluación que mida cobertura y fidelidad de citas.

---

## Pruebas y criterios de no regresión

Después de cada fase ejecutar:

```bash
uv run pytest tests/unit -q
uv run ruff check backend tests
uv run mypy backend/rag
git diff --check
```

Para el frontend:

```bash
cd frontend
npx tsc --noEmit
npx eslint .
npm run build
```

Comprobaciones funcionales mínimas:

1. Login correcto e incorrecto conservan los mismos contratos.
2. Registro deshabilitado continúa devolviendo `403`.
3. Cambio de usuario no conserva mensajes ni conversación activa.
4. Sesión expirada muestra el login y no deja el chat bloqueado.
5. `/api/query` y `/api/query/stream` funcionan igual con límites en `off`.
6. Preguntas dentro del dominio siguen recuperando fuentes y citas `[docN]`.
7. Preguntas fuera del dominio siguen rechazándose sin fuentes.
8. Un candidato cuyo contenido sea solo `.` no llega al contexto del LLM.
9. Un artículo corto válido sí puede recuperarse.
10. El Markdown de la respuesta no ejecuta HTML crudo.
11. Los endpoints admin mantienen autenticación y autorización.
12. No se creó ninguna migración, conexión nueva o cambio de infraestructura.

Las pruebas de humo contra AWS son opcionales y deben ejecutarse únicamente con credenciales y
URL explícitas. Deben seguir usando consultas sin `conversation_id` para no crear datos
persistentes.

## Revisión final antes de entregar

La IA implementadora debe entregar:

1. resumen por fase de los archivos modificados;
2. explicación de por qué cada cambio conserva compatibilidad;
3. nuevas pruebas agregadas y resultados completos;
4. cualquier validación que no pudo ejecutar y la causa exacta;
5. confirmación de que no modificó HTTP, AWS, Ollama, ChromaDB, índices, embeddings o datos;
6. `git status --short` final;
7. confirmación explícita de que no hizo commit ni push.

Si durante la implementación aparece una necesidad de ampliar el alcance, detenerse y solicitar
aprobación. No sustituir una corrección pequeña por una reescritura.
