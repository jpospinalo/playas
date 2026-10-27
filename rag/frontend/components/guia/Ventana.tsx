"use client";

import { useEffect, useState } from "react";
import { diaLargo, pedirVentana, type Ventana } from "@/lib/admin/calendario";

/**
 * Reunión del 20-oct (T5): cada participante puede seguir preguntando 2
 * semanas desde su primer día. Solo se informa; ATLAS no se bloquea.
 */
export function VentanaParticipante() {
	const [v, setV] = useState<Ventana | null>(null);
	useEffect(() => {
		let vigente = true;
		pedirVentana()
			.then((x) => {
				if (vigente) setV(x);
			})
			.catch(() => {
				// Sin datos no se muestra nada.
			});
		return () => {
			vigente = false;
		};
	}, []);
	if (!v) return null;
	return (
		<p className="pie" role="note">
			{v.dias_restantes >= 0
				? `Para el ejercicio de validación, sus preguntas cuentan hasta el ${diaLargo(v.ultimo_dia)}.`
				: `Su participación en el ejercicio terminó el ${diaLargo(v.ultimo_dia)}. Puede seguir usando ATLAS, pero las preguntas nuevas ya no cuentan.`}
		</p>
	);
}
