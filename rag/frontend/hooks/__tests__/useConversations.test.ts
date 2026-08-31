import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useConversations } from "@/hooks/useConversations";

vi.mock("@/lib/auth", () => ({
	getToken: vi.fn(() => "test-token"),
	expireAuthSession: vi.fn(),
}));

// Objeto estable: si `useAuth()` devolviera un objeto (o un `user`) nuevo en
// cada llamada, `refresh` (un `useCallback` con `[user]` como dependencia)
// cambiaría de identidad en cada render y el `useEffect` que lo dispara
// entraría en un bucle infinito de renders.
const STABLE_USER = { user_id: "u1", email: "user@example.com", display_name: null, role: "user" };

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({ user: STABLE_USER }),
}));

function rawConversation(overrides: Record<string, unknown> = {}) {
	return {
		id: "c1",
		title: "Título",
		thread_id: "thread-1",
		created_at: "2026-08-01T00:00:00Z",
		updated_at: "2026-08-01T00:00:00Z",
		message_count: 1,
		...overrides,
	};
}

function jsonResponse(body: unknown, status = 200) {
	return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
}

describe("useConversations (A4)", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("distingue loading / vacío-válido / error: un 500 no vacía una lista previamente cargada", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse([rawConversation()]))
			.mockResolvedValueOnce(jsonResponse({}, 500));

		const { result } = renderHook(() => useConversations());

		await waitFor(() => expect(result.current.conversations).toHaveLength(1));
		expect(result.current.error).toBeNull();

		await act(async () => {
			await result.current.refresh();
		});

		// A4 — la lista previa se conserva; el fallo se expone como `error`,
		// no como una lista vaciada.
		expect(result.current.conversations).toHaveLength(1);
		expect(result.current.conversations[0].id).toBe("c1");
		expect(result.current.error).toBe("Error 500");
	});

	it("un vacío legítimo (0 conversaciones, sin error) se distingue de un fallo", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock.mockResolvedValue(jsonResponse([]));

		const { result } = renderHook(() => useConversations());

		await waitFor(() => expect(result.current.loading).toBe(false));
		expect(result.current.conversations).toHaveLength(0);
		expect(result.current.error).toBeNull();
	});

	it("una respuesta obsoleta (cancelada por un refresh más reciente) no pisa el resultado vigente", async () => {
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
			.mockResolvedValueOnce(jsonResponse([rawConversation({ id: "c-new" })]));

		const { result } = renderHook(() => useConversations());

		// Segundo refresh disparado antes de que el primero (montaje inicial)
		// se resuelva: debe cancelarlo.
		await act(async () => {
			await result.current.refresh();
		});

		await waitFor(() => expect(result.current.conversations).toHaveLength(1));
		expect(result.current.conversations[0].id).toBe("c-new");
		expect(result.current.error).toBeNull();
	});
});
