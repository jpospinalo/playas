# SDD Tasks: Dual Rating System

**change_id:** dual-rating-system
**design_ref:** openspec/design-dual-rating.md
**spec_ref:** openspec/spec-dual-rating.md

---

## Review Workload Forecast

Total estimated changed lines: ~1800-2200 across 21 files (17 modified, 4 new).

| Area                                 | Est. Lines | Risk                         |
| ------------------------------------ | ---------- | ---------------------------- |
| Backend schemas & endpoints          | ~250       | Medium (breaking API change) |
| Frontend types & API client          | ~80        | Low                          |
| useChat.ts message ID fix            | ~30        | High (race condition risk)   |
| FeedbackModal refactor               | ~200       | Medium (existing component)  |
| MessageRatingPopover (new)           | ~250       | Low (new component)          |
| AssistantBubble + MessageList wiring | ~80        | Medium (prop threading)      |
| ChatInterface wiring                 | ~50        | Low                          |
| Admin overview + feedback page       | ~200       | Medium (existing pages)      |
| Admin message-feedback page (new)    | ~250       | Low (new page)               |
| Admin layout sidebar                 | ~15        | Low                          |
| Firestore rules & indexes            | ~20        | Low                          |
| firebase-config-manual.md            | ~40        | Low                          |
| Migration script                     | ~60        | Medium (data migration)      |

**Chained PR recommendation:** Given ~2000 lines, recommend 2 chained PRs:

- **PR-1 (Backend + Infra):** Schemas, endpoints, Firestore rules/indexes, migration script, firebase-config-manual. ~370 lines.
- **PR-2 (Frontend):** Types, API client, useChat fix, UI components, admin pages. ~1630 lines.

If strict 400-line budget: consider 3-4 chained PRs splitting frontend further.

---

## Task Breakdown

### T-01: Backend — Schemas for dual rating system

**RS refs:** RS-01 (REQ-01.4, REQ-01.5, REQ-01.7), RS-02 (REQ-02.4, REQ-02.5)
**Files:** `rag/api/schemas.py`
**Est. lines:** ~80
**Dependencies:** None

Add new Pydantic models:

- `RatingDimensions` (tone, length, usability, overall — each int 1-5)
- `MessageFeedbackRatings` (pertinence, accuracy — each int 1-5)
- Update `FeedbackRequest` to use `ratings: RatingDimensions` instead of `rating: int`
- Add `ConversationFeedbackRequest` as alias (deprecated `FeedbackRequest` for transition)
- Add `MessageFeedbackRequest` (conversation_id, message_id, ratings, expected_answer)
- Add `MessageFeedbackResponse` (id)
- Add `AdminMessageFeedbackItem`
- Add `AdminMessageFeedbackResponse` (items, total, avg_ratings, distributions)
- Add `RatingDimensionsFloat` (float versions for admin averages)
- Add `RatingDistributions` type
- Update `AdminFeedbackItem` to use `ratings: RatingDimensions` instead of `rating: int`
- Update `AdminFeedbackResponse` to use `avg_ratings: RatingDimensionsFloat` and `distributions: RatingDistributions`

**Validation:** Run `make lint` and `make typecheck`. All existing tests must still pass.

---

### T-02: Backend — Conversation feedback endpoint update

**RS refs:** RS-01 (REQ-01.4, REQ-01.5)
**Files:** `rag/api/routes/feedback.py`
**Est. lines:** ~30 changed
**Dependencies:** T-01

- Update `submit_feedback` to write `ratings` dict to Firestore instead of `rating` integer
- Remove `rating` field from Firestore write
- Ensure `conversation_title` lookup still works

**Validation:** `make lint && make typecheck`. Manual test with curl.

---

### T-03: Backend — Message feedback endpoint

**RS refs:** RS-02 (REQ-02.4, REQ-02.7, REQ-02.8)
**Files:** `rag/api/routes/feedback.py`
**Est. lines:** ~60 new
**Dependencies:** T-01

- Add `POST /api/feedback/message` endpoint
- Validate `MessageFeedbackRequest`
- Check for duplicate: query `message_feedback` where `userId == uid AND messageId == message_id`; if exists, return 409
- Write to `message_feedback` collection with `userId`, `userEmail`, `conversationId`, `messageId`, `ratings`, `expectedAnswer`, `createdAt`
- Return `{ "id": doc_ref.id }` with 201 status

