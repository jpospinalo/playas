import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	createAdminUser,
	listAdminUsers,
	submitConversationFeedback,
	submitMessageFeedback,
} from "@/lib/api";
import {
	AUTH_SESSION_EXPIRED_EVENT,
	clearAuth,
	expireAuthSession,
} from "@/lib/auth";
import { isRestTimeoutError } from "@/lib/httpTimeout";

/**
 * Matriz frontend-API de escenarios de error. Antes de escribir este
 * archivo se revisó qué de la lista ya estaba cubierto, para no duplicar:
 *  - 401/403/404/409/422/429/503/504 "no cierran la sesión salvo 401" ya
 *    está cubierto de forma exhaustiva (`it.each`) en
 *    `lib/__tests__/api.test.ts` (caracterización de `throwIfSessionExpired`
 *    — no se toca).
 *  - cuerpo no-JSON / demasiado largo / HTML de un proxy ya está cubierto
 *    en `lib/__tests__/readErrorDetail.test.ts`.
 *  - cierre prematuro del SSE y evento `error` de SSE:
 *    `api.stream.test.ts` y `api.cancellation.test.ts`.
 *  - cancelación del usuario: `api.cancellation.test.ts`,
 *    `useChat.cancel.test.ts`.
 *  - cambio de conversación durante el streaming:
 *    `useChat.ownership.test.ts` ("seleccionar la conversación B durante el
 *    streaming de A...").
 *  - persistencia de respuesta fallida con reintento manual:
 *    `useChat.persistence.test.ts`.
 *
 * Lo que sigue cubre los huecos reales que quedaban sin ninguna prueba
 * directa: que la sesión expira UNA sola vez (no una vez por cada 401
 * concurrente), que un 504 real del backend nunca se confunde con el
 * timeout local de `withRestTimeout`, un error de red sin respuesta en
 * absoluto, y que ningún sitio de llamada (salvo `persistMessage`, ya
 * documentado como excepción deliberada) reintenta automáticamente ante
 * 429/503/504.
 */

const TOKEN_KEY = "atlas_token";

beforeEach(() => {
	localStorage.setItem(TOKEN_KEY, "test-token");
});

afterEach(() => {
	localStorage.clear();
	vi.unstubAllGlobals();
});

describe("expireAuthSession — la sesión expira una sola vez, no una vez por cada 401 concurrente", () => {
	it("dos 401 concurrentes para el mismo token disparan el evento una sola vez", () => {
		const listener = vi.fn();
		window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
		try {
			const firedFirst = expireAuthSession("test-token");
			const firedSecond = expireAuthSession("test-token");

			expect(firedFirst).toBe(true);
			expect(firedSecond).toBe(false);
			expect(listener).toHaveBeenCalledTimes(1);
			expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
		} finally {
			window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
		}
	});

	it("un 401 tardío de un token ya reemplazado por una sesión nueva no cierra la sesión activa", () => {
		clearAuth();
		localStorage.setItem(TOKEN_KEY, "token-nuevo");
		const listener = vi.fn();
		window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
		try {
			// Un 401 tardío de una solicitud lanzada con el token ANTERIOR.
			const fired = expireAuthSession("token-viejo");

			expect(fired).toBe(false);
			expect(listener).not.toHaveBeenCalled();
			expect(localStorage.getItem(TOKEN_KEY)).toBe("token-nuevo");
		} finally {
			window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, listener);
		}
	});
});

describe("504 del backend vs. timeout local — nunca se confunden", () => {
	it("un 504 real (respuesta HTTP recibida) no es un timeout de withRestTimeout", async () => {
		const fetchMock = vi
			.fn()
			.mockResolvedValue(new Response("", { status: 504 }));
		vi.stubGlobal("fetch", fetchMock);

		let caught: unknown;
		try {
			await submitConversationFeedback({
				ratings: { tone: 5, length: 5, usability: 5, overall: 5 },
			});
		} catch (err) {
			caught = err;
		}

		expect(caught).toBeInstanceOf(Error);
		expect((caught as Error).message).toMatch(/Error del servidor \(504\)/);
		// El error es el del servidor, no un DOMException("TimeoutError") —
		// nunca podría confundirse con el timeout de 60s del cliente.
		expect(isRestTimeoutError(caught)).toBe(false);
	});
});

describe("error de red sin ninguna respuesta (fetch rechaza directamente)", () => {
	it("un fetch que rechaza (sin Response, p. ej. sin conexión) se propaga como un error real, no como éxito ni como timeout", async () => {
		const networkError = new TypeError("Failed to fetch");
		const fetchMock = vi.fn().mockRejectedValue(networkError);
		vi.stubGlobal("fetch", fetchMock);

		await expect(
			submitMessageFeedback({
				conversation_id: "c1",
				message_id: "m1",
				ratings: { pertinence: 5, accuracy: 5 },
			}),
		).rejects.toBe(networkError);

		expect(isRestTimeoutError(networkError)).toBe(false);
	});
});

describe("429/503/504 nunca se reintentan automáticamente en el cliente", () => {
	it.each([429, 503, 504])(
		"un %i en submitConversationFeedback dispara fetch exactamente una vez, con un error visible",
		async (status) => {
			const fetchMock = vi
				.fn()
				.mockResolvedValue(new Response("", { status }));
			vi.stubGlobal("fetch", fetchMock);

			await expect(
				submitConversationFeedback({
					ratings: { tone: 5, length: 5, usability: 5, overall: 5 },
				}),
			).rejects.toThrow(new RegExp(`Error del servidor \\(${status}\\)`));

			expect(fetchMock).toHaveBeenCalledTimes(1);
		},
	);

	it.each([429, 503, 504])(
		"un %i en listAdminUsers dispara fetch exactamente una vez, con un error visible",
		async (status) => {
			const fetchMock = vi
				.fn()
				.mockResolvedValue(new Response("", { status }));
			vi.stubGlobal("fetch", fetchMock);

			await expect(listAdminUsers()).rejects.toThrow(
				new RegExp(`Error del servidor \\(${status}\\)`),
			);
			expect(fetchMock).toHaveBeenCalledTimes(1);
		},
	);

	it.each([429, 503, 504])(
		"un %i en createAdminUser dispara fetch exactamente una vez, con un error visible",
		async (status) => {
			const fetchMock = vi
				.fn()
				.mockResolvedValue(new Response("", { status }));
			vi.stubGlobal("fetch", fetchMock);

			await expect(
				createAdminUser({ email: "a@b.com", password: "x" }),
			).rejects.toThrow(new RegExp(`Error del servidor \\(${status}\\)`));
			expect(fetchMock).toHaveBeenCalledTimes(1);
		},
	);
});
