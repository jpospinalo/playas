# ATLAS — Frontend

Frontend Next.js del sistema **ATLAS**. Interfaz de chat conversacional con
streaming SSE, autenticación JWT propia, historial de conversaciones (SQL),
sistema dual de feedback y panel de administración.

---

## Stack tecnológico

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| `next` | 16.2.3 | Framework React (App Router) |
| `react` / `react-dom` | 19.2.4 | UI library |
| `geist` | 1.7.2 | Fuente Geist Mono (monoespaciada, auto-hospedada) |
| `motion` | 12.38.0 | Animaciones (Framer Motion) |
| `next-themes` | 0.4.6 | Temas claro/oscuro/sistema |
| `react-markdown` + `remark-gfm` | 10.1.0 / 4.0.1 | Renderizado de markdown con GFM |
| `tailwindcss` | 4 | CSS utility-first (config CSS-first, sin `tailwind.config`) |
| `typescript` | 5 | Tipado estático |

Fuentes: **Inter** (sans, variable) y **Geist Mono** (monoespaciada) — ambas
auto-hospedadas como `.woff2` en `app/fonts/` vía `next/font/local`, sin
dependencia de red en build ni en runtime. Inter se vendoriza desde el
paquete npm `@fontsource-variable/inter` (licencia OFL, ver
`app/fonts/Inter-OFL-LICENSE.txt`); Geist Mono viene empaquetada en la
dependencia `geist` (ver `app/fonts/Geist-OFL-LICENSE.txt`).

Package manager: **Bun 1.3.13**, declarado en el [workspace](../package.json).
La autenticación es propia (JWT) contra el backend FastAPI, ver más abajo.

---

## Desarrollo

Desde `rag/frontend/`, utilizando el lock del workspace `rag/bun.lock`:

```bash
bun install --frozen-lockfile
bun dev             # http://localhost:3000
bun run build       # build de producción
bun run lint        # eslint
bun run typecheck   # chequeo de tipos (tsc --noEmit)
bun run test        # pruebas unitarias (Vitest)
```

`NEXT_PUBLIC_API_URL` puede venir del entorno o de configuración local;
`next.config.ts` también lee `rag/.env`. `frontend/.env.local` es opcional.
En producción, Next fija esta variable al construir el frontend: usar un valor
vacío para rutas relativas detrás del proxy. Ver la
[guía de despliegue](../docs/DESPLIEGUE.md).

---

## Autenticación (JWT propio)

El flujo actual:

- `lib/auth.ts` — gestiona el token y una caché `{token, user}` en
  `localStorage` (`atlas_token`, `atlas_user`). `getTokenForUser(user_id)`
  entrega la credencial del mismo registro solo si corresponde a la identidad
  mostrada y al token activo; no prueba autorización. Una caché heredada sin
  vínculo no se reutiliza hasta que `/api/auth/me` confirme la identidad.
- `components/providers/AuthProvider.tsx` — valida la sesión contra
  `GET /api/auth/me` al montar y cuando `storage` informa un cambio efectivo
  de token, incluido logout o rotación para el mismo usuario. Limpia la
  identidad anterior durante la validación, aborta validaciones obsoletas y
  descarta sus respuestas tardías. Expone `signIn`/`signOut`/`user`/`role`
  vía `useAuth()`. `signIn` llama a `POST /api/auth/login`.
- Las operaciones capturan la credencial ligada al usuario antes del primer
  `await` y la conservan durante esa operación. Así se bloquea una solicitud
  de A con el token de B incluso antes de recibir `storage`. Un `401` solo
  dispara `atlas:session-expired` si su token sigue activo; no cierra una
  sesión posterior. Un fallo transitorio de `/me` conserva únicamente una
  caché ligada al token vigente. Al cambiar de usuario se desmonta el chat y
  se descartan sus mensajes, referencias y generación anterior.
- Las conversaciones y mensajes viven en la base de datos SQL del backend
  (Postgres/SQLite vía SQLAlchemy), no en un store de cliente — el frontend
  llama a `/api/conversations` y `/api/conversations/{id}/messages` por
  cada operación; no hay listener en tiempo real, `useConversations`
  refresca con `fetch` explícito.
