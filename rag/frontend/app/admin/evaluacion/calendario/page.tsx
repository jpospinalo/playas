"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { mensajeError } from "@/lib/admin/panel";
import { diaLargo, guardarCalendario, pedirCalendario, type Calendario } from "@/lib/admin/calendario";
import { IconoAviso } from "@/components/admin/panel/Estados";
import { SubNavEvaluacion } from "@/components/admin/evaluacion/SubNav";

/**
 * Calendario del ejercicio (reunión del 20-oct, T5): las fechas que dijo
 * Camilo, editables por el administrador (por ejemplo, para ampliar un plazo).
 * Vencido un plazo, el rol correspondiente ya no puede guardar.
 */
export default function PaginaCalendario() {
	const { role } = useAuth();
	const esAdmin = role === "admin" || role === "super-admin";
	const [cal, setCal] = useState<Calendario | null>(null);
	const [fechas, setFechas] = useState<Record<string, string>>({});
	const [dias, setDias] = useState(14);
	const [error, setError] = useState<string | null>(null);
	const [aviso, setAviso] = useState<string | null>(null);

	useEffect(() => {
		let vigente = true;
		pedirCalendario()
			.then((c) => {
				if (!vigente) return;
				setCal(c);
				setFechas(Object.fromEntries(c.fechas.map((f) => [f.clave, f.fecha])));
				setDias(c.dias_participante);
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudo cargar el calendario."));
			});
		return () => {
			vigente = false;
		};
	}, []);

	async function guardar(e: React.FormEvent) {
		e.preventDefault();
		setError(null);
		setAviso(null);
		try {
			const c = await guardarCalendario(fechas, dias);
			setCal(c);
			setAviso("Calendario guardado.");
		} catch (err) {
			setError(mensajeError(err, "No se pudo guardar el calendario."));
		}
	}

	return (
		<div className="pnl-pag">
			<title>Calendario: evaluación de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Calendario del ejercicio</h1>
					<p className="pnl-sub">
						Fechas acordadas en la reunión del 20 de octubre. Al vencer un plazo, los semilleristas (o el comité) ya no
						pueden guardar; para ampliarlo, cambie la fecha aquí.
					</p>
				</div>
			</div>
			<SubNavEvaluacion />
			{error ? (
				<div className="pnl-error" role="alert">
					<IconoAviso />
					<div>
						<b>Algo salió mal.</b>
						<p>{error}</p>
					</div>
				</div>
			) : null}
			{!cal && !error ? <p className="pnl-cargando">Cargando calendario…</p> : null}
			{cal ? (
				<form className="pnl-bloque" onSubmit={guardar} aria-labelledby="t-cal">
					<h2 id="t-cal">Fechas</h2>
					<ol className="pnl-calendario">
						{cal.fechas.map((f) => (
							<li key={f.clave}>
								<label htmlFor={`f-${f.clave}`}>{f.texto}</label>
								{esAdmin ? (
									<input
										id={`f-${f.clave}`}
										type="date"
										className="pnl-input"
										value={fechas[f.clave] ?? f.fecha}
										onChange={(e) => setFechas((x) => ({ ...x, [f.clave]: e.target.value }))}
									/>
								) : (
									<span id={`f-${f.clave}`}>{diaLargo(f.fecha)}</span>
								)}
							</li>
						))}
						<li>
							<label htmlFor="f-dias">Días que cada participante puede seguir preguntando desde su primer día</label>
							{esAdmin ? (
								<input
									id="f-dias"
									type="number"
									min={1}
									max={60}
									className="pnl-input"
									value={dias}
									onChange={(e) => setDias(Number(e.target.value))}
								/>
							) : (
								<span id="f-dias">{cal.dias_participante}</span>
							)}
						</li>
					</ol>
					<p className="pnl-nota">
						Por confirmar con el profesor Camilo: en la reunión se dijo “2 semanas desde el primer día” y luego “una
						semana más”.
					</p>
					{aviso ? (
						<p className="pnl-ok" role="status">
							{aviso}
						</p>
					) : null}
					{esAdmin ? (
						<button type="submit" className="pnl-btn">
							Guardar el calendario
						</button>
					) : null}
				</form>
			) : null}
		</div>
	);
}
