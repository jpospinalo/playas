import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryRagStream } from "@/lib/api";

const sources = 'data: {"type":"sources","sources":[]}\n\n';
const token = 'data: {"type":"token","content":"Orden"}\n\n';
const status = 'data: {"type":"status","stage":"generating"}\n\n';
const failure = 'data: {"type":"error","detail":"Respuesta no disponible"}\n\n';
const done = "data: [DONE]\n\n";

beforeEach(() => localStorage.setItem("atlas_token", "test-token"));
afterEach(() => { localStorage.clear(); vi.unstubAllGlobals(); });

function mockResponse(chunks: Uint8Array[], finalError?: Error) {
	const read = vi.fn();
	for (const value of chunks) read.mockResolvedValueOnce({ done: false, value });
	if (finalError) read.mockRejectedValueOnce(finalError);
	else read.mockResolvedValue({ done: true });
	const cancel = vi.fn().mockResolvedValue(undefined);
	const releaseLock = vi.fn();
	vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
		status: 200, ok: true,
		body: { getReader: () => ({ read, cancel, releaseLock }) },
	} as unknown as Response));
	return { read, cancel, releaseLock };
}

function stream(text: string, finalError?: Error) {
	return mockResponse([new TextEncoder().encode(text)], finalError);
}

async function collect() {
	const events = [];
	for await (const event of queryRagStream({ question: "¿Qué ordenó?" })) events.push(event);
	return events;
}

describe("queryRagStream — completitud y orden de fuentes", () => {
	it.each([
		["DONE sin fuentes", done, /fuentes/],
		["tokens sin fuentes", token + done, /fuentes/],
		["fuentes posteriores a DONE", done + sources, /fuentes/],
		["fuentes duplicadas", sources + sources + done, /duplicadas/],
		["token posterior a fuentes", sources + token + done, /orden/],
		["progreso posterior a fuentes", sources + status + done, /orden/],
		["token posterior a error", failure + token + done, /orden/],
		["fuentes posteriores a error", failure + sources + done, /orden/],
	])("rechaza %s y libera la lectura", async (_name, payload, message) => {
		const reader = stream(payload);
		await expect(collect()).rejects.toThrow(message);
		expect(reader.cancel).toHaveBeenCalledTimes(1);
		expect(reader.releaseLock).toHaveBeenCalledTimes(1);
	});

	it("admite una lista de fuentes vacía y DONE sin cancelar", async () => {
		const reader = stream(sources + done);
		await expect(collect()).resolves.toEqual([{ type: "sources", sources: [] }]);
		expect(reader.cancel).not.toHaveBeenCalled();
		expect(reader.releaseLock).toHaveBeenCalledTimes(1);
	});

	it("conserva fuentes, métricas y orden de eventos", async () => {
		const event = { type: "sources", sources: [{ doc_id: "sentencia-A", fragments: [] }], context_tokens: 30, context_limit: 2048 };
		stream(status + token + `data: ${JSON.stringify(event)}\n\n` + done);
		await expect(collect()).resolves.toEqual([
			{ type: "status", stage: "generating" }, { type: "token", content: "Orden" }, event,
		]);
	});

	it("ignora comentarios y tipos desconocidos también después de las fuentes", async () => {
		stream(sources + ':ping\n\ndata: {"type":"heartbeat"}\n\n' + done);
		await expect(collect()).resolves.toEqual([{ type: "sources", sources: [] }]);
	});

	it("conserva UTF8 cuando una letra multibyte queda entre dos lecturas", async () => {
		const bytes = new TextEncoder().encode('data: {"type":"token","content":"acción"}\r\n\r\n' + sources + done);
		const split = bytes.indexOf(0xc3) + 1;
		mockResponse([bytes.slice(0, split), bytes.slice(split)]);
		await expect(collect()).resolves.toEqual([
			{ type: "token", content: "acción" }, { type: "sources", sources: [] },
		]);
	});

	it("no confunde fuentes sin DONE con un cierre completo", async () => {
		const reader = stream(sources);
		await expect(collect()).rejects.toThrow(/terminó de forma inesperada/);
		expect(reader.cancel).toHaveBeenCalledTimes(1);
		expect(reader.releaseLock).toHaveBeenCalledTimes(1);
	});

	it.each([failure + done, sources + failure + done])("mantiene el error visible sin exigir fuentes de éxito", async (payload) => {
		stream(payload);
		const events = await collect();
		expect(events.at(-1)).toEqual({ type: "error", detail: "Respuesta no disponible" });
	});

	it("conserva la cancelación original al esperar DONE después de las fuentes", async () => {
		const abort = new DOMException("Aborted", "AbortError");
		const reader = stream(sources, abort);
		await expect(collect()).rejects.toBe(abort);
		expect(reader.cancel).toHaveBeenCalledTimes(1);
		expect(reader.releaseLock).toHaveBeenCalledTimes(1);
	});

	it("entrega error antes del EOF y permite que el consumidor cancele", async () => {
		const reader = stream(failure);
		const generator = queryRagStream({ question: "¿Qué ordenó?" });
		await expect(generator.next()).resolves.toEqual({ done: false, value: { type: "error", detail: "Respuesta no disponible" } });
		await generator.return(undefined);
		expect(reader.cancel).toHaveBeenCalledTimes(1);
		expect(reader.releaseLock).toHaveBeenCalledTimes(1);
	});
});
