# SDD Delta Spec: Dual Rating System

**change_id:** dual-rating-system
**spec_type:** delta
**base_commit:** TBD (current HEAD)

---

## RS-01: Enhanced Conversation-Level Rating

**Description:** Replace the current 1-5 star + comment feedback form with a multi-dimensional usability form. The form must allow users to rate three specific dimensions (tone, length, usability) plus an overall rating and an optional free-text comment. The form is accessed via the existing floating FeedbackButton.

### Requirements

#### REQ-01.1: Rating dimensions

The conversation feedback form MUST include the following rating fields, each with a 1-5 star selector:

1. **"Tono de las respuestas"** (Tone of responses) — how appropriate the tone was
2. **"Longitud de las respuestas"** (Length of responses) — how appropriate the length was
3. **"Usabilidad del sistema"** (System usability) — how easy the system was to use
4. **"Calificación general"** (Overall rating) — overall satisfaction

All four ratings are REQUIRED. The form MUST NOT submit unless all four are selected.

#### REQ-01.2: Comment field

The form MUST include an optional free-text comment field (max 500 characters) with label "Comentario" and placeholder "¿Qué podría mejorar el sistema?".

#### REQ-01.3: Form UX

- The form MUST open as a modal dialog (existing FeedbackModal component refactored).
- Each rating dimension MUST show a label above its star row.
- Each dimension MUST show a dynamic label (Muy malo → Excelente) below the selected star value.
- The form MUST show a success state after submission with message "¡Gracias por tu calificación!".
- The form MUST show an error state if submission fails.
- After successful submission, the form MUST disable further submissions for the same conversation.

#### REQ-01.4: API contract

`POST /api/feedback` request body changes from:

```json
{ "rating": 3, "comment": "text", "conversation_id": "abc" }
```

to:

```json
{
  "ratings": {
    "tone": 4,
    "length": 3,
    "usability": 5,
    "overall": 4
  },
  "comment": "text",
  "conversation_id": "abc"
}
```

The `ratings` object is REQUIRED with all four keys. Values MUST be 1-5 integers.
The old `rating` field is REMOVED from the API (no backward compatibility per DD-2).

#### REQ-01.5: Firestore document shape

The `feedback` collection document shape changes to:

```
{
  userId: string,
  userEmail: string,
  ratings: { tone: number, length: number, usability: number, overall: number },
  comment: string | null,
  conversationId: string | null,
  conversationTitle: string | null,
  createdAt: Timestamp
}
```

#### REQ-01.6: Data migration

A one-time migration script MUST convert existing `feedback` documents from `{ rating: N, comment: "..." }` to `{ ratings: { tone: N, length: N, usability: N, overall: N }, comment: "..." }`. For legacy docs, the original `rating` value is used as all four dimension values (best-effort migration).

#### REQ-01.7: Admin endpoint adaptation

`GET /api/admin/feedback` MUST return the new shape:

- `ratings` object instead of `rating` integer
- `avg_rating` becomes `avg_ratings: { tone, length, usability, overall }`
- `distribution` becomes `distributions: { tone: {1:N,...}, length: {...}, usability: {...}, overall: {...} }`

### Scenarios

**SC-01.1: User submits conversation feedback**

> GIVEN a logged-in user with an active conversation
> WHEN they click the FeedbackButton and fill all four star ratings
> AND optionally write a comment
> AND click "Enviar calificación"
> THEN the system posts to POST /api/feedback with { ratings: {tone, length, usability, overall}, comment, conversation_id }
> AND shows a success confirmation
> AND the FeedbackButton becomes disabled for that conversation

**SC-01.2: User tries to submit without completing all ratings**

> GIVEN a user opens the feedback form
> WHEN they have not selected all four star ratings
> THEN the submit button is disabled
> AND the form does not submit

**SC-01.3: Admin views conversation feedback**

> GIVEN an admin visits /admin/feedback
> WHEN the page loads
> THEN the table shows columns for each rating dimension (tone, length, usability, overall)
> AND average statistics are computed per dimension
> AND the distribution charts show per-dimension breakdowns

---

## RS-02: Message-Level Rating

**Description:** Add a per-message rating form accessible via an action button on each assistant message. The form contains three fields: pertinence rating, accuracy rating, and an expected-answer free-text field.

### Requirements

#### REQ-02.1: Action button on AssistantBubble

Each `AssistantBubble` component MUST render a small action button (icon) at the bottom-right of the message bubble. The icon SHOULD be visible on hover/focus (desktop) or always visible (mobile). The icon SHOULD use a "message-square" or "flag" icon to indicate "rate this response".

#### REQ-02.2: Rating form (popover)

Clicking the action button MUST open an inline popover below the button containing:

