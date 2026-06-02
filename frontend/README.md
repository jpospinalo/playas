# ATLAS — Frontend

Frontend Next.js del sistema **ATLAS**. Interfaz de chat conversacional con streaming SSE, autenticación Firebase, historial de conversaciones, sistema dual de feedback y panel de administración.

---

## Stack tecnológico

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| `next` | 16.2.3 | Framework React (App Router) |
| `react` / `react-dom` | 19.2.4 | UI library |
| `firebase` | 12.12.1 | Auth + Firestore cliente |
| `motion` | 12.38.0 | Animaciones (Framer Motion) |
| `next-themes` | 0.4.6 | Temas claro/oscuro/sistema |
| `react-markdown` + `remark-gfm` | 10.1.0 / 4.0.1 | Renderizado de markdown con GFM |
| `tailwindcss` | 4 | CSS utility-first (config CSS-first, sin `tailwind.config`) |
| `typescript` | 5 | Tipado estático |

Package manager: **bun**.

---

## Desarrollo

```bash
bun dev        # http://localhost:3000
bun build      # build de producción
bun lint       # eslint
```

Requiere `frontend/.env.local` con las variables de Firebase y la URL de la API. Ver variables en el README raíz del proyecto.

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
- `app/layout.tsx` — Layout raíz: fuentes Geist, `ThemeProvider`, `AuthProvider`, metadata OpenGraph.
- `app/admin/layout.tsx` — Layout admin con sidebar: verifica `role` en Firestore, muestra 403 para no-admins.

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
| `ContextWarning` | Banner de advertencia al 60-80% (soft) y 80%+ (crítico) de uso de contexto. |
| `ConversationSidebar` | Sidebar dual: desktop (272px/60px animado) y mobile (overlay 264px). |
| `ConversationList` | Lista de conversaciones con rename inline, menú de tres puntos, confirmación de borrado. |
| `ConversationSearchDialog` | Modal de búsqueda de conversaciones por título. |
| `SidebarUserMenu` | Menú de usuario al pie del sidebar: avatar, admin link (si admin), tema, cerrar sesión. |
| `FeedbackButton` | Botón flotante de estrella (esquina inferior derecha). |
| `FeedbackModal` | Formulario de feedback de conversación: 4 dimensiones (tono, longitud, usabilidad, general) + comentario. |
| `MessageRatingPopover` | Feedback por mensaje: pertinencia + accuracy + respuesta esperada. |

### `components/common/` — Componentes compartidos

| Componente | Responsabilidad |
|------------|-----------------|
| `AuthModal` | Modal login/register con tabs. Modos `"recommendation"` (soft) y `"explicit"` (forzado). Traducción de errores Firebase al español. |
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
| `AuthProvider` | Contexto Firebase Auth. Escucha `onAuthStateChanged`. En primer login crea `users/{uid}` con role `"user"`. Expone: `user`, `role`, `loading`, `signIn`, `signUp`, `signOut`. |
| `ThemeProvider` | Wrapper de `next-themes`. Config: `attribute="class"`, `defaultTheme="system"`. |

---

## Hooks

### `useChat.ts`

Máquina de estados del chat. Gestiona el ciclo completo de una conversación.

**Retorna:** `messages`, `input`, `loading`, `isStreaming`, `stage` (`"enriching"` | `"retrieving"` | `"generating"`), `error`, `contextPercent`, `conversationId`, `ratedMessageIds`, `setInput`, `submit`, `resetChat`, `loadConversation`, `rateMessage`.

**Flujo:**
1. Genera `thread_id` (UUID) estable por sesión.
2. Primer mensaje crea doc en Firestore `conversations/{id}` + genera título con IA en background.
3. Streaming SSE vía `queryRagStream` async generator, actualizando mensajes en tiempo real.
4. Persiste mensajes user/assistant en subcollection Firestore.
5. `loadConversation` hidrata desde Firestore ordenado por `createdAt`.
6. `rateMessage` envía feedback por mensaje y marca localmente.

### `useConversations.ts`

Listener en tiempo real de Firestore para las conversaciones del usuario autenticado.

**Retorna:** `{ conversations, loading }`.

Usa `onSnapshot` filtrado por `userId`, ordenado por `updatedAt desc`.

---

## Librería (`lib/`)

### `firebase.ts`

Inicialización del cliente Firebase. Solo browser (stubs SSR). Singleton vía `getApps()`.

**Exporta:** `auth`, `db`.

### `api.ts`

Cliente API con funciones tipadas:

| Función | Endpoint | Descripción |
|---------|----------|-------------|
| `queryRagStream(request)` | POST `/api/query/stream` | AsyncGenerator SSE. Yield `StreamEvent` (`token`, `sources`, `status`, `error`). |
| `queryRag(request)` | POST `/api/query` | Query no-streaming (no usado en UI actual). |
| `generateConversationTitle(...)` | POST `/api/conversations/generate-title` | Título generado por IA. |
| `submitConversationFeedback(request)` | POST `/api/feedback` | Feedback multi-dimensión. |
| `submitMessageFeedback(request)` | POST `/api/feedback/message` | Feedback por mensaje (409 = duplicado). |
| `listAdminUsers()` | GET `/api/admin/users` | Lista de usuarios. |
| `createAdminUser(input)` | POST `/api/admin/users` | Crear usuario. |
| `updateAdminUserPassword(uid, pwd)` | PATCH `/api/admin/users/{uid}/password` | Cambiar contraseña. |

Todas las requests autenticadas usan `getAuthHeaders()` → `auth.currentUser.getIdToken(true)`.

### `types.ts`

Interfaces TypeScript: `Message`, `SourceGroup`, `SourceFragment`, `QueryRequest`, `QueryResponse`, `StreamEvent`, `FeedbackRequest`, `MessageFeedbackRequest`, `ConversationRatings`, `MessageRatings`, `AgentStage`, `DocType`, tipos admin.

Función `normalizeSources(raw)` para convertir formato legacy a `SourceGroup[]`.

---

## Sistema de diseño: "Bioluminiscencia"

El sistema visual de ATLAS está definido en `globals.css` con tokens OKLCH y dos temas:

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
- **Sin tailwind.config** — Tailwind v4 usa configuración CSS-first via `@theme inline` en `globals.css`.
- **SSE streaming** — `queryRagStream` es un async generator que lee `ReadableStream` de `fetch`, parsea eventos SSE `data:` y yield `StreamEvent` tipados.
- **Firestore como store** — conversaciones y mensajes viven en Firestore, no en el backend. El backend recibe `conversation_id` y `thread_id` para hidratar estado de LangGraph.
- **Acceso admin por roles** — el role se almacena en Firestore `users/{uid}.role` y se verifica client-side en el layout admin. El backend también valida vía Firebase ID token.
