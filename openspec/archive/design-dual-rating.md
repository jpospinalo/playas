# SDD Design: Dual Rating System

## change_id: dual-rating-system

---

## D-01: Data Model & Firestore Collections

### Conversation Feedback (extended `feedback` collection)

The existing `feedback` collection document shape changes from flat `rating` to structured `ratings`:

```
// Before (legacy)
{
  userId: string,
  userEmail: string,
  rating: number,          // 1-5
  comment: string | null,
  conversationId: string | null,
  conversationTitle: string | null,
  createdAt: Timestamp
}

// After (new)
{
  userId: string,
  userEmail: string,
  ratings: {
    tone: number,        // 1-5
    length: number,      // 1-5
    usability: number,   // 1-5
    overall: number,     // 1-5
  },
  comment: string | null,
  conversationId: string | null,
  conversationTitle: string | null,
  createdAt: Timestamp
}
```

No Firestore index changes needed for `feedback` — the existing `createdAt DESCENDING` index continues to work. The `rating` field is no longer queried for min/max filters; instead, we filter by dimension values which will use the same index pattern.

### Message Feedback (new `message_feedback` collection)

```
{
  userId: string,
  userEmail: string,
  conversationId: string,
  messageId: string,        // Firestore doc ID of the assistant message
  ratings: {
    pertinence: number,    // 1-5
    accuracy: number,      // 1-5
  },
  expectedAnswer: string | null,   // max 1000 chars
  createdAt: Timestamp
}
```

**Firestore indexes needed:**

- `message_feedback`: `createdAt DESCENDING` (for admin listing)
- `message_feedback`: `userId ASC, messageId ASC` (for duplicate check before write)

### Duplicate enforcement strategy

No Firestore unique constraint exists. The backend verifies uniqueness by querying `message_feedback` where `userId == uid AND messageId == msgId` before creating. If a document exists, return `409 Conflict`. The frontend also tracks rated messages in local state to avoid showing the rate button for already-rated messages.

### Migration script

A standalone Python script `scripts/migrate_feedback_ratings.py` that:

1. Reads all documents from `feedback` collection.
2. For each doc that has `rating` but no `ratings` field, computes `ratings = { tone: rating, length: rating, usability: rating, overall: rating }`.
3. Updates the doc with `ratings` field and removes the `rating` field (using `@exclude` or explicit field delete).
4. Logs docs processed and any errors.

This script is run once manually after deployment.

---

## D-02: Backend API

### Modified endpoint: `POST /api/feedback`

**Current:**

```python
class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    comment: str | None = Field(default=None)
    conversation_id: str | None = Field(default=None)
```

**New:**

```python
class RatingDimensions(BaseModel):
    tone: int = Field(..., ge=1, le=5, description="Calificación del tono de las respuestas")
    length: int = Field(..., ge=1, le=5, description="Calificación de la longitud de las respuestas")
    usability: int = Field(..., ge=1, le=5, description="Calificación de la usabilidad del sistema")
    overall: int = Field(..., ge=1, le=5, description="Calificación general")

class FeedbackRequest(BaseModel):
    ratings: RatingDimensions
    comment: str | None = Field(default=None, max_length=500)
    conversation_id: str | None = Field(default=None)
```

The `submit_feedback` handler writes `ratings` as a dict to Firestore instead of the flat `rating` integer.

### New endpoint: `POST /api/feedback/message`

**Request:**

```python
class MessageFeedbackRatings(BaseModel):
    pertinence: int = Field(..., ge=1, le=5)
    accuracy: int = Field(..., ge=1, le=5)

class MessageFeedbackRequest(BaseModel):
    conversation_id: str = Field(..., min_length=1)
    message_id: str = Field(..., min_length=1)
    ratings: MessageFeedbackRatings
    expected_answer: str | None = Field(default=None, max_length=1000)
```

**Response:** `{ "id": "doc_id" }` (201) or `{ "detail": "Ya existe feedback para este mensaje." }` (409)

**Handler logic:**

