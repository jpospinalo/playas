import { afterEach, describe, expect, it, vi } from "vitest";

describe("hablar sin voz en español (QA-19)", () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.resetModules();
	});

	it("avisa en vez de leer con la voz por defecto del navegador", async () => {
		const speak = vi.fn();
		vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
		Object.defineProperty(window, "speechSynthesis", {
			configurable: true,
			value: {
				getVoices: () => [{ name: "Samantha", lang: "en-US", localService: true }],
				speak,
				cancel: vi.fn(),
				addEventListener: vi.fn(),
			},
		});
		const { hablar } = await import("@/lib/voz");
		await expect(hablar("Texto que no está grabado.")).rejects.toThrow("sin-espanol");
		expect(speak).not.toHaveBeenCalled();
	});
});