- **"Pertinencia de la respuesta"** — 1-5 star rating with tooltip explaining: "¿Qué tan relevante fue la respuesta para la pregunta que hiciste? Un 1 indica que no tuvo nada que ver; un 5 indica que fue directamente relevante."
- **"Precisión de la respuesta"** — 1-5 star rating with tooltip explaining: "¿Qué tan correcta y exacta fue la respuesta? Un 1 indica que fue incorrecta; un 5 indica que fue plenamente correcta."
- **"Respuesta adecuada"** — Optional free-text field (max 1000 characters) with placeholder: "Escribe la respuesta correcta que esperabas del sistema."

#### REQ-02.3: Submit behavior

- Both star ratings (pertinence and accuracy) are REQUIRED. The "Respuesta adecuada" text field is OPTIONAL.
- On successful submission, the popover shows a brief success message and then closes.
- The action button changes to a filled/colored state to indicate the message has been rated.
- Once rated, the button shows a disabled/completed state. The user CANNOT re-rate or edit the rating.

#### REQ-02.4: API contract

New endpoint: `POST /api/feedback/message`

Request body:

```json
{
  "conversation_id": "abc123",
  "message_id": "msg456",
  "ratings": {
    "pertinence": 4,
    "accuracy": 3
  },
  "expected_answer": "La respuesta debería haber mencionado la sentencia C-123..."
}
```

- `conversation_id` is REQUIRED (string)
- `message_id` is REQUIRED (string) — the Firestore document ID of the assistant message
- `ratings` is REQUIRED with `pertinence` (1-5) and `accuracy` (1-5)
- `expected_answer` is OPTIONAL (string, max 1000 chars)

Response body:

```json
{
  "id": "feedback_doc_id"
}
```

#### REQ-02.5: Firestore document shape

New collection `message_feedback`:

```
{
  userId: string,
  userEmail: string,
  conversationId: string,
  messageId: string,
  ratings: { pertinence: number, accuracy: number },
  expectedAnswer: string | null,
  createdAt: Timestamp
}
```

#### REQ-02.6: Message ID fix

The `useChat.ts` hook MUST be refactored so that after `addDoc()` creates an assistant message in Firestore, the frontend React state is updated with the real Firestore document ID (replacing the initial `crypto.randomUUID()` temporary ID). This is REQUIRED for `message_id` in the API to reference a real Firestore document.

Specifically:

- After `addDoc()` for assistant messages, update the corresponding message in React state with `docRef.id`.
- This applies to both the streaming assistant message and messages loaded via `loadConversation`.

#### REQ-02.7: Duplicate prevention

The backend MUST check for existing feedback from the same user for the same message before creating a new document. If a duplicate is detected, return `409 Conflict` with a clear error message. The frontend SHOULD also check local state to avoid showing the rating button for already-rated messages.

#### REQ-02.8: Access control

- Any authenticated user can create message feedback (same as existing conversation feedback).
- Only admin users can list/read message feedback documents.
- The `message_feedback` collection Firestore rules MUST enforce these permissions.

### Scenarios

**SC-02.1: User rates an assistant message**

> GIVEN a logged-in user viewing an assistant message
> WHEN they click the rating action button on the message
> THEN a popover opens below the button with three fields
> AND they select pertinence=4, accuracy=2, and type "Debió citar la sentencia C-045"
> AND click "Enviar"
> THEN POST /api/feedback/message is called
> AND the popover shows a success message
> AND the action button changes to a completed state

**SC-02.2: User tries to rate without completing required fields**

> GIVEN a user opens the message rating popover
> WHEN they have not selected both star ratings
> THEN the submit button is disabled

**SC-02.3: User tries to rate the same message twice**

> GIVEN a user already submitted feedback for a message
> WHEN they view the message again
> THEN the action button shows a completed/disabled state
> AND clicking it does NOT open the rating form

**SC-02.4: Admin views message feedback**

> GIVEN an admin visits /admin/message-feedback
> WHEN the page loads
> THEN the table shows columns: Fecha, Usuario, Conversación, Pertinencia, Precisión, Respuesta esperada (truncated)
> AND pagination and date filter controls are available

---

## RS-03: Admin Dashboard Updates

**Description:** Update the admin dashboard to display both conversation-level and message-level feedback with separate pages and updated overview statistics.

### Requirements

#### REQ-03.1: Overview page statistics

The existing `/admin` overview page MUST display:

- Current stats: total conversation feedback count, overall average
- NEW: total message feedback count, average pertinence, average accuracy
- NEW: distribution charts for pertinence and accuracy

#### REQ-03.2: Message feedback page

A NEW page at `/admin/message-feedback` MUST display:

- A table of all message feedback entries with columns: Fecha, Usuario, Conversación, Pertinencia (stars), Precisión (stars), Respuesta esperada (truncated text, expandable)
- Pagination controls
- Date range filter
- Link to the conversation where the rated message belongs (if available)

#### REQ-03.3: Conversation feedback page updates

