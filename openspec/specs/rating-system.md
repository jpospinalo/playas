# Rating System — Canonical Specification

**Last updated:** 2026-05-21
**Change:** dual-rating-system

This document is the source of truth for the rating system. It consolidates all requirements and decisions from the dual-rating-system SDD change.

---

## 1. Conversation-Level Rating (System Usability)

### Data Model

- **Collection:** `feedback` (existing, schema migrated)
- **Document shape:**
  ```
  { userId, userEmail, ratings: { tone, length, usability, overall }, comment,
    conversationId, conversationTitle, createdAt }
  ```
- All four ratings are integers 1–5, REQUIRED
- Comment is optional, max 500 chars

### API

- `POST /api/feedback` — body: `{ ratings: {tone, length, usability, overall}, comment?, conversation_id? }`
- Returns `{ id: "doc_id" }` with 201
- Requires authentication
- `GET /api/admin/feedback` — supports `min_overall`, `max_overall`, `start_date`, `end_date`, pagination
  - Returns `avg_ratings: {tone, length, usability, overall}`, `distributions: {tone: {...}, ...}`

### UI (FeedbackModal)

- Floating FeedbackButton → opens modal dialog with 4 star-rating rows
- Labels: Tono, Longitud, Usabilidad, General
- Dynamic labels per star (Muy malo → Excelente)
- Optional comment textarea (500 chars)
- Disabled submit until all 4 ratings selected
- Success state with confirmation message

### Migration

- Legacy `rating` field → `ratings.overall` (with all 4 dimensions set to same value)
- Script: `scripts/migrate_feedback_ratings.py`

---

## 2. Message-Level Rating (Per-Response Performance)

### Data Model

- **Collection:** `message_feedback` (new)
- **Document shape:**
  ```
  { userId, userEmail, conversationId, messageId, ratings: { pertinence, accuracy },
    expectedAnswer, createdAt }
  ```
- `pertinence` and `accuracy` are integers 1–5, REQUIRED
- `expectedAnswer` is optional string, max 1000 chars

### API

- `POST /api/feedback/message` — body: `{ conversation_id, message_id, ratings: {pertinence, accuracy}, expected_answer? }`
- Returns `{ id: "doc_id" }` with 201
- Returns 409 on duplicate (same userId + messageId)
- Requires authentication
- `GET /api/admin/message-feedback` — supports `min/max_pertinence`, `min/max_accuracy`, `start_date`, `end_date`, pagination
  - Returns `avg_ratings: {pertinence, accuracy}`, `distributions: {pertinence: {...}, accuracy: {...}}`

### UI (MessageRatingPopover)

- Action button on each AssistantBubble (visible on hover in desktop, always in mobile)
- Clicking opens a **modal dialog** (not inline popover) with backdrop blur
- Three fields:
  1. "Pertinencia de la respuesta" — 1–5 stars with tooltip
  2. "Precisión de la respuesta" — 1–5 stars with tooltip
  3. "Respuesta adecuada" — optional textarea (1000 chars)
- Tooltips accessible via keyboard (focus on ⓘ icon), `aria-describedby`, dismiss on Escape
- Submit disabled until both ratings selected
- After submission: button shows checkmark + "Calificado" state (non-interactive)

### Message ID Fix

- `useChat.ts` propagates real Firestore doc IDs after `addDoc()` to React state
- This ensures `message_id` in API calls references actual Firestore documents

### Duplicate Prevention

- Backend checks `message_feedback` for existing `userId + messageId` before creating
- Frontend tracks `ratedMessageIds` in local state

---

## 3. Admin Dashboard

### Overview (`/admin`)

- Two sections: Conversation feedback stats + Message feedback stats
- Each shows dimension-level averages and distribution bars

### Conversation Feedback (`/admin/feedback`)

- Table with 4 rating columns: Tono, Longitud, Usabilidad, General
- Filters: overall min/max, date range
- Sidebar label: "Conversaciones"

### Message Feedback (`/admin/message-feedback`)

- Table: Fecha, Usuario, Pertinencia, Precisión, Respuesta esperada (expandable)
- Filters: pertinence min/max, accuracy min/max, date range
- Sidebar label: "Mensajes"

---

## 4. Firestore Rules & Indexes

### Rules

- `feedback/{id}`: create if auth, read/list if admin
- `message_feedback/{id}`: create if auth, read/list if admin

### Indexes

- `message_feedback`: `createdAt DESC`
- `message_feedback`: `userId ASC, messageId ASC`
- `feedback`: `createdAt DESC` (existing)
- `feedback`: `ratings.overall` filters via `min_overall`/`max_overall`

### Manual Steps

- Deploy rules: `firebase deploy --only firestore:rules`
- Create indexes in Firebase Console
- Run migration: `uv run python scripts/migrate_feedback_ratings.py`
- See `docs/firebase-config-manual.md` Section 7

---

## 5. Design Decisions

| ID   | Decision                                       | Rationale                                                      |
| ---- | ---------------------------------------------- | -------------------------------------------------------------- |
| DD-1 | Two separate Firestore collections             | Clean separation, independent rules, no chat history migration |
| DD-2 | Migrate existing feedback (no backward compat) | Cleaner schema, simpler admin dashboard                        |
| DD-3 | Modal dialog for message rating                | Consistent with FeedbackModal, avoids context switch           |
| DD-4 | Non-editable ratings                           | Simpler schema, cleaner data                                   |
| DD-5 | Separate admin page `/admin/message-feedback`  | Separate concerns, cleaner URLs                                |
| DD-6 | Fix message ID propagation                     | Prerequisite for reliable message-level references             |

---

## 6. Affected Files

**Backend:** `rag/api/schemas.py`, `rag/api/routes/feedback.py`, `rag/api/routes/admin.py`

**Frontend:** `lib/types.ts`, `lib/api.ts`, `hooks/useChat.ts`, `components/chat/FeedbackModal.tsx`, `components/chat/MessageRatingPopover.tsx` (new), `components/chat/AssistantBubble.tsx`, `components/chat/MessageList.tsx`, `components/chat/ChatInterface.tsx`, `app/admin/page.tsx`, `app/admin/feedback/page.tsx`, `app/admin/message-feedback/page.tsx` (new), `app/admin/layout.tsx`

**Infra:** `firestore.rules`, `firestore.indexes.json`, `docs/firebase-config-manual.md`, `scripts/migrate_feedback_ratings.py` (new)
