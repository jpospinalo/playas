import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import type { Conversation } from "@/hooks/useConversations";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

const STABLE_USER = { user_id: "u1", email: "user@example.com", display_name: null, role: "user" };

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER }),
}));

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

function jsonResponse(body: unknown, status = 200) {
	return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

function messagePayload(text: string) {
	return [{ id: "m1", role: "user", text, sources: null }];
}

describe("useChat — loadConversation (A4)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("una carga obsoleta (superada por otra selección) no pisa la conversación vigente", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;

		let rejectFirst: (reason?: unknown) => void = () => {};
		const firstCall = new Promise<Response>((_resolve, reject) => {
			rejectFirst = reject;
		});
		fetchMock
			.mockImplementationOnce((_url: string, init?: RequestInit) => {
				init?.signal?.addEventListener("abort", () => {
					rejectFirst(new DOMException("Aborted", "AbortError"));
				});
				return firstCall;
			})
			.mockResolvedValueOnce(jsonResponse(messagePayload("Segunda conversación")));

		const { result } = renderHook(() => useChat());

		await act(async () => {
			// No se espera esta primera llamada: se dispara y se deja en vuelo.
			void result.current.loadConversation(makeConversation({ id: "conv-1" }));
		});
		await act(async () => {
			await result.current.loadConversation(makeConversation({ id: "conv-2" }));
		});

		await waitFor(() => expect(result.current.conversationId).toBe("conv-2"));
		expect(result.current.messages).toHaveLength(1);
		expect(result.current.messages[0].text).toBe("Segunda conversación");
		expect(result.current.error).toBeNull();
	});

	it("si falla la carga, conserva la conversación visible y muestra un error (no falla en silencio)", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse(messagePayload("Primera conversación")))
			.mockResolvedValueOnce(jsonResponse({}, 500));

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.loadConversation(makeConversation({ id: "conv-1" }));
		});
		expect(result.current.conversationId).toBe("conv-1");
		expect(result.current.messages[0].text).toBe("Primera conversación");

		await act(async () => {
			await result.current.loadConversation(makeConversation({ id: "conv-2" }));
		});

		// A4 — la conversación previamente cargada sigue en pantalla; el fallo
		// se informa vía `error`, sin vaciar `messages` ni `conversationId`.
		expect(result.current.conversationId).toBe("conv-1");
		expect(result.current.messages[0].text).toBe("Primera conversación");
		expect(result.current.error).toBe("No fue posible cargar la conversación.");
	});

	it("resetChat() cancela una carga de conversación aún en vuelo", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let rejectFirst: (reason?: unknown) => void = () => {};
		const neverResolves = new Promise<Response>((_resolve, reject) => {
			rejectFirst = reject;
		});
		fetchMock.mockImplementationOnce((_url: string, init?: RequestInit) => {
			init?.signal?.addEventListener("abort", () => {
				rejectFirst(new DOMException("Aborted", "AbortError"));
			});
			return neverResolves;
		});

		const { result } = renderHook(() => useChat());

		await act(async () => {
			void result.current.loadConversation(makeConversation({ id: "conv-1" }));
		});
		act(() => {
			result.current.resetChat();
		});

		// Deja que la promesa abortada se resuelva internamente.
		await act(async () => {
			await Promise.resolve();
		});

		expect(result.current.conversationId).toBeNull();
		expect(result.current.messages).toHaveLength(0);
		expect(result.current.error).toBeNull();
	});
});
