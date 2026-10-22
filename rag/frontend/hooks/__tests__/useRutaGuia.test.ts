import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useRutaGuia } from "@/hooks/useRutaGuia";

describe("useRutaGuia", () => {
	beforeEach(() => {
		window.history.replaceState(null, "", "/");
	});

	it("'Volver' retrocede en el historial en vez de agregar otra entrada (QA-01)", async () => {
		const { result } = renderHook(() => useRutaGuia());
		const inicial = window.history.length;
		act(() => result.current.ir("tema/entrar"));
		expect(result.current.ruta).toEqual(["tema", "entrar"]);
		expect(window.history.length).toBe(inicial + 1);

		await act(async () => {
			const vuelta = new Promise((r) => window.addEventListener("popstate", r, { once: true }));
			result.current.volver("inicio");
			await vuelta;
		});
		expect(result.current.ruta).toEqual(["inicio"]);
		// No se agregó ninguna entrada nueva: el "atrás" del celular no anda en círculo.
		expect(window.history.length).toBe(inicial + 1);
	});

	it("si se entró directo a una pantalla, 'Volver' la reemplaza por la de respaldo sin salir de ATLAS", () => {
		window.history.replaceState(null, "", "/#escribir");
		const { result } = renderHook(() => useRutaGuia());
		const inicial = window.history.length;
		act(() => result.current.volver("inicio"));
		expect(result.current.ruta).toEqual(["inicio"]);
		expect(window.history.length).toBe(inicial);
	});
});