1. Authenticate user via `get_current_user`.
2. Query `message_feedback` where `userId == uid AND messageId == message_id`.
3. If doc exists → 409 Conflict.
4. Look up `conversations/{conversation_id}` to get title (fire-and-forget, non-blocking).
5. Write to `message_feedback` collection.
6. Return `{ "id": doc_ref.id }`.

### Modified endpoint: `GET /api/admin/feedback`

The admin endpoint returns `ratings` instead of `rating`:

**New response shape:**

```python
class AdminFeedbackItem(BaseModel):
    id: str
    userId: str
    userEmail: str
    ratings: RatingDimensions    # replaces rating: int
    comment: str | None
    conversationId: str | None
    conversationTitle: str | None
    createdAt: str

class AdminFeedbackResponse(BaseModel):
    items: list[AdminFeedbackItem]
    total: int
    avg_ratings: RatingDimensionsFloat  # { tone: 3.8, length: 4.1, ... }
    distributions: RatingDistributions  # { tone: {"1":n,...}, length: {...}, ... }
```

The filter params change from `min_rating`/`max_rating` to `min_overall`/`max_overall` (filtering on the `overall` dimension, which replaces the old single rating).

### New endpoint: `GET /api/admin/message-feedback`

**Query params:** `page`, `page_size`, `start_date`, `end_date`, `min_pertinence`, `max_pertinence`, `min_accuracy`, `max_accuracy`

**Response:**

```python
class AdminMessageFeedbackItem(BaseModel):
    id: str
    userId: str
    userEmail: str
    conversationId: str
    messageId: str
    ratings: MessageFeedbackRatings
    expectedAnswer: str | None
    createdAt: str

class AdminMessageFeedbackResponse(BaseModel):
    items: list[AdminMessageFeedbackItem]
    total: int
    avg_ratings: dict[str, float]  # { "pertinence": 3.8, "accuracy": 4.1 }
    distributions: dict[str, dict[str, int]]  # { "pertinence": {"1":n,...}, "accuracy": {...} }
```

---

## D-03: Frontend Types & API Client

### `frontend/lib/types.ts`

Add new types:

```typescript
// Conversation-level rating dimensions
export interface ConversationRatings {
  tone: number;
  length: number;
  usability: number;
  overall: number;
}

export interface ConversationFeedbackRequest {
  ratings: ConversationRatings;
  comment?: string;
  conversation_id?: string;
}

// Message-level rating
export interface MessageRatings {
  pertinence: number;
  accuracy: number;
}

export interface MessageFeedbackRequest {
  conversation_id: string;
  message_id: string;
  ratings: MessageRatings;
  expected_answer?: string;
}

// Admin response types
export interface AdminMessageFeedbackItem {
  id: string;
  userId: string;
  userEmail: string;
  conversationId: string;
  messageId: string;
  ratings: MessageRatings;
  expectedAnswer: string | null;
  createdAt: string;
}
```

Keep `FeedbackRequest` as-is during migration but mark it deprecated. The actual change replaces it with `ConversationFeedbackRequest`.

### `frontend/lib/api.ts`

Add two functions:

```typescript
export async function submitConversationFeedback(
  request: ConversationFeedbackRequest,
): Promise<{ id: string }> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail.trim() || `Error del servidor (${res.status})`);
  }
  return res.json();
}

export async function submitMessageFeedback(
  request: MessageFeedbackRequest,
): Promise<{ id: string }> {
  const authHeaders = await getAuthHeaders();
  const res = await fetch(`${API_URL}/api/feedback/message`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders },
    body: JSON.stringify(request),
  });
  if (res.status === 409) {
    throw new Error("Ya existe feedback para este mensaje.");
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail.trim() || `Error del servidor (${res.status})`);
  }
  return res.json();
}
```

Renamed: `submitFeedback` → `submitConversationFeedback` (with backward-compatible alias initially).

---

## D-04: Message ID Propagation in useChat.ts

### Problem

When an assistant message is created in the UI, it gets a temporary `crypto.randomUUID()` ID. When it's saved to Firestore via `addDoc()`, the Firestore-generated doc ID is different. The message-level rating system needs to reference the real Firestore doc ID.

