"use client";

import { useEffect, useRef, useState } from "react";
import { queryRagStream, throwIfSessionExpired } from "@/lib/api";
import { getToken } from "@/lib/auth";
import { API_URL } from "@/lib/config";
import type { AgentStage, Message, SourceGroup } from "@/lib/types";
import { normalizeSources } from "@/lib/types";
import { useAuth } from "@/components/providers/AuthProvider";
import type { Conversation } from "@/hooks/useConversations";

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
	retrieving: "Buscando evidencia en normas y jurisprudencia…",
	generating: "Construyendo una respuesta clara para ti…",
};

interface UseChatOptions {
	onConversationChanged?: () => void | Promise<void>;
}

interface PersistMessageInput {
	token: string;
	conversationId: string;
	messageId: string;
	role: "user" | "assistant";
	text: string;
	sources?: SourceGroup[] | null;
	errorMessage: string;
}

async function persistMessage(input: PersistMessageInput): Promise<{ id: string }> {
	let lastError = new Error(input.errorMessage);
	for (let attempt = 0; attempt < 2; attempt += 1) {
		let response: Response;
		try {
			response = await fetch(
				`${API_URL}/api/conversations/${input.conversationId}/messages`,
				{
					method: "POST",
					headers: {
						"Content-Type": "application/json",
						Authorization: `Bearer ${input.token}`,
					},
					body: JSON.stringify({
						message_id: input.messageId,
						role: input.role,
						text: input.text,
						sources: input.sources ?? null,
					}),
				},
			);
		} catch (error) {
			// Error de red/transitorio: sigue siendo elegible para reintento.
			lastError = error instanceof Error ? error : new Error(input.errorMessage);
			continue;
		}
		if (response.ok) return (await response.json()) as { id: string };
		// Un 401 nunca se reintenta: expira la sesión (si el token sigue siendo
		// el activo) y propaga de inmediato, sin consumir el segundo intento.
		await throwIfSessionExpired(response, input.token);
		lastError = new Error(input.errorMessage);
		if (response.status < 500) break;
	}
	throw lastError;
}

export function useChat({ onConversationChanged }: UseChatOptions = {}): UseChatReturn {
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
	const abortControllerRef = useRef<AbortController | null>(null);

	useEffect(() => {
		return () => abortControllerRef.current?.abort();
	}, []);

	function _setConversationId(id: string | null) {
		conversationIdRef.current = id;
		setConversationId(id);
	}

	/** Crea la conversación en la base de datos vía API al enviar el primer mensaje. */
	async function _createConversation(firstQuestion: string): Promise<string> {
		const token = getToken();
		if (!user || !token) {
			throw new Error("La sesión no es válida. Inicia sesión nuevamente.");
		}

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
					title: firstQuestion.slice(0, 120) || `Chat ${dateStr} ${timeStr}`,
				}),
			});
			await throwIfSessionExpired(res, token);
			if (!res.ok) throw new Error("No fue posible crear la conversación.");
			const data = (await res.json()) as { id: string };
			await onConversationChanged?.();
			return data.id;
		} catch (err) {
			throw err instanceof Error
				? err
				: new Error("No fue posible crear la conversación.");
		}
	}

	async function submit(question: string): Promise<void> {
		const q = question.trim();
		if (!q || loading) return;
		const token = getToken();
		if (!user || !token) {
			setError("La sesión no es válida. Inicia sesión nuevamente.");
			return;
		}

		const isFirstMessage = messages.length === 0 && !conversationIdRef.current;

		setLoading(true);
		setIsStreaming(false);
		setStage(null);
		setStageMessage(null);
		setError(null);
		streamingStartedRef.current = false;

		const localUserId = generateId();
		setMessages((prev) => [
			...prev,
			{ id: localUserId, role: "user", text: q },
		]);
		setInput("");

		if (isFirstMessage) {
			try {
				const newConvId = await _createConversation(q);
				_setConversationId(newConvId);
			} catch (err) {
				setMessages((prev) => prev.filter((message) => message.id !== localUserId));
				setInput(q);
				setLoading(false);
				setError(
					err instanceof Error ? err.message : "No fue posible crear la conversación.",
				);
				return;
			}
		}

		const activeConvId = conversationIdRef.current;
		if (!activeConvId) {
			setMessages((prev) => prev.filter((message) => message.id !== localUserId));
			setInput(q);
			setLoading(false);
			setError("No fue posible establecer la conversación.");
			return;
		}

		// Persistir mensaje del usuario
		let userMsgId = localUserId;
		try {
			const savedUserMessage = await persistMessage({
				token,
				conversationId: activeConvId,
				messageId: localUserId,
				role: "user",
				text: q,
				errorMessage: "No fue posible guardar la pregunta.",
			});
			userMsgId = savedUserMessage.id;
			setMessages((prev) =>
				prev.map((message) =>
					message.id === localUserId ? { ...message, id: userMsgId } : message,
				),
			);
		} catch (err) {
			setMessages((prev) => prev.filter((message) => message.id !== localUserId));
			setInput(q);
			setLoading(false);
			setError(err instanceof Error ? err.message : "No fue posible guardar la pregunta.");
			return;
		}

		const assistantId = generateId();
		setMessages((prev) => [
			...prev,
			{ id: assistantId, role: "assistant", text: "", sources: [] },
		]);

		let finalAssistantText = "";
		let finalAssistantSources: SourceGroup[] = [];
		const controller = new AbortController();
		abortControllerRef.current = controller;

		try {
			const stream = queryRagStream(
				{
					question: q,
					thread_id: threadIdRef.current,
					conversation_id: activeConvId,
					current_message_id: userMsgId,
				},
				controller.signal,
			);
			for await (const event of stream) {
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

			if (!finalAssistantText) {
				throw new Error("El servidor no devolvió una respuesta completa.");
			}

			// Persistir respuesta del asistente
			const savedAssistant = await persistMessage({
				token,
				conversationId: activeConvId,
				messageId: assistantId,
				role: "assistant",
				text: finalAssistantText,
				sources:
					finalAssistantSources.length > 0 ? finalAssistantSources : null,
				errorMessage: "La respuesta se obtuvo, pero no pudo guardarse.",
			});
			setMessages((prev) =>
				prev.map((m) =>
					m.id === assistantId ? { ...m, id: savedAssistant.id } : m,
				),
			);
			await onConversationChanged?.();
		} catch (err) {
			setMessages((prev) => prev.filter((m) => m.id !== assistantId));
			if (!(err instanceof DOMException && err.name === "AbortError")) {
				setError(
					err instanceof Error
						? err.message
						: "Error de conexión. Compruebe que el servidor está activo.",
				);
			}
		} finally {
			if (abortControllerRef.current === controller) {
				abortControllerRef.current = null;
			}
			setLoading(false);
			setIsStreaming(false);
			setStage(null);
			setStageMessage(null);
		}
	}

	/** Carga una conversación existente desde la API y la restaura en la UI. */
	async function loadConversation(conv: Conversation): Promise<void> {
		abortControllerRef.current?.abort();
		const token = getToken();
		if (!token) return;

		try {
			const res = await fetch(
				`${API_URL}/api/conversations/${conv.id}/messages`,
				{ headers: { Authorization: `Bearer ${token}` } },
			);
			await throwIfSessionExpired(res, token);
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
		abortControllerRef.current?.abort();
		abortControllerRef.current = null;
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
