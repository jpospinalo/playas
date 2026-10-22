import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	iniciarMedicion,
	leerMediciones,
	marcarEtapa,
	marcarPrimerTexto,
	percentil,
	resumen,
	terminarMedicion,
} from "@/lib/medicion";

describe("medición del tiempo hasta la respuesta (UX-02)", () => {
	let t = 0;
	beforeEach(() => {
		t = 0;
		vi.spyOn(performance, "now").mockImplementation(() => t);
		window.localStorage.clear();
	});
	afterEach(() => vi.restoreAllMocks());

	it("registra etapas, primer texto y respuesta, sin el texto de la pregunta", () => {
		iniciarMedicion();
		t = 900;
		marcarEtapa("enriching");
		t = 1800;
		marcarEtapa("retrieving");
		marcarEtapa("retrieving"); // repetida: no cambia
		t = 4000;
		marcarPrimerTexto();
		t = 4100;
		const m = terminarMedicion("ok");
		expect(m).toMatchObject({ etapas: { enriching: 900, retrieving: 1800 }, primerTexto: 4000, respuesta: 4100, resultado: "ok" });
		expect(Object.keys(m!)).not.toContain("pregunta");
		expect(leerMediciones()).toHaveLength(1);
	});

	it("una pregunta con error o cancelada se guarda sin tiempo de respuesta", () => {
		iniciarMedicion();
		t = 5000;
		expect(terminarMedicion("error")?.respuesta).toBeUndefined();
		expect(terminarMedicion("ok")).toBeNull(); // ya no hay medición en curso
	});

	it("resumen con p50 y p95 solo sobre las respuestas correctas", () => {
		for (const ms of [1000, 2000, 3000, 4000, 20000]) {
			t = 0;
			iniciarMedicion();
			t = ms;
			terminarMedicion("ok");
		}
		iniciarMedicion();
		terminarMedicion("cancelada");
		expect(resumen()).toMatchObject({ preguntas: 6, ok: 5, canceladas: 1, respuestaUtil_p50_ms: 3000, respuestaUtil_p95_ms: 20000 });
	});

	it("percentil por rango más cercano", () => {
		expect(percentil([], 50)).toBeNull();
		expect(percentil([5], 95)).toBe(5);
		expect(percentil([1, 2, 3, 4], 50)).toBe(2);
	});
});
