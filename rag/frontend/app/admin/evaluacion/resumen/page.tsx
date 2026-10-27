"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/AuthProvider";
import { cuantas, diaMesCalendario, mensajeError, numero, recortar } from "@/lib/admin/panel";
import { nombreTipo } from "@/lib/admin/cuentas";
import {
	NIVELES,
	RANGOS,
	descargarPlanilla,
	elegirGanadora,
	quitarGanadora,
	pedirPremios,
	pedirResumenEjercicio,
	rolComite,
	type Ct,
	type Premios,
	type ResumenEjercicio,
} from "@/lib/admin/evaluacion";
import { ChipNivel, ChipEstado, IconoAviso, IconoDescargar } from "@/components/admin/panel/Estados";
import { CabezaPestana, EncabezadoEvaluacion } from "@/components/admin/evaluacion/SubNav";
import { ResultadoJunto, useAccion } from "@/components/admin/panel/Resultado";
import { Aparece } from "@/components/admin/panel/Aparece";
import { Tablero } from "@/components/admin/evaluacion/Tablero";

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
			<EncabezadoEvaluacion />
			<CabezaPestana
				titulo="Resumen y premios"
				acciones={
					comite ? (
						<button type="button" className="pnl-btn-sec" onClick={exportar}>
							<IconoDescargar />
							Descargar planilla en Excel
						</button>
					) : null
				}
			>
				Avance de la evaluación con las cifras de la hoja “Resumen” de la planilla. Toque cualquier número para ver esas preguntas.
			</CabezaPestana>

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
				<Tablero
					resumen={resumen}
					comite={comite}
					ganadores={comite && premios ? <Ganadores premios={premios} cerrado={!!resumen.cerrado} /> : null}
				/>
			) : null}

			{comite && resumen ? <Concordancia resumen={resumen} /> : null}
			{comite && premios ? <SeccionPremios premios={premios} onCambio={setPremios} /> : null}
			{!comite && resumen ? (
				<p className="pnl-nota">Los premios y la descarga de la planilla los ve el comité.</p>
			) : null}
		</div>
	);
}


