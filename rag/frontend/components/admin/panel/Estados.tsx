import {
	ETIQUETA_CALIFICACION,
	ETIQUETA_RESULTADO,
	SIN_RESPUESTA_SEGURA,
	type Calificacion,
	type Cambio,
	type Resultado,
} from "@/lib/admin/panel";

/** Íconos y estados del panel: siempre ícono + texto, nunca solo color. */

export function IconoAviso() {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path d="M12 3l10 18H2z" />
			<path d="M12 10v4M12 17v.5" />
		</svg>
	);
}

function IconoBien() {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path d="M5 12l5 5 9-10" />
		</svg>
	);
}

function IconoMal() {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path d="M6 6l12 12M18 6L6 18" />
		</svg>
	);
}

function IconoNorma() {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<path d="M4 6h16M4 12h16M4 18h10" />
		</svg>
	);
}

function IconoNeutro() {
	return (
		<svg viewBox="0 0 24 24" aria-hidden="true">
			<circle cx="12" cy="12" r="9" />
			<path d="M8 12h8" />
		</svg>
	);
}

export function IconoDescargar() {
	return (
		<svg
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			strokeWidth="2.2"
			strokeLinecap="round"
			strokeLinejoin="round"
			aria-hidden="true"
		>
			<path d="M12 4v11M7 10l5 5 5-5M5 20h14" />
		</svg>
	);
}

export function EstadoResultado({ resultado, fuentes }: { resultado: Resultado; fuentes?: number }) {
	if (resultado === "con_fuente") {
		return (
			<span className="pnl-estado bien">
				<IconoNorma />
				{ETIQUETA_RESULTADO.con_fuente}
				{fuentes ? ` (${fuentes})` : ""}
			</span>
		);
	}
	if (SIN_RESPUESTA_SEGURA.includes(resultado)) {
		return (
			<span className="pnl-estado ojo">
				<IconoAviso />
				{ETIQUETA_RESULTADO[resultado]}
			</span>
		);
	}
	return (
		<span className="pnl-estado neutro">
			<IconoNeutro />
			{ETIQUETA_RESULTADO[resultado]}
		</span>
	);
}

export function EstadoCalificacion({ calificacion }: { calificacion: Calificacion | null }) {
	if (calificacion === "util") {
		return (
			<span className="pnl-estado bien">
				<IconoBien />
				{ETIQUETA_CALIFICACION.util}
			</span>
		);
	}
	if (calificacion === "no_util") {
		return (
			<span className="pnl-estado mal">
				<IconoMal />
				{ETIQUETA_CALIFICACION.no_util}
			</span>
		);
	}
	return (
		<span className="pnl-estado neutro">
			{calificacion ? ETIQUETA_CALIFICACION[calificacion] : "Sin calificar"}
		</span>
	);
}

/** "Le sirvió" de un grupo: % con ícono, o "pocos datos" si hay menos de 5. */
export function EstadoSatisfaccion({
	leSirvio,
	calificaciones,
	minimo,
}: {
	leSirvio: number;
	calificaciones: number;
	minimo: number;
}) {
	if (calificaciones < minimo) {
		return (
			<span className="pnl-estado neutro">
				Pocos datos: {calificaciones} {calificaciones === 1 ? "calificación" : "calificaciones"}
			</span>
		);
	}
	const p = Math.round((leSirvio / calificaciones) * 100);
	const bajo = p < 60;
	return (
		<span className={`pnl-estado ${bajo ? "ojo" : "bien"}`}>
			{bajo ? <IconoAviso /> : <IconoBien />}
			{p}&nbsp;% le sirvió <span className="sr">de {calificaciones} calificaciones</span>
		</span>
	);
}

/**
 * Flecha + texto del cambio frente al periodo anterior. `mejorSiSube` dice
 * si subir es bueno (preguntas, norma citada) o malo (sin respuesta segura).
 */
export function Delta({
	cambio,
	mejorSiSube,
	sufijo,
}: {
	cambio: Cambio | null;
	mejorSiSube: boolean;
	sufijo: string;
}) {
	if (!cambio) return <>Sin datos del periodo anterior</>;
	if (cambio.direccion === "igual") return <>Igual que {sufijo}</>;
	const bueno = (cambio.direccion === "sube") === mejorSiSube;
	return (
		<>
			<span className={`pnl-delta ${bueno ? "bien" : "mal"}`}>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					{cambio.direccion === "sube" ? (
						<path d="M12 19V5M6 11l6-6 6 6" />
					) : (
						<path d="M12 5v14M6 13l6 6 6-6" />
					)}
				</svg>
				{cambio.direccion === "sube" ? "Subió" : "Bajó"} {cambio.texto}
			</span>{" "}
			frente a {sufijo}
		</>
	);
}
