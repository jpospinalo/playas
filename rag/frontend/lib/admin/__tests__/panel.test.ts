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

	it("conteos por día y tasas en puntos, solo si superan el margen (PQ-128)", () => {
		expect(cambioConteo(500, 300, 7, 7)).toEqual({ direccion: "sube", texto: "67 % por día" });
		expect(cambioConteo(100, 300, 7, 7)).toEqual({ direccion: "baja", texto: "67 % por día" });
		expect(cambioConteo(50, 50)).toEqual({ direccion: "igual", texto: "igual" });
		// 244 en 6,4 días contra 225 en 7: dentro del margen.
		expect(cambioConteo(244, 225, 6.4, 7)).toEqual({ direccion: "incierto", texto: "sin cambio claro" });
		// Menos de 30 casos: nunca se afirma un cambio.
		expect(cambioConteo(25, 5, 7, 7)?.direccion).toBe("incierto");
		expect(cambioTasa(300, 400, 200, 400)).toEqual({ direccion: "sube", texto: "25 puntos" });
		// 36/236 (15 %) contra 41/222 (18 %): p ≈ 0,36, sin cambio claro.
		expect(cambioTasa(36, 236, 41, 222)).toEqual({ direccion: "incierto", texto: "sin cambio claro" });
		expect(cambioTasa(13, 19, 13, 22)?.direccion).toBe("incierto");
		expect(cambioTasa(5, 10, null, null)).toBeNull();
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