- El acceso admin se decide por el campo `role` que devuelve
  `/api/auth/me`/`/api/auth/login`; el backend también lo revalida vía
  `require_admin` en cada endpoint `/api/admin/*` — no hay verificación
  client-side independiente de un store externo.

---

## Estructura de rutas

| Ruta | Archivo | Descripción | Auth |
|------|---------|-------------|------|
| `/` | `app/page.tsx` | Chat principal (`ChatInterface`); login obligatorio antes de montar el chat | Sí |
| `/about` | `app/about/page.tsx` | Página informativa estática | No |
| `/admin` | `app/admin/page.tsx` | Dashboard de feedback (stats + distribuciones) | Admin |
| `/admin/feedback` | `app/admin/feedback/page.tsx` | Tabla de feedback por conversación | Admin |
| `/admin/message-feedback` | `app/admin/message-feedback/page.tsx` | Tabla de feedback por mensaje | Admin |
| `/admin/usuarios` | `app/admin/usuarios/page.tsx` | Gestión de usuarios (crear, cambiar contraseña) | Admin |

**Layouts:**
- `app/layout.tsx` — Layout raíz: fuentes Inter/Geist Mono auto-hospedadas, `ThemeProvider`, `AuthProvider`, metadata OpenGraph.
- `app/admin/layout.tsx` — Layout admin con sidebar: verifica `role` (de `useAuth()`), muestra 403 para no-admins.

---

## Componentes

### `components/chat/` — Chat principal

| Componente | Responsabilidad |
|------------|-----------------|
| `ChatInterface` | Orquestador principal. Compone sidebar, header, empty state, mensajes, loading, errores, feedback, warnings. |
| `ChatHeader` | Barra superior: wordmark, "Nuevo chat", toggle sidebar, botón login. |
| `ChatInput` | Textarea auto-creciente con botón enviar. Variantes `"hero"` (centrado) y `"docked"` (barra inferior). |
| `EmptyState` | Vista inicial: título, descripción, input hero, glow ambiental, disclaimer. |
| `MessageList` | Mapea mensajes a `UserBubble` o `AssistantBubble`. |
| `UserBubble` | Burbuja derecha con animación. |
| `AssistantBubble` | Burbuja izquierda con markdown. Convierte `[docN]` en badges interactivos que abren popover con metadata de fuente. Botón "Calificar" por mensaje. |
| `SourcesAccordion` | Acordeón expandible debajo de respuestas. Muestra grupos de fuentes con metadata y fragmentos. |
| `LoadingBubble` | Dots animados + label de etapa en vivo ("Navegando miles de paginas..."). |
| `TypingDots` | Indicador visual de tres puntos animados, usado por `LoadingBubble`. |
| `ContextWarning` | Banner de advertencia al 60-80% (soft) y 80%+ (crítico) de uso de contexto. |
| `ConversationSidebar` | Sidebar dual: desktop (288px expandido y 76px colapsado, con transición animada) y móvil como overlay. |
| `ConversationList` | Lista de conversaciones con rename inline, menú de tres puntos, confirmación de borrado. |
| `ConversationSearchDialog` | Modal de búsqueda de conversaciones por título. |
| `SidebarUserMenu` | Menú de usuario al pie del sidebar: avatar, admin link (si admin), tema, cerrar sesión. |
| `conversationSidebarUtils.ts` | Constantes compartidas de dimensiones y transición del sidebar (`SIDEBAR_EXPANDED_WIDTH`, `SIDEBAR_COLLAPSED_WIDTH`, `SIDEBAR_TRANSITION`) y `formatConversationDate()`. |
| `FeedbackButton` | Botón flotante de estrella (esquina inferior derecha). |
| `FeedbackModal` | Formulario de feedback de conversación: 4 dimensiones (tono, longitud, usabilidad, general) + comentario. |
| `MessageRatingPopover` | Feedback por mensaje: pertinencia + accuracy + respuesta esperada. |

### `components/common/` — Componentes compartidos

