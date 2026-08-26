# Informe final — Implementación de hallazgos confirmados (Fases 0–3)

Fecha: 2026-08-20
Alcance ejecutado: Fase 0 (línea base), Fase 1 (1.1 + 1.2), Fase 2 (2.1, 2.2, 2.3), Fase 3 (3.1, 3.2, 3.3).
**No implementado, según lo instruido explícitamente:** Fase 3.4 (script de auditoría), Fase 4 (paginación de feedback admin), purga/LRU de `MemorySaver`, cambios de CORS, reindexación/ingesta/OCR/dedup de corpus, diversidad forzada en el retriever.

No se encontró ningún hallazgo ni instrucción de la lista que resultara perjudicial o contradictoria con el diagnóstico original; de hecho, las instrucciones corrigieron una simplificación propia del diagnóstico (la ubicación del `key` de remount, ver Fase 1.1) y añadieron dos hallazgos nuevos que no se implementaron (correctamente, según las instrucciones: quedan fuera de este lote).

---

## Fase 0 — Línea base

Confirmada antes de tocar código: `pytest` 66/66, `ruff` limpio, `mypy` limpio, `tsc` limpio, `eslint` limpio (mismo estado que el diagnóstico original). `next build` ya fallaba en este entorno de revisión por un bloqueo de red específico a `fonts.googleapis.com` (sin acceso a internet real de ningún tipo en el dispositivo local, y ese dominio específicamente bloqueado en este sandbox) — no relacionado con el código del proyecto, documentado también en el diagnóstico original.

---

## Fase 1 — Aislamiento de sesión y manejo de expiración

### 1.1 — Aislamiento de `ChatInterface` (fuga de estado entre usuarios)

**Archivo:** `frontend/components/chat/ChatInterface.tsx`

Se extrajo todo el cuerpo del componente (hooks de conversación/chat, estado del sidebar, scroll, JSX) a un nuevo componente interno `AuthenticatedChat`, montado con `key={user.user_id}`. `ChatInterface` ahora solo decide entre mostrar el modal de login o montar `AuthenticatedChat`. El cambio de `key` en cualquier cambio de usuario fuerza un remount completo (todo el estado de React se reinicia), sin tocar `app/page.tsx` (Server Component) — corrección explícita del diagnóstico original, que proponía el `key` en el lugar equivocado.

**Compatibilidad:** cambio puramente estructural (extracción de componente); el comportamiento visual e interactivo es idéntico para un único usuario en una sesión. No cambia contratos de API ni props públicas del componente.

### 1.2 — Manejo global y seguro de 401 / expiración de sesión

**Archivos nuevos/modificados:**
- `frontend/lib/auth.ts` — nuevo evento `AUTH_SESSION_EXPIRED_EVENT` y función `expireAuthSession(expectedToken, message)`: solo limpia la sesión si el token que recibió el 401 sigue siendo el token activo (evita que una respuesta 401 tardía de una sesión anterior cierre la sesión de un usuario que inició sesión después, en la misma pestaña).
- `frontend/lib/api.ts` — nuevo `throwIfSessionExpired(response, requestToken)`, aplicado a **todas** las llamadas autenticadas: `queryRag`, `generateConversationTitle`, `listAdminUsers`, `createAdminUser`, `updateAdminUserPassword`, `submitConversationFeedback`, `submitMessageFeedback`, `queryRagStream`.
- `frontend/components/providers/AuthProvider.tsx` — escucha el evento global y limpia `user`; `validateSession()` solo expira la sesión ante un 401 explícito de `/api/auth/me` — cualquier otro fallo (red, 5xx, no-ok inesperado) conserva la sesión cacheada en vez de cerrarla.
- `frontend/components/common/AuthModal.tsx` — muestra el mensaje de expiración en un bloque separado del error de credenciales.
- `frontend/hooks/useChat.ts` — `persistMessage`, `_createConversation` y `loadConversation` usan `throwIfSessionExpired`; se separó el error de red (reintentable) del manejo por código de estado HTTP.
- `frontend/hooks/useConversations.ts` — `refresh()` usa `throwIfSessionExpired`.
- `frontend/components/chat/ConversationList.tsx` — `saveEdit()` y `confirmDelete()` usan `throwIfSessionExpired`, envueltos en `try/catch` para no bloquear el flujo local de edición/eliminación.
- `frontend/app/admin/page.tsx`, `app/admin/feedback/page.tsx`, `app/admin/message-feedback/page.tsx` — todas las llamadas `fetch` administrativas usan `throwIfSessionExpired`.

