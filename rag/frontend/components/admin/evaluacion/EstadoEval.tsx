import { TEXTO_ESTADO, type EstadoPregunta } from "@/lib/admin/evaluacion";

/** Estado de una pregunta en la evaluación, con texto (nunca solo color). */
export function EstadoEval({ estado }: { estado: EstadoPregunta }) {
	const clase =
		estado === "con_diferencias"
			? "ojo"
			: estado === "final" || estado === "concordante"
				? "bien"
				: "neutro";
	return <span className={`pnl-estado ${clase}`}>{TEXTO_ESTADO[estado]}</span>;
}
