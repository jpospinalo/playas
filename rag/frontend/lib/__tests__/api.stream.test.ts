import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryRagStream } from "@/lib/api";
import type { QueryRequest } from "@/lib/types";

/**
 * Pruebas de integración de `queryRagStream` con el parser SSE de
 * `lib/sseParser.ts`. A diferencia de `lib/__tests__/api.test.ts` (que
 * caracteriza el contrato YA existente y no debe modificarse), estos casos
 * son justamente los que un parser ingenuo (`buffer.split("\n\n")`, una
 * sola línea `data:` por bloque, sin soporte de CRLF/comentarios) no
 * soportaría — demuestran el comportamiento robusto del parser actual.
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

describe("queryRagStream — casos que el parser SSE ingenuo anterior no soportaba", () => {
	it("un stream con CRLF (`\\r\\n`) en vez de `\\n` se interpreta igual", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					'data: {"type":"token","content":"Hola"}\r\n\r\ndata: [DONE]\r\n\r\n',
				]),
			),
		);
		await expect(collect(QUESTION)).resolves.toEqual([
			{ type: "token", content: "Hola" },
		]);
	});

	it("líneas de comentario/keep-alive (`:...`) entre eventos se ignoran sin romper el stream", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					':ping\n\ndata: {"type":"token","content":"Hola"}\n\n:ping\n\ndata: [DONE]\n\n',
				]),
			),
		);
		await expect(collect(QUESTION)).resolves.toEqual([
			{ type: "token", content: "Hola" },
		]);
	});

	it("varias líneas `data:` en un mismo evento se concatenan con `\\n` antes de parsear el JSON", async () => {
		const payload = '{"type":"error",\n"detail":"línea partida"}';
		const [firstHalf, secondHalf] = [
			payload.slice(0, payload.indexOf("\n") + 1),
			payload.slice(payload.indexOf("\n") + 1),
		];
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					`data: ${firstHalf}data: ${secondHalf}\n\ndata: [DONE]\n\n`,
				]),
			),
		);
		await expect(collect(QUESTION)).resolves.toEqual([
			{ type: "error", detail: "línea partida" },
		]);
	});

	it("un evento de tipo desconocido se ignora sin romper el stream ni el resto de eventos", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					'data: {"type":"heartbeat","ping":true}\n\n' +
						'data: {"type":"token","content":"Hola"}\n\n' +
						"data: [DONE]\n\n",
				]),
			),
		);
		await expect(collect(QUESTION)).resolves.toEqual([
			{ type: "token", content: "Hola" },
		]);
	});

	it("un evento `error` válido llega al frontend como un StreamEvent de tipo error, no como excepción", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse([
					'data: {"type":"error","detail":"el LLM no respondió"}\n\ndata: [DONE]\n\n',
				]),
			),
		);
		await expect(collect(QUESTION)).resolves.toEqual([
			{ type: "error", detail: "el LLM no respondió" },
		]);
	});

	it("JSON inválido en un evento produce un error controlado y legible, no una excepción críptica", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(sseResponse(["data: {esto no es json\n\n"])),
		);
		await expect(collect(QUESTION)).rejects.toThrow(/formato inválido/);
	});

	it("la conexión cerrada antes de `[DONE]` sigue produciendo un error visible (comportamiento preexistente, sin cambios)", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue(
				sseResponse(['data: {"type":"token","content":"Hola"}\n\n']),
			),
		);
		await expect(collect(QUESTION)).rejects.toThrow(
			/terminó de forma inesperada/,
		);
	});
});
