"use client";

import { useRef, useState } from "react";
import { generateConversationTitle, queryRagStream } from "@/lib/api";
import { getToken } from "@/lib/auth";
import type { AgentStage, Message, SourceGroup } from "@/lib/types";
import { normalizeSources } from "@/lib/types";
import { useAuth } from "@/components/providers/AuthProvider";
import type { Conversation } from "@/hooks/useConversations";
'Modificacion para tomar string vacio como falsy y evitar el error 404 en burbuja'
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8080";
function generateId(): string {
	if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
		return crypto.randomUUID();
	}
	return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
		const r = (Math.random() * 16) | 0;
		return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
	});
}

export interface UseChatReturn {
	messages: Message[];
	input: string;
	loading: boolean;
	isStreaming: boolean;
	stage: AgentStage | null;
	stageMessage: string | null;
	error: string | null;
	contextPercent: number;
	/** ID de la conversación activa en la base de datos (null si no hay sesión o aún no se creó). */
	conversationId: string | null;
	ratedMessageIds: Set<string>;
	setInput: (value: string) => void;
	submit: (question: string) => Promise<void>;
	resetChat: () => void;
	loadConversation: (conv: Conversation) => Promise<void>;
	rateMessage: (
		messageId: string,
		ratings: { pertinence: number; accuracy: number },
		expectedAnswer?: string,
	) => Promise<void>;
}

const DEFAULT_STAGE_MESSAGES: Record<AgentStage, string> = {
	enriching: "Entendiendo tu pregunta con más precisión…",
	retrieving: "Navegando miles de páginas de sentencias…",
	generating: "Construyendo una respuesta clara para ti…",
};

