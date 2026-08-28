# Informe — Correcciones posteriores a la implementación de las fases 0–3

Corrige los 5 hallazgos de `CORRECCIONES_POST_IMPLEMENTACION_IA.md` sobre el
commit `6507684` (`update: backend`, ya publicado en `origin/v2`). No se hizo
`reset`, `rebase`, `commit --amend` ni `push --force`; no se reescribió ese
commit ni el historial de `origin/v2`.

Esta versión del informe además incorpora una ronda de retroalimentación
tuya sobre mi entrega anterior de estas mismas correcciones: fortalece las
4 pruebas simuladas de carrera para verificar el orden exacto de llamadas
(no solo el conteo), agrega `_claude_sync/` a `.gitignore` (17º archivo
modificado, fuera de `rag/`), corrige un error aritmético que tenía este
mismo informe, y aclara que los datos de prueba (correos/IPs/contraseñas)
son sintéticos. Los detalles de cada punto están en las secciones
correspondientes abajo.

## 1. Archivos modificados y explicación breve

### Corrección 1 — `/api/auth/me` ya no aplica una respuesta obsoleta

- **`frontend/components/providers/AuthProvider.tsx`** — `validateSession()`
  captura `token` al inicio y define `canApplyResult = () => !cancelled &&
  getToken() === token`. Esa comprobación se exige de nuevo justo antes de
  aplicar cualquier resultado no-401 (`setUser(getStoredUser())` en el
  fallback transitorio/de red, y `setAuth`+`setUser` tras leer el JSON del
  200 — repetida después del `await res.json()`, porque el token también
  puede cambiar durante esa espera). El 401 sigue usando
  `expireAuthSession(token, ...)`, que ya hace su propia comprobación de
  token. El `finally` sigue terminando `loading` con solo `!cancelled`
  (nunca reactiva ni copia datos de una sesión anterior).

### Corrección 2 — cerrar el estado React cuando falta el token

- **`frontend/lib/auth.ts`** — se exporta `SESSION_EXPIRED_MESSAGE` (único
  punto de definición). `expireAuthSession` ahora acepta
  `expectedToken: string | null` con `message` por defecto = ese texto;
  compara `getToken() !== expectedToken` incluso cuando ambos son `null`.
- **`frontend/lib/api.ts`** — importa `SESSION_EXPIRED_MESSAGE` de
  `lib/auth.ts` en vez de duplicarlo. `throwIfSessionExpired` llama siempre a
  `expireAuthSession(requestToken)` ante un 401 (se quitó el `if
  (requestToken)`). `queryRagStream` llama a `expireAuthSession(null)` antes
  de lanzar cuando descubre que no hay token.
- **`frontend/hooks/useChat.ts`** — `_createConversation`, `submit` y
  `loadConversation` llaman a `expireAuthSession(null)` cuando descubren
  `!token` mientras `user` (el estado React) sigue siendo no nulo.
- **`frontend/hooks/useConversations.ts`** — `refresh()` separa el caso
  `!token` (notifica solo si `user` sigue siendo no nulo — no en el estado
  inicial normal antes de iniciar sesión) del caso `!user`.
- **`frontend/components/chat/ConversationList.tsx`** — `saveEdit` y
  `confirmDelete` llaman a `expireAuthSession(null)` en el `else` cuando no
  hay token (este componente solo se renderiza autenticado).
- **`frontend/app/admin/page.tsx`**, **`.../admin/feedback/page.tsx`**,
  **`.../admin/message-feedback/page.tsx`** — el `load()`/efecto de cada
  página llama a `expireAuthSession(null)` antes de lanzar `"Sin sesión"`
  cuando `!token`.
- Ningún 401 de `/api/auth/login` pasa por este mecanismo (sigue siendo
  "credenciales incorrectas"); `/api/auth/me` conserva su manejo explícito
  dentro de `AuthProvider` (Corrección 1), no usa `throwIfSessionExpired`.