**Validation:** `make lint && make typecheck`. Manual test: create message feedback, attempt duplicate → 409.

---

### T-04: Backend — Admin endpoints update and new

**RS refs:** RS-01 (REQ-01.7), RS-03 (REQ-03.5)
**Files:** `rag/api/routes/admin.py`
**Est. lines:** ~120 (60 changed + 60 new)
**Dependencies:** T-01

- Update `list_feedback` to return `ratings` dict, `avg_ratings`, and `distributions` instead of `rating`, `avg_rating`, `distribution`
- Change filter params from `min_rating`/`max_rating` to `min_overall`/`max_overall` (filtering on `ratings.overall`)
- Add `GET /api/admin/message-feedback` endpoint with pagination and filters (min/max pertinence, min/max accuracy, date range)
- Compute `avg_ratings` and `distributions` for both pertinence and accuracy

**Validation:** `make lint && make typecheck`. Manual test: curl both admin endpoints.

---

### T-05: Frontend — Types and API client

**RS refs:** RS-01 (REQ-01.4), RS-02 (REQ-02.4)
**Files:** `frontend/lib/types.ts`, `frontend/lib/api.ts`
**Est. lines:** ~80
**Dependencies:** None (parallel with T-01 if desired)

- Add `ConversationRatings`, `MessageRatings` types
- Add `ConversationFeedbackRequest` type
- Add `MessageFeedbackRequest` type
- Add `AdminMessageFeedbackItem` type
- Rename/deprecate old `FeedbackRequest` type
- Add `submitConversationFeedback()` function to `api.ts`
- Add `submitMessageFeedback()` function to `api.ts`
- Update `submitFeedback` to call new API shape (or rename)

**Validation:** `cd frontend && bun run build` should pass.

---

### T-06: Frontend — useChat.ts message ID propagation

**RS refs:** RS-02 (REQ-02.6)
**Files:** `frontend/hooks/useChat.ts`
**Est. lines:** ~30 changed
**Dependencies:** None

- In `submit()`, change the assistant message `addDoc()` from fire-and-forget to `await`
- After `addDoc()`, update the message in React state with `docRef.id`
- Similarly await the user message `addDoc()` and propagate the real ID
- Add `ratedMessageIds` state (`Set<string>`) and `rateMessage(messageId: string)` callback to `UseChatReturn`
- Export `ratedMessageIds` and `rateMessage` from the hook

**Validation:** Chat must still work — user and assistant messages appear correctly. Verify via Firestore Console that message IDs in React state match Firestore doc IDs.

---

### T-07: Frontend — FeedbackModal refactor (conversation feedback)

**RS refs:** RS-01 (REQ-01.1, REQ-01.2, REQ-01.3)
**Files:** `frontend/components/chat/FeedbackModal.tsx`
**Est. lines:** ~200 (major refactor)
**Dependencies:** T-05

- Replace single-star row with four star-rating rows, each with label and dynamic label
- Labels: "Tono de las respuestas", "Longitud de las respuestas", "Usabilidad del sistema", "Calificación general"
- Dynamic labels per star value (Muy malo → Excelente)
- Keep comment textarea (max 500 chars, placeholder "¿Qué podría mejorar el sistema?")
- Submit button disabled until all 4 ratings selected
- Call `submitConversationFeedback` with `{ ratings: { tone, length, usability, overall }, comment, conversation_id }`
- Keep success/error states and animations
- FeedbackButton tooltip: change to "Calificar la conversación"

**Validation:** Manual test: open modal, verify 4 star rows, submit only works when all selected, success state shown.

---

### T-08: Frontend — MessageRatingPopover component (new)

**RS refs:** RS-02 (REQ-02.1, REQ-02.2, REQ-02.3), RS-05 (REQ-05.1, REQ-05.2)
**Files:** `frontend/components/chat/MessageRatingPopover.tsx` (NEW)
**Est. lines:** ~250
**Dependencies:** T-05

