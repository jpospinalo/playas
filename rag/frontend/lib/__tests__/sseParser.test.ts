import { describe, expect, it } from "vitest";
import {
	SSE_DONE,
	SseEventAccumulator,
	parseStreamEvent,
	type RawSseEvent,
} from "@/lib/sseParser";

/**
 * Pruebas directas del reensamblador/parser SSE. Cubren los casos que un
 * parser ingenuo (`buffer.split("\n\n")` dentro
 * de `queryRagStream`) no soportaba CRLF/`\r`, comentarios, ni varias
 * líneas `data:` por bloque — estos casos habrían fallado contra ese código
 * y ahora deben pasar contra el módulo extraído.
 */

function pushAll(acc: SseEventAccumulator, chunks: string[]): RawSseEvent[] {
	const events: RawSseEvent[] = [];
	for (const chunk of chunks) events.push(...acc.push(chunk));
	return events;
}

describe("SseEventAccumulator — reensamblado de bloques SSE", () => {
	it("un evento completo en un solo chunk", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, [
			'data: {"type":"token","content":"Hola"}\n\n',
		]);
		expect(events).toEqual([{ data: '{"type":"token","content":"Hola"}' }]);
	});

	it("el mismo evento partido en cada posición crítica produce el mismo resultado", () => {
		const full = 'data: {"type":"token","content":"Hola"}\n\ndata: [DONE]\n\n';
		for (let i = 1; i < full.length; i++) {
			const acc = new SseEventAccumulator();
			const events = pushAll(acc, [full.slice(0, i), full.slice(i)]);
			expect(events, `corte en la posición ${i}`).toEqual([
				{ data: '{"type":"token","content":"Hola"}' },
				{ data: "[DONE]" },
			]);
		}
	});

	it("dos eventos en un mismo chunk se reensamblan en orden", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, [
			'data: {"type":"status","stage":"retrieving"}\n\n' +
				'data: {"type":"token","content":"a"}\n\n',
		]);
		expect(events).toEqual([
			{ data: '{"type":"status","stage":"retrieving"}' },
			{ data: '{"type":"token","content":"a"}' },
		]);
	});

	it("acepta CRLF, CR solo, y estilos de línea mezclados dentro del mismo bloque", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, [
			'data: {"type":"token","content":"a"}\r\n\r\n' +
				'data: {"type":"token","content":"b"}\r\r' +
				'data: {"type":"token","content":"c"}\n\n',
		]);
		expect(events).toEqual([
			{ data: '{"type":"token","content":"a"}' },
			{ data: '{"type":"token","content":"b"}' },
			{ data: '{"type":"token","content":"c"}' },
		]);
	});

	it("un `\\r` como último carácter del chunk no se resuelve hasta ver el siguiente chunk (posible `\\r\\n` partido)", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, [
			'data: {"type":"token","content":"a"}\r',
			'\n\n',
		]);
		expect(events).toEqual([{ data: '{"type":"token","content":"a"}' }]);
	});

	it("ignora líneas de comentario/keep-alive (prefijo `:`) sin producir un evento vacío", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, [
			":ping\n\n" + 'data: {"type":"token","content":"a"}\n\n',
		]);
		expect(events).toEqual([{ data: '{"type":"token","content":"a"}' }]);
	});

	it("ignora campos SSE distintos de `data` sin romper el bloque", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, [
			'event: message\nretry: 3000\ndata: {"type":"token","content":"a"}\n\n',
		]);
		expect(events).toEqual([{ data: '{"type":"token","content":"a"}' }]);
	});

	it("concatena varias líneas `data:` de un mismo bloque con `\\n`", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, ["data: línea1\ndata: línea2\n\n"]);
		expect(events).toEqual([{ data: "línea1\nlínea2" }]);
	});

	it("recorta como máximo un espacio después de `data:`", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, ["data: x\n\n", "data:y\n\n", "data:  z\n\n"]);
		expect(events).toEqual([{ data: "x" }, { data: "y" }, { data: " z" }]);
	});

	it("`[DONE]` fragmentado entre varios chunks se reensambla igual que cualquier otro dato", () => {
		const acc = new SseEventAccumulator();
		const events = pushAll(acc, ["data: [DO", "NE]\n", "\n"]);
		expect(events).toEqual([{ data: "[DONE]" }]);
	});

	it("un carácter multibyte partido entre chunks de bytes se reensambla correctamente (vía TextDecoder en modo streaming)", () => {
		const acc = new SseEventAccumulator();
		const encoder = new TextEncoder();
		const decoder = new TextDecoder();
		const bytes = encoder.encode(
			'data: {"type":"token","content":"§ñ"}\n\n',
		);
		const events: RawSseEvent[] = [];
		// Corta a la mitad, muy probablemente a mitad de un carácter multibyte.
		const mid = Math.floor(bytes.length / 2);
		events.push(
			...acc.push(decoder.decode(bytes.slice(0, mid), { stream: true })),
		);
		events.push(...acc.push(decoder.decode(bytes.slice(mid))));
		expect(events).toEqual([
			{ data: '{"type":"token","content":"§ñ"}' },
		]);
	});
});

describe("parseStreamEvent — interpretación de un bloque ya reensamblado", () => {
	it("`[DONE]` produce el sentinela SSE_DONE", () => {
		expect(parseStreamEvent({ data: "[DONE]" })).toBe(SSE_DONE);
	});

	it("JSON inválido lanza un error controlado y legible", () => {
		expect(() => parseStreamEvent({ data: "{no es json" })).toThrow(
			/formato inválido/,
		);
	});

	it("un valor JSON que no es un objeto lanza un error controlado", () => {
		expect(() => parseStreamEvent({ data: "42" })).toThrow(/formato inválido/);
		expect(() => parseStreamEvent({ data: "null" })).toThrow(
			/formato inválido/,
		);
	});

	it("un evento `error` válido se interpreta tal cual", () => {
		expect(
			parseStreamEvent({ data: '{"type":"error","detail":"algo falló"}' }),
		).toEqual({ type: "error", detail: "algo falló" });
	});

	it("un evento `token` sin `content` (tipo conocido, forma inválida) lanza un error controlado", () => {
		expect(() =>
			parseStreamEvent({ data: '{"type":"token"}' }),
		).toThrow(/formato inválido/);
	});

	it("un evento `status` con `stage` desconocido lanza un error controlado", () => {
		expect(() =>
			parseStreamEvent({ data: '{"type":"status","stage":"volando"}' }),
		).toThrow(/formato inválido/);
	});

	it("un `type` no reconocido se ignora (retorna null) sin lanzar, sin romper el stream", () => {
		expect(
			parseStreamEvent({ data: '{"type":"heartbeat","ping":true}' }),
		).toBeNull();
	});

	it("un evento `sources` válido conserva sus campos opcionales presentes y omite los ausentes", () => {
		const result = parseStreamEvent({
			data: JSON.stringify({
				type: "sources",
				sources: [],
				query_route: "in_scope",
				context_tokens: 120,
			}),
		});
		expect(result).toEqual({
			type: "sources",
			sources: [],
			query_route: "in_scope",
			context_tokens: 120,
		});
	});
});
