"use client";

import { useId, useState } from "react";
import {
	NIVELES,
	RANGOS,
	cvEnRango,
	totalPlanilla,
	type CalificacionIn,
	type CalificacionOut,
	type Ct,
	type Rubrica,
} from "@/lib/admin/evaluacion";

/**
 * Formulario de la planilla: F1, F2 y F3 (1 a 3) con la rúbrica del
 * Instructivo a la vista, Ct (S/I/A) y Cv solo dentro del rango del nivel,
 * total automático, "no válida" y observaciones. Lo usan el semillerista
 * (su calificación) y el comité (la final).
 */
export function FormCalificacion({
	rubrica,
	inicial,
	textoBoton,
	onGuardar,
	deshabilitado,
}: {
	rubrica: Rubrica;
	inicial: CalificacionOut | null;
	textoBoton: string;
	onGuardar: (c: CalificacionIn) => Promise<void>;
	deshabilitado?: boolean;
}) {
	const id = useId();
	const [f, setF] = useState<Record<"f1" | "f2" | "f3", number>>({
		f1: inicial?.f1 ?? 0,
		f2: inicial?.f2 ?? 0,
		f3: inicial?.f3 ?? 0,
	});
	const [ct, setCt] = useState<Ct | null>(inicial?.ct ?? null);
	const [cv, setCv] = useState<number>(inicial?.cv ?? 0);
	const [valida, setValida] = useState(inicial?.valida ?? true);
	const [obs, setObs] = useState(inicial?.observaciones ?? "");
	const [faltan, setFaltan] = useState<string | null>(null);
	const [enviando, setEnviando] = useState(false);

	const forma = f.f1 && f.f2 && f.f3 ? f.f1 + f.f2 + f.f3 : null;
	const total = forma !== null && ct && cv ? totalPlanilla(f.f1, f.f2, f.f3, cv) : null;

	async function enviar(e: React.FormEvent) {
		e.preventDefault();
		const sinMarcar = [
			!f.f1 && "F1",
			!f.f2 && "F2",
			!f.f3 && "F3",
			!ct && "Ct (nivel)",
			(!cv || (ct && cvEnRango(ct, cv) !== cv)) && "Cv",
		].filter(Boolean);
		if (sinMarcar.length || !ct) {
			setFaltan(`Falta elegir: ${sinMarcar.join(", ")}.`);
			return;
		}
		setFaltan(null);
		setEnviando(true);
		try {
			await onGuardar({ ...f, ct, cv, valida, observaciones: obs.trim() || null });
		} finally {
			setEnviando(false);
		}
	}

	return (
		<form onSubmit={enviar} className="pnl-planilla" aria-describedby={faltan ? `${id}-faltan` : undefined}>
			<h3>Forma</h3>
			{(["f1", "f2", "f3"] as const).map((k) => {
				const r = rubrica.forma[k];
				return (
					<fieldset key={k} className="pnl-criterio" disabled={deshabilitado}>
						<legend>
							{r.nombre} <span className="pnl-criterio-q">{r.pregunta}</span>
						</legend>
						<div className="pnl-opciones">
							{[1, 2, 3].map((n) => (
								<label key={n} className="pnl-opcion">
									<input
										type="radio"
										name={`${id}-${k}`}
										value={n}
										checked={f[k] === n}
										onChange={() => setF((x) => ({ ...x, [k]: n }))}
									/>
									<span>
										<b>{n}</b> {r.niveles[String(n)]}
									</span>
								</label>
							))}
						</div>
					</fieldset>
				);
			})}
			<p className="pnl-subtotal">
				Puntaje de forma: <b className="num">{forma ?? "—"}</b> de 9
			</p>

			<h3>Fondo</h3>
			<fieldset className="pnl-criterio" disabled={deshabilitado}>
				<legend>Ct: complejidad jurídica</legend>
				<div className="pnl-opciones">
					{(Object.keys(NIVELES) as Ct[]).map((k) => (
						<label key={k} className="pnl-opcion">
							<input
								type="radio"
								name={`${id}-ct`}
								value={k}
								checked={ct === k}
								onChange={() => {
									setCt(k);
									// Cv siempre dentro del rango del nivel elegido.
									setCv((v) => (v ? cvEnRango(k, v) : 0));
								}}
							/>
							<span>
								<b>
									{k}: {NIVELES[k]} (Cv {RANGOS[k][0]} a {RANGOS[k][1]})
								</b>{" "}
								{rubrica.fondo[k].como}
							</span>
						</label>
					))}
				</div>
			</fieldset>
			{ct ? (
				<fieldset className="pnl-criterio" disabled={deshabilitado}>
					<legend>
						Cv: valor de fondo para un caso {NIVELES[ct].toLowerCase()} ({RANGOS[ct][0]} a {RANGOS[ct][1]})
					</legend>
					<div className="pnl-opciones">
						{Object.entries(rubrica.fondo[ct].guia).map(([n, guia]) => (
							<label key={n} className="pnl-opcion">
								<input
									type="radio"
									name={`${id}-cv`}
									value={n}
									checked={cv === Number(n)}
									onChange={() => setCv(Number(n))}
								/>
								<span>
									<b>{n}</b> {guia}
								</span>
							</label>
						))}
					</div>
				</fieldset>
			) : (
				<p className="pnl-nota">Elija primero el nivel (Ct) para ver los valores de Cv que le corresponden.</p>
			)}

			<p className="pnl-total" role="status">
				Puntaje total (forma + Cv): <b className="num">{total ?? "—"}</b>
			</p>

			<div className="pnl-criterio">
				<label className="pnl-check">
					<input type="checkbox" checked={!valida} onChange={(e) => setValida(!e.target.checked)} disabled={deshabilitado} />
					<span>Esta pregunta no es válida (no cuenta para premios ni para la gratificación)</span>
				</label>
				{/* Reunión del 20-oct (Isabella 15:21): qué no es una pregunta válida. */}
				<p className="pnl-ayuda-campo">
					No es válida si no es una consulta (un saludo, “soy pescador”, una prueba) o si no tiene que ver con las
					playas.
				</p>
			</div>
			<div className="pnl-campo">
				<label htmlFor={`${id}-obs`}>Observaciones</label>
				<textarea
					id={`${id}-obs`}
					className="pnl-textarea"
					rows={3}
					value={obs}
					onChange={(e) => setObs(e.target.value)}
					disabled={deshabilitado}
				/>
			</div>
			{faltan ? (
				<p id={`${id}-faltan`} className="pnl-error-linea" role="alert">
					{faltan}
				</p>
			) : null}
			<p style={{ marginTop: 14 }}>
				<button type="submit" className="pnl-btn" disabled={deshabilitado || enviando}>
					{enviando ? "Guardando…" : textoBoton}
				</button>
			</p>
		</form>
	);
}

/** Una calificación ya guardada, en lectura (para comparar en el comité). */
export function TarjetaCalificacion({ c, titulo }: { c: CalificacionOut; titulo: string }) {
	return (
		<div className="pnl-tarjeta-cal">
			<h3>{titulo}</h3>
			<p className="pnl-fila-meta">
				<span>{c.evaluador}</span>
				{c.sede ? <span>{c.sede}</span> : null}
			</p>
			<dl>
				<div>
					<dt>F1, F2, F3</dt>
					<dd className="num">
						{c.f1}, {c.f2}, {c.f3} (forma {c.forma})
					</dd>
				</div>
				<div>
					<dt>Nivel</dt>
					<dd>
						{c.ct}: {NIVELES[c.ct]}
					</dd>
				</div>
				<div>
					<dt>Cv</dt>
					<dd className="num">{c.cv}</dd>
				</div>
				<div>
					<dt>Total</dt>
					<dd className="pnl-veces num">{c.total}</dd>
				</div>
				<div>
					<dt>Válida</dt>
					<dd>{c.valida ? "Sí" : "No"}</dd>
				</div>
			</dl>
			{c.observaciones ? <p className="pnl-esperaba">“{c.observaciones}”</p> : null}
		</div>
	);
}
