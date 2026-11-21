import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "@/components/providers/AuthProvider";
import { useChat } from "@/hooks/useChat";
import { useConversations, type Conversation } from "@/hooks/useConversations";
import { queryRagStream } from "@/lib/api";
import { setAuth, type AuthUser } from "@/lib/auth";

vi.mock("@/lib/api", async (importOriginal) => ({
	...await importOriginal<typeof import("@/lib/api")>(),
	queryRagStream: vi.fn(),
}));

const A: AuthUser = { user_id: "A", email: "a@example.test", display_name: "A", user_type: null, role: "user" };
const B: AuthUser = { user_id: "B", email: "b@example.test", display_name: "B", user_type: null, role: "user" };
const conversation: Conversation = { id: "conv-A", title: "A", threadId: "thread-A", createdAt: new Date(), updatedAt: new Date(), messageCount: 0 };
const fetchMock = vi.fn<typeof fetch>();
function json(body: unknown): Response { return { ok: true, status: 200, json: async () => body } as Response; }
function mountChat() {
	return renderHook(() => ({ auth: useAuth(), chat: useChat() }), {
		wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
	});
}

beforeEach(() => {
	localStorage.clear();
	setAuth("token-A", A);
	fetchMock.mockReset().mockImplementation(async (url) => {
		if (String(url).endsWith("/api/auth/me")) return json(A);
		if (String(url).endsWith("/messages")) return json({ id: "message-A" });
		return json({ id: "conv-A" });
	});
	vi.stubGlobal("fetch", fetchMock);
	vi.mocked(queryRagStream).mockReset().mockImplementation(async function* () {
		yield { type: "token", content: "Respuesta A" };
	});
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

describe("frontera de sesión antes de recibir storage", () => {
	it("no crea, persiste ni consulta B desde la UI todavía identificada como A", async () => {
		const { result } = mountChat();
		await waitFor(() => expect(result.current.auth.user?.user_id).toBe("A"));
		fetchMock.mockClear();
		setAuth("token-B", B); // El navegador todavía no entregó storage a esta pestaña.
		await act(async () => { await result.current.chat.submit("Pregunta de A"); });
		expect(fetchMock).not.toHaveBeenCalled();
		expect(queryRagStream).not.toHaveBeenCalled();
		expect(result.current.chat.messages).toHaveLength(0);
	});

	it("no carga historial con JWT B desde una selección de A", async () => {
		const { result } = mountChat();
		await waitFor(() => expect(result.current.auth.user?.user_id).toBe("A"));
		fetchMock.mockClear();
		setAuth("token-B", B);
		await act(async () => { await result.current.chat.loadConversation(conversation); });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("no lista conversaciones B al refrescar una UI identificada como A", async () => {
		fetchMock.mockImplementation(async (url) => String(url).endsWith("/api/auth/me") ? json(A) : json([]));
		const { result } = renderHook(() => ({ auth: useAuth(), list: useConversations() }), {
			wrapper: ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>,
		});
		await waitFor(() => expect(result.current.auth.user?.user_id).toBe("A"));
		await waitFor(() => expect(result.current.list.loading).toBe(false));
		fetchMock.mockClear();
		setAuth("token-B", B);
		await act(async () => { await result.current.list.refresh(); });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("una operación A iniciada conserva su token en persistencia y SSE tras rotar el almacenamiento", async () => {
		let finishCreate!: (response: Response) => void;
		const create = new Promise<Response>((resolve) => { finishCreate = resolve; });
		fetchMock.mockImplementation(async (url, init) => {
			if (String(url).endsWith("/api/auth/me")) return json(A);
			if (String(url).endsWith("/api/conversations") && init?.method === "POST") return create;
			return json({ id: "message-A" });
		});
		const { result } = mountChat();
		await waitFor(() => expect(result.current.auth.user?.user_id).toBe("A"));
		let submission!: Promise<void>;
		act(() => { submission = result.current.chat.submit("Pregunta de A"); });
		setAuth("token-B", B);
		await act(async () => { finishCreate(json({ id: "conv-A" })); await submission; });
		const writes = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
		expect(writes.length).toBeGreaterThan(1);
		for (const [, init] of writes) expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer token-A");
		expect(queryRagStream).toHaveBeenCalledWith(expect.anything(), expect.anything(), "token-A");
	});

	it("un reintento de guardar una respuesta A no escribe bajo B antes de storage", async () => {
		fetchMock.mockImplementation(async (url, init) => {
			if (String(url).endsWith("/api/auth/me")) return json(A);
			if (String(url).endsWith("/messages")) {
				const body = JSON.parse(String(init?.body)) as { role: string };
				return body.role === "assistant" ? new Response("", { status: 500 }) : json({ id: "user-A" });
			}
			return json({ id: "conv-A" });
		});
		const { result } = mountChat();
		await waitFor(() => expect(result.current.auth.user?.user_id).toBe("A"));
		await act(async () => { await result.current.chat.submit("Pregunta de A"); });
		const failed = result.current.chat.messages.find((message) => message.persistenceStatus === "failed");
		expect(failed).toBeDefined();
		fetchMock.mockClear();
		setAuth("token-B", B);
		await act(async () => { await result.current.chat.retryPersistMessage(failed!.id); });
		expect(fetchMock).not.toHaveBeenCalled();
	});

	it("el feedback de un mensaje A no se envía bajo B antes de storage", async () => {
		const { result } = mountChat();
		await waitFor(() => expect(result.current.auth.user?.user_id).toBe("A"));
		await act(async () => { await result.current.chat.submit("Pregunta de A"); });
		fetchMock.mockClear();
		setAuth("token-B", B);
		await act(async () => { await result.current.chat.rateMessage("message-A", { pertinence: 4, accuracy: 4 }); });
		expect(fetchMock).not.toHaveBeenCalled();
	});
});
