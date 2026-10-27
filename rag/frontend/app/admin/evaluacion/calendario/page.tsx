"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { mensajeError } from "@/lib/admin/panel";
import {
	cerrarEjercicio,
	diaLargo,
	guardarCalendario,
	pedirCalendario,
	type Calendario,
} from "@/lib/admin/calendario";
import { IconoAviso } from "@/components/admin/panel/Estados";
import { CabezaPestana, EncabezadoEvaluacion } from "@/components/admin/evaluacion/SubNav";
import { Aparece, AparecerSi } from "@/components/admin/panel/Aparece";
import { ResultadoJunto, textoBoton, useAccion } from "@/components/admin/panel/Resultado";
import { ChipEstado } from "@/components/admin/panel/Estados";

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
	const acc = useAccion();

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

	// J6-A1: el resultado (o el error) queda junto al botón, no arriba de la página.
	async function guardar(e: React.FormEvent) {
		e.preventDefault();
		await acc.correr(
			async () => {
				setCal(await guardarCalendario(fechas, dias));
				return "Calendario guardado.";
			},
			{ error: "No se pudo guardar el calendario." },
		);
	}

	return (
		<div className="pnl-pag">
			<title>Calendario: evaluación de ATLAS</title>
			<EncabezadoEvaluacion />
			<CabezaPestana titulo="Calendario del ejercicio">
				Fechas acordadas en la reunión del 20 de octubre. Al vencer un plazo, los semilleristas (o el comité) ya no
				pueden guardar; para ampliarlo, cambie la fecha aquí.
			</CabezaPestana>
			<AparecerSi valor={error}>
				{(error) => (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>Algo salió mal.</b>
							<p>{error}</p>
						</div>
					</div>
				)}
			</AparecerSi>
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
					{esAdmin ? (
						<div className="pnl-mt">
							<button type="submit" className="pnl-btn" disabled={acc.enviando}>
								{textoBoton(acc.estado, { listo: "Guardar el calendario" })}
							</button>
							<ResultadoJunto resultado={acc.resultado} />
						</div>
					) : null}
				</form>
			) : null}
			{cal && esAdmin ? <Cierre inicial={!!cal.cerrado} /> : null}
		</div>
	);
}

/** E6: al terminar la validación, el ejercicio se cierra y los resultados quedan congelados. */
function Cierre({ inicial }: { inicial: boolean }) {
	const [confirmar, setConfirmar] = useState(false);
	const [cerrado, setCerrado] = useState(inicial);
	const [cambiado, setCambiado] = useState(false);
	const [error, setError] = useState<string | null>(null);

	async function cambiar(cerrar: boolean) {
		setError(null);
		try {
			setCerrado((await cerrarEjercicio(cerrar)).cerrado);
			setCambiado(true);
			setConfirmar(false);
		} catch (e) {
			setError(mensajeError(e, "No se pudo cambiar."));
		}
	}

	return (
		<section className="pnl-bloque" aria-labelledby="t-cierre">
			<h2 id="t-cierre">Cerrar el ejercicio</h2>
			<p>
				Al cerrar, nadie puede calificar, validar ni elegir ganadoras; el resumen, los ganadores y el Excel quedan
				como están. Se puede reabrir.
			</p>
			{/* PQ-86: siempre se dice en qué estado está; solo se ofrece la acción que aplica. */}
			<p role="status" aria-live={cambiado ? "polite" : undefined}>
				<ChipEstado tono={cerrado ? "bien" : "espera"}>
					{cerrado ? "El ejercicio está cerrado" : "El ejercicio está abierto"}
				</ChipEstado>
			</p>
			<AparecerSi valor={error}>
				{(error) => (
					<p className="pnl-error-linea" role="alert">
						{error}
					</p>
				)}
			</AparecerSi>
			<Aparece abierto={confirmar} enfocar>
				<div className="pnl-confirmar" role="group" aria-labelledby="t-conf-cierre">
					<p id="t-conf-cierre">¿Cerrar el ejercicio ahora?</p>
					<div className="pnl-acciones">
						<button type="button" className="pnl-btn" onClick={() => cambiar(true)}>
							Sí, cerrar
						</button>
						<button type="button" className="pnl-btn-sec" data-foco onClick={() => setConfirmar(false)}>
							Cancelar
						</button>
					</div>
				</div>
			</Aparece>
			{confirmar ? null : (
				<div className="pnl-acciones">
					{cerrado ? (
						<button type="button" className="pnl-btn-sec" onClick={() => cambiar(false)}>
							Reabrir el ejercicio
						</button>
					) : (
						<button type="button" className="pnl-btn-sec" onClick={() => setConfirmar(true)}>
							Cerrar el ejercicio
						</button>
					)}
				</div>
			)}
		</section>
	);
}

