# SDD Explore: Dual Rating System

## 1. Scope Summary

Replace the single 1-5 star conversation rating with two distinct rating systems:

1. **Conversation-level system usability rating** — multi-dimensional form (tone, length, usability + comment) tied to the whole chat.
2. **Message-level per-response rating** — attached to each assistant bubble, measuring pertinence, accuracy, and expected answer.

Both require authenticated users.

---

## 2. Feasibility Assessment

### ✅ Feasible with moderate effort (~3–4 days)

**Backend:**

- The existing `/api/feedback` endpoint and `feedback` Firestore collection can be **extended** rather than replaced.
- The message-level data model needs a decision: **separate `message_feedback` collection** is recommended over inline fields in message docs.

**Frontend:**

- `FeedbackModal.tsx` and `FeedbackButton.tsx` are cleanly isolated — the conversation-level modal can be **refactored** to accept a multi-field form.
- `AssistantBubble.tsx` currently has no action buttons, but its layout allows adding a small action row.
- `MessageList.tsx` needs to pass `messageId` (and possibly `onRate`) down to bubbles.

**Auth/Firestore rules:**

- Current rules already enforce auth for creating feedback and admin-only reads. Only a new rule for the `message_feedback` collection needs to be added.

---

## 3. Data Model & Collection Strategy

### Recommended: Two collections, unified read endpoint

| Collection                      | Purpose                             | Document shape                                                                                                               |
| ------------------------------- | ----------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `feedback` (existing, extended) | Conversation-level system usability | `userId`, `userEmail`, `conversationId`, `conversationTitle`, `ratings: { tone, length, usability }`, `comment`, `createdAt` |
| `message_feedback` (new)        | Per-response performance            | `userId`, `userEmail`, `conversationId`, `messageId`, `ratings: { pertinence, accuracy }`, `expectedAnswer`, `createdAt`     |

### Why separate collection for message ratings instead of inline?

- **Firestore rules** — granularity: a user should only be able to create feedback docs, not modify `conversations/{id}/messages/{id}` entries.
- **Schema evolution** — adding fields to conversation messages requires migration of existing chat history; a new collection is zero-migration.
- **Admin queries** — listing all message feedback is simpler from a top-level collection than querying across nested subcollections.
- **Rate limiting / duplicates** — easier to enforce "one rating per user per message" with a compound unique constraint.

---

## 4. Affected Files

### Backend

