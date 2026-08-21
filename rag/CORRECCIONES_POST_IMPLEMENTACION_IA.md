# Correcciones posteriores a la implementación de las fases 0–3

## Objetivo

Corregir únicamente los hallazgos detectados durante la revisión del commit
`6507684` (`update: backend`), actualmente publicado en `origin/v2`, sin
reescribir el historial ni modificar las funcionalidades que ya funcionan.

La implementación de las fases 0–3 es mayoritariamente correcta. Este documento
no autoriza una refactorización general: solicita un cambio de seguimiento
pequeño, aislado y verificable.

## Restricciones obligatorias

1. Trabajar sobre el estado actual de la rama `v2`.
2. No usar `reset`, `rebase`, `commit --amend`, `push --force` ni ninguna acción
   que reescriba el commit ya publicado.
3. No hacer commit ni push salvo autorización expresa del usuario.
4. Conservar HTTP. No añadir HTTPS obligatorio, HSTS ni cookies `Secure`.
5. No modificar AWS Academy, Ollama, ChromaDB, índices, embeddings ni datos.
6. No reindexar documentos ni modificar el proyecto de ingesta.
7. No modificar prompts, clasificación temática, recuperación RRF, BM25, pesos,
   `k`, `k_candidates` ni el grafo determinista del RAG.
8. No modificar CORS, `MemorySaver`, infraestructura o migraciones.
9. Preservar los contratos HTTP y los mensajes actuales, salvo los mensajes de
   `429` incorrectos indicados expresamente en este documento.
10. No introducir un framework de pruebas de frontend en esta corrección.
11. No incluir tokens, contraseñas, correos o direcciones IP en nuevos logs,
    mensajes de error o fixtures. No retirar los correos de las respuestas y
    pantallas administrativas donde forman parte de la funcionalidad existente.

## Línea base que debe reproducirse antes de editar

Ejecutar:

```bash
git status --short --branch
uv run pytest tests/unit -q
uv run ruff check backend tests
uv run mypy backend/rag
cd frontend
npx tsc --noEmit
npx eslint .
npm run build
```

La referencia revisada es:

- 82 pruebas unitarias aprobadas;
- Ruff aprobado;
- MyPy aprobado;
- TypeScript aprobado;
- ESLint aprobado;
- build de producción de Next.js aprobado cuando el entorno permite descargar
  las fuentes utilizadas por `next/font`;
- tres pruebas de humo omitidas si no se proporcionan URL y token.

No ejecutar pruebas contra AWS sin credenciales y URL proporcionadas
expresamente.

---

## Corrección 1 — Impedir que `/api/auth/me` aplique una respuesta obsoleta

### Problema confirmado

`AuthProvider.validateSession()` captura el token utilizado en la llamada a
`/api/auth/me`, pero aplica un `200`, un fallo transitorio o la identidad
almacenada comprobando únicamente `cancelled`.

Si el token cambia mientras la solicitud está en curso, una respuesta tardía de
la sesión A podría sobrescribir la sesión B o restaurar una sesión que ya se
cerró desde otra pestaña.

El plan aprobado exigía comprobar que el token enviado continuara siendo el
token activo antes de aplicar cualquier resultado.

### Archivo

- `frontend/components/providers/AuthProvider.tsx`

### Modificación requerida

1. Dentro de `validateSession`, después de capturar `const token = getToken()`,
   crear una comprobación local equivalente a:

```tsx
const canApplyResult = () => !cancelled && getToken() === token;
```

2. Mantener el tratamiento actual del `401` mediante
   `expireAuthSession(token, ...)`; esa función ya comprueba la coincidencia.
3. Antes de ejecutar `setUser(getStoredUser())` por un estado distinto de `401`
   o por un error de red, exigir `canApplyResult()`.
4. Después de leer el JSON de un `200` y antes de ejecutar `setAuth` o `setUser`,
   volver a exigir `canApplyResult()`. La comprobación debe hacerse después del
   `await res.json()` porque el token también puede cambiar durante esa espera.