### Solution

Refactor the streaming message persistence to capture the Firestore doc ID and propagate it to React state:

**In `submit()`, after the streaming loop completes and the assistant response is saved:**

```typescript
// Current (fire-and-forget):
if (user && activeConvId && finalAssistantText) {
  addDoc(collection(db, "conversations", activeConvId, "messages"), {
    role: "assistant",
    text: finalAssistantText,
    sources: finalAssistantSources.length > 0 ? finalAssistantSources : null,
    createdAt: serverTimestamp(),
  }).catch(() => {});
}

// New (await and propagate):
if (user && activeConvId && finalAssistantText) {
  const docRef = await addDoc(
    collection(db, "conversations", activeConvId, "messages"),
    {
      role: "assistant",
      text: finalAssistantText,
      sources: finalAssistantSources.length > 0 ? finalAssistantSources : null,
      createdAt: serverTimestamp(),
    },
  );
  // Update React state with the real Firestore doc ID
  setMessages((prev) =>
    prev.map((m) => (m.id === assistantId ? { ...m, id: docRef.id } : m)),
  );
}
```

**In `loadConversation()`, message IDs already use `docSnap.id`** — no change needed.

The user message persistence should also be propagated similarly for consistency:

```typescript
if (user && activeConvId) {
  const userDocRef = await addDoc(
    collection(db, "conversations", activeConvId, "messages"),
    {
      role: "user",
      text: q,
      createdAt: serverTimestamp(),
    },
  );
  setMessages((prev) =>
    prev.map((m) =>
      m.id === userPlaceholderId ? { ...m, id: userDocRef.id } : m,
    ),
  );
}
```

**Trade-off:** This changes fire-and-forget writes to awaited writes, adding ~50-100ms latency per message save. This is acceptable because the UX benefit (reliable message IDs for ratings) outweighs the slight delay, and the delay is invisible to the user since messages appear optimistically in the UI.

---

## D-05: Conversation Feedback UI (FeedbackModal refactor)

### Current component

`FeedbackModal.tsx` — 270 lines, single-star rating + comment modal.

### New design

Refactor `FeedbackModal` into a multi-step form:

1. **Four star-rating rows**, each with:
   - Label above: "Tono de las respuestas", "Longitud de las respuestas", "Usabilidad del sistema", "Calificación general"
   - 5-star interactive row with hover/selected states (reuse existing star SVG patterns)
   - Dynamic label below selected value (same "Muy malo" → "Excelente" labels)

2. **Comment textarea** (optional, max 500 chars)

3. **Submit button** (disabled until all 4 ratings are set)

4. **Success state** (reuse existing success markup)

The modal uses the same motion/Framer Motion animations and styling patterns as the current FeedbackModal. The API call changes from `submitFeedback` to `submitConversationFeedback` with the new `ratings` payload shape.

**FeedbackButton.tsx** changes are minimal — only the tooltip text from "Calificar el sistema" to "Calificar la conversación".

---

## D-06: Message Rating Popover (new component)

### Component: `MessageRatingPopover.tsx`

A popover component that renders inline beneath the action button on an `AssistantBubble`.

**Props:**

```typescript
interface MessageRatingPopoverProps {
  conversationId: string;
  messageId: string;
  onSubmit: (ratings: MessageRatings, expectedAnswer?: string) => Promise<void>;
  onClose: () => void;
}
```

**Layout:**

```
┌─────────────────────────────────┐
│  Pertinencia de la respuesta ⓘ │
│  ★ ★ ★ ★ ★                     │
│                                 │
│  Precisión de la respuesta ⓘ   │
│  ★ ★ ★ ★ ★                     │
│                                 │
│  Respuesta adecuada            │
│  ┌─────────────────────────────┐│
│  │ Escribe la respuesta que... ││
│  └─────────────────────────────┘│
│                                 │
│  [Cancelar]  [Enviar]          │
└─────────────────────────────────┘
```

**Tooltip behavior:**

