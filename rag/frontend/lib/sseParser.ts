import type {
	AgentStage,
	QueryRoute,
	SourceGroup,
	StreamEvent,
} from "@/lib/types";

/**
 * Reensamblado y parseo de eventos SSE (Server-Sent Events) del stream
 * `/api/query/stream`. Extraído de `queryRagStream` (`lib/api.ts`) para
 * poder probarlo de forma aislada y para que soporte, sin cambiar ningún
 * evento ni el terminador `[DONE]` que el backend ya emite hoy:
 *
 *  - separadores de línea `\n`, `\r\n` y `\r` (incluso mezclados dentro de
 *    un mismo stream), sin depender de que los chunks respeten los límites
 *    de línea o de bloque;
 *  - líneas de comentario SSE (`:...`), ignoradas;
 *  - varias líneas `data:` dentro de un mismo bloque, concatenadas con `\n`
 *    (regla del estándar SSE, no algo específico de este backend);
 *  - campos SSE distintos de `data` (desconocidos), ignorados sin error;
 *  - un espacio opcional después de `data:` (`data: x` y `data:x` son
 *    equivalentes; solo se recorta como máximo un espacio, por el estándar).
 *
 * La validación de cada evento ya reensamblado es deliberadamente mínima:
 * el objetivo es distinguir "este evento no se puede interpretar" (error
 * controlado, nunca datos a medias) de "este evento no se reconoce, pero el
 * stream sigue" (se ignora en silencio) — no reconstruir en tiempo de
 * ejecución los tipos de `lib/types.ts` ni validar metadata anidada.
 */

/** Un bloque SSE ya reensamblado: solo conserva el contenido `data:` unido. */
export interface RawSseEvent {
	data: string;
}

/** Sentinela para el terminador `[DONE]`, preservado tal cual llega hoy. */
export const SSE_DONE = Symbol("SSE_DONE");

/**
 * Reensambla texto ya decodificado (no bytes) en bloques SSE completos,
 * agnóstico a dónde caigan los cortes de chunk — incluso a mitad de un
 * separador de línea (p. ej. un `\r` como último carácter de un chunk,
 * seguido de `\n` al inicio del siguiente). Quien lo use decide cómo
 * decodificar los bytes (p. ej. `TextDecoder` en modo streaming, que ya
 * maneja correctamente caracteres multibyte partidos entre chunks) antes de
 * llamar a `push`.
 */
export class SseEventAccumulator {
	private buffer = "";
	private currentLines: string[] = [];

	/** Añade texto decodificado y retorna los bloques `data:` completos que se puedan reensamblar con lo ya recibido. */
	push(chunk: string): RawSseEvent[] {
		this.buffer += chunk;
		return this.consumeLines();
	}

	private consumeLines(): RawSseEvent[] {
		const events: RawSseEvent[] = [];
		let pos = 0;
		while (true) {
			const found = this.findLineBreak(pos);
			if (!found) break;
			const line = this.buffer.slice(pos, found.lineEnd);
			pos = found.nextPos;
			if (line === "") {
				const event = this.finalizeBlock();
				if (event) events.push(event);
			} else {
				this.currentLines.push(line);
			}
		}
		this.buffer = this.buffer.slice(pos);
		return events;
	}

	/**
	 * Busca el próximo salto de línea a partir de `pos`, reconociendo `\n`,
	 * `\r\n` y `\r` como un único salto. Si el único candidato visible es un
	 * `\r` justo al final de lo recibido hasta ahora, no lo resuelve todavía
	 * (podría ser la primera mitad de un `\r\n` partido entre chunks) — esa
	 * porción queda en el buffer para la próxima llamada a `push`.
	 */
	private findLineBreak(
		pos: number,
	): { lineEnd: number; nextPos: number } | null {
		for (let i = pos; i < this.buffer.length; i++) {
			const ch = this.buffer[i];
			if (ch === "\n") return { lineEnd: i, nextPos: i + 1 };
			if (ch === "\r") {
				if (i + 1 < this.buffer.length) {
					const isCrlf = this.buffer[i + 1] === "\n";
					return { lineEnd: i, nextPos: i + (isCrlf ? 2 : 1) };
				}
				return null;
			}
		}
		return null;
	}

