"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Ruta del flujo guiado guardada en el `#` de la dirección
 * (`#tema/entrar`, `#playa/vender/0`, `#escribir`…). Así el botón "atrás"
 * del celular vuelve a la pantalla anterior sin lógica extra.
 *
 * Cada pantalla que abre `ir()` guarda en `history.state` cuántos pasos
 * lleva dentro de ATLAS. `volver()` usa eso: si hay una pantalla de ATLAS
 * detrás, retrocede en el historial (igual que el "atrás" del celular, sin
 * agregar entradas que lo hagan andar en círculo); si no (p. ej. se entró
 * directo con un enlace a `#escribir`), reemplaza la pantalla por la de
 * respaldo, sin sacar a la persona de ATLAS.
 */

const EVENTO = "hashchange";

function suscribir(cambio: () => void): () => void {
	window.addEventListener(EVENTO, cambio);
	window.addEventListener("popstate", cambio);
	return () => {
		window.removeEventListener(EVENTO, cambio);
		window.removeEventListener("popstate", cambio);
	};
}

function leer(): string {
	return window.location.hash.replace(/^#/, "");
}

function profundidad(): number {
	const p = (window.history.state as { guia?: unknown } | null)?.guia;
	return typeof p === "number" ? p : 0;
}

function url(destino: string): string {
	const hash = destino === "inicio" ? "" : `#${destino}`;
	return `${window.location.pathname}${window.location.search}${hash}`;
}

export function useRutaGuia(): {
	ruta: string[];
	ir: (destino: string, opciones?: { reemplazar?: boolean }) => void;
	volver: (respaldo: string) => void;
} {
	const hash = useSyncExternalStore(suscribir, leer, () => "");
	const ruta = hash ? hash.split("/").map((p) => decodeURIComponent(p)) : ["inicio"];

	const ir = useCallback((destino: string, opciones?: { reemplazar?: boolean }) => {
		const actual = leer() || "inicio";
		if (destino === actual && !opciones?.reemplazar) return;
		if (opciones?.reemplazar) {
			window.history.replaceState({ guia: profundidad() }, "", url(destino));
		} else {
			window.history.pushState({ guia: profundidad() + 1 }, "", url(destino));
		}
		window.dispatchEvent(new HashChangeEvent(EVENTO));
	}, []);

	const volver = useCallback(
		(respaldo: string) => {
			if (profundidad() > 0) {
				window.history.back();
				return;
			}
			ir(respaldo, { reemplazar: true });
		},
		[ir],
	);

	return { ruta, ir, volver };
}
