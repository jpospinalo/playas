"use client";

import { useEffect, useRef, useState } from "react";
import { detenerVoz, hablar, prepararVoz } from "@/lib/voz";
import { Parlante } from "@/components/guia/iconos";

interface EscucharProps {
	/** Texto que se lee. Se calcula al tocar, para leer lo que hay en pantalla. */
	texto: () => string;
	etiqueta?: string;
}

/**
 * Botón "Escuchar". Lee el texto con un audio grabado si existe para ese
 * texto exacto, o con la mejor voz en español del dispositivo.
 */
export function Escuchar({ texto, etiqueta = "Escuchar" }: EscucharProps) {
	const [estado, setEstado] = useState<"quieto" | "leyendo" | "sin-voz" | "sin-espanol">("quieto");
	// Un doble toque no debe encender y apagar la lectura enseguida.
	const ultimoToque = useRef(0);

	useEffect(() => {
		prepararVoz();
		return () => detenerVoz();
	}, []);

	function tocar() {
		const ahora = Date.now();
		if (ahora - ultimoToque.current < 600) return;
		ultimoToque.current = ahora;
		if (estado === "leyendo") {
			detenerVoz();
			setEstado("quieto");
			return;
		}
		setEstado("leyendo");
		hablar(texto())
			.then(() => setEstado((e) => (e === "leyendo" ? "quieto" : e)))
			.catch((e: unknown) =>
				setEstado(e instanceof Error && e.message === "sin-espanol" ? "sin-espanol" : "sin-voz"),
			);
	}

	return (
		<button
			type="button"
			className="guia-escuchar"
			aria-pressed={estado === "leyendo"}
			onClick={tocar}
		>
			<Parlante />
			<span>
				{estado === "leyendo"
					? "Detener la lectura"
					: estado === "sin-voz"
						? "Este equipo no puede leer en voz alta"
						: estado === "sin-espanol"
							? "Este equipo no tiene voz en español"
							: etiqueta}
			</span>
		</button>
	);
}
