"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { decimal, mensajeError, numero, recortar } from "@/lib/admin/panel";
import { diaLargo } from "@/lib/admin/calendario";
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
								<span className="pnl-det">
									{resumen.solo_revisadas
										? "Validadas por el comité"
										: "Final del comité, o dos concordantes aún por validar"}
								</span>
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

			{comite && premios ? <Ganadores premios={premios} cerrado={!!resumen?.cerrado} /> : null}
			{comite && resumen ? <AvancePlazo resumen={resumen} /> : null}
			{comite && resumen ? <Concordancia resumen={resumen} /> : null}
			{comite && premios ? <PorValidar premios={premios} /> : null}
			{comite && premios ? <SeccionPremios premios={premios} onElegir={elegir} /> : null}
			{!comite && resumen ? (
				<p className="pnl-nota">Los premios y la descarga de la planilla los ve el comité.</p>
			) : null}
		</div>
	);
}

/**
 * Reunión del 20-oct (T2): nada cuenta para premios hasta que la validación
 * jurídica esté de acuerdo con las dos evaluaciones de la pregunta.
 */
function PorValidar({ premios }: { premios: Premios }) {
	const n = premios.por_validar;
	if (!premios.solo_revisadas || n === 0) return null;
	return (
		<section className="pnl-aviso" aria-labelledby="t-por-validar">
			<IconoAviso />
			<div>
				<h2 id="t-por-validar" className="pnl-aviso-titulo">
					Faltan {numero(n)} evaluaciones por validar
				</h2>
				<p>
					Todavía no cuentan para los premios: según el documento del ejercicio, el comité valida todas las
					evaluaciones.
				</p>
				<div className="pnl-acciones">
					<a className="pnl-btn-sec" href="/admin/evaluacion/validar">
						Ir a validar
					</a>
				</div>
			</div>
		</section>
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
	filas: { codigo: string; dias: number; preguntas_validas: number; puntaje: number; empate?: boolean }[];
	destacar?: boolean;
}) {
	if (!filas.length) return <p className="pnl-vacio">Todavía no hay preguntas válidas con calificación oficial.</p>;
	const empatados = destacar ? filas.filter((f) => f.empate) : [];
	return (
		<>
		{empatados.length > 1 ? (
			<p className="pnl-aviso" role="note">
				<b>Empate: decide el comité.</b> {empatados.map((f) => f.codigo).join(", ")} tienen los mismos días,
				preguntas válidas y puntaje; la app no desempata.
			</p>
		) : null}
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
								{destacar && f.empate ? <b> (empatado en el primer puesto)</b> : null}
								{destacar && i === 0 && !f.empate ? <b> (primer puesto)</b> : null}
							</td>
							<td className="num">{numero(f.dias)}</td>
							<td className="num">{numero(f.preguntas_validas)}</td>
							<td className="num">{numero(f.puntaje)}</td>
						</tr>
					))}
				</tbody>
			</table>
		</div>
		</>
	);
}

/**
 * T6 (reunión del 20-oct: "cada 2 días, media hora"): quién va al día y
 * cuántas por día le faltan para llegar a su plazo.
 */