### Corrección 3 — pruebas de carrera de email reescritas

- **`tests/unit/test_email_race_conditions.py`** — las dos pruebas
  `..._masks_concurrent_duplicate_email_as_conflict` (registro y admin) se
  reescribieron con una sesión simulada (`unittest.mock.AsyncMock`/
  `MagicMock`) que fuerza el `IntegrityError` exactamente en
  `session.commit()`. Se añadieron dos pruebas nuevas
  (`..._unrelated_to_email_race_mocked`) para el caso no relacionado: dos
  `execute` sin encontrar el email, `commit` lanza un `IntegrityError`
  conocido, se relanza la misma instancia (no 409). Las cuatro pruebas
  simuladas no solo cuentan cuántas veces se llamó cada método
  (`commit`/`rollback` una vez, dos `execute`): la sesión simulada registra
  en una lista (`call_order`) el momento exacto de cada llamada a
  `execute`/`commit`/`rollback`, y cada prueba afirma
  `call_order == ["execute", "commit", "rollback", "execute"]` — es decir, la
  secuencia exacta que produce el bloque real `try/except IntegrityError`
  (comprobación inicial, commit que pierde la carrera, rollback, reconsulta),
  no solo conteos que una implementación distinta también podría satisfacer.
  Las dos pruebas SQLite reales
  `..._reraises_integrity_error_unrelated_to_email_race` se conservan sin
  cambios como cobertura adicional (fuerzan un `IntegrityError` real vía
  colisión de id, no de email). No se tocó código de producción: la traza
  manual confirmó que `routes/auth.py::register` y
  `routes/admin.py::create_user` ya hacían exactamente lo esperado.

  Todos los correos, contraseñas e IPs usados en este archivo y en
  `tests/unit/test_rate_limit.py` son valores sintéticos de prueba, no datos
  reales: los correos usan el dominio `example.com` (RFC 2606, reservado
  para documentación) y las IPs usan el rango `203.0.113.0/24` (RFC 5737,
  TEST-NET-3, reservado para ejemplos); las "contraseñas" son literales de
  prueba que nunca se envían a ningún servicio externo, solo se comparan en
  memoria dentro de la propia prueba. Ambos archivos incluyen ahora esta
  aclaración en su docstring.

### Corrección 4 — mensajes y configuración de los limitadores

- **`backend/rag/api/rate_limit.py`** — `SlidingWindowRateLimiter.__init__`
  ahora acepta `detail` (texto del 429) y `scope` (etiqueta estática de log,
  nunca datos de usuario), con `detail` por defecto = el texto original del
  limitador de consultas RAG (sin cambio para `query_rate_limiter`).
  `title_rate_limiter` y `login_rate_limiter` reciben su propio `detail`
  ("...límite de generación de títulos...", "...límite de intentos de inicio
  de sesión...") y `scope` ("title", "login"). El log en modo `observe` usa
  `extra={"scope": self.scope}` en vez de la clave cruda.
- **`backend/rag/config.py`** y **`.env.example`** —
  `TITLE_RATE_LIMIT_REQUESTS` por defecto pasó de `10` a `5`, como
  especificaba el plan aprobado. `RAG_RATE_LIMIT_*` y `AUTH_RATE_LIMIT_*` no
  se tocaron. Las tres instancias siguen en modo `off` por defecto.
- **`tests/unit/test_rate_limit.py`** — pruebas nuevas: el limitador de
  consultas conserva su detalle exacto; título y login tienen su propio
  detalle (con `Retry-After` presente en ambos); las tres instancias tienen
  su propio `scope`; `TITLE_RATE_LIMIT_REQUESTS == 5`; `off` nunca adquiere
  el lock ni escribe logs (ni con 5 llamadas seguidas); un log de `observe`
  para login con email/IP/contraseña de prueba no contiene ninguno de los
  tres en el texto del log.

### Corrección 5 — referencias obsoletas en documentación

- **`docs/AGENTS.md`** — la línea sobre Docker ya no afirma que el frontend
  requiere variables Firebase como build args (confirmado contra
  `docker/Dockerfile.frontend`: solo declara `NEXT_PUBLIC_API_URL`). Ahora
  indica que el backend usa `.env` en la raíz y que el frontend puede
  recibir `NEXT_PUBLIC_API_URL` como build arg, sin otras variables
  requeridas por los Dockerfiles actuales.
- **`backend/rag/core/tools.py`** — el docstring del módulo ahora aclara que
  `retrieve_forced` solo se ejecuta para consultas clasificadas como
  `in_scope` por `enrich_query`; `conversation`, `needs_clarification` y
  `out_of_scope` van directo a `respond_without_retrieval` y no recuperan
  documentos (confirmado contra `query_enricher.py` y `agent.py`).

## 2. Pruebas nuevas o reescritas

- `tests/unit/test_email_race_conditions.py`: 4 → 6 pruebas (2 reescritas
  con sesión simulada y verificación de orden exacto de llamadas, 2 nuevas
  para el caso no relacionado simulado).
- `tests/unit/test_rate_limit.py`: **9 → 15 pruebas** (6 nuevas para
  mensajes/scope/config/logs de la Corrección 4). *(Corrección a este mismo
  informe: una versión anterior de este documento decía "15 → 21", conteo
  incorrecto; el conteo correcto, verificado con `pytest --collect-only`, es
  9 → 15.)*
- Total de la suite: **82 → 90 pruebas**, todas en verde.

## 3. Resultados de validación (entorno de revisión, réplica exacta del
   estado actual de `v2` extraída del dispositivo)

