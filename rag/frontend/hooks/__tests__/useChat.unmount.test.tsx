import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import { queryRagStream } from "@/lib/api";

const session = vi.hoisted(() => ({ userId: "A" }));

vi.mock("@/components/providers/AuthProvider", () => ({
	useAuth: () => ({
		user: { user_id: session.userId, email: "user@example.test", role: "user" },
	}),
}));

vi.mock("@/lib/auth", () => ({
	getTokenForUser: vi.fn((userId: string) => `token-${userId}`),
	expireAuthSession: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
	queryRagStream: vi.fn(),
	throwIfSessionExpired: vi.fn(async () => {}),
}));

function json(body: unknown): Response {
	return { ok: true, status: 200, json: async () => body } as Response;
}

function deferredResponse() {
	let resolve!: (response: Response) => void;
	const promise = new Promise<Response>((complete) => { resolve = complete; });
	return { promise, resolve };
}

describe("useChat — desmontaje antes de iniciar SSE", () => {
	beforeEach(() => {
		session.userId = "A";
		vi.stubGlobal("fetch", vi.fn());
		vi.mocked(queryRagStream).mockImplementation(async function* () {
			yield { type: "token", content: "Respuesta completa" };
			yield { type: "sources", sources: [] };
		});
	});

	afterEach(() => {
		cleanup();
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it.each(["crear conversación", "guardar pregunta"] as const)(
		"no inicia SSE ni guarda asistente tras desmontar durante %s; otra sesión funciona",
		async (phase) => {
			const pending = deferredResponse();
			const fetchMock = vi.mocked(fetch);
			fetchMock.mockImplementation(async (_url, init) => {
				const body = JSON.parse(String(init?.body)) as { role?: string };
				return json({ id: body.role ? `message-${body.role}` : "conv-B" });
			});
			if (phase === "crear conversación") {
				fetchMock.mockImplementationOnce(() => pending.promise);
			} else {
				fetchMock.mockResolvedValueOnce(json({ id: "conv-A" }));
				fetchMock.mockImplementationOnce(() => pending.promise);
			}

			const first = renderHook(() => useChat());
			let submission!: Promise<void>;
			await act(async () => {
				submission = first.result.current.submit("Pregunta de A");
			});
			expect(fetchMock).toHaveBeenCalledTimes(phase === "crear conversación" ? 1 : 2);
			first.unmount();
			session.userId = "B";
			await act(async () => {
				pending.resolve(json({ id: phase === "crear conversación" ? "conv-A" : "user-A" }));
				await submission;
			});

			expect(queryRagStream).not.toHaveBeenCalled();
			expect(fetchMock).toHaveBeenCalledTimes(phase === "crear conversación" ? 1 : 2);
			for (const [, init] of fetchMock.mock.calls) {
				expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-A");
			}
			expect(fetchMock.mock.calls.some(([, init]) =>
				(JSON.parse(String(init?.body)) as { role?: string }).role === "assistant",
			)).toBe(false);

			fetchMock.mockClear();
			const second = renderHook(() => useChat());
			await act(async () => { await second.result.current.submit("Pregunta de B"); });
			expect(queryRagStream).toHaveBeenCalledTimes(1);
			expect(queryRagStream).toHaveBeenCalledWith(
				expect.objectContaining({ question: "Pregunta de B", conversation_id: "conv-B" }),
				expect.any(AbortSignal),
				"token-B",
			);
			expect(second.result.current.messages.map((message) => message.text)).toEqual([
				"Pregunta de B", "Respuesta completa",
			]);
			for (const [, init] of fetchMock.mock.calls) {
				expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-B");
			}
		},
	);
});