| Componente | Responsabilidad |
|------------|-----------------|
| `AuthModal` | Formulario de login. `dismissible=false` impide cerrarlo cuando se exige sesión; no ofrece registro ni pestañas de modos. |
| `ThemeToggle` | Control segmentado de 3 posiciones: claro / sistema / oscuro. |
| `AtlasWordmark` | Texto "ATLAS" estilizado con letter-spacing. |

### `components/about/` — Página informativa

| Componente | Responsabilidad |
|------------|-----------------|
| `AboutNav` | Nav sticky con glyph + CTA. |
| `AboutHero` | Hero: badge, h1, descripción, 2 CTAs, glow ambiental. |
| `HowItWorks` | 3 tarjetas de pasos con animaciones scroll-triggered. |
| `WhyRag` | "ATLAS no inventa, ATLAS cita." Layout de dos columnas. |
| `AboutFooter` | Footer con branding y copyright. |

### `components/providers/` — Contextos React

| Provider | Responsabilidad |
|----------|-----------------|
| `AuthProvider` | Contexto de sesión JWT (ver "Autenticación" arriba). Expone `user`, `role`, `loading`, `sessionExpiredMessage`, `signIn`, `signOut`. |
| `ThemeProvider` | Wrapper de `next-themes`. Config: `attribute="class"`, `defaultTheme="system"`. |

---

## Hooks

### `useChat.ts`

Máquina de estados del chat. Gestiona el ciclo completo de una conversación.

**Capacidades y estado:**

- Vista: `messages`, `input`, `loading`, `isStreaming`, `stage`, `stageMessage`,
  `error` y `contextPercent`.
- Conversación: `conversationId`, `setInput`, `submit`, `resetChat`,
  `loadConversation` y `handleConversationDeleted`.
- Acciones: `cancel`/`canCancel`, `generationStopped`, `generationFinished`,
  `persistingMessageIds`/`retryPersistMessage` y `ratedMessageIds`/`rateMessage`.

`stage` distingue `"enriching"`, `"retrieving"` y `"generating"`.

`cancel()` detiene solo la generación activa, sin abortar una carga de historial
ni un guardado. Una generación cancelada no se persiste como respuesta completa.
`retryPersistMessage()` reintenta guardar una respuesta ya generada cuyo guardado
falló; no vuelve a consultar el RAG.

Desmontar el chat invalida los envíos pendientes, incluso antes de iniciar SSE.
Las listas notifican los borrados confirmados mediante `handleConversationDeleted`:
el hook decide con la vista y carga vigentes, sin cancelar otra selección ni
restaurar una conversación eliminada si esa carga falla.

**Flujo:**
1. Genera `thread_id` (UUID) estable por sesión de chat.
2. Primer mensaje crea la conversación vía `POST /api/conversations` (backend SQL), con el título fijado a los primeros 120 caracteres de la pregunta. `generateConversationTitle` existe como función/endpoint (ver tabla de `api.ts` más abajo), pero la UI vigente no lo invoca.
3. Cada turno se persiste con `POST /api/conversations/{id}/messages` (pregunta y respuesta, por separado), con un reintento para errores transitorios (no para `401`, que expira la sesión de inmediato).
4. SSE vía `queryRagStream`: las etapas avanzan durante la espera; el texto llega en fragmentos después de generar y validar la respuesta completa, no como tokens en vivo del modelo.
5. `loadConversation` hidrata desde `GET /api/conversations/{id}/messages`, ordenado por el backend. Cada llamada reclama la propiedad del estado compartido (un id de operación monotónico + el `AbortController` dedicado a la carga, comparados por identidad): detiene de inmediato el estado transitorio de una generación en curso (`isStreaming`/`stage`), pero solo reemplaza los mensajes visibles y libera `loading` si, al resolver, sigue siendo la operación vigente — una respuesta tardía de una selección ya superada nunca pisa la conversación que el usuario ve.
6. `rateMessage` envía feedback por mensaje (`POST /api/feedback/message`) y marca localmente.

### `useConversations.ts`

Lista las conversaciones del usuario autenticado vía `GET /api/conversations`, con `refresh()` explícito (sin listener en tiempo real).

