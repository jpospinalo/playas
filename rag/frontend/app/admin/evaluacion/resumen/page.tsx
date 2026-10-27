"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { decimal, mensajeError, numero, recortar } from "@/lib/admin/panel";
import { nombreTipo } from "@/lib/admin/cuentas";
import {
	NIVELES,
	RANGOS,
	TEXTO_ESTADO,
	descargarPlanilla,
	elegirGanadora,
	pedirPremios,
	pedirResumenEjercicio,
	rolComite,
	type Ct,
	type EstadoPregunta,
	type Premios,
	type ResumenEjercicio,
} from "@/lib/admin/evaluacion";
import { IconoAviso, IconoDescargar } from "@/components/admin/panel/Estados";
import { SubNavEvaluacion } from "@/components/admin/evaluacion/SubNav";

/**
 * Resumen del ejercicio (como la hoja "Resumen" de la planilla), avance por
 * semillerista y, para el comité, los dos premios del documento, el puntaje
 * acumulado para la gratificación, la participación por día y la descarga
 * de la planilla en Excel.
 */
export default function PaginaResumenEjercicio() {
	const { role } = useAuth();
	const comite = rolComite(role);
	const [resumen, setResumen] = useState<ResumenEjercicio | null>(null);
	const [premios, setPremios] = useState<Premios | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [errorAccion, setErrorAccion] = useState<string | null>(null);

	useEffect(() => {
		let vigente = true;
		Promise.all([pedirResumenEjercicio(), comite ? pedirPremios() : Promise.resolve(null)])
			.then(([r, p]) => {
				if (vigente) {
					setResumen(r);
					setPremios(p);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudo cargar el resumen."));
			});
		return () => {
			vigente = false;
		};
	}, [comite]);

	async function elegir(nivel: Ct, id: string) {
		setErrorAccion(null);
		try {
			setPremios(await elegirGanadora(nivel, id));
		} catch (e) {
			setErrorAccion(mensajeError(e, "No se pudo guardar la ganadora."));
		}
	}

	async function exportar() {
		setErrorAccion(null);
		try {
			await descargarPlanilla();
		} catch (e) {
			setErrorAccion(mensajeError(e, "No se pudo descargar la planilla."));
		}
	}

	return (
		<div className="pnl-pag">
			<title>Resumen del ejercicio: evaluación de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Resumen del ejercicio</h1>
					<p className="pnl-sub">Avance de la evaluación con las cifras de la hoja “Resumen” de la planilla.</p>
				</div>
				{comite ? (
					<div className="pnl-controles">
						<button type="button" className="pnl-btn-sec" onClick={exportar}>
							<IconoDescargar />
							Descargar planilla en Excel
						</button>
					</div>
				) : null}
			</div>
			<SubNavEvaluacion />

			{error || errorAccion ? (
				<div className="pnl-error" role="alert">
					<IconoAviso />
					<div>
						<b>Algo no salió bien.</b>
						<p>{error ?? errorAccion}</p>
					</div>
				</div>
			) : null}
			{!resumen && !error ? <p className="pnl-cargando">Cargando resumen…</p> : null}

			{resumen ? (
				<>
					<dl className="pnl-cifras pnl-cifras-5">
						<div className="pnl-cifra">
							<dt>Preguntas registradas</dt>
							<dd>
								<span className="pnl-valor num">{numero(resumen.preguntas_registradas)}</span>
								<span className="pnl-det">De participantes con número</span>
							</dd>
						</div>
						<div className="pnl-cifra">
							<dt>Con calificación oficial</dt>
							<dd>
								<span className="pnl-valor num">{numero(resumen.evaluadas)}</span>
								<span className="pnl-det">Final del comité o dos concordantes</span>
							</dd>
						</div>
						<div className="pnl-cifra">
							<dt>Con diferencias</dt>
							<dd>
								<span className="pnl-valor num">{numero(resumen.estados.con_diferencias)}</span>
								<span className="pnl-det">
									Esperan al comité (umbral: {resumen.umbral_diferencia} puntos o distinto nivel)
								</span>
							</dd>
						</div>
						<div className="pnl-cifra">
							<dt>Promedio puntaje total</dt>
							<dd>
								<span className="pnl-valor num">{decimal(resumen.promedio_total)}</span>
								<span className="pnl-det">Solo preguntas válidas, de 6 a 21</span>
							</dd>
						</div>
						<div className="pnl-cifra">
							<dt>No válidas</dt>
							<dd>
								<span className="pnl-valor num">{numero(resumen.no_validas)}</span>
								<span className="pnl-det">No cuentan para premios</span>
							</dd>
						</div>
					</dl>

					<div className="pnl-grid">
						<section className="pnl-bloque pnl-c4" aria-labelledby="t-niveles">
							<h2 id="t-niveles">Casos por nivel</h2>
							<p className="pnl-sub">Preguntas válidas con calificación oficial</p>
							<ul className="pnl-lista-simple">
								{(Object.keys(NIVELES) as Ct[]).map((k) => (
									<li key={k}>
										<span>
											Casos {NIVELES[k].toLowerCase()}s (Cv {RANGOS[k][0]} a {RANGOS[k][1]})
										</span>
										<b className="num">{numero(resumen.por_nivel[k])}</b>
									</li>
								))}
							</ul>
						</section>
						<section className="pnl-bloque pnl-c4" aria-labelledby="t-estados">
							<h2 id="t-estados">Estado de la evaluación</h2>
							<ul className="pnl-lista-simple">
								{(Object.keys(TEXTO_ESTADO) as EstadoPregunta[]).map((k) => (
									<li key={k}>
										<span>{TEXTO_ESTADO[k]}</span>
										<b className="num">{numero(resumen.estados[k])}</b>
									</li>
								))}
							</ul>
						</section>
						<section className="pnl-bloque pnl-c4" aria-labelledby="t-avance">
							<h2 id="t-avance">Avance por semillerista</h2>
							{resumen.avance_evaluadores.length ? (
								<ul className="pnl-lista-simple">
									{resumen.avance_evaluadores.map((a) => (
										<li key={`${a.evaluador}-${a.sede}`}>
											<span>
												{a.evaluador}
												{a.sede ? <small className="pnl-sede"> {a.sede}</small> : null}
											</span>
											<b className="num">{numero(a.evaluadas)}</b>
										</li>
									))}
								</ul>
							) : (
								<p className="pnl-vacio">Todavía nadie ha calificado.</p>
							)}
						</section>
					</div>
				</>
			) : null}

			{comite && premios ? <SeccionPremios premios={premios} onElegir={elegir} /> : null}
			{!comite && resumen ? (
				<p className="pnl-nota">Los premios y la descarga de la planilla los ve el comité.</p>
			) : null}
		</div>
	);
}

function SeccionPremios({ premios, onElegir }: { premios: Premios; onElegir: (n: Ct, id: string) => void }) {
	const [verTodos, setVerTodos] = useState(false);
	return (
		<>
			<section className="pnl-bloque" aria-labelledby="t-mejor">
				<h2 id="t-mejor">Premio: mejor pregunta del ejercicio</h2>
				<p className="pnl-sub" style={{ marginBottom: 12 }}>
					Mayor puntaje de fondo (Cv) en cada nivel, solo preguntas válidas. Si hay empate en Cv, decide el
					comité por pertinencia jurídica.
				</p>
				<ol className="pnl-filas">
					{(Object.keys(NIVELES) as Ct[]).map((k) => {
						const n = premios.mejor_pregunta[k];
						return (
							<li key={k} className="pnl-fila">
								<div className="pnl-fila-q">
									<p className="pnl-fila-titulo" style={{ margin: 0 }}>
										Nivel {NIVELES[k].toLowerCase()}
									</p>
									{n.ganadora ? (
										<>
											<p style={{ margin: "6px 0 0" }}>
												<span className="pnl-etq">{n.ganadora.codigo}</span>
												{recortar(n.ganadora.texto, 240)}
											</p>
										</>
									) : n.decide_comite ? (
										<>
											<p className="pnl-estado ojo" style={{ margin: "6px 0" }}>
												<IconoAviso />
												Empate: decide el comité
											</p>
											<Empatadas
												total={n.empatadas.length}
												render={(cuantas) => (
											<ul className="pnl-empatadas">
												{n.empatadas.slice(0, cuantas).map((f) => (
													<li key={f.message_id}>
														<p style={{ margin: 0 }}>
															<span className="pnl-etq">{f.codigo}</span>
															{recortar(f.texto, 200)}
														</p>
														<p style={{ margin: "6px 0 0" }}>
															<Link href={`/admin/evaluacion/pregunta?id=${encodeURIComponent(f.message_id)}`}>
																Leer la pregunta
															</Link>{" "}
															<button type="button" className="pnl-btn-sec" onClick={() => onElegir(k, f.message_id)}>
																Elegir como ganadora<span className="sr"> del nivel {NIVELES[k]}</span>
															</button>
														</p>
													</li>
												))}
											</ul>
												)}
											/>
										</>
									) : (
										<p className="pnl-vacio">Todavía no hay preguntas válidas de este nivel.</p>
									)}
								</div>
								<dl className="pnl-fila-estado">
									<div>
										<dt>Cv</dt>
										<dd className="pnl-veces num">
											{n.ganadora?.cv ?? n.empatadas[0]?.cv ?? "—"} de {RANGOS[k][1]}
										</dd>
									</div>
								</dl>
							</li>
						);
					})}
				</ol>
			</section>

			<section className="pnl-bloque" aria-labelledby="t-constancia">
				<h2 id="t-constancia">Premio: participación más constante</h2>
				<p className="pnl-sub" style={{ marginBottom: 12 }}>
					Más días distintos con preguntas válidas; si empatan, más preguntas válidas; si siguen empatados,
					mayor puntaje acumulado.
				</p>
				<TablaRanking filas={premios.participacion_constante} destacar />
			</section>

			<section className="pnl-bloque" aria-labelledby="t-grat">
				<h2 id="t-grat">Puntaje acumulado por participante (gratificación)</h2>
				<p className="pnl-sub" style={{ marginBottom: 12 }}>
					Suma del puntaje total de sus preguntas válidas con calificación oficial.
				</p>
				<TablaRanking filas={premios.gratificacion} />
			</section>

			<section className="pnl-bloque" aria-labelledby="t-dias">
				<h2 id="t-dias">Participación por día</h2>
				<p className="pnl-sub" style={{ marginBottom: 12 }}>
					Días en que cada participante hizo preguntas (no es la asistencia a las sesiones).
				</p>
				<div className="pnl-tabla-datos" role="region" aria-label="Tabla de participación por día" tabIndex={0}>
					<table>
						<thead>
							<tr>
								<th scope="col">Participante</th>
								<th scope="col">Tipo</th>
								<th scope="col" className="num">
									Preguntas
								</th>
								<th scope="col" className="num">
									Días
								</th>
								<th scope="col">Fechas</th>
							</tr>
						</thead>
						<tbody>
							{premios.participacion_por_dia.slice(0, verTodos ? undefined : 15).map((f) => (
								<tr key={f.codigo}>
									<td>{f.codigo}</td>
									<td>{nombreTipo(f.tipo_playa)}</td>
									<td className="num">{numero(f.preguntas)}</td>
									<td className="num">{numero(f.dias.length)}</td>
									<td>{f.dias.join(", ")}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
				{premios.participacion_por_dia.length > 15 ? (
					<button type="button" className="pnl-enlace" aria-expanded={verTodos} onClick={() => setVerTodos((v) => !v)}>
						{verTodos ? "Ver menos" : `Ver los ${numero(premios.participacion_por_dia.length)} participantes`}
					</button>
				) : null}
			</section>
			<p className="pnl-nota">{premios.nota}</p>
		</>
	);
}

/** Con muchas empatadas se muestran 5 y un botón para ver todas. */
function Empatadas({ total, render }: { total: number; render: (n: number) => React.ReactNode }) {
	const [todas, setTodas] = useState(false);
	return (
		<>
			<p className="pnl-nota" style={{ marginTop: 0 }}>
				{numero(total)} preguntas empatadas con el mismo Cv.
			</p>
			{render(todas ? total : 5)}
			{total > 5 ? (
				<button type="button" className="pnl-enlace" aria-expanded={todas} onClick={() => setTodas((t) => !t)}>
					{todas ? "Ver menos" : `Ver las ${numero(total)} empatadas`}
				</button>
			) : null}
		</>
	);
}

function TablaRanking({
	filas,
	destacar,
}: {
	filas: { codigo: string; dias: number; preguntas_validas: number; puntaje: number }[];
	destacar?: boolean;
}) {
	if (!filas.length) return <p className="pnl-vacio">Todavía no hay preguntas válidas con calificación oficial.</p>;
	return (
		<div className="pnl-tabla-datos" role="region" aria-label="Tabla de participantes" tabIndex={0}>
			<table>
				<thead>
					<tr>
						<th scope="col" className="num">
							Puesto
						</th>
						<th scope="col">Participante</th>
						<th scope="col" className="num">
							Días con preguntas válidas
						</th>
						<th scope="col" className="num">
							Preguntas válidas
						</th>
						<th scope="col" className="num">
							Puntaje acumulado
						</th>
					</tr>
				</thead>
				<tbody>
					{filas.slice(0, 10).map((f, i) => (
						<tr key={f.codigo} className={destacar && i === 0 ? "pnl-primero" : undefined}>
							<td className="num">{i + 1}</td>
							<td>
								{f.codigo}
								{destacar && i === 0 ? <b> (primer puesto)</b> : null}
							</td>
							<td className="num">{numero(f.dias)}</td>
							<td className="num">{numero(f.preguntas_validas)}</td>
							<td className="num">{numero(f.puntaje)}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
	);
}
