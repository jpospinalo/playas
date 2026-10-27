"use client";

import { type ReactNode, useEffect, useRef, useState } from "react";

/**
 * J5-6: todo lo que aparece o desaparece en el panel (campos, formularios,
 * confirmaciones, avisos, hilos) entra y sale con altura + opacidad: 180 ms
 * ease-out al abrir y 140 ms al cerrar. Solo empuja hacia abajo, nunca mueve
 * lo de al lado. Con `prefers-reduced-motion: reduce` no hay animación
 * (WCAG 2.3.3). Mientras se cierra, el contenido sigue montado para que la
 * salida se vea; al terminar se desmonta.
 */

const CIERRE_MS = 140;

function sinMovimiento(): boolean {
	if (typeof window === "undefined" || typeof window.matchMedia !== "function") return true;
	return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

const ENFOCABLE = 'input:not([type="hidden"]), select, textarea, button, a[href], [tabindex]:not([tabindex="-1"])';

export function Aparece({
	abierto,
	children,
	enfocar = false,
	className,
}: {
	abierto: boolean;
	children: ReactNode;
	/** Al abrir, el foco va al elemento con `data-foco` o, si no hay, al primer campo o botón. */
	enfocar?: boolean;
	className?: string;
}) {
	const [antes, setAntes] = useState(abierto);
	const [cerrando, setCerrando] = useState(false);
	if (antes !== abierto) {
		setAntes(abierto);
		setCerrando(!abierto && !sinMovimiento());
	}

	useEffect(() => {
		if (!cerrando) return;
		const t = setTimeout(() => setCerrando(false), CIERRE_MS);
		return () => clearTimeout(t);
	}, [cerrando]);

	const caja = useRef<HTMLDivElement>(null);
	const primera = useRef(true);
	useEffect(() => {
		if (primera.current) {
			primera.current = false;
			return;
		}
		// PQ-99: en una confirmación destructiva el foco va a "Cancelar" (marcado
		// con data-foco), para que un Enter de más no borre ni desactive nada.
		if (abierto && enfocar)
			(
				caja.current?.querySelector<HTMLElement>("[data-foco]") ??
				caja.current?.querySelector<HTMLElement>(ENFOCABLE)
			)?.focus();
	}, [abierto, enfocar]);

	if (!abierto && !cerrando) return null;
	return (
		<div ref={caja} className={cerrando ? "pnl-aparece pnl-aparece-cierra" : "pnl-aparece"}>
			<div className={className ? `pnl-aparece-in ${className}` : "pnl-aparece-in"}>{children}</div>
		</div>
	);
}

/** Último valor no nulo: el aviso que se cierra sigue visible mientras sale. */
export function useUltimo<T>(valor: T | null): T | null {
	const [ultimo, setUltimo] = useState(valor);
	if (valor !== null && valor !== ultimo) setUltimo(valor);
	return valor ?? ultimo;
}

/** Aviso o error que aparece cuando hay valor; al cerrarse sigue mostrando el último mientras sale. */
export function AparecerSi<T>({
	valor,
	children,
}: {
	valor: T | null | undefined;
	children: (v: T) => ReactNode;
}) {
	const ultimo = useUltimo(valor ?? null);
	return <Aparece abierto={valor !== null && valor !== undefined}>{ultimo !== null ? children(ultimo) : null}</Aparece>;
}
