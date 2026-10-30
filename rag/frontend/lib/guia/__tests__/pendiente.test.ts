import { beforeEach, describe, expect, it } from "vitest";
import { borrarPendiente, guardarPendiente, hayPendiente, leerPendiente } from "@/lib/guia/pendiente";

describe("pregunta pendiente atada a la persona (E2-19)", () => {
	beforeEach(() => window.sessionStorage.clear());

	it("se ofrece de nuevo solo a quien la hizo", () => {
		guardarPendiente({ texto: "¿Puedo vender?", envio: "¿Puedo vender?", playa: null }, "persona-1");
		expect(leerPendiente("persona-1")).toEqual({ texto: "¿Puedo vender?", envio: "¿Puedo vender?", playa: null });
	});

	it("si entra otra persona no la ve y se borra", () => {
		guardarPendiente({ texto: "Me llamo Pedro, cédula 123", envio: "x", playa: null }, "persona-1");
		expect(hayPendiente()).toBe(true);
		expect(leerPendiente("persona-2")).toBeNull();
		expect(hayPendiente()).toBe(false);
		expect(leerPendiente("persona-1")).toBeNull();
	});

	it("borrarPendiente la quita", () => {
		guardarPendiente({ texto: "a", envio: "a", playa: null }, "p");
		borrarPendiente();
		expect(leerPendiente("p")).toBeNull();
	});
});
