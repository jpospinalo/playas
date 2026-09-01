import { describe, expect, it } from "vitest";
import { readErrorDetail } from "@/lib/api";

/**
 * `readErrorDetail`: lector único y seguro del detalle de un error HTTP.
 * Los tres casos que ya caracteriza `api.test.ts` (JSON con `detail`,
 * texto plano, cuerpo vacío) siguen intactos ahí sin tocarse — este
 * archivo cubre los casos que un lector más ingenuo maneja mal:
 *  - un cuerpo JSON válido pero sin `detail` nunca se muestra como JSON
 *    serializado;
 *  - un cuerpo que parece HTML (de un proxy/balanceador) no se muestra tal
 *    cual, aunque el content-type mienta;
 *  - un cuerpo demasiado largo se recorta;
 *  - un `fallback` explícito reemplaza el genérico "Error del servidor
 *    (N)" cuando el llamador lo necesita (p. ej. login).
 */

describe("readErrorDetail — saneamiento del detalle de error", () => {
	it("un cuerpo JSON válido sin `detail` usable NUNCA se muestra como JSON serializado — usa el fallback", async () => {
		const res = new Response(JSON.stringify({ message: "algo pasó" }), {
			status: 500,
			headers: { "Content-Type": "application/json" },
		});
		await expect(readErrorDetail(res)).resolves.toBe(
			"Error del servidor (500)",
		);
	});

	it("un `detail` vacío o solo espacios en un JSON válido también cae al fallback, no a una cadena vacía", async () => {
		const res = new Response(JSON.stringify({ detail: "   " }), {
			status: 422,
			headers: { "Content-Type": "application/json" },
		});
		await expect(readErrorDetail(res)).resolves.toBe(
			"Error del servidor (422)",
		);
	});

	it("un cuerpo HTML (p. ej. de un proxy/balanceador) nunca se muestra tal cual, aunque el content-type diga texto plano", async () => {
		const res = new Response(
			"<!DOCTYPE html><html><body>502 Bad Gateway</body></html>",
			{ status: 502, headers: { "Content-Type": "text/plain" } },
		);
		await expect(readErrorDetail(res)).resolves.toBe(
			"Error del servidor (502)",
		);
	});

	it("un content-type que no es texto plano ni JSON (p. ej. text/html declarado) cae al fallback aunque el cuerpo sea corto", async () => {
		const res = new Response("Bad Gateway", {
			status: 502,
			headers: { "Content-Type": "text/html; charset=utf-8" },
		});
		await expect(readErrorDetail(res)).resolves.toBe(
			"Error del servidor (502)",
		);
	});

	it("un cuerpo de texto plano demasiado largo se recorta, nunca se muestra completo", async () => {
		const longText = "x".repeat(5000);
		const res = new Response(longText, {
			status: 500,
			headers: { "Content-Type": "text/plain" },
		});
		const detail = await readErrorDetail(res);
		expect(detail.length).toBeLessThanOrEqual(500);
		expect(detail).toBe("x".repeat(500));
	});

	it("un `detail` de JSON demasiado largo también se recorta", async () => {
		const res = new Response(JSON.stringify({ detail: "y".repeat(5000) }), {
			status: 400,
			headers: { "Content-Type": "application/json" },
		});
		const detail = await readErrorDetail(res);
		expect(detail.length).toBeLessThanOrEqual(500);
	});

	it("un `fallback` explícito reemplaza el mensaje genérico por código cuando el cuerpo no aporta nada usable", async () => {
		const res = new Response("", { status: 401 });
		await expect(
			readErrorDetail(res, "Correo o contraseña incorrectos."),
		).resolves.toBe("Correo o contraseña incorrectos.");
	});

	it("el `detail` del backend sigue teniendo prioridad sobre un `fallback` explícito cuando sí viene", async () => {
		const res = new Response(
			JSON.stringify({ detail: "La cuenta está deshabilitada." }),
			{ status: 401, headers: { "Content-Type": "application/json" } },
		);
		await expect(
			readErrorDetail(res, "Correo o contraseña incorrectos."),
		).resolves.toBe("La cuenta está deshabilitada.");
	});

	it("un cuerpo declarado `application/json` pero malformado nunca se muestra como texto plano — usa el fallback", async () => {
		const res = new Response('{"detail": "sin cerrar', {
			status: 500,
			headers: { "Content-Type": "application/json" },
		});
		await expect(readErrorDetail(res)).resolves.toBe(
			"Error del servidor (500)",
		);
	});
});
