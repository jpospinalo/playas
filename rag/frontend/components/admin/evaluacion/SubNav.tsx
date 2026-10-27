"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/components/providers/AuthProvider";
import { rolComite } from "@/lib/admin/evaluacion";

/** Pestañas internas de la evaluación: preguntas, validación (comité) y resumen. */
export function SubNavEvaluacion() {
	const pathname = usePathname();
	const { role } = useAuth();
	const enResumen = pathname.startsWith("/admin/evaluacion/resumen");
	const enValidar = pathname.startsWith("/admin/evaluacion/validar");
	return (
		<nav aria-label="Evaluación" className="pnl-subnav">
			<Link href="/admin/evaluacion" aria-current={!enResumen && !enValidar ? "page" : undefined}>
				Preguntas para calificar
			</Link>
			{rolComite(role) ? (
				<Link href="/admin/evaluacion/validar" aria-current={enValidar ? "page" : undefined}>
					Validar evaluaciones
				</Link>
			) : null}
			<Link href="/admin/evaluacion/resumen" aria-current={enResumen ? "page" : undefined}>
				Resumen y premios
			</Link>
		</nav>
	);
}
