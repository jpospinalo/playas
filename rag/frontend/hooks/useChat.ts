"use client";

import { useEffect, useRef, useState } from "react";
import { queryRagStream, throwIfSessionExpired } from "@/lib/api";
import { expireAuthSession, getToken } from "@/lib/auth";
import { API_URL } from "@/lib/config";
import { MAX_QUESTION_CHARS } from "@/lib/contracts";
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
	/** A5 — IDs de mensajes de asistente cuyo reintento de guardado está en curso. */
	persistingMessageIds: Set<string>;
	/**
	 * A6 — true únicamente mientras la generación en streaming de la
	 * respuesta está activa (distinto de `loading`, que también cubre crear
	 * la conversación y persistir la pregunta/respuesta — fases que
	 * "Detener" no debe interrumpir).
	 */
	canCancel: boolean;
	/**
	 * A6 — true justo después de que el usuario detuvo una generación en
	 * curso con `cancel()`. Habilita un aviso breve y no persistente
	 * ("Generación detenida"); se limpia automáticamente al iniciar un nuevo
	 * envío, cambiar de conversación o reiniciar el chat.
	 */
	generationStopped: boolean;
	/**
	 * True justo después de que la generación en streaming de la respuesta
	 * terminó con éxito para la operación vigente (independiente de si el
	 * guardado posterior de la respuesta tuvo éxito o falló). Se limpia
	 * igual que `generationStopped`: al iniciar un nuevo envío, cambiar de
	 * conversación o reiniciar el chat. Nunca se pone en true tras un error
	 * o una cancelación, ni desde una operación que ya dejó de ser la
	 * vigente (`isCurrentRun()` deja de cumplirse antes).
	 */
	generationFinished: boolean;
	setInput: (value: string) => void;
	submit: (question: string) => Promise<void>;
	resetChat: () => void;
	loadConversation: (conv: Conversation) => Promise<void>;
	/** A5 — reintenta guardar una respuesta con `persistenceStatus: "failed"`. */
	retryPersistMessage: (messageId: string) => Promise<void>;
	/** A6 — cancela únicamente la consulta en streaming actualmente activa. */
	cancel: () => void;
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
	// A5 — mensajes de asistente cuyo reintento manual de guardado está en
	// curso ahora mismo (deshabilita el botón de reintento mientras dura).
	const [persistingMessageIds, setPersistingMessageIds] = useState<Set<string>>(
		new Set(),
	);
	// A6 — ver los comentarios de `canCancel`/`generationStopped` en
	// `UseChatReturn`.
	const [canCancel, setCanCancel] = useState(false);
	const [generationStopped, setGenerationStopped] = useState(false);
	// Ver el comentario de `generationFinished` en `UseChatReturn`.
	const [generationFinished, setGenerationFinished] = useState(false);
	// Sincrónica: distingue un AbortError disparado por `cancel()` (debe
	// mostrar "Generación detenida") de uno disparado por otra causa —
	// desmontaje del componente, o `resetChat()`/cambio de conversación
	// abortando la generación en curso (donde el chat ya se vació o cambió,
	// así que el aviso no tendría sentido).
	const cancelRequestedRef = useRef(false);
	// G2.1 — identificador monotónico de la operación de chat "dueña" del
	// estado compartido (messages/loading/isStreaming/stage/stageMessage/
	// error/contextPercent). `submit()`, `loadConversation()` y
	// `resetChat()` lo incrementan al reclamar esa propiedad; cualquier
	// continuación asíncrona de una operación anterior (un `then`/`catch`
	// que se resuelve tarde) comprueba este valor antes de tocar ese
	// estado y se vuelve no-op en cuanto deja de coincidir. Es una guarda
	// local — no una máquina de estados ni una dependencia nueva.
	const chatRunIdRef = useRef(0);
	// G2.1 — guarda síncrona para `retryPersistMessage`: `persistingMessageIds`
	// (estado) solo existe para pintar el botón de reintento; una segunda
	// llamada disparada en el mismo ciclo síncrono, antes de que React
	// vuelva a renderizar, debe bloquearse aquí, no en el estado (que
	// llegaría demasiado tarde para evitar la segunda solicitud).
	const persistingRetryRef = useRef<Set<string>>(new Set());

	const threadIdRef = useRef<string>(generateId());
	const conversationIdRef = useRef<string | null>(null);
	const streamingStartedRef = useRef(false);
	const abortControllerRef = useRef<AbortController | null>(null);
	// A4/A6/G2.2 — controlador dedicado para `loadConversation`,
	// deliberadamente distinto de `abortControllerRef` (usado solo por la
	// generación en streaming de `submit`); ambos se cancelan por vías
	// separadas y con reglas distintas:
	//   - `cancel()` (el botón "Detener") nunca aborta una carga de
	//     historial en vuelo — solo conoce `abortControllerRef`.
	//   - un nuevo `submit()` SÍ aborta una carga de historial obsoleta
	//     (`loadConversationAbortRef`), para que su resultado tardío no
	//     pise el chat que se está empezando ahora.
	//   - `loadConversation()`, a su vez, SÍ aborta directamente una
	//     generación en streaming activa (`abortControllerRef`) — sin pasar
	//     por `cancel()` — para impedir que su resultado contamine la
	//     conversación recién seleccionada; ese aborto nunca debe mostrar
	//     "Generación detenida" (aviso exclusivo de que el usuario pulse
	//     "Detener").
	// También sirve para descartar una respuesta de carga obsoleta: si el
	// usuario selecciona otra conversación antes de que la anterior termine
	// de cargar, la que llegue tarde nunca debe pisar la vigente.
	const loadConversationAbortRef = useRef<AbortController | null>(null);

	useEffect(() => {
		return () => {
			abortControllerRef.current?.abort();
			loadConversationAbortRef.current?.abort();
		};
	}, []);

	function _setConversationId(id: string | null) {
		conversationIdRef.current = id;
		setConversationId(id);
	}

	/** Crea la conversación en la base de datos vía API al enviar el primer mensaje. */
	async function _createConversation(firstQuestion: string): Promise<string> {
		const token = getToken();
		if (!user || !token) {
			// Si React todavía cree que hay un usuario pero el token ya no está
			// (p. ej. otra pestaña cerró sesión), notifica para que la UI se
			// actualice en vez de solo lanzar un error con el chat aún montado.
			if (user) expireAuthSession(null);
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
		// A7 — defensa en profundidad: el `maxLength` del textarea ya impide
		// escribir de más en el uso normal, pero esto cubre cualquier otra vía
		// de llegar aquí (paste que lo esquive, uso programático) sin
		// depender solo del rechazo tardío del backend. Nunca se persiste una
		// pregunta que supere el límite.
		if (q.length > MAX_QUESTION_CHARS) {
			setError(
				`La pregunta no puede superar ${MAX_QUESTION_CHARS} caracteres.`,
			);
			return;
		}
		const token = getToken();
		if (!user || !token) {
			// Mismo caso que en _createConversation: notifica si React aún cree
			// que hay sesión activa.
			if (user) expireAuthSession(null);
			setError("La sesión no es válida. Inicia sesión nuevamente.");
			return;
		}

		const isFirstMessage = messages.length === 0 && !conversationIdRef.current;

		// G2.1 — reclama la propiedad del estado compartido del chat. A
		// partir de aquí, cualquier `loadConversation()`/`submit()` anterior
		// que siguiera resolviendo en segundo plano deja de poder tocar
		// messages/loading/isStreaming/stage/stageMessage/error/
		// contextPercent en cuanto compruebe `isCurrentRun()`.
		const runId = ++chatRunIdRef.current;
		const isCurrentRun = () => chatRunIdRef.current === runId;
		cancelRequestedRef.current = false;
		// Un envío nuevo invalida también una carga de historial que
		// siguiera en vuelo: su respuesta tardía no debe poder sobrescribir
		// el chat que se está empezando ahora.
		loadConversationAbortRef.current?.abort();
		loadConversationAbortRef.current = null;

		setLoading(true);
		setIsStreaming(false);
		setStage(null);
		setStageMessage(null);
		setError(null);
		setGenerationStopped(false);
		setGenerationFinished(false);
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
				if (!isCurrentRun()) return;
				_setConversationId(newConvId);
			} catch (err) {
				if (!isCurrentRun()) return;
				setMessages((prev) => prev.filter((message) => message.id !== localUserId));
				setInput(q);
				setLoading(false);
				setError(
					err instanceof Error ? err.message : "No fue posible crear la conversación.",
				);
				return;
			}
		}

		if (!isCurrentRun()) return;

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
			if (!isCurrentRun()) return;
			userMsgId = savedUserMessage.id;
			setMessages((prev) =>
				prev.map((message) =>
					message.id === localUserId ? { ...message, id: userMsgId } : message,
				),
			);
		} catch (err) {
			if (!isCurrentRun()) return;
			setMessages((prev) => prev.filter((message) => message.id !== localUserId));
			setInput(q);
			setLoading(false);
			setError(err instanceof Error ? err.message : "No fue posible guardar la pregunta.");
			return;
		}

		if (!isCurrentRun()) return;

		const assistantId = generateId();
		setMessages((prev) => [
			...prev,
			{ id: assistantId, role: "assistant", text: "", sources: [] },
		]);

		let finalAssistantText = "";
		let finalAssistantSources: SourceGroup[] = [];
		const controller = new AbortController();
		abortControllerRef.current = controller;

		// A5 — el streaming y la persistencia de la respuesta son dos fases
		// con fallos de naturaleza distinta, y ya no comparten un único
		// `catch`:
		//   - un fallo DURANTE el streaming (antes de completarse) nunca deja
		//     una respuesta incompleta presentada como si fuera la final: el
		//     mensaje del asistente se descarta y se informa un error.
		//   - un fallo SOLO al guardar, después de que el streaming ya
		//     terminó por completo, no debe ocultar una respuesta que el
		//     usuario ya vio generarse entera: el mensaje se conserva visible,
		//     marcado como no guardado (`persistenceStatus: "failed"`), con
		//     reintento manual — nunca automático ni destructivo.
		let streamSucceeded = false;
		// A6 — "Detener" solo debe estar disponible mientras esta fase (la
		// generación en streaming) está activa: nunca durante la creación de
		// la conversación o la persistencia de la pregunta (ya ocurridas) ni
		// durante la persistencia de la respuesta final (fase siguiente).
		setCanCancel(true);
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
				// G2.1 — defensa adicional: si otra operación reclamó la
				// propiedad del estado mientras este chunk ya estaba en
				// vuelo (carrera entre el abort y una lectura ya en curso),
				// deja de procesar eventos y de tocar el estado de
				// inmediato.
				if (!isCurrentRun()) return;
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

			if (!isCurrentRun()) return;
			if (!finalAssistantText) {
				throw new Error("El servidor no devolvió una respuesta completa.");
			}
			streamSucceeded = true;
			// Se marca en cuanto el stream produjo la respuesta completa,
			// no al final de la persistencia (fase siguiente, que puede tardar
			// o fallar sin que eso afecte lo que ya se muestra en pantalla). El
			// consumidor (`ChatInterface`) le da prioridad sobre `loading` al
			// anunciar el progreso, así que este valor decide el anuncio desde
			// aquí en adelante, aunque `loading` siga en `true` mientras se
			// guarda la respuesta.
			setGenerationFinished(true);
		} catch (err) {
			// A6 — al detener deliberadamente, la respuesta parcial se retira
			// del chat (igual que ante cualquier otro fallo de streaming), la
			// pregunta ya persistida del usuario permanece, y NUNCA se muestra
			// como un error de red — solo el aviso breve "Generación
			// detenida". G2.1 — pero solo si esta sigue siendo la operación
			// vigente: si ya se cambió de conversación o se reinició el chat,
			// ninguno de estos efectos debe tocar el estado.
			if (isCurrentRun()) {
				setMessages((prev) => prev.filter((m) => m.id !== assistantId));
				if (err instanceof DOMException && err.name === "AbortError") {
					if (cancelRequestedRef.current) setGenerationStopped(true);
				} else {
					setError(
						err instanceof Error
							? err.message
							: "Error de conexión. Compruebe que el servidor está activo.",
					);
				}
			}
		} finally {
			// G2.2 — tanto el reseteo de `cancelRequestedRef` como el de
			// `canCancel` se limitan a la operación vigente. `cancelRequestedRef`
			// es una única ref compartida entre operaciones: si esta operación
			// ya quedó obsoleta (se cambió de conversación, se reinició el
			// chat, o ya empezó un envío más nuevo) y termina tarde, no puede
			// borrar la intención de cancelación que el usuario acabe de
			// expresar sobre la operación vigente con `cancel()` — eso dejaría
			// a esa cancelación más reciente sin mostrar "Generación
			// detenida". Cuando esta operación SÍ sigue vigente, el reseteo
			// ocurre igual que antes, sin depender de qué rama del catch se
			// haya tomado (streaming completado con éxito, fallo, o abort).
			if (isCurrentRun()) {
				cancelRequestedRef.current = false;
				setCanCancel(false);
			}
			// G2.1 — limpia el controlador de streaming inmediatamente al
			// terminar esta fase, ANTES de la persistencia de la respuesta:
			// así `cancel()` es un no-op real durante el guardado (ya no hay
			// nada que abortar). Comprobación por identidad del propio
			// controller — deliberadamente independiente de `isCurrentRun()`:
			// debe limpiarse siempre que sea EL controlador que esta llamada
			// creó, sin importar si la operación sigue siendo la vigente.
			if (abortControllerRef.current === controller) {
				abortControllerRef.current = null;
			}
		}

		if (streamSucceeded && isCurrentRun()) {
			try {
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
				if (isCurrentRun()) {
					setMessages((prev) =>
						prev.map((m) =>
							m.id === assistantId
								? { ...m, id: savedAssistant.id, persistenceStatus: undefined }
								: m,
						),
					);
				}
				await onConversationChanged?.();
			} catch (err) {
				if (
					isCurrentRun() &&
					!(err instanceof DOMException && err.name === "AbortError")
				) {
					// A5 — la respuesta ya está completa y visible: no se elimina
					// ni se sustituye por el banner de error genérico. Solo se
					// marca localmente como no guardada.
					setMessages((prev) =>
						prev.map((m) =>
							m.id === assistantId
								? { ...m, persistenceStatus: "failed" }
								: m,
						),
					);
				}
			}
		}

		if (isCurrentRun()) {
			setLoading(false);
			setIsStreaming(false);
			setStage(null);
			setStageMessage(null);
		}
	}

	/**
	 * A6 — cancela únicamente la consulta en streaming activa en este
	 * momento (su propio `AbortController`, distinto del de
	 * `loadConversation`). No-op si no hay ninguna en curso (`canCancel`
	 * false) — nunca afecta otras conversaciones ni el historial.
	 */
	function cancel(): void {
		if (!abortControllerRef.current) return;
		cancelRequestedRef.current = true;
		// Feedback inmediato: el botón "Detener" se oculta/deshabilita sin
		// esperar a que el `catch` de `submit()` termine de propagarse.
		setCanCancel(false);
		abortControllerRef.current.abort();
	}

	/**
	 * A5 — reintento manual (nunca automático) de guardar una respuesta del
	 * asistente que ya se generó por completo pero cuyo guardado falló
	 * (`persistenceStatus === "failed"`). Reutiliza el mismo `messageId` local
	 * ya mostrado, así que es idempotente respecto al primer intento fallido.
	 */
	async function retryPersistMessage(messageId: string): Promise<void> {
		// G2.1 — guarda síncrona: bloquea una segunda llamada disparada en el
		// mismo ciclo (antes del siguiente render), cuando `persistingMessageIds`
		// (estado) todavía no refleja la primera. `persistingRetryRef.current`
		// se actualiza sincrónicamente más abajo, antes del primer `await`.
		if (persistingRetryRef.current.has(messageId)) return;

		const token = getToken();
		const activeConvId = conversationIdRef.current;
		const target = messages.find((m) => m.id === messageId);
		if (!activeConvId || !target || target.persistenceStatus !== "failed") {
			return;
		}
		if (!user || !token) {
			if (user) expireAuthSession(null);
			setError("La sesión no es válida. Inicia sesión nuevamente.");
			return;
		}

		persistingRetryRef.current.add(messageId);
		setPersistingMessageIds((prev) => new Set(prev).add(messageId));
		try {
			const savedAssistant = await persistMessage({
				token,
				conversationId: activeConvId,
				messageId,
				role: "assistant",
				text: target.text,
				sources:
					target.sources && target.sources.length > 0
						? target.sources
						: null,
				errorMessage: "La respuesta se obtuvo, pero no pudo guardarse.",
			});
			setMessages((prev) =>
				prev.map((m) =>
					m.id === messageId
						? { ...m, id: savedAssistant.id, persistenceStatus: undefined }
						: m,
				),
			);
			await onConversationChanged?.();
		} catch {
			// Sigue marcada como no guardada; el botón de reintento sigue
			// disponible para que el usuario lo intente de nuevo.
		} finally {
			persistingRetryRef.current.delete(messageId);
			setPersistingMessageIds((prev) => {
				const next = new Set(prev);
				next.delete(messageId);
				return next;
			});
		}
	}

	/** Carga una conversación existente desde la API y la restaura en la UI. */
	async function loadConversation(conv: Conversation): Promise<void> {
		// G2.1 — reclama la propiedad del estado compartido del chat. Si
		// había una generación en streaming activa (`submit()` en curso), se
		// aborta aquí — pero deliberadamente SIN pasar por `cancel()`, así
		// que nunca se muestra "Generación detenida" (ese aviso es exclusivo
		// de que el usuario pulse "Detener"): la propia comprobación de
		// `isCurrentRun()` en `submit()` ya evita que su continuación toque
		// el estado, y `cancelRequestedRef` se deja en `false`.
		const runId = ++chatRunIdRef.current;
		cancelRequestedRef.current = false;
		if (abortControllerRef.current) {
			abortControllerRef.current.abort();
			abortControllerRef.current = null;
		}
		setCanCancel(false);

		// A4 — cancela una carga anterior aún en vuelo (p. ej. el usuario hizo
		// clic en otra conversación antes de que la primera terminara), pero
		// nunca la generación en streaming de `submit` (controlador propio,
		// ya tratado arriba).
		loadConversationAbortRef.current?.abort();
		const controller = new AbortController();
		loadConversationAbortRef.current = controller;

		const token = getToken();
		if (!token) {
			// Igual que arriba: si React aún cree que hay sesión, notifica.
			if (user) expireAuthSession(null);
			return;
		}

		try {
			const res = await fetch(
				`${API_URL}/api/conversations/${conv.id}/messages`,
				{
					headers: { Authorization: `Bearer ${token}` },
					signal: controller.signal,
				},
			);
			await throwIfSessionExpired(res, token);
			if (!res.ok) {
				throw new Error("No fue posible cargar la conversación.");
			}

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

			// A4/G2.1 — una respuesta obsoleta (superada por una selección más
			// reciente de otra conversación, un `resetChat()`, o un nuevo
			// `submit()`) nunca debe pisar el estado vigente.
			if (loadConversationAbortRef.current !== controller) return;
			if (chatRunIdRef.current !== runId) return;

			setMessages(loaded);
			threadIdRef.current = conv.threadId;
			_setConversationId(conv.id);
			setInput("");
			setLoading(false);
			setIsStreaming(false);
			setStage(null);
			setStageMessage(null);
			setError(null);
			setGenerationStopped(false);
			setGenerationFinished(false);
			setContextPercent(0);
			streamingStartedRef.current = false;
		} catch (err) {
			// Una cancelación deliberada (superada por otra selección) no es un
			// error visible para el usuario.
			if (err instanceof DOMException && err.name === "AbortError") return;
			if (loadConversationAbortRef.current !== controller) return;
			if (chatRunIdRef.current !== runId) return;
			// A4 — a diferencia del comportamiento anterior (fallar en
			// silencio), la conversación actualmente visible se conserva tal
			// cual estaba y se muestra un error explícito del intento fallido.
			setError(
				err instanceof Error
					? err.message
					: "No fue posible cargar la conversación.",
			);
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
		// G2.1 — reclama la propiedad del estado compartido: invalida
		// cualquier `submit()`/`loadConversation()` que siguiera resolviendo
		// en segundo plano (su continuación dejará de tocar el estado en
		// cuanto compruebe `chatRunIdRef`).
		chatRunIdRef.current += 1;
		// A6 — este abort (si había una generación en curso) NUNCA debe
		// mostrar "Generación detenida": el chat entero se está vaciando, así
		// que no queda ningún mensaje parcial al que ese aviso pudiera
		// referirse.
		cancelRequestedRef.current = false;
		abortControllerRef.current?.abort();
		abortControllerRef.current = null;
		// A4 — una "Nueva consulta" mientras una carga de conversación seguía
		// en vuelo debe descartarla también: que llegue tarde no debe resucitar
		// mensajes de la conversación anterior sobre un chat ya reiniciado.
		loadConversationAbortRef.current?.abort();
		loadConversationAbortRef.current = null;
		setMessages([]);
		setInput("");
		setLoading(false);
		setIsStreaming(false);
		setStage(null);
		setStageMessage(null);
		setError(null);
		setGenerationStopped(false);
		setGenerationFinished(false);
		setCanCancel(false);
		setContextPercent(0);
		_setConversationId(null);
		streamingStartedRef.current = false;
		setRatedMessageIds(new Set());
		setPersistingMessageIds(new Set());
		persistingRetryRef.current = new Set();
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
		persistingMessageIds,
		canCancel,
		generationStopped,
		generationFinished,
		setInput,
		submit,
		resetChat,
		loadConversation,
		retryPersistMessage,
		cancel,
		rateMessage,
	};
}