5. `finally` debe seguir terminando `loading` cuando el componente continúe
   montado. No debe reactivar ni copiar datos de una sesión anterior.
6. No añadir renovación de JWT, decodificación del token o listeners nuevos de
   almacenamiento en esta corrección.

### Criterios de aceptación

- Un `200` de un token que sigue activo actualiza el usuario normalmente.
- Un `401` del token activo limpia la sesión y muestra el modal.
- Una respuesta tardía perteneciente a un token distinto no modifica el token,
  el usuario ni el mensaje de sesión actual.
- Un error de red conserva la identidad almacenada solamente si el token no ha
  cambiado.
- El login y logout actuales mantienen su comportamiento.

### Validación manual de la respuesta tardía

1. Iniciar sesión como usuario A en dos pestañas.
2. En una pestaña, ralentizar temporalmente la solicitud `/api/auth/me` y
   recargarla para que la respuesta de A quede pendiente.
3. En la otra pestaña, cerrar la sesión de A e iniciar sesión como B.
4. Permitir que finalice la respuesta pendiente de A.
5. Verificar que el token y usuario almacenados continúan siendo los de B. La
   respuesta antigua puede finalizar el estado de carga de su pestaña, pero no
   puede restaurar A ni sobrescribir B.

---

## Corrección 2 — Cerrar el estado React cuando falta el token

### Problema confirmado

`throwIfSessionExpired(response, requestToken)` no emite el evento cuando
`requestToken` es `null`. Además, varios flujos terminan anticipadamente cuando
no encuentran token y solo muestran un error o limpian listas.

Esto permite que, por ejemplo, otra pestaña elimine `localStorage` mientras la
pestaña actual conserva `user` en React. La siguiente operación falla, pero el
chat puede continuar montado y no vuelve a mostrar el login.

### Archivos principales

- `frontend/lib/auth.ts`
- `frontend/lib/api.ts`
- `frontend/hooks/useChat.ts`
- `frontend/hooks/useConversations.ts`
- `frontend/components/chat/ConversationList.tsx`
- componentes administrativos que salen anticipadamente por falta de token.

### Modificación requerida

1. Mover el texto común a una constante exportada en `frontend/lib/auth.ts`, por
   ejemplo:

```tsx
export const SESSION_EXPIRED_MESSAGE =
  "Tu sesión expiró. Inicia sesión nuevamente.";
```

2. Cambiar la firma a:

```tsx
expireAuthSession(expectedToken: string | null, message = SESSION_EXPIRED_MESSAGE)
```

3. Conservar este orden dentro de `expireAuthSession`:
   - si no existe `window`, retornar `false`;
   - comparar `getToken()` con `expectedToken`, incluso cuando ambos sean
     `null`;
   - si no coinciden, retornar `false`;
   - si coinciden, ejecutar `clearAuth()`, emitir el evento sin incluir el token
     y retornar `true`.
4. En `throwIfSessionExpired`, ante cualquier `401`, llamar siempre a
   `expireAuthSession(requestToken)`; eliminar la condición
   `if (requestToken)`.
5. Mantener el comportamiento del login: el `401` de `/api/auth/login` no debe
   usar este helper porque significa credenciales incorrectas.
6. En cada flujo autenticado que retorna antes de hacer `fetch` porque no existe
   token, llamar primero a `expireAuthSession(null)`. Revisar como mínimo:
   - `queryRagStream`;
   - `_createConversation`, `submit` y `loadConversation` en `useChat`;
   - `refresh` en `useConversations` cuando todavía existe `user`;
   - edición/eliminación de conversaciones;
   - páginas administrativas que detectan `!token`.
7. No emitir el aviso cuando no existe usuario React y simplemente se está
   mostrando el login inicial. La señal es necesaria cuando un flujo
   autenticado descubre que perdió su token.
8. No cerrar la sesión por `403`, `404`, `409`, `422`, `429`, `5xx` o errores de
   red.

### Casos manuales obligatorios

