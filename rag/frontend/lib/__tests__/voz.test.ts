import { describe, expect, it } from "vitest";
import { claveAudio, dividirEnFrases, elegirVoz, puntajeVoz } from "@/lib/voz";

const v = (name: string, lang: string) => ({ name, lang, localService: true });

describe("elegirVoz", () => {
	it("prefiere una voz natural en español de la región antes que una básica", () => {
		const voces = [
			v("Samantha", "en-US"),
			v("Mónica", "es-ES"),
			v("Paulina", "es-MX"),
			v("Microsoft Salome Online (Natural) - Spanish (Colombia)", "es-CO"),
		];
		expect(elegirVoz(voces)?.name).toContain("Salome");
	});

	it("entre voces básicas prefiere es-CO / es-MX sobre es-ES", () => {
		expect(elegirVoz([v("Mónica", "es-ES"), v("Paulina", "es-MX")])?.name).toBe("Paulina");
		expect(elegirVoz([v("Google español", "es-ES"), v("Google español de Estados Unidos", "es-US")])?.lang).toBe("es-US");
	});

	it("evita las voces de juguete de Apple y las que no son español", () => {
		expect(puntajeVoz(v("Grandma (Spanish (Mexico))", "es-MX"))).toBe(0);
		expect(puntajeVoz(v("Daniel", "en-GB"))).toBe(-1);
		expect(elegirVoz([v("Daniel", "en-GB")])).toBeNull();
	});
});

describe("dividirEnFrases", () => {
	it("corta por frases y por líneas, sin perder preguntas", () => {
		expect(dividirEnFrases("Sí. Las playas son de todos.\n¿Qué puede hacer? Avise.")).toEqual([
			"Sí.",
			"Las playas son de todos.",
			"¿Qué puede hacer?",
			"Avise.",
		]);
		expect(dividirEnFrases("Texto sin punto final")).toEqual(["Texto sin punto final"]);
	});
});

describe("claveAudio", () => {
	it("ignora espacios y mayúsculas al buscar un audio grabado", () => {
		expect(claveAudio("  ¿Sobre qué es\nsu pregunta? ")).toBe(claveAudio("¿sobre qué es su pregunta?"));
	});
});
