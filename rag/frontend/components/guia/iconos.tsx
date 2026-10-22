import type { IconoTema } from "@/lib/guia/temas";

// Íconos de línea simples para cada tema (mismos trazos del MVP v3).
const TRAZOS: Record<IconoTema, string[]> = {
	caminar: ["M13 9l-3 4 2 3v6M13 9l4 3 3-1M12 16l-4 6M10 13l-3 1"],
	pez: ["M3 12c3-5 9-6 14-3l4-3v12l-4-3c-5 3-11 2-14-3z"],
	venta: ["M4 10l8-6 8 6M7 10v10h10V10M10 20v-5h4v5"],
	hotel: ["M5 21V5h14v16M9 9h2M13 9h2M9 13h2M13 13h2M10 21v-4h4v4"],
	lancha: ["M3 16h18l-3 4H6zM12 4v10M12 4l6 9h-6"],
	obra: ["M3 21h18M6 21V11l6-5 6 5v10M10 21v-5h4v5M17 4h2v4"],
};

export function IconoDeTema({ icono }: { icono: IconoTema }) {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			{icono === "caminar" && <circle cx="15" cy="5" r="2.5" />}
			{icono === "pez" && <circle cx="14" cy="8" r=".8" />}
			{TRAZOS[icono].map((d) => (
				<path key={d} d={d} />
			))}
		</svg>
	);
}

export function Flecha() {
	return (
		<svg className="flecha" viewBox="0 0 24 24" aria-hidden="true">
			<path d="M9 5l7 7-7 7" />
		</svg>
	);
}

export function FlechaVolver() {
	return (
		<svg
			viewBox="0 0 24 24"
			aria-hidden="true"
			fill="none"
			stroke="currentColor"
			strokeWidth="3"
			strokeLinecap="round"
			strokeLinejoin="round"
		>
			<path d="M15 5l-7 7 7 7" />
		</svg>
	);
}

export function Boya() {
	return (
		<svg className="boya" viewBox="0 0 44 44" aria-hidden="true">
			<path d="M22 4v8" stroke="#14212b" strokeWidth="3" />
			<path d="M14 30l4-18h8l4 18z" fill="#a3166f" />
			<path d="M8 34q7-4 14 0t14 0" fill="none" stroke="#2f6f99" strokeWidth="3" />
		</svg>
	);
}

export function Atencion() {
	return (
		<svg viewBox="0 0 34 34" aria-hidden="true">
			<circle cx="17" cy="17" r="15" fill="#a3166f" />
			<path d="M17 8v11" stroke="#fff" strokeWidth="3.5" strokeLinecap="round" />
			<circle cx="17" cy="25" r="2.2" fill="#fff" />
		</svg>
	);
}

/** Curvas de profundidad detrás del veredicto (solo decoración, solo en PC). */
export function Curvas() {
	return (
		<svg className="curvas" viewBox="0 0 170 200" preserveAspectRatio="none" aria-hidden="true">
			<g fill="none" stroke="#8db8d4" strokeWidth="2">
				<path d="M60 0 C40 50 90 80 70 120 C55 150 80 175 75 200" />
				<path d="M95 0 C75 50 125 80 105 120 C90 150 115 175 110 200" strokeDasharray="3 6" />
				<path d="M130 0 C110 50 160 80 140 120 C125 150 150 175 145 200" />
			</g>
			<g fontFamily="Source Sans 3, Arial" fontStyle="italic" fontSize="13" fill="#5b7f99">
				<text x="82" y="62">8</text>
				<text x="118" y="150">15</text>
			</g>
		</svg>
	);
}

export function Parlante() {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path d="M4 9v6h4l5 4V5L8 9z" />
			<path d="M16 8.5a5 5 0 0 1 0 7M19 6a9 9 0 0 1 0 12" />
		</svg>
	);
}