1. Iniciar sesión y comprobar que el chat funciona normalmente.
2. Abrir dos pestañas con la misma sesión.
3. Cerrar sesión en la primera pestaña.
4. En la segunda pestaña, intentar cargar o enviar una conversación.
5. Verificar que aparece el modal de login y que se desmonta el chat anterior.
6. Confirmar que una contraseña incorrecta solo muestra el error de credenciales.
7. Confirmar que un `403` administrativo y un `429` no cierran una sesión válida.

---

## Corrección 3 — Reescribir las pruebas de carrera de email

### Problema confirmado

Las pruebas denominadas `masks_concurrent_duplicate_email_as_conflict` insertan
el usuario competidor antes de ejecutar el primer `SELECT`. Por ello, el endpoint
encuentra el email en la comprobación inicial y devuelve `409` sin ejecutar el
`commit` ni el bloque `except IntegrityError` que la prueba afirma validar.

La cobertura dirigida confirmó que las líneas del `commit`, `rollback` y
reconsulta no se ejecutan en esas dos pruebas.

El código de producción parece correcto, pero la evidencia de prueba es
insuficiente.

### Archivo

- `tests/unit/test_email_race_conditions.py`

### Modificación requerida

1. Reemplazar las dos pruebas engañosas por pruebas controladas del flujo exacto.
2. Para registro y creación administrativa, construir una sesión simulada con:
   - primer `session.execute`: resultado cuyo `scalar_one_or_none()` sea `None`;
   - `session.commit`: `AsyncMock` que lance una instancia concreta de
     `sqlalchemy.exc.IntegrityError`;
   - `session.rollback`: `AsyncMock`;
   - segundo `session.execute`: resultado que contenga el usuario competidor.
3. Ejecutar el endpoint y comprobar:
   - respuesta `409` con el mensaje ya existente;
   - `commit` esperado exactamente una vez;
   - `rollback` esperado exactamente una vez;
   - dos consultas `execute` en el orden correcto.
4. Añadir el caso no relacionado para ambos endpoints:
   - primer y segundo `execute` no encuentran el email;
   - `commit` lanza una instancia conocida de `IntegrityError`;
   - se ejecuta `rollback`;
   - se propaga la misma instancia, no un `409`.
5. Se pueden conservar las pruebas con SQLite como pruebas adicionales, pero no
   deben presentarse como validación de la carrera si no fuerzan el error en el
   `commit`.
6. No cambiar el código de producción salvo que las nuevas pruebas revelen un
   defecto real.

### Construcción sugerida del error

```python
integrity_error = IntegrityError(
    "INSERT INTO users ...",
    {},
    Exception("unique violation"),
)
```

Usar `AsyncMock`/`MagicMock` de `unittest.mock`; no añadir nuevas dependencias.

---

## Corrección 4 — Mensajes y configuración de los limitadores

### Problemas confirmados

1. `SlidingWindowRateLimiter` devuelve siempre el mensaje de “límite de
   consultas”, incluso para login y generación de títulos.
2. Si se activa el limitador de login, el formulario mostraría un mensaje
   semánticamente incorrecto.
3. El plan aprobado indicó `TITLE_RATE_LIMIT_REQUESTS=5`, pero el código y
   `.env.example` usan `10`.

Los tres limitadores están actualmente en `off`, por lo que esta corrección no
debe producir ningún bloqueo nuevo.

### Archivos

- `backend/rag/api/rate_limit.py`
- `backend/rag/config.py`
- `.env.example`
- `tests/unit/test_rate_limit.py`

### Modificación requerida

1. Permitir que `SlidingWindowRateLimiter.__init__` reciba un `detail` de `429`
   y una etiqueta de alcance para logs, con valores predeterminados que
   conserven exactamente el mensaje actual del limitador RAG.
2. Usar mensajes independientes y genéricos, sin incluir claves ni datos
   sensibles:
   - consultas RAG: conservar el texto actual;
   - títulos: indicar temporalmente el límite de generación de títulos;
   - login: indicar temporalmente el límite de intentos de inicio de sesión.
3. Los logs pueden incluir una etiqueta estática como `query`, `title` o
   `login`, pero nunca email, IP, contraseña o token. Para login, si se conserva
   la clave opaca, debe continuar siendo únicamente el SHA-256.