- Each rating label has an ⓘ icon that shows a tooltip on hover/focus
- Pertinence tooltip: "¿Qué tan relevante fue la respuesta para la pregunta que hiciste? Un 1 indica que no tuvo nada que ver; un 5 indica que fue directamente relevante."
- Accuracy tooltip: "¿Qué tan correcta y exacta fue la respuesta? Un 1 indica que fue incorrecta; un 5 indica que fue plenamente correcta."
- Tooltips use `aria-describedby` for accessibility
- Tooltips dismiss on Escape key

**Submit validation:**

- Both star ratings (pertinence, accuracy) required
- "Respuesta adecuada" optional
- Submit button disabled until both ratings are selected

**Success state:**

- Brief "¡Gracias! Tu calificación fue enviada." message (1.5s duration)
- Auto-close popover
- Parent `AssistantBubble` updates the action button to a "completed" state

---

## D-07: AssistantBubble Changes

### Current structure

`AssistantBubble` receives `text` and `sources` props, renders markdown + sources accordion.

### New structure

```typescript
interface AssistantBubbleProps {
  text: string;
  sources: SourceGroup[];
  messageId: string; // NEW: Firestore doc ID
  conversationId: string; // NEW: for feedback submission
  isRated?: boolean; // NEW: whether this message already has feedback
  onRate?: (messageId: string) => void; // NEW: callback when rating is submitted
}
```

**Action button area (bottom-right of bubble):**

- A small icon button renders below the `SourcesAccordion`
- When `isRated` is true → show a filled checkmark icon in a muted color, non-interactive
- When `isRated` is false → show an outline icon (e.g., `message-square-rate` or `star-border`) that becomes visible on hover/focus on desktop, always visible on mobile
- Clicking the action button sets `popoverOpen = true`
- The `MessageRatingPopover` renders as a positioned dropdown below the button

**Visibility on hover (desktop):**
The action button uses `opacity-0 group-hover:opacity-100 transition-opacity` to appear on hover of the entire bubble. On mobile (`@media (max-width: 767px)`), it's always visible.

**Popover positioning:**
The popover uses `position: absolute` relative to the bubble container, positioned `bottom: 100%` with `mb-2` offset. On narrow viewports, it switches to a centered overlay.

---

## D-08: MessageList & ChatInterface Wiring

### `MessageList.tsx`

Add props for message feedback:

```typescript
interface MessageListProps {
  messages: Message[];
  conversationId: string;
  ratedMessageIds: Set<string>; // IDs of messages already rated
  onMessageRate: (messageId: string) => void; // called after successful rating
}
```

Pass `messageId`, `conversationId`, `isRated`, and `onRate` to each `AssistantBubble`.

### `ChatInterface.tsx`

- Add `ratedMessageIds` state: `Set<string>` tracked in `ChatInterface`. When a message is successfully rated, add its ID to this set.
- Pass `ratedMessageIds` and `onMessageRate` callback down to `MessageList`.
- The `onMessageRate` callback calls `submitMessageFeedback` and on success adds the message ID to `ratedMessageIds`.

### Tracking rated status

We also need to check if a message was already rated when a conversation is loaded. Two approaches:

**Design decision:** Check rated status on demand (when popover opens) rather than upfront (loading all ratings for all messages). This avoids an extra API call per conversation load. The frontend optimistically marks messages as rated after local submission and uses the `409 Conflict` response from the backend as a fallback check.

This means:

- `ratedMessageIds` starts empty for new conversations
- When `loadConversation` is called, start with an empty set (the popover will handle the 409 case)
- On successful rating submission, add the message ID to the set

---

## D-09: Admin Dashboard

### Overview page (`/admin/page.tsx`)

Add a second section for message feedback stats:

