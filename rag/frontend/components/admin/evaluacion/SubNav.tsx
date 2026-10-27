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
	const enCalendario = pathname.startsWith("/admin/evaluacion/calendario");
	return (
		<nav aria-label="Evaluación" className="pnl-subnav">
			<Link
				href="/admin/evaluacion"
				aria-current={!enResumen && !enValidar && !enCalendario ? "page" : undefined}
			>
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
			{rolComite(role) ? (
				<Link href="/admin/evaluacion/calendario" aria-current={enCalendario ? "page" : undefined}>
					Calendario
				</Link>
			) : null}
		</nav>
	);
}

/**
 * J5-1: el mismo encabezado en Preguntas, Validar, Resumen y Calendario, para
 * que las pestañas no cambien de lugar al pasar de una a otra. Lo propio de
 * cada pestaña (descripción, botones, avisos) va debajo con
 * ``CabezaPestana``.
 */
export function EncabezadoEvaluacion() {
	return (
		<>
			<div className="pnl-cabeza">
				<div>
					<h1>Evaluación de preguntas</h1>
					<p className="pnl-sub">Ejercicio de validación de ATLAS: evaluar, validar y ver resultados.</p>
				</div>
			</div>
			<SubNavEvaluacion />
		</>
	);
}

/** Título, descripción y acciones de una pestaña, debajo del menú. */
export function CabezaPestana({
	titulo,
	children,
	acciones,
}: {
	titulo: string;
	children?: React.ReactNode;
	acciones?: React.ReactNode;
}) {
	return (
		<div className="pnl-cabeza-pestana">
			<div>
				<h2>{titulo}</h2>
				{children ? <p className="pnl-sub">{children}</p> : null}
			</div>
			{acciones ? <div className="pnl-controles">{acciones}</div> : null}
		</div>
	);
}