**Retorna:** `{ conversations, loading, error, refresh }`. `error` es el mensaje del último intento de refresco fallido, o `null` si el más reciente tuvo éxito (o todavía no se ha intentado ninguno). Un fallo transitorio (red caída, error del backend) nunca vacía `conversations`: la última lista válida conocida se conserva en pantalla, y `error` es lo único que le permite a la UI mostrar un aviso con opción de reintentar (`refresh`).

---

## Librería (`lib/`)

### `auth.ts`

Gestión de sesión JWT en el cliente, sin dependencias externas. El
[contrato de autenticación](#autenticación-jwt-propio) describe el vínculo
entre identidad y credencial, la migración de caché y la expiración segura.

### `api.ts`

Cliente API vigente, con funciones tipadas:

| Función | Endpoint | Descripción |
|---------|----------|-------------|
| `queryRagStream(request, signal?, token?)` | POST `/api/query/stream` | AsyncGenerator de `StreamEvent` (`token`, `sources`, `status`, `error`). Única vía de consulta usada por la UI. Sin límite de tiempo común; conserva la señal de cancelación del llamador. |
| `generateConversationTitle(...)` | POST `/api/conversations/generate-title` | Título generado por IA, con fallback silencioso a los primeros 50 caracteres del mensaje. Tampoco tiene el límite de tiempo común — llamada al LLM con su propio presupuesto. |
| `submitConversationFeedback(request, token?)` | POST `/api/feedback` | Feedback multi-dimensión. |
| `submitMessageFeedback(request, token?)` | POST `/api/feedback/message` | Feedback por mensaje (409 = duplicado). |
| `listAdminUsers(token?)` | GET `/api/admin/users` | Lista de usuarios. |
| `createAdminUser(input, token?)` | POST `/api/admin/users` | Crear usuario. |
| `updateAdminUserPassword(uid, pwd, token?)` | PATCH `/api/admin/users/{uid}/password` | Cambiar contraseña. |

Las llamadas autenticadas usan `Authorization: Bearer <token>`. Los
componentes pasan la credencial capturada con `getTokenForUser`: `null`
explícito bloquea el envío y nunca toma el token de otra sesión. Solo omitir
el argumento (`undefined`) conserva la lectura local por compatibilidad con
llamadores anteriores; no usar ese modo para una nueva operación de UI.
El chat conserva el mismo token en creación, persistencia, SSE y feedback.
Un `401` pasa por `throwIfSessionExpired` y solo expira el token aún activo.

Las operaciones REST de duración finita — autenticación, listar/cargar/crear/renombrar/borrar conversaciones, persistencia de mensajes y feedback, y las pantallas de administración — comparten un límite de tiempo conservador de 60s (`lib/httpTimeout.ts::withRestTimeout`, sobre `AbortSignal.timeout()`/`AbortSignal.any()`), que se combina con cualquier señal de cancelación propia del llamador sin reemplazarla. Quedan fuera, deliberadamente, `queryRagStream` (streaming) y `generateConversationTitle` (ver tabla arriba). El límite aplica POR INTENTO, no por operación completa: `persistMessage` (`hooks/useChat.ts`) hace como máximo dos intentos ante un error transitorio o `5xx`, y cada uno recibe su propio presupuesto completo de 60s — un intento que agota su límite no le resta tiempo al siguiente.

Los mensajes de error HTTP mostrados al usuario pasan por un único lector seguro (`lib/api.ts::readErrorDetail`): intenta `{"detail": "..."}` de un cuerpo JSON, luego texto plano corto y de confianza, y si no hay nada usable (cuerpo vacío, JSON sin `detail`, HTML de un proxy, o un cuerpo demasiado largo) usa un mensaje por código — nunca muestra JSON serializado ni un cuerpo sin acotar.

Un cierre SSE de éxito requiere un único evento `sources` antes de `[DONE]`;
`sources: []` es válido para una abstención. El cliente rechaza fuentes
ausentes o duplicadas, tokens/etapas posteriores a las fuentes y eventos
conocidos posteriores a un error. Un flujo truncado, un error o una
cancelación no se persisten como respuesta completada. Los comentarios SSE,
UTF-8 fragmentado y eventos desconocidos inocuos siguen admitidos.

### `types.ts`

Interfaces TypeScript: `Message`, `SourceGroup`, `SourceFragment`, `QueryRequest`, `StreamEvent`, `FeedbackRequest`, `MessageFeedbackRequest`, `ConversationRatings`, `MessageRatings`, `AgentStage`, `DocType`, tipos admin.

Función `normalizeSources(raw)` para convertir conversaciones antiguas guardadas en el shape plano legado al shape actual (`SourceGroup[]`).

`SourceGroup.metadata` contiene la identidad del documento;
`SourceFragment.metadata` contiene la atribución del pasaje, incluidos
artículo, título y capítulo normativos. `lib/sourceAttribution.ts` reúne su
lectura compatible para el acordeón y el popover: no atribuir el artículo de
un fragmento a todo el grupo. Los índices `[docN]` conservan el orden global
de los fragmentos, no un índice independiente por grupo.

### `config.ts`

`API_URL` normaliza `NEXT_PUBLIC_API_URL`: ausente usa
`http://localhost:8080`; definida como cadena vacía conserva rutas relativas
`/api/...` detrás del proxy; una URL explícita pierde solo sus barras finales.
No configurar `/api` como prefijo: cada llamada ya añade ese segmento.

---

## Sistema de diseño: "Bioluminiscencia"

El sistema visual de ATLAS está definido en `globals.css` con tokens OKLCH y dos temas — ver `../docs/DESIGN.md` para la especificación completa:

- **Shore (claro):** Fondo luminoso, acento turquesa sobre superficie blanca.
- **Abyss (oscuro):** Fondo oceánico profundo, glow bioluminescente turquesa-verde.

**Elementos clave:**
- `.atlas-glow` — halo radial bioluminescente (elemento visual signature).
- `.doc-badge` — chip interactivo de citación `[docN]`.
- `.doc-popover` — popover de vista previa de fuente.
- `.rag-prose` — sistema tipográfico para respuestas legales renderizadas.

**Animaciones personalizadas:** `message-in`, `typing-dot`, `fade-in`, `glow-pulse`.

**Accesibilidad:** `prefers-reduced-motion` se respeta tanto en CSS (regla global) como en las animaciones de `motion/react` (`MotionConfig reducedMotion="user"` en `ThemeProvider`), además de estilos de foco visible. No se declara conformidad WCAG ni contraste AA sin una auditoría formal.

---

## Decisiones arquitectónicas

- **Sin API routes** — el frontend es un SPA puro que habla directamente con el backend Python vía `NEXT_PUBLIC_API_URL`. No hay directorio `app/api/`.
- **Sin tailwind.config** — Tailwind v4 usa configuración CSS-first vía `@theme inline` en `globals.css`.
- **SSE streaming** — `queryRagStream` es un async generator que lee el `ReadableStream` de `fetch` y yield `StreamEvent` tipados. El reensamblado de bloques SSE y su interpretación viven en `lib/sseParser.ts` (`SseEventAccumulator`/`parseStreamEvent`): tolera separadores `\n`/`\r\n`/`\r` mezclados y fragmentados en cualquier punto entre chunks, líneas de comentario (`:...`), varias líneas `data:` por bloque (unidas con `\n`), e ignora tipos de evento desconocidos sin romper el stream. Si el consumidor abandona el generador antes de `[DONE]` (cancelación del usuario, un error de parseo, o una nueva selección de conversación), `queryRagStream` cancela el `reader` subyacente además de soltar su lock — un fallo al cancelar nunca reemplaza el error real ni produce uno nuevo si no lo había.
- **Sesión sin backend de terceros** — credencial y caché de usuario vinculadas en `localStorage`; el backend verifica identidad, roles y propiedad (ver "Autenticación" arriba).
- **Conversaciones en SQL del backend** — no en un store de cliente. El frontend recibe `conversation_id`/`thread_id` y persiste/lee cada turno vía REST.
- **Acceso admin por roles** — el `role` viene de la respuesta de auth del backend (`/api/auth/me`, `/api/auth/login`) y se revalida server-side en cada endpoint `/api/admin/*` vía `require_admin`.