- Popover component with three fields:
  - Pertinence stars (1-5) with ⓘ tooltip
  - Accuracy stars (1-5) with ⓘ tooltip
  - "Respuesta adecuada" textarea (max 1000 chars)
- Tooltip implementation:
  - Activate on hover (desktop) and focus (keyboard)
  - Use `aria-describedby` for accessibility
  - Dismiss on Escape
  - Tooltip text as defined in REQ-05.1
- Submit validation: both star ratings required, textarea optional
- Cancel button and Submit button
- Success state: brief "¡Gracias! Tu calificación fue enviada." → auto-close after 1.5s
- Styling: consistent with existing FeedbackModal design tokens
- Position: absolute, below trigger button, auto-flip on viewport edge

**Validation:** Component renders correctly, tooltips accessible via keyboard, submit sends correct payload.

---

### T-09: Frontend — AssistantBubble action button and wiring

**RS refs:** RS-02 (REQ-02.1, REQ-02.3)
**Files:** `frontend/components/chat/AssistantBubble.tsx`, `frontend/components/chat/MessageList.tsx`, `frontend/components/chat/ChatInterface.tsx`
**Est. lines:** ~80 changed
**Dependencies:** T-06, T-08

- `AssistantBubble`: add props `messageId`, `conversationId`, `isRated`, `onRate`
- Render action button row below SourcesAccordion
- Button icon: visible on hover (desktop), always visible (mobile)
- `isRated=false`: outline icon, click opens MessageRatingPopover
- `isRated=true`: filled checkmark icon, non-interactive
- MessageRatingPopover renders inline when open
- After successful rating, call `onRate(messageId)` → ChatInterface adds to `ratedMessageIds`
- `MessageList`: pass `conversationId`, `ratedMessageIds`, `onMessageRate` to AssistantBubble
- `ChatInterface`: add `ratedMessageIds` state, `handleMessageRate` callback, pass down via MessageList

**Validation:** Rating button appears on hover for assistant messages. Clicking opens popover. After submit, button changes to completed state.

---

### T-10: Frontend — Admin overview page update

**RS refs:** RS-03 (REQ-03.1)
**Files:** `frontend/app/admin/page.tsx`
**Est. lines:** ~60 changed
**Dependencies:** T-04 (backend endpoint must exist)

- Add fetch for `GET /api/admin/message-feedback?page=1&page_size=1` to get total, avg_pertinence, avg_accuracy
- Add new card section "Calificaciones por mensaje" with: total count, avg pertinence stars, avg accuracy stars
- Add distribution bars for pertinence and accuracy
- Keep existing conversation feedback section, update to use `avg_ratings.overall` and `distributions.overall`

**Validation:** Admin overview page renders both sections with correct data.

---

### T-11: Frontend — Admin feedback page update (4-dimension table)

**RS refs:** RS-03 (REQ-03.3)
**Files:** `frontend/app/admin/feedback/page.tsx`
**Est. lines:** ~100 changed
**Dependencies:** T-04 (backend endpoint change)

- Update `FeedbackItem` and `FeedbackResponse` types to match new API shape (`ratings` dict, `avg_ratings`, `distributions`)
- Change table columns from single "Rating" to four: Tono, Longitud, Usabilidad, General
- Each column renders a star rating
- Update filter params from `min_rating`/`max_rating` to `min_overall`/`max_overall`
- Update stats display to show per-dimension averages and distributions

**Validation:** Feedback page renders 4-dimension columns, filters work correctly.

---

### T-12: Frontend — Admin message feedback page (new)

**RS refs:** RS-03 (REQ-03.2, REQ-03.4)
**Files:** `frontend/app/admin/message-feedback/page.tsx` (NEW), `frontend/app/admin/layout.tsx`
**Est. lines:** ~250 + ~15
**Dependencies:** T-04 (backend endpoint must exist)

- New page at `/admin/message-feedback` with table, filters, pagination
- Table columns: Fecha, Usuario, Conversación, Pertinencia (stars), Precisión (stars), Respuesta esperada (truncated/expandable)
- Filters: min/max pertinence, min/max accuracy, date range
- Pagination controls (same pattern as feedback page)
- Fetch from `GET /api/admin/message-feedback`
- Add sidebar link "Calificaciones por mensaje" in admin layout