**Deliberadamente sin cambios:** `/api/auth/me` (maneja su propio 401 directamente en `AuthProvider`, no vía `throwIfSessionExpired`) y `/api/auth/login` (un 401 ahí significa credenciales incorrectas, no sesión expirada — se sigue manejando como error de formulario).

**Compatibilidad:** en el camino feliz (sin 401) no cambia ningún comportamiento observable. Un 429, 403, 404, 409, 422 o 5xx nunca dispara `throwIfSessionExpired` (solo actúa sobre 401), así que los rate limiters (Fase 2) y los checks de autorización de admin siguen funcionando exactamente igual.

---

## Fase 2 — Rate limiting y condición de carrera

### 2.1 — Rate limiter de generación de título

**Archivos:** `backend/rag/api/rate_limit.py`, `backend/rag/config.py`, `backend/rag/api/routes/conversations.py`, `.env.example`.

`QueryRateLimiter` se generalizó a `SlidingWindowRateLimiter` (misma lógica, clave genérica en vez de asumir `user_id` de consulta); `QueryRateLimiter = SlidingWindowRateLimiter` se conserva como alias de compatibilidad. Nuevo `title_rate_limiter` + dependencia `get_title_user`, aplicados solo a `POST /api/conversations/generate-title`. Nuevas env vars `TITLE_RATE_LIMIT_MODE/REQUESTS/WINDOW_SECONDS`, default `off` — sin cambio de comportamiento hasta activarlo explícitamente.

### 2.2 — Rate limiter de login

**Archivos:** `backend/rag/config.py`, `backend/rag/api/rate_limit.py`, `backend/rag/api/routes/auth.py`, `.env.example`.

Nuevo `login_rate_limiter` (mismo `SlidingWindowRateLimiter`, sin dependencia de `get_current_user` porque el login ocurre antes de autenticar). La clave es un hash SHA-256 de `email_normalizado:ip_origen` (`_login_rate_limit_key`). **Precaución documentada explícitamente en código y `.env.example`:** `request.client.host` no considera ningún proxy de confianza — no se lee `X-Forwarded-For`, porque sin una política de proxy confiable sería falsificable por el cliente. `AUTH_RATE_LIMIT_MODE` default `off` (no se activó `enforce`, tal como se indicó).

### 2.3 — Condición de carrera de email duplicado

**Archivos:** `backend/rag/api/routes/auth.py` (`register`), `backend/rag/api/routes/admin.py` (`create_user`).

Ambos ahora envuelven `session.commit()` en `try/except IntegrityError`: en caso de excepción, `rollback()`, re-verificación de existencia por email y `409 Conflict` si la carrera fue real; si el `IntegrityError` no corresponde a ese email (otro tipo de violación de integridad), se relanza sin enmascarar (`raise` desnudo).

---

## Fase 3 — Limpieza de código muerto y dependencias

### 3.1 — Eliminación de la tool `retrieve` muerta

**Archivos:** `backend/rag/core/tools.py`, `docs/AGENTS.md`.

Se confirmó por `grep` que `retrieve` y `ALL_TOOLS` no tenían ninguna otra referencia en `backend/` ni en `tests/` antes de eliminarlos, junto con los imports que quedaban sin uso (`Annotated`, `ToolMessage`, `InjectedToolCallId`, `tool`, `InjectedState`, `Command`, `get_ensemble_retriever`). `build_context_block` y `sanitize_replacement_chars` se conservan (los usa el flujo determinista real en `agent.py` y `api/main.py`). `docs/AGENTS.md` se corrigió para describir el grafo único determinista (`enrich_query → route_after_analysis → {retrieve_forced → generate | respond_without_retrieval} → END`, confirmado leyendo `build_graph()`) en vez del ReAct/tool-calling que ya no existe, y se eliminaron las referencias obsoletas a Firestore/Firebase Admin SDK (el proyecto usa JWT propio + SQLAlchemy async, sin ningún archivo `firebase_admin.py` — confirmado que no existe en el repo).

### 3.2 — Eliminación de `rehype-raw`

**Archivos:** `frontend/package.json`, `bun.lock`.

Confirmado por `grep` que `rehype-raw` nunca se usaba: `ReactMarkdown` solo recibe `remarkPlugins={[remarkGfm]}`, sin ningún `rehypePlugins`. Eliminado con `bun remove rehype-raw` desde `frontend/`. El `bun.lock` resultante se generó a partir del lockfile real del dispositivo (no de una reinstalación completa desde cero) para que el diff fuera mínimo: solo desaparecen `rehype-raw` y sus dependencias transitivas que ya no usa nadie más (`entities`, `hast-util-from-parse5`, `hast-util-parse-selector`, `hast-util-raw`, `hast-util-to-parse5`, `hastscript`, `html-void-elements`, `parse5`, `vfile-location`, `web-namespaces`) — verificado línea por línea contra el `bun.lock` original del dispositivo antes de escribirlo de vuelta.