function SeccionPremios({ premios, onCambio }: { premios: Premios; onCambio: (p: Premios) => void }) {
	const [verTodos, setVerTodos] = useState(false);
	return (
		<>
			<section className="pnl-bloque" aria-labelledby="t-mejor">
				<h2 id="t-mejor">Premio: mejor pregunta del ejercicio</h2>
				<p className="pnl-sub pnl-mb">
					Mayor puntaje de fondo (Cv) en cada nivel, solo preguntas válidas. Si hay empate en el valor de fondo, decide el
					comité por pertinencia jurídica.
				</p>
				<ol className="pnl-filas">
					{(Object.keys(NIVELES) as Ct[]).map((k) => (
						<NivelPremio key={k} nivel={k} n={premios.mejor_pregunta[k]} onCambio={onCambio} />
					))}
				</ol>
			</section>

			<section className="pnl-bloque" aria-labelledby="t-constancia">
				<h2 id="t-constancia">Premio: participación más constante</h2>
				<p className="pnl-sub pnl-mb">
					Más días distintos con preguntas válidas; si empatan, más preguntas válidas; si siguen empatados,
					mayor puntaje acumulado.
				</p>
				<TablaRanking filas={premios.participacion_constante} destacar />
			</section>

			<section className="pnl-bloque" aria-labelledby="t-grat">
				<h2 id="t-grat">Puntaje acumulado por participante (gratificación)</h2>
				<p className="pnl-sub pnl-mb">
					Suma del puntaje total de sus preguntas válidas con calificación oficial.
				</p>
				<TablaRanking filas={premios.gratificacion} />
			</section>

			<section className="pnl-bloque" aria-labelledby="t-dias">
				<h2 id="t-dias">Participación por día</h2>
				<p className="pnl-sub pnl-mb">
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
									<td>{f.dias.map(diaMesCalendario).join(", ")}</td>
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
				{cuantas(total, "pregunta empatada", "preguntas empatadas")} con el mismo valor de fondo.
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


/** T8 (reunión del 20-oct): los 4 ganadores, listos para el evento del 11 dic. */
function Ganadores({ premios, cerrado }: { premios: Premios; cerrado: boolean }) {
	const niveles: Ct[] = ["S", "I", "A"];
	const constante = premios.participacion_constante;
	const empateConstancia = constante.filter((f) => (f as { empate?: boolean }).empate).length > 1;
	return (
		<section className="pnl-bloque" aria-labelledby="t-ganadores">
			<h2 id="t-ganadores">Ganadores {cerrado ? "" : "(provisional)"}</h2>
			<p className="pnl-sub pnl-mb">
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
							<p className="pnl-ganador-tit">
								Mejor pregunta: <ChipNivel ct={n} texto={`nivel ${NIVELES[n].toLowerCase()}`} />
							</p>
							{r.ganadora ? (
								<>
									<p className="pnl-ganador-quien">{r.ganadora.codigo}</p>
									<p className="pnl-ganador-det">
										Valor de fondo {r.ganadora.cv}: “{recortar(r.ganadora.texto, 140)}”
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
	// PQ-87: dos decimales (0,993 no debe verse como "1").
	const v = (x: number | null | undefined) =>
		x === null || x === undefined ? "—" : x.toLocaleString("es-CO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	return (
		<section className="pnl-bloque" aria-labelledby="t-conc">
			<h2 id="t-conc">Acuerdo entre Santa Marta y Barranquilla</h2>
			<p className="pnl-sub pnl-mb">
				En {cuantas(c.pares, "pregunta", "preguntas")} con las dos evaluaciones. Kappa y alfa van de 0 (acuerdo por azar) a 1 (acuerdo
				total); sobre 0,6 se considera bueno.
			</p>
			<dl className="pnl-cifras pnl-cifras-4">
				<div className="pnl-cifra">
					<dt>Mismo nivel</dt>
					<dd>
						<span className="pnl-valor num">{c.mismo_nivel}&nbsp;%</span>
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
						<span className="pnl-valor num">{c.misma_validez}&nbsp;%</span>
					</dd>
				</div>
			</dl>
			{c.alfa ? (
				<p className="pnl-nota">
					Qué tanto coinciden los semilleristas, de 0 a 1 (alfa de Krippendorff): F1 {v(c.alfa.f1)}, F2 {v(c.alfa.f2)}, F3 {v(c.alfa.f3)}, valor de fondo {v(c.alfa.cv)}.
				</p>
			) : null}
		</section>
	);
}

/**
 * Un nivel del premio. PQ-107: la elección del comité tiene su contraria
 * ("Quitar la elección", con confirmación y registro en el historial); al
 * quitarla, el nivel vuelve al empate y se puede elegir otra. J6-A1: el
 * resultado sale junto al botón.
 */
function NivelPremio({
	nivel: k,
	n,
	onCambio,
}: {
	nivel: Ct;
	n: Premios["mejor_pregunta"][Ct];
	onCambio: (p: Premios) => void;
}) {
	const acc = useAccion();
	const [confirmar, setConfirmar] = useState(false);
	const elegida = n.ganadora !== null && n.decide_comite;

	async function elegir(id: string) {
		await acc.correr(
			async () => {
				onCambio(await elegirGanadora(k, id));
				return `Ganadora del nivel ${NIVELES[k].toLowerCase()} elegida.`;
			},
			{ error: "No se pudo guardar la ganadora." },
		);
	}

	async function quitar() {
		await acc.correr(
			async () => {
				onCambio(await quitarGanadora(k));
				setConfirmar(false);
				return "Elección quitada: puede elegir otra entre las empatadas.";
			},
			{ error: "No se pudo quitar la elección." },
		);
	}

	return (
		<li className="pnl-fila">
			<div className="pnl-fila-q">
				<div className="pnl-titulo-estado">
					<p className="pnl-fila-titulo" style={{ margin: 0 }}>
						<ChipNivel ct={k} texto={`Nivel ${NIVELES[k].toLowerCase()}`} />
					</p>
					{elegida ? (
						<ChipEstado tono="bien">Elegida por el comité</ChipEstado>
					) : n.decide_comite ? (
						<ChipEstado tono="ojo">
							<IconoAviso />
							Empate: decide el comité
						</ChipEstado>
					) : null}
				</div>
				{n.ganadora ? (
					<p style={{ margin: 0 }}>
						<span className="pnl-etq">{n.ganadora.codigo}</span>
						{recortar(n.ganadora.texto, 240)}
					</p>
				) : n.decide_comite ? (
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
											<button
												type="button"
												className="pnl-btn-sec"
												disabled={acc.enviando}
												onClick={() => elegir(f.message_id)}
											>
												Elegir como ganadora<span className="sr"> del nivel {NIVELES[k]}</span>
											</button>
										</p>
									</li>
								))}
							</ul>
						)}
					/>
				) : (
					<p className="pnl-vacio">Todavía no hay preguntas válidas de este nivel.</p>
				)}
				{elegida && !confirmar ? (
					<div className="pnl-acciones">
						<button type="button" className="pnl-btn-sec" onClick={() => setConfirmar(true)}>
							Cambiar o quitar la elección<span className="sr"> del nivel {NIVELES[k]}</span>
						</button>
					</div>
				) : null}
				<Aparece abierto={confirmar} enfocar>
					<div className="pnl-confirmar" role="group" aria-labelledby={`t-quitar-${k}`}>
						<p id={`t-quitar-${k}`}>
							¿Quitar la ganadora elegida del nivel {NIVELES[k].toLowerCase()}? El nivel vuelve al empate y podrá
							elegir otra. Queda en el historial de cambios.
						</p>
						<div className="pnl-acciones">
							<button type="button" className="pnl-btn" disabled={acc.enviando} onClick={quitar}>
								Sí, quitar la elección
							</button>
							<button type="button" className="pnl-btn-sec" data-foco onClick={() => setConfirmar(false)}>
								Cancelar
							</button>
						</div>
					</div>
				</Aparece>
				<ResultadoJunto resultado={acc.resultado} />
			</div>
			<dl className="pnl-fila-estado">
				<div>
					<dt>Valor de fondo (Cv)</dt>
					<dd className="pnl-veces num">
						{n.ganadora?.cv ?? n.empatadas[0]?.cv ?? "—"} de {RANGOS[k][1]}
					</dd>
				</div>
			</dl>
		</li>
	);
}
