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

/** Un stream que emite un token y luego se queda "generando" hasta que se aborte su signal — igual que el generador real de `queryRagStream`. */
async function* hangingStream(_request: unknown, signal?: AbortSignal) {
	yield { type: "token", content: "Respuesta parc" } as const;
	await new Promise<never>((_resolve, reject) => {
		const onAbort = () => reject(new DOMException("Aborted", "AbortError"));
		if (signal?.aborted) {
			onAbort();
			return;
		}
		signal?.addEventListener("abort", onAbort);
	});
}

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
	return {
		id: "conv-1",
		title: "Conversación",
		threadId: "thread-1",
		createdAt: new Date("2026-08-01T00:00:00Z"),
		updatedAt: new Date("2026-08-01T00:00:00Z"),
		messageCount: 2,
		...overrides,
	};
}

describe("useChat — cancel() / Detener (A6)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("Detener aborta solo la consulta activa y deja el chat en un estado consistente", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // _createConversation
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" })); // persistir pregunta

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			hangingStream,
		);

		const { result } = renderHook(() => useChat());

		let submitPromise!: Promise<void>;
		act(() => {
			submitPromise = result.current.submit("¿Qué dice la norma?");
		});

		// canCancel solo se activa una vez que la fase de streaming empezó —
		// nunca durante crear la conversación o persistir la pregunta.
		await waitFor(() => expect(result.current.canCancel).toBe(true));
		expect(
			result.current.messages.some(
				(m) => m.role === "assistant" && m.text === "Respuesta parc",
			),
		).toBe(true);

		act(() => {
			result.current.cancel();
		});

		// Feedback inmediato, antes de que la promesa de streaming termine de
		// resolverse.
		expect(result.current.canCancel).toBe(false);

		await act(async () => {
			await submitPromise;
		});

		// La pregunta ya persistida del usuario permanece intacta.
		expect(
			result.current.messages.some(
				(m) => m.role === "user" && m.text === "¿Qué dice la norma?",
			),
		).toBe(true);
		// La respuesta parcial se retira — nunca se presenta como final.
		expect(result.current.messages.some((m) => m.role === "assistant")).toBe(
			false,
		);
		// Nunca como error de red: solo el aviso breve y no persistente.
		expect(result.current.error).toBeNull();
		expect(result.current.generationStopped).toBe(true);
		expect(result.current.loading).toBe(false);
		expect(result.current.canCancel).toBe(false);
		// Solo dos solicitudes (crear conversación + persistir pregunta): la
		// cancelación nunca llegó a intentar persistir una respuesta.
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

	it("cancel() es un no-op cuando no hay ninguna generación activa", () => {
		const { result } = renderHook(() => useChat());
		expect(result.current.canCancel).toBe(false);
		expect(() => result.current.cancel()).not.toThrow();
		expect(result.current.generationStopped).toBe(false);
	});

	it("cancel() no afecta una carga de conversación en curso (controladores independientes)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let rejectLoad: (reason?: unknown) => void = () => {};
		const hangingLoad = new Promise<Response>((_resolve, reject) => {
			rejectLoad = reject;
		});
		fetchMock.mockImplementationOnce((_url: string, init?: RequestInit) => {
			init?.signal?.addEventListener("abort", () => {
				rejectLoad(new DOMException("Aborted", "AbortError"));
			});
			return hangingLoad;
		});

		const { result } = renderHook(() => useChat());

		act(() => {
			void result.current.loadConversation(makeConversation());
		});

		// No hay generación en streaming activa — cancel() no debe abortar la
		// carga de la conversación en curso.
		act(() => {
			result.current.cancel();
		});

		expect(fetchMock).toHaveBeenCalledTimes(1);
		// La promesa de carga sigue pendiente (no fue abortada por cancel()).
		rejectLoad(new DOMException("cleanup", "AbortError"));
		await act(async () => {
			await Promise.resolve();
		});
	});
});
