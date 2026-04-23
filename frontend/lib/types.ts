export interface SourceDocument {
  content: string;
  source: string;
  title: string;
  metadata: Record<string, unknown>;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: SourceDocument[];
}

export interface QueryRequest {
  question: string;
  /** Number of context fragments (1–8, default 4) */
  k?: number;
  /** Initial retriever candidates (4–20, default 8) */
  k_candidates?: number;
  /** Conversation thread identifier. Reuse across requests to maintain multi-turn context. */
  thread_id?: string;
  /** Firestore conversation document ID. Used by the backend to hydrate LangGraph state on server restart. */
  conversation_id?: string;
}

export interface QueryResponse {
  answer: string;
  sources: SourceDocument[];
  context_tokens: number;
  context_limit: number;
}

export interface FeedbackRequest {
  rating: number;
  comment?: string;
  conversation_id?: string;
}

// ── SSE stream event types ─────────────────────────────────────────────────

export type AgentStage = "enriching" | "retrieving" | "generating";

export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "sources"; sources: SourceDocument[]; enriched_query?: string | null; context_tokens?: number; context_limit?: number }
  | { type: "status"; stage: AgentStage; message?: string }
  | { type: "error"; detail: string };