4. Cambiar el valor predeterminado de `TITLE_RATE_LIMIT_REQUESTS` a `5` tanto en
   `backend/rag/config.py` como en `.env.example`.
5. No modificar `RAG_RATE_LIMIT_*`, `AUTH_RATE_LIMIT_*` ni valores de AWS.
6. Mantener las tres instancias independientes y sus modos predeterminados en
   `off`.
7. El modo `off` debe retornar antes de adquirir locks, guardar eventos o
   escribir logs, como ocurre actualmente.

### Pruebas requeridas

- El alias `QueryRateLimiter` sigue funcionando.
- El limitador RAG conserva exactamente su detalle actual.
- Títulos y login devuelven sus respectivos detalles en modo `enforce`.
- `Retry-After` continúa presente.
- Las tres instancias no comparten eventos.
- `off` nunca bloquea ni registra.
- Los logs de login no contienen email, IP ni contraseña.

---

## Corrección 5 — Referencia obsoleta en la documentación

### Archivo

- `docs/AGENTS.md`

### Modificación requerida

Reemplazar la frase que afirma que el frontend requiere variables Firebase como
argumentos de build. El `docker/Dockerfile.frontend` actual solo declara
`NEXT_PUBLIC_API_URL`.

La documentación debe indicar que:

- el backend usa el `.env` raíz;
- el frontend puede recibir `NEXT_PUBLIC_API_URL` durante el build;
- no se requieren variables Firebase para el Dockerfile actual.

En `backend/rag/core/tools.py`, ajustar también el docstring para aclarar que la
recuperación siempre ocurre únicamente en consultas clasificadas como
`in_scope`; conversación, aclaración y fuera de alcance no recuperan documentos.

Estos son cambios documentales, sin modificar comportamiento.

---

## Validación final obligatoria

Después de implementar todas las correcciones:

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

También ejecutar:

```bash
rg -n "fetch\\(" frontend --glob '!node_modules/**' --glob '!.next/**'
rg -n "Firebase|Firestore" docs/AGENTS.md || true
```

La segunda búsqueda no debe encontrar referencias activas en `docs/AGENTS.md`;
`|| true` evita confundir la ausencia esperada de coincidencias con un fallo de
la validación.

Revisar cada `fetch` autenticado y cada retorno temprano por falta de token. Las
únicas llamadas que no deben tratar su `401` como expiración son
`/api/auth/login`; `/api/auth/me` mantiene su manejo explícito y seguro dentro
de `AuthProvider`.

## Criterios para aprobar el cambio

1. La línea base continúa en verde. Deben existir al menos 82 pruebas; el total
   puede mantenerse si las pruebas defectuosas se reemplazan una por una. No
   añadir pruebas artificiales solo para aumentar el contador.
2. Una respuesta obsoleta de `/api/auth/me` nunca escribe otra sesión.
3. La pérdida del token desmonta el chat y muestra el login.
4. Un `401` de login incorrecto no se interpreta como expiración.
5. Estados distintos de `401` no cierran sesión.
6. Las pruebas de carrera ejecutan realmente `commit → IntegrityError →
   rollback → reconsulta`.
7. Los limitadores siguen independientes y desactivados por defecto.
8. No se modificaron HTTP, AWS, ChromaDB, Ollama, datos, índices o ingesta.
9. No se reescribió el commit `6507684` ni el historial de `origin/v2`.

## Entrega requerida a la IA implementadora

Al finalizar, reportar:

1. archivos modificados y explicación breve de cada corrección;
2. pruebas nuevas o reescritas;
3. resultados completos de pytest, Ruff, MyPy, TypeScript, ESLint y build;
4. casos manuales ejecutados y resultado;
5. validaciones no ejecutadas y motivo exacto;
6. `git status --short --branch` final;
7. confirmación de que no hizo commit, push ni reescritura de historial;
8. confirmación de que no modificó los componentes fuera de alcance.

Si una corrección exige ampliar el alcance, detenerse y solicitar aprobación.
