import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import { queryRagStream } from "@/lib/api";
import type { Conversation } from "@/hooks/useConversations";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const STABLE_USER = { user_id: "u1", email: "user@example.com", display_name: null, role: "user" };

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER }),
}));

vi.mock("@/lib/api", () => ({
	queryRagStream: vi.fn(),
	throwIfSessionExpired: vi.fn(async () => {}),
}));

function jsonResponse(body: unknown, status = 200) {
	return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
	return {
		id: "conv-2",
		title: "Conversación B",
		threadId: "thread-b",
		createdAt: new Date("2026-08-01T00:00:00Z"),
		updatedAt: new Date("2026-08-01T00:00:00Z"),
		messageCount: 2,
		...overrides,
	};
}

/** Igual que en useChat.cancel.test.ts: un stream que emite un token y luego
 * se queda "generando" hasta que se aborte su signal — como el generador
 * real de `queryRagStream`. */
async function* hangingStream(_request: unknown, signal?: AbortSignal) {
	yield { type: "token", content: "Respuesta parcial A" } as const;
	await new Promise<never>((_resolve, reject) => {
		const onAbort = () => reject(new DOMException("Aborted", "AbortError"));
		if (signal?.aborted) {
			onAbort();
			return;
		}
		signal?.addEventListener("abort", onAbort);
	});
}

async function* okStream() {
	yield { type: "token", content: "Respuesta completa." } as const;
	yield { type: "sources", sources: [] } as const;
}

async function* okStreamB() {
	yield { type: "token", content: "Respuesta B completa." } as const;
	yield { type: "sources", sources: [] } as const;
}