```
┌─ Resumen ──────────────────────────────────┐
│                                             │
│  ┌─ Calificaciones de conversación ───────┐│
│  │ Total: 42  Promedio: 4.1               ││
│  │ [Distribution bars for overall]         ││
│  └─────────────────────────────────────────┘│
│                                             │
│  ┌─ Calificaciones por mensaje ────────────┐│
│  │ Total: 128                              ││
│  │ Avg Pertinencia: 4.2  Avg Precisión: 3.8││
│  │ [Distribution bars for pertinence]       ││
│  │ [Distribution bars for accuracy]         ││
│  └─────────────────────────────────────────┘│
└─────────────────────────────────────────────┘
```

The page makes an additional fetch to `GET /api/admin/message-feedback?page=1&page_size=1` to get aggregate stats.

### Conversation Feedback page (`/admin/feedback/page.tsx`)

Update the table columns from a single "Rating" column to four dimension columns:

- Tono | Longitud | Usabilidad | General

Each column renders a star rating. The filter changes to "Overall mínimo/máximo".

### New Message Feedback page (`/admin/message-feedback/page.tsx`)

Separate page at `/admin/message-feedback` with:

- Table columns: Fecha | Usuario | Conversación | Pertinencia | Precisión | Respuesta esperada | Acciones
- "Respuesta esperada" column truncates to 50 chars with expandable tooltip
- Filters: min/max pertinence, min/max accuracy, date range
- Pagination

### Admin sidebar

Add a new link in `frontend/app/admin/layout.tsx`:

```
- Feedback (existing → /admin/feedback)
- Calificaciones por mensaje (new → /admin/message-feedback)
```

---

## D-10: Firestore Rules & Indexes

### `firestore.rules` additions

```
// message_feedback: crear si autenticado (con validación de no-duplicado en backend);
// leer solo admins
match /message_feedback/{feedbackId} {
  allow create: if request.auth != null;
  allow read, list: if isAdmin();
}
```

### `firestore.indexes.json` additions

```json
{
  "indexes": [
    // ... existing indexes ...
    {
      "collectionGroup": "message_feedback",
      "queryScope": "COLLECTION",
      "fields": [
        { "fieldPath": "userId", "order": "ASCENDING" },
        { "fieldPath": "messageId", "order": "ASCENDING" }
      ]
    },
    {
      "collectionGroup": "message_feedback",
      "queryScope": "COLLECTION",
      "fields": [{ "fieldPath": "createdAt", "order": "DESCENDING" }]
    }
  ]
}
```

### `docs/firebase-config-manual.md` updates

Add a new section:

**Section 7: message_feedback collection**

1. Deploy updated `firestore.rules` (`firebase deploy --only firestore:rules`)
2. Create composite indexes for `message_feedback`:
   - `userId ASC + messageId ASC`
   - `createdAt DESC`
3. Run the migration script: `uv run python scripts/migrate_feedback_ratings.py`
4. Verify the `message_feedback` collection appears in Firestore Console after first submission

---

## D-11: File Change Summary