```
uv run pytest tests/unit -q     → 90 passed
uv run ruff check backend tests → All checks passed!
uv run mypy backend/rag         → Success: no issues found in 25 source files
cd frontend
npx tsc --noEmit                → sin errores
npx eslint .                    → sin errores
npm run build                   → BLOQUEADO por el entorno (ver abajo)
```

`npm run build` falla con `next/font: error: Failed to fetch 'Inter'/'Geist
Mono' from Google Fonts` — el entorno de revisión bloquea específicamente
`fonts.googleapis.com` (confirmado con `curl`: `CONNECT tunnel failed,
response 403`, mientras que `registry.npmjs.org` sí responde). Es la misma
limitación ya documentada en el diagnóstico y el informe de fases 0–3, no
introducida por esta corrección. No se cambió código para "ocultar" este
problema del entorno.

`rg -n "fetch\(" frontend --glob '!node_modules/**' --glob '!.next/**'` —
revisado manualmente: los 20 `fetch(` autenticados pasan por
`throwIfSessionExpired`/`expireAuthSession`, salvo los dos casos
intencionalmente excluidos (`/api/auth/login`, `/api/auth/me`).

`rg -n "Firebase|Firestore" docs/AGENTS.md` — sin coincidencias.

`git diff --check` (ejecutado en el dispositivo tras escribir los archivos) —
sin errores de espacios en blanco.

## 4. Casos manuales — NO ejecutados

Los 7 casos manuales de la Corrección 2 (dos pestañas, cerrar sesión en una y
verificar que la otra muestra el login) y el caso de respuesta tardía de la
Corrección 1 requieren un servidor backend y frontend corriendo con
navegador interactivo en dos pestañas reales. Esta sesión no tiene acceso a
un navegador interactivo contra un servidor vivo del proyecto (el `backend`
necesita ChromaDB/Ollama reales para levantar completo, y las restricciones
del encargo prohíben tocar esos servicios). Se verificó el mismo
comportamiento por revisión de código: trazado manual línea por línea de
`validateSession`, `expireAuthSession`, `throwIfSessionExpired` y cada sitio
de llamada, confirmando que la lógica implementada satisface cada criterio
de aceptación descrito (respuesta tardía de un token distinto no aplica
resultado; 401 del token activo limpia sesión; error de red conserva
identidad solo si el token no cambió; 403/404/409/422/429/5xx nunca cierran
sesión). Recomiendo que el usuario ejecute los 7 casos manuales contra un
entorno real antes de considerar la corrección definitivamente cerrada.

