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

Package manager: **bun**. La autenticación es propia (JWT) contra el backend
FastAPI, ver más abajo.

---

## Desarrollo

```bash
bun install
bun dev             # http://localhost:3000
bun run build       # build de producción
bun run lint        # eslint
bun run typecheck   # chequeo de tipos (tsc --noEmit)
```

Requiere `frontend/.env.local` con `NEXT_PUBLIC_API_URL` (URL del backend;
vacío para usar rutas relativas detrás de un proxy como nginx — ver
`../docs/DESPLIEGUE.md`).

---

## Autenticación (JWT propio)

El flujo actual:

- `lib/auth.ts` — gestiona el token y el usuario en `localStorage`
  (`atlas_token`, `atlas_user`). Expone `getToken`, `setAuth`, `clearAuth`,
  y el evento `atlas:session-expired` que dispara cualquier llamada
  autenticada que reciba un `401`.
- `components/providers/AuthProvider.tsx` — valida la sesión contra
  `GET /api/auth/me` al montar la app, escucha `atlas:session-expired` para
  cerrar sesión en memoria, y expone `signIn`/`signOut`/`user`/`role` vía
  `useAuth()`. `signIn` llama a `POST /api/auth/login`.
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
| `/` | `app/page.tsx` | Chat principal (`ChatInterface`) | Opcional |
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
| `ConversationSidebar` | Sidebar dual: desktop (272px/60px animado) y mobile (overlay 264px). |
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
| `AuthModal` | Modal login/register con tabs. Modos `"recommendation"` (soft) y `"explicit"` (forzado). |
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

**Retorna:** `messages`, `input`, `loading`, `isStreaming`, `stage` (`"enriching"` | `"retrieving"` | `"generating"`), `error`, `contextPercent`, `conversationId`, `ratedMessageIds`, `setInput`, `submit`, `resetChat`, `loadConversation`, `rateMessage`.

**Flujo:**
1. Genera `thread_id` (UUID) estable por sesión de chat.
2. Primer mensaje crea la conversación vía `POST /api/conversations` (backend SQL) + genera título con IA en background.
3. Cada turno se persiste con `POST /api/conversations/{id}/messages` (pregunta y respuesta, por separado), con un reintento para errores transitorios (no para `401`, que expira la sesión de inmediato).
4. Streaming SSE vía `queryRagStream` async generator, actualizando mensajes en tiempo real.
5. `loadConversation` hidrata desde `GET /api/conversations/{id}/messages`, ordenado por el backend.
6. `rateMessage` envía feedback por mensaje (`POST /api/feedback/message`) y marca localmente.

### `useConversations.ts`

Lista las conversaciones del usuario autenticado vía `GET /api/conversations`, con `refresh()` explícito (sin listener en tiempo real).

**Retorna:** `{ conversations, loading, refresh }`.

---

## Librería (`lib/`)

### `auth.ts`

Gestión de sesión JWT en el cliente — token y usuario en `localStorage`, más el mecanismo de expiración de sesión seguro frente a carreras entre pestañas/sesiones (ver comentarios en el archivo). Sin dependencias externas.

### `api.ts`

Cliente API vigente, con funciones tipadas:

| Función | Endpoint | Descripción |
|---------|----------|-------------|
| `queryRagStream(request)` | POST `/api/query/stream` | AsyncGenerator SSE. Yield `StreamEvent` (`token`, `sources`, `status`, `error`). Única vía de consulta usada por la UI. |
| `generateConversationTitle(...)` | POST `/api/conversations/generate-title` | Título generado por IA. |
| `submitConversationFeedback(request)` | POST `/api/feedback` | Feedback multi-dimensión. |
| `submitMessageFeedback(request)` | POST `/api/feedback/message` | Feedback por mensaje (409 = duplicado). |
| `listAdminUsers()` | GET `/api/admin/users` | Lista de usuarios. |
| `createAdminUser(input)` | POST `/api/admin/users` | Crear usuario. |
| `updateAdminUserPassword(uid, pwd)` | PATCH `/api/admin/users/{uid}/password` | Cambiar contraseña. |

Todas las requests autenticadas usan `Authorization: Bearer <token>` (`lib/auth.ts::getToken()`). Un `401` en cualquiera de ellas pasa por `throwIfSessionExpired`, que expira la sesión de forma segura frente a condiciones de carrera (ver `lib/auth.ts::expireAuthSession`).

### `types.ts`

Interfaces TypeScript: `Message`, `SourceGroup`, `SourceFragment`, `QueryRequest`, `StreamEvent`, `FeedbackRequest`, `MessageFeedbackRequest`, `ConversationRatings`, `MessageRatings`, `AgentStage`, `DocType`, tipos admin.

Función `normalizeSources(raw)` para convertir conversaciones antiguas guardadas en el shape plano legado al shape actual (`SourceGroup[]`).

### `config.ts`

`API_URL` — `process.env.NEXT_PUBLIC_API_URL` con fallback a `http://localhost:8080`.

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

**Accesibilidad:** Soporte completo de `prefers-reduced-motion`, skip-link, focus rings visibles, contraste AA.

---

## Decisiones arquitectónicas

- **Sin API routes** — el frontend es un SPA puro que habla directamente con el backend Python vía `NEXT_PUBLIC_API_URL`. No hay directorio `app/api/`.
- **Sin tailwind.config** — Tailwind v4 usa configuración CSS-first vía `@theme inline` en `globals.css`.
- **SSE streaming** — `queryRagStream` es un async generator que lee `ReadableStream` de `fetch`, parsea eventos SSE `data:` y yield `StreamEvent` tipados.
- **Sesión sin backend de terceros** — token JWT + datos de usuario en `localStorage`; el backend es la única fuente de verdad de identidad y roles (ver "Autenticación" arriba).
- **Conversaciones en SQL del backend** — no en un store de cliente. El frontend recibe `conversation_id`/`thread_id` y persiste/lee cada turno vía REST.
- **Acceso admin por roles** — el `role` viene de la respuesta de auth del backend (`/api/auth/me`, `/api/auth/login`) y se revalida server-side en cada endpoint `/api/admin/*` vía `require_admin`.
