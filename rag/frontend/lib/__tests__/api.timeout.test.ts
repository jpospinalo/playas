import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	createAdminUser,
	listAdminUsers,
	submitConversationFeedback,
	submitMessageFeedback,
	updateAdminUserPassword,
} from "@/lib/api";

/**
 * Verifica que las operaciones REST finitas de `lib/api.ts` (feedback y
 * administración) efectivamente pasan una señal producida por
 * `withRestTimeout` a `fetch`. El comportamiento del propio límite (cuándo
 * se cumple, cómo se distingue de una cancelación externa, etc.) ya está
 * cubierto de forma exhaustiva en `httpTimeout.test.ts`; esto solo confirma
 * el cableado en cada sitio de llamada.
 */

const TOKEN_KEY = "atlas_token";

beforeEach(() => {
	localStorage.setItem(TOKEN_KEY, "test-token");
});

afterEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
});

function okJson(body: unknown) {
	return new Response(JSON.stringify(body), {
		status: 200,
		headers: { "Content-Type": "application/json" },
	});
}

describe("lib/api.ts — cada operación REST finita pasa una señal de withRestTimeout a fetch", () => {
	it("submitConversationFeedback", async () => {
		const fetchMock = vi.fn().mockResolvedValue(okJson({ id: "1" }));
		vi.stubGlobal("fetch", fetchMock);

		await submitConversationFeedback({
			ratings: { tone: 5, length: 5, usability: 5, overall: 5 },
		});

		const init = fetchMock.mock.calls[0][1] as RequestInit;
		expect(init.signal).toBeInstanceOf(AbortSignal);
	});

	it("submitMessageFeedback", async () => {
		const fetchMock = vi.fn().mockResolvedValue(okJson({ id: "1" }));
		vi.stubGlobal("fetch", fetchMock);

		await submitMessageFeedback({
			conversation_id: "c1",
			message_id: "m1",
			ratings: { pertinence: 5, accuracy: 5 },
		});

		const init = fetchMock.mock.calls[0][1] as RequestInit;
		expect(init.signal).toBeInstanceOf(AbortSignal);
	});

	it("listAdminUsers", async () => {
		const fetchMock = vi.fn().mockResolvedValue(okJson({ items: [], total: 0 }));
		vi.stubGlobal("fetch", fetchMock);

		await listAdminUsers();

		const init = fetchMock.mock.calls[0][1] as RequestInit;
		expect(init.signal).toBeInstanceOf(AbortSignal);
	});

	it("createAdminUser", async () => {
		const fetchMock = vi.fn().mockResolvedValue(
			okJson({
				uid: "u1",
				email: "a@b.com",
				displayName: null,
				role: "admin",
				createdAt: "2026-01-01",
			}),
		);
		vi.stubGlobal("fetch", fetchMock);

		await createAdminUser({ email: "a@b.com", password: "x" });

		const init = fetchMock.mock.calls[0][1] as RequestInit;
		expect(init.signal).toBeInstanceOf(AbortSignal);
	});

	it("updateAdminUserPassword", async () => {
		const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		await updateAdminUserPassword("u1", "x");

		const init = fetchMock.mock.calls[0][1] as RequestInit;
		expect(init.signal).toBeInstanceOf(AbortSignal);
	});

	it("queryRagStream NO recibe una señal combinada con timeout — conserva únicamente la que ya recibía", async () => {
		// Import dinámico para no repetir el mock de fetch de otros escenarios
		// de este archivo dentro del módulo compartido.
		const { queryRagStream } = await import("@/lib/api");
		const encoder = new TextEncoder();
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				controller.enqueue(encoder.encode("data: [DONE]\n\n"));
				controller.close();
			},
		});
		const fetchMock = vi.fn().mockResolvedValue(new Response(stream, { status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		const events = [];
		for await (const event of queryRagStream({ question: "¿x?" })) {
			events.push(event);
		}

		const init = fetchMock.mock.calls[0][1] as RequestInit;
		// Sin `signal` explícita en la llamada, no hay señal en absoluto —
		// `queryRagStream` queda deliberadamente fuera del timeout común.
		expect(init.signal).toBeUndefined();
		expect(events).toEqual([]);
	});
});