The existing `/admin/feedback` page MUST be updated:

- Table columns change from single "Rating" to four columns: Tono, Longitud, Usabilidad, General
- Summary statistics show per-dimension averages
- Distribution charts show per-dimension breakdowns

#### REQ-03.4: Admin sidebar navigation

The admin sidebar MUST include a new "Calificaciones por mensaje" link pointing to `/admin/message-feedback`.

#### REQ-03.5: Backend endpoint for message feedback admin

New endpoint: `GET /api/admin/message-feedback`

Query parameters:

- `page` (int, default 1)
- `page_size` (int, default 20, max 100)
- `min_pertinence` (int, 1-5, optional)
- `max_pertinence` (int, 1-5, optional)
- `min_accuracy` (int, 1-5, optional)
- `max_accuracy` (int, 1-5, optional)
- `start_date` (ISO date string, optional)
- `end_date` (ISO date string, optional)

Response:

```json
{
  "items": [
    {
      "id": "doc_id",
      "userId": "...",
      "userEmail": "...",
      "conversationId": "...",
      "messageId": "...",
      "ratings": { "pertinence": 4, "accuracy": 3 },
      "expectedAnswer": "...",
      "createdAt": "ISO 8601"
    }
  ],
  "total": 42,
  "avg_ratings": { "pertinence": 3.8, "accuracy": 4.1 },
  "distributions": {
    "pertinence": { "1": 2, "2": 5, "3": 10, "4": 15, "5": 10 },
    "accuracy": { "1": 1, "2": 3, "3": 8, "4": 18, "5": 12 }
  }
}
```

### Scenarios

**SC-03.1: Admin views overview with both rating types**

> GIVEN an admin visits /admin
> WHEN the page loads
> THEN they see conversation feedback stats AND message feedback stats
> AND each section shows dimension-level averages and distributions

**SC-03.2: Admin navigates between feedback pages**

> GIVEN an admin on /admin
> WHEN they click "Calificaciones por conversación" in the sidebar
> THEN they navigate to /admin/feedback
> WHEN they click "Calificaciones por mensaje" in the sidebar
> THEN they navigate to /admin/message-feedback

---

## RS-04: Firestore and Infrastructure

**Description:** Update Firestore rules, indexes, and documentation to support the new collections and data shapes.

### Requirements

#### REQ-04.1: Firestore rules for `message_feedback`

Add to `firestore.rules`:

```
match /message_feedback/{feedbackId} {
  allow create: if request.auth != null;
  allow read, list: if isAdmin();
}
```

#### REQ-04.2: Update Firestore rules for `feedback`

The existing `feedback` rules remain the same (auth create, admin read). No changes needed beyond the new collection rule.

#### REQ-04.3: Firestore indexes for `message_feedback`

Add to `firestore.indexes.json`:

- `message_feedback`: `createdAt DESCENDING` (for admin listing)
- `message_feedback`: `userId ASC` + `createdAt DESC` (for per-user queries)

#### REQ-04.4: Manual Firebase steps

The following MANUAL steps are required and MUST be documented in `docs/firebase-config-manual.md`:

1. Deploy updated `firestore.rules`
2. Create the new composite indexes for `message_feedback`
3. Run the data migration script for existing `feedback` documents
4. Verify the `message_feedback` collection appears in Firestore Console after first submission

### Scenarios

**SC-04.1: Unauthenticated user tries to submit message feedback**

> GIVEN an unauthenticated user
> WHEN they attempt POST /api/feedback/message
> THEN the request is rejected with 401 Unauthorized

**SC-04.2: Non-admin tries to list message feedback**

> GIVEN a regular authenticated user
> WHEN they attempt GET /api/admin/message-feedback
> THEN the request is rejected with 403 Forbidden

---

## RS-05: Tooltip Accessibility

**Description:** Tooltips for "Pertinencia" and "Precisión" labels must be accessible and clear.

### Requirements

#### REQ-05.1: Tooltip content

- **"Pertinencia"** tooltip: "¿Qué tan relevante fue la respuesta para la pregunta que hiciste? Un 1 indica que no tuvo nada que ver; un 5 indica que fue directamente relevante."
- **"Precisión"** tooltip: "¿Qué tan correcta y exacta fue la respuesta? Un 1 indica que fue incorrecta; un 5 indica que fue plenamente correcta."

#### REQ-05.2: Tooltip accessibility

Each tooltip MUST:

- Activate on hover (desktop) and tap (mobile)
- Be reachable via keyboard (focus on the info icon)
- Use `aria-describedby` to associate the tooltip text with the trigger
- Dismiss on Escape key

### Scenarios

**SC-05.1: User sees pertinence tooltip**

> GIVEN a user viewing the message rating popover
> WHEN they hover over or focus the info icon next to "Pertinencia"
> THEN a tooltip appears with the full explanation
> AND the tooltip is announced by screen readers
