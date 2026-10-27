import { TEXTO_ESTADO, type EstadoPregunta } from "@/lib/admin/evaluacion";

/** Estado de una pregunta en la evaluación, con texto (nunca solo color). */
export function EstadoEval({ estado }: { estado: EstadoPregunta }) {
	// J6-A5: gris sin empezar, azul en proceso, ámbar necesita atención, verde terminado.
	const clase =
		estado === "con_diferencias"
			? "ojo"
			: estado === "final" || estado === "validada"
				? "bien"
				: estado === "sin_evaluar"
					? "sin"
					: "espera";
	return <span className={`pnl-estado ${clase}`}>{TEXTO_ESTADO[estado]}</span>;
}