**Verificación del payload `<script>`:** no hay ningún framework de pruebas de frontend instalado en este repo (confirmado: no hay `vitest`/`jest`/`testing-library` en `package.json`), así que no fue posible automatizar un test de render. Se verificó en su lugar, a nivel de código, que el comportamiento por defecto de `react-markdown` sin `rehype-raw` (que ya era el caso antes de este cambio, porque nunca estuvo conectado) trata el HTML crudo dentro del markdown como texto literal, no como HTML parseado/ejecutable. Recomiendo una verificación manual rápida en el navegador si se quiere una confirmación visual directa.

### 3.3 — Filtro conservador de candidatos estructurales en el retriever

**Archivo:** `backend/rag/core/retriever.py`.

Nueva función `_has_retrievable_content(text) -> bool` (`any(c.isalnum() for c in text)`), aplicada como filtro **posterior** a la fusión RRF dentro de `HybridEnsembleRetriever._get_relevant_documents`: recorre los candidatos ya rankeados por score, descarta los que no tienen ningún carácter alfanumérico y rellena con el siguiente mejor candidato válido, sin nunca superar `max_results`. No toca BM25, el vectorstore, los pesos ni el índice — opera solo sobre el resultado ya fusionado.

---

## Pruebas nuevas y resultados

Todas ejecutadas contra el entorno del sandbox (con `uv sync` fresco, sin tocar ChromaDB/Ollama reales):

| Archivo | Qué cubre |
|---|---|
| `tests/unit/test_rate_limit.py` (ampliado) | Alias `QueryRateLimiter is SlidingWindowRateLimiter`; independencia entre limitadores de consultas y título; `title_rate_limiter`/`login_rate_limiter` default `off`; clave de login combina email+IP sin exponerlos en claro; enforcement aislado por clave |
| `tests/unit/test_email_race_conditions.py` (nuevo) | Carrera real de email duplicado enmascarada como 409 en `register` y en `create_user`; `IntegrityError` no relacionado con el email (colisión de id) se relanza sin enmascarar, en ambos endpoints |
| `tests/unit/test_retriever_structural_filter.py` (nuevo) | Candidatos estructurales descartados y rellenados; texto corto pero válido conservado; orden relativo entre candidatos válidos preservado; nunca excede `max_results`; entrada 100% estructural devuelve lista vacía |

**Resultado final:** `pytest tests/unit -q` → **82 passed** (66 originales + 16 nuevos/ampliados). `ruff check backend tests` → limpio. `mypy backend/rag` → limpio (25 archivos). `tsc --noEmit` (frontend) → limpio. `eslint .` (frontend) → limpio. `git diff --check` → sin errores de espacios en blanco ni marcadores de conflicto.

## Validaciones que no se pudieron ejecutar, y por qué

- **`next build`** (Turbopack, producción): falla por `next/font` intentando alcanzar `fonts.googleapis.com`, bloqueado específicamente en este sandbox de revisión (y sin ningún acceso a internet en el dispositivo local). Es una limitación del entorno de revisión, no del código — ya estaba presente en la línea base del diagnóstico original y no cambia con esta implementación. No se modificó código para ocultarlo.
- **QA manual en vivo de los criterios de aceptación de Fase 1.2** (401 real cierra sesión y muestra login; 429/403/404/409/422/5xx no la cierran; fallo de red no la cierra; contraseña incorrecta no muestra "sesión expirada"; un 401 tardío de un usuario A no cierra la sesión más nueva de un usuario B): verificado por lectura de código, `tsc` y `eslint`, pero no con un navegador real contra el backend en vivo — este sandbox no tiene acceso a Ollama/ChromaDB/el backend real, y no hay framework de pruebas de frontend instalado en el repo para automatizarlo. Recomiendo una pasada manual rápida en el entorno real antes de dar el lote por cerrado del todo.

---

## Confirmación de restricciones