| #   | File                                                | Change Type    | Description                                                                                                                                                                                     |
| --- | --------------------------------------------------- | -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `rag/api/schemas.py`                                | Modify         | Add `RatingDimensions`, `MessageFeedbackRatings`, update `FeedbackRequest`, add `MessageFeedbackRequest`, `MessageFeedbackResponse`, `AdminMessageFeedbackItem`, `AdminMessageFeedbackResponse` |
| 2   | `rag/api/routes/feedback.py`                        | Modify         | Update `submit_feedback` to write `ratings` dict instead of `rating`. Add `POST /api/feedback/message` endpoint.                                                                                |
| 3   | `rag/api/routes/admin.py`                           | Modify         | Update `list_feedback` to return `ratings` instead of `rating`. Add `GET /api/admin/message-feedback` endpoint.                                                                                 |
| 4   | `rag/api/routes/__init__.py`                        | Check          | Ensure feedback router includes new message endpoint.                                                                                                                                           |
| 5   | `frontend/lib/types.ts`                             | Modify         | Add `ConversationRatings`, `MessageRatings`, `ConversationFeedbackRequest`, `MessageFeedbackRequest`, `AdminMessageFeedbackItem`. Mark `FeedbackRequest` as deprecated.                         |
| 6   | `frontend/lib/api.ts`                               | Modify         | Add `submitConversationFeedback`, `submitMessageFeedback`. Rename `submitFeedback` → `submitConversationFeedback`.                                                                              |
| 7   | `frontend/hooks/useChat.ts`                         | Modify         | Fix message ID propagation (await `addDoc` + update state). Add `ratedMessageIds` tracking to `UseChatReturn`.                                                                                  |
| 8   | `frontend/components/chat/FeedbackModal.tsx`        | Major refactor | Replace single-star form with 4-dimension star form. New payload shape with `ratings` object.                                                                                                   |
| 9   | `frontend/components/chat/FeedbackButton.tsx`       | Minor          | Update tooltip to "Calificar la conversación".                                                                                                                                                  |
| 10  | `frontend/components/chat/AssistantBubble.tsx`      | Modify         | Add `messageId`, `conversationId`, `isRated`, `onRate` props. Add action button row with rating icon. Integrate `MessageRatingPopover`.                                                         |
| 11  | `frontend/components/chat/MessageRatingPopover.tsx` | **New**        | Popover component for per-message rating (pertinence, accuracy, expected answer).                                                                                                               |
| 12  | `frontend/components/chat/MessageList.tsx`          | Modify         | Pass `conversationId`, `ratedMessageIds`, `onMessageRate` props to `AssistantBubble`.                                                                                                           |
| 13  | `frontend/components/chat/ChatInterface.tsx`        | Modify         | Add `ratedMessageIds` state. Wire `onMessageRate` through `MessageList`.                                                                                                                        |
| 14  | `frontend/app/admin/page.tsx`                       | Modify         | Add message feedback stats section.                                                                                                                                                             |
| 15  | `frontend/app/admin/feedback/page.tsx`              | Modify         | Update table for 4-dimension ratings. Change filters to use `overall` dimension.                                                                                                                |
| 16  | `frontend/app/admin/message-feedback/page.tsx`      | **New**        | New page for message feedback listing with filters and pagination.                                                                                                                              |
| 17  | `frontend/app/admin/layout.tsx`                     | Modify         | Add sidebar link for "Calificaciones por mensaje".                                                                                                                                              |
| 18  | `firestore.rules`                                   | Modify         | Add `message_feedback` collection rule.                                                                                                                                                         |
| 19  | `firestore.indexes.json`                            | Modify         | Add indexes for `message_feedback`.                                                                                                                                                             |
| 20  | `docs/firebase-config-manual.md`                    | Modify         | Add section 7 for `message_feedback` collection and migration steps.                                                                                                                            |
| 21  | `scripts/migrate_feedback_ratings.py`               | **New**        | One-time migration script for existing `feedback` docs.                                                                                                                                         |

---

## D-12: Implementation Order

The recommended implementation order accounts for dependencies:

1. **Backend schemas** — `rag/api/schemas.py` (foundation for everything)
2. **Backend conversation feedback endpoint** — `rag/api/routes/feedback.py` (modify existing)
3. **Backend message feedback endpoint** — `rag/api/routes/feedback.py` (new endpoint)
4. **Backend admin endpoints** — `rag/api/routes/admin.py` (modify + new)
5. **Frontend types & API client** — `frontend/lib/types.ts`, `frontend/lib/api.ts`
6. **useChat.ts message ID fix** — `frontend/hooks/useChat.ts`
7. **Conversation FeedbackModal refactor** — `frontend/components/chat/FeedbackModal.tsx`
8. **MessageRatingPopover component** — **new** `frontend/components/chat/MessageRatingPopover.tsx`
9. **AssistantBubble action button** — `frontend/components/chat/AssistantBubble.tsx`
10. **MessageList & ChatInterface wiring** — `MessageList.tsx`, `ChatInterface.tsx`
11. **Admin dashboard updates** — all admin files
12. **Firestore rules & indexes** — `firestore.rules`, `firestore.indexes.json`
13. **Firebase config manual** — `docs/firebase-config-manual.md`
14. **Migration script** — `scripts/migrate_feedback_ratings.py`
15. **End-to-end testing**
