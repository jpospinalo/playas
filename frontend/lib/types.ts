export interface SourceFragment {
  /** Posición global 1-based; coincide con el `[docN]` que cita el LLM. */
  index: number;
  content: string;
  metadata: Record<string, unknown>;
}

export interface SourceGroup {
  /** Nombre del archivo fuente (clave de agrupación). */
  source: string;
  title: string;
  /** Metadatos a nivel documento (Corporación, Radicado, Magistrado, Tema, ...). */
  metadata: Record<string, unknown>;
  fragments: SourceFragment[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: SourceGroup[];
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
  sources: SourceGroup[];
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
  | { type: "sources"; sources: SourceGroup[]; enriched_query?: string | null; context_tokens?: number; context_limit?: number }
  | { type: "status"; stage: AgentStage; message?: string }
  | { type: "error"; detail: string };

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Acepta sources tanto en el shape nuevo (SourceGroup[]) como en el shape
 * plano legado (objetos con `content`/`source`/`title`) que persistieron en
 * Firestore antes de la migración. Convierte el shape viejo en grupos de un
 * solo fragmento para que el resto de la UI sea agnóstica.
 */
export function normalizeSources(raw: unknown): SourceGroup[] {
  if (!Array.isArray(raw)) return [];

  // Heurística: si el primer elemento tiene `fragments`, es el shape nuevo.
  const first = raw[0] as Record<string, unknown> | undefined;
  if (first && Array.isArray((first as { fragments?: unknown }).fragments)) {
    return raw as SourceGroup[];
  }

  return raw.map((item, i): SourceGroup => {
    const it = (item ?? {}) as Record<string, unknown>;
    const meta = (it.metadata as Record<string, unknown> | undefined) ?? {};
    return {
      source: (it.source as string) ?? "",
      title: (it.title as string) ?? "",
      metadata: meta,
      fragments: [
        {
          index: i + 1,
          content: (it.content as string) ?? "",
          metadata: meta,
        },
      ],
    };
  });
}
