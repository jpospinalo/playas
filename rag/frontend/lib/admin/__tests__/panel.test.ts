import { describe, expect, it } from "vitest";
import {
	cambioConteo,
	cambioTasa,
	decimal,
	diaMesCalendario,
	fechaHora,
	numero,
	porcentaje,
	recortar,
	textoPorcentaje,
} from "@/lib/admin/panel";
import { tope } from "@/components/admin/panel/Graficos";

describe("formato del panel en español de Colombia", () => {
	it("miles con punto y decimales con coma", () => {
		expect(numero(1234)).toBe("1.234");
		expect(decimal(7.46)).toBe("7,5");
	});

	it("porcentaje sin base no es NaN ni Infinity", () => {
		expect(porcentaje(3, 0)).toBeNull();
		expect(textoPorcentaje(3, 0)).toBe("—");
		expect(textoPorcentaje(312, 385)).toBe("81 %");
	});

	it("fechas en hora de Colombia, sin punto de abreviatura", () => {
		// 26-oct 03:00 UTC = 25-oct 22:00 en Colombia.
		expect(fechaHora("2026-10-26T03:00:00Z")).toMatch(/^25 oct, 22:00$/);
		expect(diaMesCalendario("2026-10-19")).toBe("19 oct");
	});
});

describe("cambio frente al periodo anterior", () => {
	it("sin periodo anterior o en cero no inventa un +100 %", () => {
		expect(cambioConteo(10, 0)).toBeNull();
		expect(cambioConteo(10, null)).toBeNull();
	});

	it("conteos en %, tasas en puntos", () => {
		expect(cambioConteo(482, 430)).toEqual({ direccion: "sube", texto: "12 %" });
		expect(cambioConteo(50, 100)).toEqual({ direccion: "baja", texto: "50 %" });
		expect(cambioConteo(5, 5)).toEqual({ direccion: "igual", texto: "igual" });
		expect(cambioTasa(81, 78)).toEqual({ direccion: "sube", texto: "3 puntos" });
		expect(cambioTasa(8, 9)).toEqual({ direccion: "baja", texto: "1 punto" });
		expect(cambioTasa(null, 9)).toBeNull();
	});
});

describe("escala del eje de columnas", () => {
	it("deja aire sobre el máximo y la mitad es entera", () => {
		for (const max of [0, 1, 3, 7, 13, 45, 113, 480]) {
			const t = tope(max);
			expect(t).toBeGreaterThan(max);
			expect(Number.isInteger(t / 2)).toBe(true);
		}
	});
});

describe("recortar", () => {
	it("corta en palabra completa y deja intacto lo corto", () => {
		expect(recortar("corto")).toBe("corto");
		const largo = "palabra ".repeat(300);
		const r = recortar(largo, 280);
		expect(r.length).toBeLessThanOrEqual(281);
		expect(r.endsWith("palabra…")).toBe(true);
	});
});