No se tocó nada relacionado con: HTTP/HTTPS/HSTS/cookies, Ollama, ChromaDB (ni su máquina, configuración, colecciones, índices ni embeddings), reindexación o datos del corpus, Terraform/ECS/ALB/Nginx/red/DNS/IAM, migraciones de base de datos, prompts/alcance RAG/flujo determinista del agente, contrato público de la API (los únicos endpoints tocados ganan un rate limiter opcional en modo `off` y manejo de `IntegrityError`, ambos sin cambiar la forma de la respuesta en el camino feliz), ni ningún secreto/token/contraseña en código, tests o logs. No se ejecutó ningún `git commit` ni `git push` en ningún momento de esta sesión.

## `git status --short` final (dispositivo del usuario)

```
 M .env.example
 M backend/pyproject.toml
 M backend/rag/api/auth.py
 M backend/rag/api/main.py
 M backend/rag/api/routes/admin.py
 M backend/rag/api/routes/auth.py
 M backend/rag/api/routes/conversations.py
 M backend/rag/api/routes/feedback.py
 M backend/rag/api/schemas.py
 M backend/rag/config.py
 M backend/rag/core/agent.py
 M backend/rag/core/prompts.py
 M backend/rag/core/query_enricher.py
 M backend/rag/core/retriever.py
 M backend/rag/core/tools.py
 M backend/rag/core/vectorstore.py
 M bun.lock
 M docs/AGENTS.md
 M frontend/app/about/page.tsx
 M frontend/app/admin/feedback/page.tsx
 M frontend/app/admin/layout.tsx
 M frontend/app/admin/message-feedback/page.tsx
 M frontend/app/admin/page.tsx
 M frontend/app/admin/usuarios/page.tsx
 M frontend/app/layout.tsx
 M frontend/app/page.tsx
 M frontend/components/about/AboutHero.tsx
 M frontend/components/about/HowItWorks.tsx
 M frontend/components/chat/AssistantBubble.tsx
 M frontend/components/chat/ChatInterface.tsx
 M frontend/components/chat/ConversationList.tsx
 M frontend/components/chat/EmptyState.tsx
 M frontend/components/chat/LoadingBubble.tsx
 M frontend/components/chat/MessageList.tsx
 M frontend/components/common/AuthModal.tsx
 M frontend/components/providers/AuthProvider.tsx
 M frontend/hooks/useChat.ts
 M frontend/hooks/useConversations.ts
 M frontend/lib/api.ts
 M frontend/lib/auth.ts
 M frontend/lib/types.ts
 M frontend/package.json
 M pyproject.toml
 M uv.lock
?? INSTRUCCIONES_IMPLEMENTACION_IA.md
?? REVISION_IA.md
?? REVISION_IA_diagnostico.md
?? backend/rag/api/passwords.py
?? backend/rag/api/rate_limit.py
?? docs/SMOKE_TESTS.md
?? tests/integration/
?? tests/unit/test_agent_controls.py
?? tests/unit/test_agent_graph.py
?? tests/unit/test_auth_tokens.py
?? tests/unit/test_bm25_compatibility.py
?? tests/unit/test_conversation_hydration.py
?? tests/unit/test_email_race_conditions.py
?? tests/unit/test_passwords.py
?? tests/unit/test_query_analysis.py
?? tests/unit/test_query_schema.py
?? tests/unit/test_rate_limit.py
?? tests/unit/test_retriever_limit.py
?? tests/unit/test_retriever_structural_filter.py
```

**Nota importante sobre esta lista:** varios de estos archivos (por ejemplo `backend/rag/api/main.py`, `feedback.py`, `schemas.py`, `agent.py`, `prompts.py`, `query_enricher.py`, `vectorstore.py`, `pyproject.toml`, `uv.lock`, y casi todos los `.tsx` de `frontend/app/about`, `admin/layout.tsx`, `admin/usuarios`, `layout.tsx`, `page.tsx`, `AboutHero.tsx`, `HowItWorks.tsx`, `AssistantBubble.tsx`, `EmptyState.tsx`, `LoadingBubble.tsx`, `MessageList.tsx`, `types.ts`, así como varios `??` como `backend/rag/api/passwords.py`, `docs/SMOKE_TESTS.md`, `tests/integration/` y varios `tests/unit/test_*.py`) **ya estaban modificados o presentes sin comitear antes de esta sesión** — no fueron tocados por esta implementación. Solo los 25 archivos listados en la sección "Pruebas nuevas y resultados" y en el detalle de cada fase arriba fueron escritos por este trabajo.

## Confirmación explícita

No se ejecutó ningún `git add`, `git commit` ni `git push` en ningún momento. Todos los cambios quedan como modificaciones locales sin comitear en el árbol de trabajo del usuario, exactamente como estaban las instrucciones.