export function useChat(): UseChatReturn {
	const { user } = useAuth();

	const [messages, setMessages] = useState<Message[]>([]);
	const [input, setInput] = useState("");
	const [loading, setLoading] = useState(false);
	const [isStreaming, setIsStreaming] = useState(false);
	const [stage, setStage] = useState<AgentStage | null>(null);
	const [stageMessage, setStageMessage] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [contextPercent, setContextPercent] = useState(0);
	const [conversationId, setConversationId] = useState<string | null>(null);
	const [ratedMessageIds, setRatedMessageIds] = useState<Set<string>>(new Set());

	const threadIdRef = useRef<string>(generateId());
	const conversationIdRef = useRef<string | null>(null);
	const streamingStartedRef = useRef(false);

	function _setConversationId(id: string | null) {
		conversationIdRef.current = id;
		setConversationId(id);
	}

	/** Crea la conversación en la base de datos vía API al enviar el primer mensaje. */
	async function _createConversation(firstQuestion: string): Promise<string> {
		const token = getToken();
		if (!user || !token) return "";

		const now = new Date();
		const dateStr = now.toLocaleDateString("es-CO", {
			day: "2-digit",
			month: "2-digit",
			year: "numeric",
		});
		const timeStr = now.toLocaleTimeString("es-CO", {
			hour: "2-digit",
			minute: "2-digit",
		});

		try {
			const res = await fetch(`${API_URL}/api/conversations`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Authorization: `Bearer ${token}`,
				},
				body: JSON.stringify({
					thread_id: threadIdRef.current,
					title: `Chat ${dateStr} ${timeStr}`,
				}),
			});
			if (!res.ok) return "";
			const data = (await res.json()) as { id: string };

			// Generar título con IA en background
			generateConversationTitle(firstQuestion, data.id).catch(() => {});

			return data.id;
		} catch {
			return "";
		}
	}

	async function submit(question: string): Promise<void> {
		const q = question.trim();
		if (!q || loading) return;

		const isFirstMessage = messages.length === 0 && !conversationIdRef.current;

		setLoading(true);
		setIsStreaming(false);
		setStage(null);
		setStageMessage(null);
		setError(null);
		streamingStartedRef.current = false;

		setMessages((prev) => [
			...prev,
			{ id: generateId(), role: "user", text: q },
		]);
		setInput("");

		if (user && isFirstMessage) {
			const newConvId = await _createConversation(q);
			_setConversationId(newConvId);
		}

		const activeConvId = conversationIdRef.current;
		const token = getToken();

		// Persistir mensaje del usuario
		let userMsgId: string | null = null;
		if (user && activeConvId && token) {
			fetch(`${API_URL}/api/conversations/${activeConvId}/messages`, {
				method: "POST",
				headers: {
					"Content-Type": "application/json",
					Authorization: `Bearer ${token}`,
				},
				body: JSON.stringify({ role: "user", text: q }),
			})
				.then(async (res) => {
					if (res.ok) {
						const data = (await res.json()) as { id: string };
						userMsgId = data.id;
					}
				})
				.catch(() => {});
		}

		const assistantId = generateId();
		setMessages((prev) => [
			...prev,
			{ id: assistantId, role: "assistant", text: "", sources: [] },
		]);

		let finalAssistantText = "";
		let finalAssistantSources: SourceGroup[] = [];

		try {
			for await (const event of queryRagStream({
				question: q,
				thread_id: threadIdRef.current,
				conversation_id: activeConvId ?? undefined,
			})) {
				if (event.type === "token") {
					if (!streamingStartedRef.current) {
						streamingStartedRef.current = true;
						setIsStreaming(true);
						setStage(null);
						setStageMessage(null);
					}
					finalAssistantText += event.content;
					setMessages((prev) =>
						prev.map((m) =>
							m.id === assistantId
								? { ...m, text: m.text + event.content }
								: m,
						),
					);
				} else if (event.type === "status") {
					setStage(event.stage);
					setStageMessage(
						event.message ?? DEFAULT_STAGE_MESSAGES[event.stage],
					);
				} else if (event.type === "sources") {
					const groups = normalizeSources(event.sources);
					finalAssistantSources = groups;
					setMessages((prev) =>
						prev.map((m) =>
							m.id === assistantId ? { ...m, sources: groups } : m,
						),
					);
					if (event.context_tokens != null && event.context_limit) {
						setContextPercent(
							Math.round(
								(event.context_tokens / event.context_limit) * 100,
							),
						);
					}
				} else if (event.type === "error") {
					throw new Error(event.detail);
				}
			}

			// Persistir respuesta del asistente
			if (user && activeConvId && token && finalAssistantText) {
				fetch(`${API_URL}/api/conversations/${activeConvId}/messages`, {
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${token}`,
					},
					body: JSON.stringify({
						role: "assistant",
						text: finalAssistantText,
						sources:
							finalAssistantSources.length > 0
								? finalAssistantSources
								: null,
					}),
				})
					.then(async (res) => {
						if (res.ok) {
							const data = (await res.json()) as { id: string };
							setMessages((prev) =>
								prev.map((m) =>
									m.id === assistantId ? { ...m, id: data.id } : m,
								),
							);
						}
					})
					.catch(() => {});
			}
		} catch (err) {
			setMessages((prev) => prev.filter((m) => m.id !== assistantId));
			setError(
				err instanceof Error
					? err.message
					: "Error de conexión. Compruebe que el servidor está activo.",
			);
		} finally {
			setLoading(false);
			setIsStreaming(false);
			setStage(null);
			setStageMessage(null);
		}

		void userMsgId; // evitar warning de variable no usada
	}

	/** Carga una conversación existente desde la API y la restaura en la UI. */
	async function loadConversation(conv: Conversation): Promise<void> {
		const token = getToken();
		if (!token) return;

		try {
			const res = await fetch(
				`${API_URL}/api/conversations/${conv.id}/messages`,
				{ headers: { Authorization: `Bearer ${token}` } },
			);
			if (!res.ok) return;

			const data = (await res.json()) as Array<{
				id: string;
				role: string;
				text: string;
				sources: unknown[] | null;
			}>;

			const loaded: Message[] = data.map((m) => ({
				id: m.id,
				role: m.role as "user" | "assistant",
				text: m.text,
				sources: m.sources ? normalizeSources(m.sources as Parameters<typeof normalizeSources>[0]) : undefined,
			}));

			setMessages(loaded);
			threadIdRef.current = conv.threadId;
			_setConversationId(conv.id);
			setInput("");
			setLoading(false);
			setIsStreaming(false);
			setStage(null);
			setStageMessage(null);
			setError(null);
			setContextPercent(0);
			streamingStartedRef.current = false;
		} catch {
			// Si falla la carga, no hace nada
		}
	}

	async function rateMessage(
		messageId: string,
		ratings: { pertinence: number; accuracy: number },
		expectedAnswer?: string,
	): Promise<void> {
		if (!user || !conversationIdRef.current) return;

		const { submitMessageFeedback } = await import("@/lib/api");
		await submitMessageFeedback({
			conversation_id: conversationIdRef.current,
			message_id: messageId,
			ratings: { pertinence: ratings.pertinence, accuracy: ratings.accuracy },
			expected_answer: expectedAnswer,
		});

		setRatedMessageIds((prev) => new Set(prev).add(messageId));
	}

	function resetChat(): void {
		setMessages([]);
		setInput("");
		setLoading(false);
		setIsStreaming(false);
		setStage(null);
		setStageMessage(null);
		setError(null);
		setContextPercent(0);
		_setConversationId(null);
		streamingStartedRef.current = false;
		setRatedMessageIds(new Set());
		threadIdRef.current = generateId();
	}

	return {
		messages,
		input,
		loading,
		isStreaming,
		stage,
		stageMessage,
		error,
		contextPercent,
		conversationId,
		ratedMessageIds,
		setInput,
		submit,
		resetChat,
		loadConversation,
		rateMessage,
	};
}