**Validation:** Page renders correctly, filters work, pagination works.

---

### T-13: Infrastructure — Firestore rules and indexes

**RS refs:** RS-04 (REQ-04.1, REQ-04.2, REQ-04.3)
**Files:** `firestore.rules`, `firestore.indexes.json`
**Est. lines:** ~20 changed
**Dependencies:** None

- Add `message_feedback` collection rule to `firestore.rules`
- Add composite indexes for `message_feedback` to `firestore.indexes.json`

**Validation:** `firebase deploy --only firestore:rules` succeeds. Verify indexes in Firebase Console.

---

### T-14: Infrastructure — Firebase config manual update

**RS refs:** RS-04 (REQ-04.4)
**Files:** `docs/firebase-config-manual.md`
**Est. lines:** ~40 added
**Dependencies:** T-13

- Add section 7 "message_feedback collection" documenting:
  - Deploy updated rules
  - Create composite indexes for `message_feedback`
  - Run migration script
  - Verify collection appears in Console

**Validation:** Review updated doc for completeness.

---

### T-15: Migration script

**RS refs:** RS-01 (REQ-01.6)
**Files:** `scripts/migrate_feedback_ratings.py` (NEW)
**Est. lines:** ~60
**Dependencies:** T-02 (backend must write new shape)

- Read all documents from `feedback` collection
- For each doc with `rating` field but no `ratings` field:
  - Compute `ratings = { tone: rating, length: rating, usability: rating, overall: rating }`
  - Update doc: set `ratings` field, delete `rating` field
- Log docs processed and any errors
- Support `--dry-run` flag to preview changes without writing
- Use Firebase Admin SDK (same as `rag/api/firebase_admin.py`)

**Validation:** Run with `--dry-run` on production data snapshot. Verify shape matches expected.

---

### T-16: End-to-end integration test

**RS refs:** All
**Files:** None (testing activity)
**Est. lines:** 0 (manual testing)
**Dependencies:** T-01 through T-15

Manual test scenarios:

1. Submit conversation feedback with all 4 dimensions → verify Firestore doc shape
2. Submit message feedback on an assistant message → verify Firestore doc and popover success state
3. Attempt duplicate message feedback → verify 409 response
4. View admin overview with both rating types
5. View admin feedback page with 4-dimension columns
6. View admin message-feedback page with filters
7. Verify tooltips on pertinence and accuracy labels
8. Verify message ID propagation: send a message, check Firestore Console for ID match
9. Run migration script with `--dry-run`
10. Verify auth-gated feedback: unauthenticated user cannot submit

---

## Dependency Graph

```
T-01 (schemas) ─┬─→ T-02 (conv feedback endpoint) ─┬─→ T-04 (admin endpoints) ─┬─→ T-10 (admin overview)
                 ├─→ T-03 (msg feedback endpoint)  ─┘                           ├─→ T-11 (admin feedback page)
                 └─→ T-05 (frontend types) ─┬─→ T-07 (FeedbackModal)
                                               └─→ T-08 (MessageRatingPopover) ─┬─→ T-09 (AssistantBubble wiring)
                                                                                    └─→ T-12 (admin msg-feedback page)

T-06 (useChat fix) ─→ T-09 (AssistantBubble wiring)
T-13 (Firestore) ─→ T-14 (firebase-config-manual)
T-02 ─→ T-15 (migration script)
All ─→ T-16 (integration test)
```

## Implementation Order

**Phase 1 — Backend (T-01 → T-02 → T-03 → T-04)**
Can be done sequentially since each depends on the previous schemas.

**Phase 2 — Frontend Foundation (T-05, T-06)**
Parallel with Phase 1 — no backend dependency yet (just types).

**Phase 3 — Frontend UI (T-07, T-08, T-09)**
T-07 and T-08 can be parallel. T-09 depends on T-06 and T-08.

**Phase 4 — Admin (T-10, T-11, T-12)**
After T-04 (backend admin endpoints).

**Phase 5 — Infra (T-13, T-14, T-15)**
Parallel with Phases 3-4.

**Phase 6 — Integration (T-16)**
After all tasks complete.