## 5. `git status --short --branch` final (dispositivo, tras escribir los
   16 archivos, el propio informe, y el ajuste al `.gitignore`)

```
## v2...origin/v2
 M .gitignore
 M rag/.env.example
 M rag/backend/rag/api/rate_limit.py
 M rag/backend/rag/config.py
 M rag/backend/rag/core/tools.py
 M rag/docs/AGENTS.md
 M rag/frontend/app/admin/feedback/page.tsx
 M rag/frontend/app/admin/message-feedback/page.tsx
 M rag/frontend/app/admin/page.tsx
 M rag/frontend/components/chat/ConversationList.tsx
 M rag/frontend/components/providers/AuthProvider.tsx
 M rag/frontend/hooks/useChat.ts
 M rag/frontend/hooks/useConversations.ts
 M rag/frontend/lib/api.ts
 M rag/frontend/lib/auth.ts
 M rag/tests/unit/test_email_race_conditions.py
 M rag/tests/unit/test_rate_limit.py
?? rag/CORRECCIONES_POST_IMPLEMENTACION_IA.md
?? rag/CORRECCIONES_POST_IMPLEMENTACION_INFORME.md
```

(Rutas relativas a la raíz real del repositorio git, un nivel arriba de
`rag/`; `git diff --check` sobre el árbol completo: sin salida, `EXIT:0`,
sin errores de espacios en blanco.)

Exactamente los 16 archivos de las 5 correcciones originales aparecen
modificados (`rag/...` de la lista de arriba), más un 17º cambio esperado
de esta ronda de correcciones: **`.gitignore`** (en la raíz del repo, fuera
de `rag/`), al que se agregó la entrada `_claude_sync/` — es el cambio que
pediste explícitamente en el punto 1 de esta ronda ("Eliminar
`../_claude_sync/` para evitar incluir accidentalmente el archivo
comprimido con `git add .`"). No pude borrar la carpeta `_claude_sync/`
desde aquí (el puente al dispositivo no permite eliminar archivos), así que
en su lugar se excluyó vía `.gitignore`: con eso queda fuera de forma
permanente de `git add .` y de cualquier `git status`, sin que tengas que
borrarla tú mismo — y en efecto ya **no aparece** en el `git status` de
arriba. Los únicos `.md` no rastreados que permanecen son los que decidimos
conservar intencionalmente: `CORRECCIONES_POST_IMPLEMENTACION_IA.md` (tu
encargo original) y este mismo informe,
`CORRECCIONES_POST_IMPLEMENTACION_INFORME.md`. No hay ningún otro archivo
modificado o sin rastrear fuera de esta lista.

## 6. Confirmación: sin commit, sin push, sin reescritura de historial

No se ejecutó `git add`, `git commit`, `git push`, `reset`, `rebase` ni
`commit --amend` en ningún momento de esta corrección. El commit `6507684`
en `origin/v2` permanece exactamente como estaba. Los 16 archivos existen
solo como cambios sin confirmar en el árbol de trabajo, listos para que tú
decidas cuándo y cómo confirmarlos.

## 7. Confirmación: nada tocado fuera de alcance

No se modificó HTTP/HTTPS/HSTS/cookies, AWS Academy, Ollama, ChromaDB,
índices, embeddings, datos del corpus, prompts, clasificación temática,
recuperación RRF/BM25/pesos/k/k_candidates, el grafo determinista del RAG,
CORS, `MemorySaver`, infraestructura ni migraciones. No se introdujo ningún
framework de pruebas de frontend. No se incluyeron tokens, contraseñas,
correos ni direcciones IP en logs, mensajes de error o fixtures nuevos (la
prueba de logs de login lo verifica explícitamente). No se retiraron los
correos de las respuestas/pantallas administrativas existentes.
