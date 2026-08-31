import { describe, expect, it } from "vitest";
import { normalizeApiUrl } from "@/lib/config";

describe("normalizeApiUrl (A1)", () => {
	it("usa el fallback de desarrollo cuando la variable no está definida", () => {
		expect(normalizeApiUrl(undefined)).toBe("http://localhost:8080");
	});

	it("conserva la cadena vacía en vez de caer al fallback (despliegue con rutas relativas)", () => {
		expect(normalizeApiUrl("")).toBe("");
	});

	it("retira una barra final redundante de una URL absoluta", () => {
		expect(normalizeApiUrl("https://api.example.com/")).toBe(
			"https://api.example.com",
		);
	});

	it("retira varias barras finales redundantes", () => {
		expect(normalizeApiUrl("https://api.example.com///")).toBe(
			"https://api.example.com",
		);
	});

	it("no modifica una URL absoluta sin barra final", () => {
		expect(normalizeApiUrl("https://api.example.com")).toBe(
			"https://api.example.com",
		);
	});

	it("no fuerza https sobre una URL http explícita", () => {
		expect(normalizeApiUrl("http://192.168.1.10:8080")).toBe(
			"http://192.168.1.10:8080",
		);
	});

	it("produce rutas relativas /api/... cuando el resultado es cadena vacía", () => {
		const apiUrl = normalizeApiUrl("");
		expect(`${apiUrl}/api/conversations`).toBe("/api/conversations");
	});
});