function AvancePlazo({ resumen }: { resumen: ResumenEjercicio }) {
	const evaluadores = resumen.avance_evaluadores.filter((a) => a.asignadas !== undefined);
	const validadores = resumen.avance_validadores ?? [];
	if (!evaluadores.length && !validadores.length) return null;
	return (
		<section className="pnl-bloque" aria-labelledby="t-plazo">
			<h2 id="t-plazo">Avance frente al plazo</h2>
			{resumen.fin_evaluacion ? (
				<p className="pnl-sub" style={{ marginBottom: 12 }}>
					Semilleristas hasta el {diaLargo(resumen.fin_evaluacion)}; validación hasta el{" "}
					{diaLargo(resumen.fin_validacion ?? resumen.fin_evaluacion)}. “Al día” es cuántas tendría que hacer cada día
					para llegar.
				</p>
			) : null}
			<div className="pnl-tabla-datos" role="region" aria-label="Avance de los semilleristas" tabIndex={0}>
				<table>
					<caption>Semilleristas</caption>
					<thead>
						<tr>
							<th scope="col">Semillerista</th>
							<th scope="col">Sede</th>
							<th scope="col" className="num">Asignadas</th>
							<th scope="col" className="num">Evaluadas</th>
							<th scope="col" className="num">Sin evaluar</th>
							<th scope="col" className="num">Al día</th>
						</tr>
					</thead>
					<tbody>
						{evaluadores.map((a) => (
							<tr key={`${a.evaluador}-${a.sede}`}>
								<td>{a.evaluador}</td>
								<td>{a.sede ?? "—"}</td>
								<td className="num">{numero(a.asignadas ?? 0)}</td>
								<td className="num">{numero(a.evaluadas)}</td>
								<td className="num">{numero(a.pendientes ?? 0)}</td>
								<td className="num">{decimal(a.por_dia ?? 0)}</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
			{validadores.length ? (
				<div className="pnl-tabla-datos" role="region" aria-label="Avance de la validación" tabIndex={0} style={{ marginTop: 16 }}>
					<table>
						<caption>Validación jurídica</caption>
						<thead>
							<tr>
								<th scope="col">Validadora</th>
								<th scope="col">Sede</th>
								<th scope="col" className="num">Evaluaciones</th>
								<th scope="col" className="num">Validadas</th>
								<th scope="col" className="num">Por validar</th>
								<th scope="col" className="num">Al día</th>
							</tr>
						</thead>
						<tbody>
							{validadores.map((v) => (
								<tr key={v.validador}>
									<td>{v.validador}</td>
									<td>{v.sede ?? "—"}</td>
									<td className="num">{numero(v.evaluaciones)}</td>
									<td className="num">{numero(v.validadas)}</td>
									<td className="num">{numero(v.pendientes)}</td>
									<td className="num">{decimal(v.por_dia)}</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			) : null}
		</section>
	);
}

/** T8 (reunión del 20-oct): los 4 ganadores, listos para el evento del 11 dic. */
function Ganadores({ premios, cerrado }: { premios: Premios; cerrado: boolean }) {
	const niveles: Ct[] = ["S", "I", "A"];
	const constante = premios.participacion_constante;
	const empateConstancia = constante.filter((f) => (f as { empate?: boolean }).empate).length > 1;
	return (
		<section className="pnl-bloque" aria-labelledby="t-ganadores">
			<h2 id="t-ganadores">Ganadores {cerrado ? "" : "(provisional)"}</h2>
			<p className="pnl-sub" style={{ marginBottom: 12 }}>
				{cerrado
					? "El ejercicio está cerrado: estos son los resultados finales."
					: "Cambia a medida que se validan evaluaciones; queda fijo al cerrar el ejercicio."}{" "}
				Bono de $150.000 cada uno.
			</p>
			<ol className="pnl-ganadores">
				{niveles.map((n) => {
					const r = premios.mejor_pregunta[n];
					return (
						<li key={n}>
							<p className="pnl-ganador-tit">Mejor pregunta: nivel {NIVELES[n].toLowerCase()}</p>
							{r.ganadora ? (
								<>
									<p className="pnl-ganador-quien">{r.ganadora.codigo}</p>
									<p className="pnl-ganador-det">
										Cv {r.ganadora.cv}: “{recortar(r.ganadora.texto, 140)}”
									</p>
								</>
							) : r.decide_comite ? (
								<p className="pnl-ganador-det">Empate: decide el comité ({r.empatadas.length} preguntas)</p>
							) : (
								<p className="pnl-ganador-det">Todavía no hay preguntas válidas validadas.</p>
							)}
						</li>
					);
				})}
				<li>
					<p className="pnl-ganador-tit">Participación más constante</p>
					{constante.length ? (
						empateConstancia ? (
							<p className="pnl-ganador-det">Empate: decide el comité</p>
						) : (
							<>
								<p className="pnl-ganador-quien">{constante[0].codigo}</p>
								<p className="pnl-ganador-det">
									{constante[0].dias} días con preguntas válidas, {constante[0].preguntas_validas} preguntas
								</p>
							</>
						)
					) : (
						<p className="pnl-ganador-det">Todavía no hay preguntas válidas validadas.</p>
					)}
				</li>
			</ol>
		</section>
	);
}

/** E2: qué tanto coinciden las dos sedes (resultado para el informe del ejercicio). */
function Concordancia({ resumen }: { resumen: ResumenEjercicio }) {
	const c = resumen.concordancia;
	if (!c || !c.pares) return null;
	const v = (x: number | null | undefined) => (x === null || x === undefined ? "—" : decimal(x));
	return (
		<section className="pnl-bloque" aria-labelledby="t-conc">
			<h2 id="t-conc">Acuerdo entre Santa Marta y Barranquilla</h2>
			<p className="pnl-sub" style={{ marginBottom: 12 }}>
				En {numero(c.pares)} preguntas con las dos evaluaciones. Kappa y alfa van de 0 (acuerdo por azar) a 1 (acuerdo
				total); sobre 0,6 se considera bueno.
			</p>
			<dl className="pnl-cifras pnl-cifras-4">
				<div className="pnl-cifra">
					<dt>Mismo nivel</dt>
					<dd>
						<span className="pnl-valor num">{c.mismo_nivel}%</span>
					</dd>
				</div>
				<div className="pnl-cifra">
					<dt>Kappa ponderada del nivel</dt>
					<dd>
						<span className="pnl-valor num">{v(c.kappa_nivel)}</span>
					</dd>
				</div>
				<div className="pnl-cifra">
					<dt>Diferencia media de puntaje</dt>
					<dd>
						<span className="pnl-valor num">{v(c.diferencia_media_total)}</span>
					</dd>
				</div>
				<div className="pnl-cifra">
					<dt>Misma validez</dt>
					<dd>
						<span className="pnl-valor num">{c.misma_validez}%</span>
					</dd>
				</div>
			</dl>
			{c.alfa ? (
				<p className="pnl-nota">
					Alfa de Krippendorff (ordinal): F1 {v(c.alfa.f1)}, F2 {v(c.alfa.f2)}, F3 {v(c.alfa.f3)}, Cv {v(c.alfa.cv)}.
				</p>
			) : null}
		</section>
	);
}

