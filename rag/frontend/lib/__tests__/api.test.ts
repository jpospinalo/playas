import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readErrorDetail, queryRagStream, throwIfSessionExpired } from "@/lib/api";
import { AUTH_SESSION_EXPIRED_EVENT } from "@/lib/auth";
import type { QueryRequest } from "@/lib/types";

/**
 * Pruebas de caracterización: fijan el contrato VIGENTE de `lib/api.ts`
 * como línea base de regresión. Deben seguir pasando sin modificarse pase
 * lo que pase con la implementación interna (extracción del parser SSE,
 * timeout REST, lectura unificada de errores, etc.) — no codifican ninguna
 * solución particular (CRLF, comentarios, timeout...), solo el contrato
 * observable que ya existe hoy.
 */

const TOKEN_KEY = "atlas_token";

beforeEach(() => {
	localStorage.setItem(TOKEN_KEY, "test-token");
});

afterEach(() => {
	localStorage.clear();
});

describe("throwIfSessionExpired — 401 expira la sesión; los demás códigos relevantes no", () => {
	it("401 dispara AUTH_SESSION_EXPIRED_EVENT, borra el token y lanza", async () => {
		const listener = vi.fn();
		window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
		try {
			const res = new Response(null, { status: 401 });
			await expect(throwIfSessionExpired(res, "test-token")).rejects.toThrow();
			expect(listener).toHaveBeenCalledTimes(1);
			expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
		} finally {
			window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
		}
	});

	it.each([403, 404, 409, 422, 429, 503, 504])(
		"%i no dispara AUTH_SESSION_EXPIRED_EVENT ni cierra la sesión",
		async (status) => {
			const listener = vi.fn();
			window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
			try {
				const res = new Response(null, { status });
				await expect(
					throwIfSessionExpired(res, "test-token"),
				).resolves.toBeUndefined();
				expect(listener).not.toHaveBeenCalled();
				expect(localStorage.getItem(TOKEN_KEY)).toBe("test-token");
			} finally {
				window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
			}
		},
	);
});

describe("readErrorDetail — lectura vigente del detalle de un error HTTP", () => {
	it("usa `detail` de un cuerpo JSON", async () => {
		const res = new Response(JSON.stringify({ detail: "Mensaje del servidor" }), {
			status: 400,
			headers: { "Content-Type": "application/json" },
		});
		await expect(readErrorDetail(res)).resolves.toBe("Mensaje del servidor");
	});

	it("cae a texto plano cuando el cuerpo no es JSON válido", async () => {
		const res = new Response("texto plano de error", { status: 500 });
		await expect(readErrorDetail(res)).resolves.toBe("texto plano de error");
	});

	it("cae al mensaje por código cuando el cuerpo está vacío", async () => {
		const res = new Response("", { status: 500 });
		await expect(readErrorDetail(res)).resolves.toBe("Error del servidor (500)");
	});
});

describe("queryRagStream — contrato vigente del parser SSE (casos ya soportados hoy)", () => {
	const QUESTION: QueryRequest = { question: "¿Qué dice la norma?" };

	function sseResponse(chunks: string[]): Response {
		const encoder = new TextEncoder();
		const stream = new ReadableStream<Uint8Array>({
			start(controller) {
				for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
				controller.close();
			},
		});
		return new Response(stream, { status: 200 });
	}

	async function collect(request: QueryRequest) {
		const events = [];
		for await (const event of queryRagStream(request)) {
			events.push(event);
		}
		return events;
	}

	it("un evento completo en un solo chunk, terminado en [DONE]", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse(['data: {"type":"token","content":"Hola"}\n\ndata: [DONE]\n\n']),
			),
		);
		try {
			await expect(collect(QUESTION)).resolves.toEqual([
				{ type: "token", content: "Hola" },
			]);
		} finally {
			vi.unstubAllGlobals();
		}
	});

	it("un evento dividido entre dos chunks, justo en el separador `\\n\\n`", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					'data: {"type":"token","content":"Hola"}',
					"\n\ndata: [DONE]\n\n",
				]),
			),
		);
		try {
			await expect(collect(QUESTION)).resolves.toEqual([
				{ type: "token", content: "Hola" },
			]);
		} finally {
			vi.unstubAllGlobals();
		}
	});

	it("varios eventos en un mismo chunk se emiten en orden", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					'data: {"type":"status","stage":"retrieving"}\n\n' +
						'data: {"type":"token","content":"a"}\n\n' +
						"data: [DONE]\n\n",
				]),
			),
		);
		try {
			await expect(collect(QUESTION)).resolves.toEqual([
				{ type: "status", stage: "retrieving" },
				{ type: "token", content: "a" },
			]);
		} finally {
			vi.unstubAllGlobals();
		}
	});
});
