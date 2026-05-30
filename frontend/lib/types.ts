/** Tipo de fuente documental que respalda la respuesta. */
export type DocType = "jurisprudencia" | "normativa";

/**
 * Metadatos a nivel documento. Es un saco abierto (`Record`) porque el backend
 * adjunta claves heterogéneas según el tipo de fuente. Estos campos opcionales
 * documentan los que la UI consume explícitamente:
 *  - jurisprudencia: Corporación, Radicado, Magistrado ponente, Tema principal.
 *  - normativa: norma/title, titulo (Título), capitulo (Capítulo), articulo (Artículo).
 */
export interface SourceMetadata extends Record<string, unknown> {
	/** Discrimina la atribución a mostrar. Si falta, se trata como jurisprudencia. */
	doc_type?: DocType;
	// ── Campos de normativa ──
	norma?: string;
	titulo?: string;
	capitulo?: string;
	articulo?: string;
}

export interface SourceFragment {
	/** Posición global 1-based; coincide con el `[docN]` que cita el LLM. */
	index: number;
	content: string;
	metadata: SourceMetadata;
}

export interface SourceGroup {
	/** Nombre del archivo fuente (clave de agrupación). */
	source: string;
	title: string;
	/** Metadatos a nivel documento (doc_type + atribución según tipo). */
	metadata: SourceMetadata;
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
	ratings: ConversationRatings;
	comment?: string;
	conversation_id?: string;
}

// ── Conversation-level rating dimensions ──

export interface ConversationRatings {
	tone: number;
	length: number;
	usability: number;
	overall: number;
}

// ── Message-level rating dimensions ──

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

// ── Admin response types ──

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

export interface AdminMessageFeedbackResponse {
	items: AdminMessageFeedbackItem[];
	total: number;
	avg_ratings: { pertinence: number; accuracy: number };
	distributions: {
		pertinence: Record<string, number>;
		accuracy: Record<string, number>;
	};
}

// ── SSE stream event types ─────────────────────────────────────────────────

export type AgentStage = "enriching" | "retrieving" | "generating";

export type StreamEvent =
	| { type: "token"; content: string }
	| {
			type: "sources";
			sources: SourceGroup[];
			enriched_query?: string | null;
			context_tokens?: number;
			context_limit?: number;
	  }
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