	private finalizeBlock(): RawSseEvent | null {
		const lines = this.currentLines;
		this.currentLines = [];
		if (lines.length === 0) return null;

		const dataLines: string[] = [];
		for (const line of lines) {
			if (line.startsWith(":")) continue; // línea de comentario/keep-alive
			const colonIdx = line.indexOf(":");
			const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
			if (field !== "data") continue; // campo SSE distinto de `data`, ignorado

			let value = colonIdx === -1 ? "" : line.slice(colonIdx + 1);
			if (value.startsWith(" ")) value = value.slice(1);
			dataLines.push(value);
		}
		if (dataLines.length === 0) return null; // bloque sin ninguna línea `data:` útil

		return { data: dataLines.join("\n") };
	}
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null;
}

const KNOWN_STAGES: readonly AgentStage[] = [
	"enriching",
	"retrieving",
	"generating",
];

const INVALID_EVENT_MESSAGE =
	"El servidor envió un evento de streaming con formato inválido.";

/**
 * Convierte un `RawSseEvent` ya reensamblado en un `StreamEvent` tipado, en
 * el sentinela `SSE_DONE`, o en `null` si el `type` no se reconoce (se
 * ignora sin romper el stream). Lanza un `Error` controlado y legible si el
 * `data` no es JSON válido, o si un `type` SÍ reconocido no trae los campos
 * escalares indispensables — nunca acepta ni entrega datos a medias.
 */
export function parseStreamEvent(
	raw: RawSseEvent,
): StreamEvent | typeof SSE_DONE | null {
	if (raw.data === "[DONE]") return SSE_DONE;

	let parsed: unknown;
	try {
		parsed = JSON.parse(raw.data);
	} catch {
		throw new Error(INVALID_EVENT_MESSAGE);
	}
	if (!isRecord(parsed)) {
		throw new Error(INVALID_EVENT_MESSAGE);
	}

	switch (parsed.type) {
		case "token": {
			if (typeof parsed.content !== "string") {
				throw new Error(INVALID_EVENT_MESSAGE);
			}
			return { type: "token", content: parsed.content };
		}
		case "status": {
			if (
				typeof parsed.stage !== "string" ||
				!KNOWN_STAGES.includes(parsed.stage as AgentStage)
			) {
				throw new Error(INVALID_EVENT_MESSAGE);
			}
			const event: Extract<StreamEvent, { type: "status" }> = {
				type: "status",
				stage: parsed.stage as AgentStage,
			};
			if (typeof parsed.message === "string") event.message = parsed.message;
			return event;
		}
		case "sources": {
			if (!Array.isArray(parsed.sources)) {
				throw new Error(INVALID_EVENT_MESSAGE);
			}
			const event: Extract<StreamEvent, { type: "sources" }> = {
				type: "sources",
				sources: parsed.sources as SourceGroup[],
			};
			if (
				typeof parsed.enriched_query === "string" ||
				parsed.enriched_query === null
			) {
				event.enriched_query = parsed.enriched_query;
			}
			if (
				typeof parsed.query_route === "string" ||
				parsed.query_route === null
			) {
				event.query_route = parsed.query_route as QueryRoute | null;
			}
			if (typeof parsed.context_tokens === "number") {
				event.context_tokens = parsed.context_tokens;
			}
			if (typeof parsed.context_limit === "number") {
				event.context_limit = parsed.context_limit;
			}
			return event;
		}
		case "error": {
			if (typeof parsed.detail !== "string") {
				throw new Error(INVALID_EVENT_MESSAGE);
			}
			return { type: "error", detail: parsed.detail };
		}
		default:
			// Tipo no reconocido: se ignora, no rompe el stream.
			return null;
	}
}
