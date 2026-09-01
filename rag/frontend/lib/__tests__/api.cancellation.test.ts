import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryRagStream } from "@/lib/api";
import type { QueryRequest } from "@/lib/types";

/**
 * Pruebas de la semántica de cancelación del reader en `queryRagStream`:
 * distingue cierre normal, cancelación y error, sin que un fallo de
 * `reader.cancel()` enmascare el error real.
 *
 * Usan un `Response`/reader completamente simulados (no un `ReadableStream`
 * real) porque lo que estas pruebas verifican es el manejo del propio
 * `ReadableStreamDefaultReader` — cuándo se llama `reader.cancel()`, cuándo
 * NO, y que un fallo de `cancel()` nunca reemplace el error real — no el
 * parseo SSE en sí (ya cubierto en `sseParser.test.ts` y
 * `api.stream.test.ts`).
 */

const TOKEN_KEY = "atlas_token";

beforeEach(() => {
	localStorage.setItem(TOKEN_KEY, "test-token");
});

afterEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
});

const QUESTION: QueryRequest = { question: "¿Qué dice la norma?" };

type ReadResult = { done: boolean; value?: Uint8Array };

function encode(text: string): Uint8Array {
	return new TextEncoder().encode(text);
}

/** Construye un `Response` simulado cuyo reader se controla completamente desde la prueba. */
function mockStreamResponse(options: {
	read: () => Promise<ReadResult>;
	cancelImpl?: () => Promise<void> | void;
}) {
	const cancelSpy = vi.fn(async () => {
		await options.cancelImpl?.();
	});
	const releaseLockSpy = vi.fn();
	const res = {
		status: 200,
		ok: true,
		body: {
			getReader: () => ({
				read: options.read,
				cancel: cancelSpy,
				releaseLock: releaseLockSpy,
			}),
		},
	} as unknown as Response;
	return { res, cancelSpy, releaseLockSpy };
}

async function collectAll(request: QueryRequest) {
	const events = [];
	for await (const event of queryRagStream(request)) {
		events.push(event);
	}
	return events;
}

describe("queryRagStream — cancelación del reader", () => {
	it("una terminación normal ([DONE]) NO cancela el reader, solo libera el lock", async () => {
		const read = vi
			.fn()
			.mockResolvedValueOnce({ done: false, value: encode("data: [DONE]\n\n") });
		const { res, cancelSpy, releaseLockSpy } = mockStreamResponse({ read });
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

		await expect(collectAll(QUESTION)).resolves.toEqual([]);

		expect(cancelSpy).not.toHaveBeenCalled();
		expect(releaseLockSpy).toHaveBeenCalledTimes(1);
	});

	it("un abort externo (reader.read() rechaza con AbortError) cancela el reader y preserva el AbortError original", async () => {
		const abortError = new DOMException(
			"The user aborted a request.",
			"AbortError",
		);
		const read = vi.fn().mockRejectedValueOnce(abortError);
		const { res, cancelSpy, releaseLockSpy } = mockStreamResponse({ read });
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

		await expect(collectAll(QUESTION)).rejects.toBe(abortError);

		expect(cancelSpy).toHaveBeenCalledTimes(1);
		expect(releaseLockSpy).toHaveBeenCalledTimes(1);
	});

	it("un intento de parseo inválido cancela el reader y preserva el error de parseo original", async () => {
		const read = vi
			.fn()
			.mockResolvedValueOnce({ done: false, value: encode("data: {esto no es json\n\n") });
		const { res, cancelSpy, releaseLockSpy } = mockStreamResponse({ read });
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

		await expect(collectAll(QUESTION)).rejects.toThrow(/formato inválido/);

		expect(cancelSpy).toHaveBeenCalledTimes(1);
		expect(releaseLockSpy).toHaveBeenCalledTimes(1);
	});

	it("si reader.cancel() también falla, el error visible sigue siendo el original, no el de cancel()", async () => {
		const read = vi
			.fn()
			.mockResolvedValueOnce({ done: false, value: encode("data: {esto no es json\n\n") });
		const { res, cancelSpy, releaseLockSpy } = mockStreamResponse({
			read,
			cancelImpl: () => {
				throw new Error("cancel() explotó");
			},
		});
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

		await expect(collectAll(QUESTION)).rejects.toThrow(/formato inválido/);

		expect(cancelSpy).toHaveBeenCalledTimes(1);
		expect(releaseLockSpy).toHaveBeenCalledTimes(1);
	});

	it("un cierre prematuro (done sin [DONE]) produce el error visible existente, libera el lock, e intenta cancelar sin lanzar una segunda excepción", async () => {
		const read = vi.fn().mockResolvedValueOnce({ done: true });
		const { res, cancelSpy, releaseLockSpy } = mockStreamResponse({ read });
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

		await expect(collectAll(QUESTION)).rejects.toThrow(
			/terminó de forma inesperada/,
		);

		expect(cancelSpy).toHaveBeenCalledTimes(1);
		expect(releaseLockSpy).toHaveBeenCalledTimes(1);
	});

	it("si el consumidor abandona el generador antes de [DONE] (p. ej. Detener), se cancela el reader sin producir un error visible", async () => {
		const read = vi.fn().mockResolvedValueOnce({
			done: false,
			value: encode('data: {"type":"token","content":"a"}\n\n'),
		});
		const { res, cancelSpy, releaseLockSpy } = mockStreamResponse({ read });
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res));

		const generator = queryRagStream(QUESTION);
		const first = await generator.next();
		expect(first).toEqual({
			done: false,
			value: { type: "token", content: "a" },
		});

		await expect(generator.return(undefined)).resolves.toEqual({
			done: true,
			value: undefined,
		});

		expect(cancelSpy).toHaveBeenCalledTimes(1);
		expect(releaseLockSpy).toHaveBeenCalledTimes(1);
	});
});