| File                         | Change                                                                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rag/api/schemas.py`         | Extend `FeedbackRequest` to support `ratings` dict. Add `MessageFeedbackRequest`, `MessageFeedbackResponse`, `AdminMessageFeedbackItem`, `AdminMessageFeedbackResponse`. |
| `rag/api/routes/feedback.py` | Extend `submit_feedback` to handle conversation-level multi-field payload. Add `POST /api/feedback/message` for message-level feedback.                                  |
| `rag/api/routes/admin.py`    | Extend `/api/admin/feedback` to return conversation-level aggregates. Add `/api/admin/message-feedback` endpoint.                                                        |

### Frontend — Shared

| File                    | Change                                                                                           |
| ----------------------- | ------------------------------------------------------------------------------------------------ |
| `frontend/lib/types.ts` | Add `MessageRating`, `UsabilityRating` types. Update `FeedbackRequest` or add new request types. |
| `frontend/lib/api.ts`   | Add `submitConversationFeedback()` and `submitMessageFeedback()` functions.                      |

### Frontend — Chat

| File                                           | Change                                                                                              |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `frontend/components/chat/FeedbackModal.tsx`   | Major refactor: replace single-star form with multi-field usability form.                           |
| `frontend/components/chat/FeedbackButton.tsx`  | Minor: update tooltip label to "Calificar la conversación".                                         |
| `frontend/components/chat/AssistantBubble.tsx` | Add action row with rating icon that opens a popover for per-message rating.                        |
| `frontend/components/chat/MessageList.tsx`     | Pass `messageId` and rating handler callback to `AssistantBubble`.                                  |
| `frontend/components/chat/ChatInterface.tsx`   | Update `FeedbackModal` invocation to new props. Wire message rating callback down to `MessageList`. |

### Frontend — Admin

| File                                   | Change                                                            |
| -------------------------------------- | ----------------------------------------------------------------- | ------------------------------ |
| `frontend/app/admin/page.tsx`          | Add message feedback stats (total, avg pertinence, avg accuracy). |
| `frontend/app/admin/feedback/page.tsx` | Add tab switcher for "Conversaciones"                             | "Mensajes". New table columns. |

### Firebase

| File                             | Change                                                      |
| -------------------------------- | ----------------------------------------------------------- |
| `firestore.rules`                | Add rule for `message_feedback/{id}` collection.            |
| `firestore.indexes.json`         | Add index on `message_feedback` for `createdAt DESCENDING`. |
| `docs/firebase-config-manual.md` | Document new `message_feedback` collection and indexes.     |

---

## 5. Risks & Mitigations

| Risk                                             | Severity | Mitigation                                                                                        |
| ------------------------------------------------ | -------- | ------------------------------------------------------------------------------------------------- |
| **Firestore compound query cost**                | Low      | Both collections are small. In-memory pagination acceptable.                                      |
| **UI clutter on AssistantBubble**                | Medium   | Compact inline action button (popover, not full modal). Only show on hover/focus.                 |
| **Message ID mismatch**                          | High     | Refactor `useChat.ts` to capture and propagate Firestore doc IDs to React state after `addDoc()`. |
| **Data migration if changing `feedback` schema** | Low      | Keep old `rating` field alongside new `ratings` dict. Treat legacy docs gracefully.               |
| **Duplicate message ratings**                    | Low      | Application-level check before write (query by `userId+messageId`).                               |

### 🔥 Critical Gap: Message ID Mismatch

When a user submits a message-level rating immediately after receiving a response, the frontend `message.id` is the temporary `crypto.randomUUID()` assigned before Firestore persistence. The actual Firestore `messages/{docId}` is created asynchronously via `addDoc()`.

**Recommendation:** Refactor `useChat.ts` to `await addDoc(...)` and update the local message state with the real Firestore doc ID.

---

## 6. Open Questions

1. **Deprecate single `rating` field or keep backward compatibility?** — Keep `rating` for existing docs; new docs write both.
2. **Editable message ratings?** — No. One submission per message per user.
3. **Message rating as popover or modal?** — Popover inside `AssistantBubble` for faster UX.
4. **"Report/hallucination" flag separate from numeric ratings?** — Not in scope now, natural place to add later.
5. **Aggregation: Python or Firestore?** — Python aggregation for now.

---

## 7. Recommendations

1. **Two separate collections:** `feedback` (extended) and `message_feedback` (new).
2. **Refactor `useChat.ts` first** to capture Firestore message doc IDs.
3. **Evolve `FeedbackModal.tsx`** rather than replace it — generalize into multi-field form.
4. **New `MessageRatingPopover.tsx`** component for message-level ratings.
5. **Admin dashboard in two phases:** message feedback list first, then cross-tab aggregates.
6. **Firestore indexes:** Add `message_feedback` index before deploying.

---

## 8. Estimated Effort

| Task                                                                             | Est.          |
| -------------------------------------------------------------------------------- | ------------- |
| Fix message ID propagation in `useChat.ts`                                       | 0.5 d         |
| Backend schemas + endpoint extensions                                            | 1 d           |
| Frontend: refactor FeedbackModal                                                 | 0.75 d        |
| Frontend: add message rating UI to AssistantBubble + MessageList + ChatInterface | 1 d           |
| Frontend: admin dashboard updates                                                | 0.75 d        |
| Firestore rules + indexes + manual testing                                       | 0.5 d         |
| **Total**                                                                        | **~4.5 days** |
