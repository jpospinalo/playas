import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useChat } from "@/hooks/useChat";
import { queryRagStream } from "@/lib/api";
import type { Conversation } from "@/hooks/useConversations";

/**
 * Ciclo de vida de `loadConversation`. Cubre específicamente los puntos que
 * `useChat.test.ts`/`useChat.ownership.test.ts` no ejercían:
 *  2. se marca como carga activa (`loading`) desde que se llama, no solo
 *     al terminar;
 *  3. el estado TRANSITORIO de una generación en curso (isStreaming/
 *     stage/stageMessage) se detiene de inmediato al tomar la propiedad,
 *     sin esperar a que la nueva carga resuelva — los mensajes visibles sí
 *     se conservan hasta entonces;
 *  4/5. A responde tarde CON ÉXITO (no por aborto) después de que B ya
 *     ganó, y A falla después de que B ya ganó — ninguno de los dos casos
 *     debe pisar el estado de B;
 *  7. sin token, ningún estado queda atascado en `loading`/`isStreaming`/
 *     `canCancel`.
 */

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

import { getToken } from "@/lib/auth";

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

/** Igual que en useChat.ownership.test.ts: emite un token y se queda
 * "generando" hasta que se aborte su signal. */
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

describe("useChat — ciclo de vida de loadConversation", () => {
	beforeEach(() => {
		vi.stubGlobal("fetch", vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.clearAllMocks();
	});

	it("se marca como carga activa (loading=true) desde que se llama, no solo al resolver", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let resolveFetch: (res: Response) => void = () => {};
		fetchMock.mockImplementationOnce(
			() => new Promise<Response>((resolve) => (resolveFetch = resolve)),
		);

		const { result } = renderHook(() => useChat());

		act(() => {
			void result.current.loadConversation(makeConversation());
		});

		// Sincrónico: `loading` ya es `true` aunque el fetch siga en vuelo.
		expect(result.current.loading).toBe(true);

		await act(async () => {
			resolveFetch(jsonResponse([]));
			await Promise.resolve();
		});

		await waitFor(() => expect(result.current.loading).toBe(false));
	});

	it("detiene isStreaming/stage/stageMessage de inmediato al tomar la propiedad, pero conserva los mensajes visibles hasta que la nueva carga tenga éxito", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		fetchMock
			.mockResolvedValueOnce(jsonResponse({ id: "conv-1" })) // _createConversation (A)
			.mockResolvedValueOnce(jsonResponse({ id: "user-msg-A" })); // persistir pregunta (A)
		(queryRagStream as unknown as ReturnType<typeof vi.fn>).mockImplementation(
			hangingStream,
		);

		const { result } = renderHook(() => useChat());

		act(() => {
			void result.current.submit("Pregunta A");
		});
		await waitFor(() => expect(result.current.canCancel).toBe(true));
		expect(result.current.isStreaming).toBe(true);
		const messagesDuringStreamingA = result.current.messages.length;
		expect(messagesDuringStreamingA).toBeGreaterThan(0);

		// El GET del historial de B se deja sin resolver: lo que importa es
		// el estado justo después de LLAMAR a loadConversation, no tras su
		// éxito.
		fetchMock.mockImplementationOnce(() => new Promise<Response>(() => {}));

		act(() => {
			void result.current.loadConversation(makeConversation());
		});

		expect(result.current.isStreaming).toBe(false);
		expect(result.current.stage).toBeNull();
		expect(result.current.stageMessage).toBeNull();
		expect(result.current.canCancel).toBe(false);
		// Los mensajes de A siguen visibles: todavía no hay éxito de B.
		expect(result.current.messages.length).toBe(messagesDuringStreamingA);
	});

	it("A responde con éxito tarde (no por aborto) después de que B ya ganó: la respuesta tardía de A no pisa a B", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let resolveA: (res: Response) => void = () => {};
		fetchMock
			.mockImplementationOnce(
				() => new Promise<Response>((resolve) => (resolveA = resolve)),
			)
			.mockResolvedValueOnce(
				jsonResponse([
					{ id: "b1", role: "user", text: "Pregunta de B", sources: null },
				]),
			);

		const { result } = renderHook(() => useChat());

		act(() => {
			void result.current.loadConversation(makeConversation({ id: "conv-a" }));
		});
		await act(async () => {
			await result.current.loadConversation(makeConversation({ id: "conv-b" }));
		});

		expect(result.current.conversationId).toBe("conv-b");
		expect(result.current.messages).toHaveLength(1);

		// A "responde" ahora, mucho después de que B ya ganó — no por un
		// aborto, sino con datos reales, como podría pasar con una respuesta
		// de red genuinamente lenta.
		await act(async () => {
			resolveA(
				jsonResponse([
					{ id: "a1", role: "user", text: "Pregunta de A", sources: null },
				]),
			);
			await Promise.resolve();
			await Promise.resolve();
		});

		expect(result.current.conversationId).toBe("conv-b");
		expect(result.current.messages).toHaveLength(1);
		expect(result.current.messages[0].text).toBe("Pregunta de B");
		expect(result.current.loading).toBe(false);
	});

	it("A falla (error real, no aborto) después de que B ya ganó: el error de A no se muestra ni toca el loading de B", async () => {
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
		let rejectA: (err: unknown) => void = () => {};
		fetchMock
			.mockImplementationOnce(
				() => new Promise<Response>((_resolve, reject) => (rejectA = reject)),
			)
			.mockResolvedValueOnce(
				jsonResponse([
					{ id: "b1", role: "user", text: "Pregunta de B", sources: null },
				]),
			);

		const { result } = renderHook(() => useChat());

		act(() => {
			void result.current.loadConversation(makeConversation({ id: "conv-a" }));
		});
		await act(async () => {
			await result.current.loadConversation(makeConversation({ id: "conv-b" }));
		});

		expect(result.current.conversationId).toBe("conv-b");
		expect(result.current.error).toBeNull();
		expect(result.current.loading).toBe(false);

		// A falla ahora, mucho después de que B ya ganó — un error de red
		// genuino, no relacionado con el aborto de A.
		await act(async () => {
			rejectA(new Error("Fallo de red tardío de A"));
			await Promise.resolve();
			await Promise.resolve();
		});

		expect(result.current.conversationId).toBe("conv-b");
		expect(result.current.error).toBeNull();
		expect(result.current.loading).toBe(false);
		expect(result.current.messages).toHaveLength(1);
		expect(result.current.messages[0].text).toBe("Pregunta de B");
	});

	it("sin token, ningún estado queda atascado: loading/isStreaming/canCancel vuelven a su valor de reposo", async () => {
		(getToken as unknown as ReturnType<typeof vi.fn>).mockReturnValueOnce(null);
		const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;

		const { result } = renderHook(() => useChat());

		await act(async () => {
			await result.current.loadConversation(makeConversation());
		});

		expect(result.current.loading).toBe(false);
		expect(result.current.isStreaming).toBe(false);
		expect(result.current.canCancel).toBe(false);
		// Sin token, nunca debió intentarse la solicitud HTTP.
		expect(fetchMock).not.toHaveBeenCalled();

		// Una carga posterior CON token debe funcionar con normalidad: el
		// intento sin token no debió dejar ninguna referencia residual que
		// pudiera interferir con la propiedad de una carga futura.
		fetchMock.mockResolvedValueOnce(
			jsonResponse([
				{ id: "m1", role: "user", text: "Pregunta tras el intento sin token", sources: null },
			]),
		);
		await act(async () => {
			await result.current.loadConversation(makeConversation({ id: "conv-after" }));
		});

		expect(result.current.conversationId).toBe("conv-after");
		expect(result.current.messages).toHaveLength(1);
		expect(result.current.loading).toBe(false);
	});
});
