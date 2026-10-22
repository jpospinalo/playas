"use client";

import { useCallback, useSyncExternalStore } from "react";

/**
 * Ruta del flujo guiado guardada en el `#` de la dirección
 * (`#tema/entrar`, `#playa/vender/0`, `#escribir`…). Así el botón "atrás"
 * del celular vuelve a la pantalla anterior sin lógica extra.
 */

function suscribir(cambio: () => void): () => void {
	window.addEventListener("hashchange", cambio);
	return () => window.removeEventListener("hashchange", cambio);
}

function leer(): string {
	return window.location.hash.replace(/^#/, "");
}

export function useRutaGuia(): {
	ruta: string[];
	ir: (destino: string, opciones?: { reemplazar?: boolean }) => void;
} {
	const hash = useSyncExternalStore(suscribir, leer, () => "");
	const ruta = hash ? hash.split("/").map((p) => decodeURIComponent(p)) : ["inicio"];

	const ir = useCallback((destino: string, opciones?: { reemplazar?: boolean }) => {
		const nuevo = destino === "inicio" ? "" : `#${destino}`;
		if (opciones?.reemplazar) {
			const url = `${window.location.pathname}${window.location.search}${nuevo}`;
			window.history.replaceState(null, "", url);
			window.dispatchEvent(new HashChangeEvent("hashchange"));
			return;
		}
		if (destino === "inicio") {
			if (!window.location.hash) return;
			window.history.pushState(null, "", `${window.location.pathname}${window.location.search}`);
			window.dispatchEvent(new HashChangeEvent("hashchange"));
			return;
		}
		window.location.hash = destino;
	}, []);

	return { ruta, ir };
}
