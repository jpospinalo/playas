"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Pestañas internas de la evaluación: preguntas y resumen del ejercicio. */
export function SubNavEvaluacion() {
	const pathname = usePathname();
	const enResumen = pathname.startsWith("/admin/evaluacion/resumen");
	return (
		<nav aria-label="Evaluación" className="pnl-subnav">
			<Link href="/admin/evaluacion" aria-current={!enResumen ? "page" : undefined}>
				Preguntas para calificar
			</Link>
			<Link href="/admin/evaluacion/resumen" aria-current={enResumen ? "page" : undefined}>
				Resumen y premios
			</Link>
		</nav>
	);
}
