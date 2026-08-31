import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import { queryRagStream } from "@/lib/api";
import type { Conversation } from "@/hooks/useConversations";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const STABLE_USER = {
	user_id: "u1",
	email: "user@example.com",
	display_name: null,
	role: "user",
};

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER }),
}));

vi.mock("@/lib/api", () => ({
	queryRagStream: vi.fn(),
	throwIfSessionExpired: vi.fn(async () => {}),
}));

function jsonResponse(body: unknown, status = 200) {
	return {
		ok: status >= 200 && status < 300,
		status,
		json: async () => body,
	} as Response;
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

async function* okStream() {
	yield { type: "token", content: "Respuesta completa." } as const;
	yield { type: "sources", sources: [] } as const;
}

/** Igual que en useChat.cancel.test.ts: se queda "generando" hasta que se
 * aborte su signal — como el generador real de `queryRagStream`. */
async function* hangingStream(_request: unknown, signal?: AbortSignal) {
	yield { type: "token", content: "Respuesta parcial" } as const;
	await new Promise<never>((_resolve, reject) => {
		const onAbort = () => reject(new DOMException("Aborted", "AbortError"));
		if (signal?.aborted) {
			onAbort();
			return;
		}
		signal?.addEventListener("abort", onAbort);
	});
}

async function* erroringStream() {
	yield { type: "token", content: "Respuesta parc" } as const;
	yield { type: "error", detail: "Falla del modelo" } as const;
}

describe("useChat — generationFinished", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("una generación exitosa marca generationFinished en true, sin error ni 'detenida'", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // crear conversación
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" })) // persistir pregunta
			.mockResolvedValueOnce(jsonResponse({ id: "assistant-msg-1" })); // persistir respuesta

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());
		expect(result.current.generationFinished).toBe(false);

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		expect(result.current.generationFinished).toBe(true);
		expect(result.current.error).toBeNull();
		expect(result.current.generationStopped).toBe(false);
		expect(result.current.loading).toBe(false);
	});

	it("un error durante el streaming nunca marca generationFinished", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => erroringStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		expect(result.current.error).not.toBeNull();
		expect(result.current.generationFinished).toBe(false);
	});

	it("cancelar ('Detener') nunca marca generationFinished", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			hangingStream,
		);

		const { result } = renderHook(() => useChat());

		let submitPromise!: Promise<void>;
		act(() => {
			submitPromise = result.current.submit("¿Qué dice la norma?");
		});
		await waitFor(() => expect(result.current.canCancel).toBe(true));

		act(() => {
			result.current.cancel();
		});
		await act(async () => {
			await submitPromise;
		});

		expect(result.current.generationStopped).toBe(true);
		expect(result.current.generationFinished).toBe(false);
	});

	it("iniciar una nueva consulta limpia generationFinished de la anterior, aunque haya terminado con éxito", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "assistant-msg-1" }));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("Pregunta A");
		});
		expect(result.current.generationFinished).toBe(true);

		// Segunda consulta: al reclamar la propiedad del estado, debe limpiar
		// de inmediato el aviso de la generación anterior, no solo al
		// terminar la nueva.
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-2" }))
			.mockResolvedValueOnce(jsonResponse({ id: "assistant-msg-2" }));
		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			hangingStream,
		);

		act(() => {
			void result.current.submit("Pregunta B");
		});
		await waitFor(() => expect(result.current.loading).toBe(true));
		expect(result.current.generationFinished).toBe(false);
	});

	it("cambiar de conversación limpia generationFinished de una generación anterior exitosa", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "assistant-msg-1" }))
			.mockResolvedValueOnce(
				jsonResponse([
					{ id: "b1", role: "user", text: "Pregunta de B", sources: null },
					{ id: "b2", role: "assistant", text: "Respuesta de B", sources: null },
				]),
			); // GET historial de B

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("Pregunta A");
		});
		expect(result.current.generationFinished).toBe(true);

		await act(async () => {
			await result.current.loadConversation(makeConversation());
		});

		expect(result.current.generationFinished).toBe(false);
		expect(result.current.conversationId).toBe("conv-2");
	});

	it("reiniciar el chat limpia generationFinished de una generación anterior exitosa", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "assistant-msg-1" }));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("Pregunta A");
		});
		expect(result.current.generationFinished).toBe(true);

		act(() => {
			result.current.resetChat();
		});

		expect(result.current.generationFinished).toBe(false);
		expect(result.current.messages).toHaveLength(0);
	});

	it("una operación obsoleta cuya persistencia termina DESPUÉS de haber sido reemplazada nunca marca generationFinished (G2.1)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let resolvePersistA: (r: Response) => void = () => {};
		const pendingPersistA = new Promise<Response>((resolve) => {
			resolvePersistA = resolve;
		});
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // crear conversación (A)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-A" })) // persistir pregunta (A)
			.mockReturnValueOnce(pendingPersistA) // persistir respuesta (A): deliberadamente colgada
			.mockResolvedValueOnce(
				jsonResponse([
					{ id: "b1", role: "user", text: "Pregunta de B", sources: null },
					{ id: "b2", role: "assistant", text: "Respuesta ya guardada de B", sources: null },
				]),
			); // GET historial de B

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		// A: el streaming termina (tercera solicitud = persistir la
		// respuesta, deliberadamente en vuelo).
		let submitAPromise!: Promise<void>;
		act(() => {
			submitAPromise = result.current.submit("Pregunta A");
		});
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
		// Ya en `true`: se marca en cuanto el streaming de A terminó, sin
		// esperar a que la persistencia (deliberadamente en vuelo) resuelva.
		expect(result.current.generationFinished).toBe(true);

		// B reclama la propiedad del estado MIENTRAS la persistencia de A
		// sigue pendiente — exactamente la carrera que `isCurrentRun()` debe
		// cubrir en el bloque final de `submit()`, no solo dentro del bucle
		// de streaming.
		await act(async () => {
			await result.current.loadConversation(makeConversation());
		});
		expect(result.current.conversationId).toBe("conv-2");
		expect(result.current.generationFinished).toBe(false);

		// Ahora se deja terminar la persistencia tardía de A.
		await act(async () => {
			resolvePersistA(jsonResponse({ id: "assistant-msg-A" }));
			await submitAPromise;
		});

		// La operación A, ya obsoleta, no debe marcar generationFinished ni
		// pisar el estado (mensajes/conversación) que B ya estableció.
		expect(result.current.generationFinished).toBe(false);
		expect(result.current.conversationId).toBe("conv-2");
		expect(result.current.messages).toHaveLength(2);
		expect(
			result.current.messages.some((m) => m.text.includes("Respuesta completa")),
		).toBe(false);
	});

	it("generationFinished pasa a true en cuanto termina el streaming, sin esperar a que se guarde la respuesta", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let resolvePersist: (r: Response) => void = () => {};
		const pendingPersist = new Promise<Response>((resolve) => {
			resolvePersist = resolve;
		});
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // crear conversación
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" })) // persistir pregunta
			.mockReturnValueOnce(pendingPersist); // persistir respuesta: deliberadamente en vuelo

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		let submitPromise!: Promise<void>;
		act(() => {
			submitPromise = result.current.submit("¿Qué dice la norma?");
		});

		// El streaming ya terminó (se alcanzó la tercera solicitud, la de
		// persistir la respuesta) pero esa persistencia sigue colgada:
		// generationFinished ya debe ser true, y loading debe seguir true
		// (la persistencia todavía cuenta como parte de la operación en
		// curso: esto no cambia loading, solo el estado anunciado).
		await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
		expect(result.current.generationFinished).toBe(true);
		expect(result.current.loading).toBe(true);

		await act(async () => {
			resolvePersist(jsonResponse({ id: "assistant-msg-1" }));
			await submitPromise;
		});
		expect(result.current.generationFinished).toBe(true);
		expect(result.current.loading).toBe(false);
	});

	it("una persistencia fallida no revierte generationFinished (la respuesta ya se mostró completa)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" }))
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-1" }))
			.mockRejectedValueOnce(new Error("fallo de red al guardar"));

		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			() => okStream(),
		);

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.submit("¿Qué dice la norma?");
		});

		expect(result.current.generationFinished).toBe(true);
		expect(
			result.current.messages.some((m) => m.persistenceStatus === "failed"),
		).toBe(true);
	});
});