describe("useChat — propiedad del estado compartido entre operaciones concurrentes (G2.1)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("seleccionar la conversación B durante el streaming de A aborta A sin mostrar 'Generación detenida', y B queda intacta", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // _createConversation (A)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-A" })) // persistir pregunta (A)
			.mockResolvedValueOnce(
				jsonResponse([
					{ id: "b1", role: "user", text: "Pregunta de B", sources: null },
					{ id: "b2", role: "assistant", text: "Respuesta ya guardada de B", sources: null },
				]),
			); // GET historial de B

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			hangingStream,
		);

		const { result } = renderHook(() => useChat());

		let submitAPromise!: Promise<void>;
		act(() => {
			submitAPromise = result.current.submit("Pregunta A");
		});

		await waitFor(() => expect(result.current.canCancel).toBe(true));
		expect(
			result.current.messages.some(
				(m) => m.role === "assistant" && m.text === "Respuesta parcial A",
			),
		).toBe(true);

		await act(async () => {
			await result.current.loadConversation(makeConversation());
		});
		await act(async () => {
			await submitAPromise;
		});

		// B es ahora la conversación vigente, con exactamente sus dos mensajes
		// — nada de la generación abortada de A sobrevive.
		expect(result.current.conversationId).toBe("conv-2");
		expect(result.current.messages).toHaveLength(2);
		expect(
			result.current.messages.some((m) => m.text === "Respuesta parcial A"),
		).toBe(false);
		expect(
			result.current.messages.some(
				(m) => m.role === "assistant" && m.text === "Respuesta ya guardada de B",
			),
		).toBe(true);

		// El aviso "Generación detenida" es exclusivo de `cancel()` — cambiar
		// de conversación nunca debe activarlo, aunque haya abortado una
		// generación en curso.
		expect(result.current.generationStopped).toBe(false);
		expect(result.current.error).toBeNull();
		expect(result.current.canCancel).toBe(false);
		expect(result.current.loading).toBe(false);
		expect(result.current.isStreaming).toBe(false);
	});

	it("reiniciar el chat e iniciar de inmediato otra consulta: la limpieza tardía de la operación anterior no altera la nueva", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // crear conversación (A)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-A" })) // persistir pregunta (A)
			.mockResolvedValueOnce(jsonResponse({ id: "conv-2" })) // crear conversación (B)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-B" })) // persistir pregunta (B)
			.mockResolvedValueOnce(jsonResponse({ id: "assistant-msg-B" })); // persistir respuesta (B)

		(queryRagStream as unknown as ReturnType<typeof vi.fn>)
			.mockImplementationOnce(hangingStream)
			.mockImplementationOnce(() => okStreamB());

		const { result } = renderHook(() => useChat());

		let submitAPromise!: Promise<void>;
		act(() => {
			submitAPromise = result.current.submit("Pregunta A");
		});

		await waitFor(() => expect(result.current.canCancel).toBe(true));
		expect(
			result.current.messages.some((m) => m.text === "Respuesta parcial A"),
		).toBe(true);

		// Reiniciar el chat: se deja que React vuelva a renderizar antes de la
		// siguiente consulta, igual que ocurriría con dos interacciones
		// separadas del usuario (botón "Nueva consulta" y luego escribir).
		act(() => {
			result.current.resetChat();
		});
		expect(result.current.messages).toHaveLength(0);
		expect(result.current.canCancel).toBe(false);
		expect(result.current.loading).toBe(false);

		let submitBPromise!: Promise<void>;
		act(() => {
			submitBPromise = result.current.submit("Pregunta B");
		});

		await act(async () => {
			await submitBPromise;
			// Deja que la continuación tardía y ya obsoleta de A (su catch de
			// AbortError) termine de resolverse también.
			await submitAPromise;
		});

		// El estado final refleja únicamente a B — nada de la operación A,
		// abortada y descartada por `resetChat()`, la contamina.
		expect(result.current.conversationId).toBe("conv-2");
		expect(
			result.current.messages.some(
				(m) => m.role === "user" && m.text === "Pregunta B",
			),
		).toBe(true);
		expect(
			result.current.messages.some(
				(m) => m.role === "assistant" && m.text === "Respuesta B completa.",
			),
		).toBe(true);
		expect(
			result.current.messages.some((m) => m.text.includes("parcial A")),
		).toBe(false);
		expect(result.current.error).toBeNull();
		expect(result.current.generationStopped).toBe(false);
		expect(result.current.loading).toBe(false);
		expect(result.current.isStreaming).toBe(false);
	});

	it("cancel() tras terminar el streaming, mientras se persiste la respuesta, es un no-op real", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let resolvePersist: (r: Response) => void = () => {};
		const pendingPersist = new Promise<Response>((resolve) => {
			resolvePersist = resolve;
		});
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // crear conversación
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" })) // persistir pregunta
			.mockReturnValueOnce(pendingPersist); // persistir respuesta: deliberadamente colgada

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		let submitPromise!: Promise<void>;
		act(() => {
			submitPromise = result.current.submit("¿Qué dice la norma?");
		});

		// El streaming ya se completó (tercera solicitud = persistir la
		// respuesta, en vuelo) — la fase de streaming terminó y ya no hay
		// nada que "Detener".
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
		expect(result.current.canCancel).toBe(false);
		const beforeText = result.current.messages.find(
			(m) => m.role === "assistant",
		)?.text;
		expect(beforeText).toBe("Respuesta completa.");

		act(() => {
			result.current.cancel();
		});

		// No-op real: ningún efecto observable, ni siquiera el intento de
		// abortar la persistencia (que ni usa el `AbortController` de
		// streaming, ya limpiado por entonces).
		expect(result.current.canCancel).toBe(false);
		expect(result.current.generationStopped).toBe(false);
		expect(result.current.error).toBeNull();
		expect(
			result.current.messages.find((m) => m.role === "assistant")?.text,
		).toBe("Respuesta completa.");

		await act(async () => {
			resolvePersist(jsonResponse({ id: "assistant-msg-saved" }));
			await submitPromise;
		});

		// La persistencia terminó con éxito, sin ninguna interferencia de
		// `cancel()`: la respuesta completa se guarda con normalidad.
		const savedMsg = result.current.messages.find(
			(m) => m.id === "assistant-msg-saved",
		);
		expect(savedMsg).toBeDefined();
		expect(savedMsg?.persistenceStatus).toBeUndefined();
		expect(fetchMock).toHaveBeenCalledTimes(3);
	});

	it("dos llamadas síncronas a retryPersistMessage(), en el mismo ciclo, producen una sola solicitud", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockResolvedValue(jsonResponse({}, 500));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());
		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		const failedId = result.current.messages.find(
			(m) => m.role === "assistant",
		)?.id;
		expect(failedId).toBeDefined();

		fetchMock.mockReset();
		let resolveRetry: (r: Response) => void = () => {};
		const pending = new Promise<Response>((resolve) => {
			resolveRetry = resolve;
		});
		fetchMock.mockReturnValue(pending);

		// A diferencia del test ya existente en useChat.persistence.test.ts
		// (que usa `waitFor` para esperar a que el estado se actualice antes
		// de la segunda llamada), esto dispara ambas llamadas en el MISMO
		// ciclo síncrono — sin ningún `await` entre medias — para verificar
		// específicamente la guarda síncrona basada en `useRef`
		// (`persistingRetryRef`), que debe bloquear la segunda llamada
		// incluso antes de que React vuelva a renderizar (momento en el que
		// el estado `persistingMessageIds` aún no reflejaría la primera).
		let firstSettled = false;
		let secondSettled = false;
		act(() => {
			void result.current
				.retryPersistMessage(failedId!)
				.then(() => {
					firstSettled = true;
				});
			void result.current
				.retryPersistMessage(failedId!)
				.then(() => {
					secondSettled = true;
				});
		});

		expect(fetchMock).toHaveBeenCalledTimes(1);

		await act(async () => {
			resolveRetry(jsonResponse({ id: "assistant-msg-saved" }));
			await Promise.resolve();
			await Promise.resolve();
			await Promise.resolve();
		});

		expect(fetchMock).toHaveBeenCalledTimes(1);
		expect(firstSettled).toBe(true);
		expect(secondSettled).toBe(true);
	});

	it("una operación A obsoleta que finaliza tarde no borra la intención de cancelación de una operación B más reciente (G2.2)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // crear conversación (A)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-A" })) // persistir pregunta (A)
			.mockResolvedValueOnce(jsonResponse([])) // GET historial de B (invalida a A)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-B" })); // persistir pregunta (B)

		// Promesas controladas: cada stream solo termina cuando el test lo
		// decide explícitamente — nunca por un temporizador ni por una
		// carrera implícita contra el evento real de `AbortSignal`. Esto
		// permite fijar con certeza el orden exacto exigido por el
		// escenario: la finalización de A debe ocurrir DESPUÉS de haberse
		// pedido la cancelación de B, y ANTES de que el propio stream de B
		// termine.
		let resolveA: () => void = () => {};
		const pendingA = new Promise<void>((resolve) => {
			resolveA = resolve;
		});
		async function* streamA() {
			yield { type: "token", content: "Respuesta parcial A" } as const;
			await pendingA;
		}

		let rejectB: (reason?: unknown) => void = () => {};
		const pendingB = new Promise<never>((_resolve, reject) => {
			rejectB = reject;
		});
		async function* streamB() {
			yield { type: "token", content: "Respuesta parcial B" } as const;
			await pendingB;
		}

		(queryRagStream as unknown as ReturnType<typeof vi.fn>)
			.mockImplementationOnce(() => streamA())
			.mockImplementationOnce(() => streamB());

		const { result } = renderHook(() => useChat());

		// 1) La operación A inicia streaming.
		let submitAPromise!: Promise<void>;
		act(() => {
			submitAPromise = result.current.submit("Pregunta A");
		});
		await waitFor(() => expect(result.current.canCancel).toBe(true));
		expect(
			result.current.messages.some((m) => m.text === "Respuesta parcial A"),
		).toBe(true);

		// 2) A es invalidada: `loadConversation` reclama la propiedad del
		// estado (incrementa `chatRunIdRef`) y aborta directamente el
		// `AbortController` de streaming de A — pero, deliberadamente, su
		// finalización queda retrasada: el mock de `queryRagStream` para A
		// no está atado a esa señal real, así que `pendingA` sigue sin
		// resolverse y el `finally` de A todavía no se ha ejecutado.
		await act(async () => {
			await result.current.loadConversation(
				makeConversation({ id: "conv-2", threadId: "thread-b" }),
			);
		});
		expect(result.current.conversationId).toBe("conv-2");
		// `loadConversation` deja `loading` en `false`: es lo que habilita
		// que la operación B pueda empezar a continuación (el guard inicial
		// de `submit()` es un no-op mientras `loading` sigue en `true`).
		expect(result.current.loading).toBe(false);

		// 3) Se inicia la operación B.
		let submitBPromise!: Promise<void>;
		act(() => {
			submitBPromise = result.current.submit("Pregunta B");
		});
		await waitFor(() => expect(result.current.canCancel).toBe(true));
		expect(
			result.current.messages.some((m) => m.text === "Respuesta parcial B"),
		).toBe(true);

		// 4) El usuario ejecuta cancel() sobre B.
		act(() => {
			result.current.cancel();
		});
		expect(result.current.canCancel).toBe(false);

		// 5) A termina DESPUÉS de haberse solicitado la cancelación de B. Con
		// la guarda de G2.2 (el reseteo de `cancelRequestedRef`/`canCancel`
		// en el `finally` de streaming limitado a `isCurrentRun()`), el
		// `finally` de A —ya obsoleto— no debe tocar ninguno de los dos.
		await act(async () => {
			resolveA();
			await submitAPromise;
		});

		// 6) Finalmente termina B: su propio stream lanza ahora el
		// `AbortError` que representa la cancelación pedida en el paso 4.
		await act(async () => {
			rejectB(new DOMException("Aborted", "AbortError"));
			await submitBPromise;
		});

		// La finalización tardía de A no borró la intención de cancelación
		// de B: si lo hubiera hecho (comportamiento previo a G2.2),
		// `cancelRequestedRef` habría quedado en `false` para cuando el
		// propio catch de B lo consultó, y `generationStopped` nunca se
		// habría activado.
		expect(result.current.generationStopped).toBe(true);
		expect(result.current.error).toBeNull();
		// La respuesta parcial de B se retira; no queda ningún mensaje de
		// asistente (la de A ya se descartó al cargar la conversación B en
		// el paso 2, y la de B se retira en su propio catch).
		expect(result.current.messages.some((m) => m.role === "assistant")).toBe(
			false,
		);
		// Ninguna respuesta parcial —ni de A ni de B— llegó a intentar
		// persistirse: las únicas cuatro solicitudes fueron crear la
		// conversación de A, persistir su pregunta, cargar el historial de
		// B, y persistir la pregunta de B.
		expect(fetchMock).toHaveBeenCalledTimes(4);
		expect(result.current.canCancel).toBe(false);
		expect(result.current.loading).toBe(false);
		expect(result.current.isStreaming).toBe(false);
	});
});
