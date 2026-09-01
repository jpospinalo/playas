import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	isRestTimeoutError,
	restErrorMessage,
	REST_TIMEOUT_MS,
	withRestTimeout,
} from "@/lib/httpTimeout";

describe("withRestTimeout — combina timeout y cancelación externa", () => {
	it("sin señal externa, retorna una señal aún no abortada", () => {
		const signal = withRestTimeout();
		expect(signal.aborted).toBe(false);
	});

	it("si la señal externa ya estaba abortada, la combinada también lo está de inmediato", () => {
		const controller = new AbortController();
		controller.abort();
		const signal = withRestTimeout(controller.signal);
		expect(signal.aborted).toBe(true);
	});

	it("si la señal externa se aborta después (antes del timeout), la combinada se aborta por esa razón, no por timeout", () => {
		const controller = new AbortController();
		const signal = withRestTimeout(controller.signal);
		expect(signal.aborted).toBe(false);
		controller.abort();
		expect(signal.aborted).toBe(true);
		expect(isRestTimeoutError(signal.reason)).toBe(false);
	});
});

describe("isRestTimeoutError", () => {
	it('true solo para el DOMException("TimeoutError") que produce AbortSignal.timeout', () => {
		expect(isRestTimeoutError(new DOMException("x", "TimeoutError"))).toBe(
			true,
		);
	});

	it("false para una cancelación deliberada (AbortError)", () => {
		expect(isRestTimeoutError(new DOMException("x", "AbortError"))).toBe(
			false,
		);
	});

	it("false para un error genérico o un valor que no es un error", () => {
		expect(isRestTimeoutError(new Error("boom"))).toBe(false);
		expect(isRestTimeoutError("boom")).toBe(false);
		expect(isRestTimeoutError(undefined)).toBe(false);
	});
});

describe("restErrorMessage — mensaje controlado en los límites de presentación", () => {
	it("un timeout local siempre se traduce al mismo mensaje breve en español, sin importar el `fallback`", () => {
		const timeoutError = new DOMException("The operation was aborted due to timeout", "TimeoutError");
		expect(restErrorMessage(timeoutError, "cualquier fallback")).toBe(
			"La solicitud tardó demasiado. Intenta nuevamente.",
		);
	});

	it("un `Error` que no es timeout conserva su propio mensaje", () => {
		expect(restErrorMessage(new Error("Error 404"), "fallback")).toBe(
			"Error 404",
		);
	});

	it("un valor que no es `Error` (ni timeout) usa el `fallback`", () => {
		expect(restErrorMessage("boom", "No fue posible completar la solicitud.")).toBe(
			"No fue posible completar la solicitud.",
		);
		expect(restErrorMessage(undefined, "fallback")).toBe("fallback");
	});

	it("una cancelación deliberada (AbortError) NO se traduce al mensaje de timeout — no es el caso que cubre esta función", () => {
		const abortError = new DOMException("Aborted", "AbortError");
		// `restErrorMessage` no decide si un AbortError debe mostrarse: cada
		// flujo cancelable lo filtra antes de llegar aquí (comprobando
		// `instanceof DOMException && name === "AbortError"`) y retorna en
		// silencio sin llegar a llamar a esta función. Esta prueba solo
		// confirma que, si llegara, en ningún caso se lo confunde con un
		// timeout ni produce el mensaje de timeout.
		const result = restErrorMessage(abortError, "fallback");
		expect(result).not.toBe("La solicitud tardó demasiado. Intenta nuevamente.");
	});
});

describe("withRestTimeout — comportamiento extremo a extremo con fetch (temporizadores simulados)", () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
	});

	it("una respuesta que llega antes del límite se resuelve con normalidad, y avanzar el tiempo después no tiene ningún efecto observable", async () => {
		const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
			expect(init?.signal?.aborted).toBe(false);
			return Promise.resolve(new Response("ok", { status: 200 }));
		});
		vi.stubGlobal("fetch", fetchMock);

		const res = await fetch("https://example.test/x", {
			signal: withRestTimeout(),
		});
		expect(res.status).toBe(200);

		// La operación ya terminó; que el límite "dispare" después no debe
		// producir ningún error ni reintento.
		await vi.advanceTimersByTimeAsync(REST_TIMEOUT_MS + 1000);
	});

	it("una operación que nunca resuelve se aborta al llegar al límite, y el error resultante es identificable como timeout", async () => {
		const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
			return new Promise((_resolve, reject) => {
				init?.signal?.addEventListener("abort", () => {
					reject(init.signal?.reason);
				});
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		let caught: unknown;
		const pending = fetch("https://example.test/x", {
			signal: withRestTimeout(),
		}).catch((error: unknown) => {
			caught = error;
		});

		await vi.advanceTimersByTimeAsync(REST_TIMEOUT_MS + 1);
		await pending;

		expect(isRestTimeoutError(caught)).toBe(true);
	});

	it("una cancelación externa antes del límite aborta con esa razón, no como timeout", async () => {
		const controller = new AbortController();
		const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
			return new Promise((_resolve, reject) => {
				init?.signal?.addEventListener("abort", () => {
					reject(init.signal?.reason);
				});
			});
		});
		vi.stubGlobal("fetch", fetchMock);

		let caught: unknown;
		const pending = fetch("https://example.test/x", {
			signal: withRestTimeout(controller.signal),
		}).catch((error: unknown) => {
			caught = error;
		});

		controller.abort();
		await pending;

		expect(isRestTimeoutError(caught)).toBe(false);
	});
});
