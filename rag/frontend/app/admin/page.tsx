"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
	MINIMO_PARA_PORCENTAJE,
	PERIODOS,
	TEMAS_PANEL,
	cambioConteo,
	diasTranscurridos,
	mensajeError,
	cambioTasa,
	cuantas,
	cuantasDecimal,
	decimal,
	descargarCsv,
	diaMes,
	fechaLarga,
	numero,
	pedirResumen,
	porcentaje,
	tasaConBase,
	textoPorcentaje,
	tipoDocumento,
	type FiltroPersona,
	type FiltroResultado,
	type Resumen,
} from "@/lib/admin/panel";
import { TIPOS_PLAYA } from "@/lib/admin/cuentas";
import {
	Barras,
	Columnas,
	TablaSerie,
	VerComoTabla,
	type FilaBarra,
} from "@/components/admin/panel/Graficos";
import {
	Delta,
	EstadoSatisfaccion,
	IconoAviso,
	IconoDescargar,
} from "@/components/admin/panel/Estados";
import { Brechas } from "@/components/admin/panel/Brechas";
import { Recientes } from "@/components/admin/panel/Recientes";
import { AparecerSi } from "@/components/admin/panel/Aparece";
import { LimpiarFiltros } from "@/components/admin/panel/LimpiarFiltros";
import { CifraBoton, Grupo } from "@/components/admin/evaluacion/Tablero";

/**
 * Resumen del panel: qué se pregunta, sobre qué temas y normas, qué tan bien
 * responde ATLAS y dónde falla. Métricas y fórmulas: playas-notas/panel/
 * METRICAS-panel.md. Todo sale de `GET /api/admin/panel/*` (solo lectura).
 */
export default function PanelResumen() {
	return (
		<Suspense fallback={<p className="pnl-cargando">Cargando cifras…</p>}>
			<ResumenConFiltros />
		</Suspense>
	);
}

const DIAS_VALIDOS: readonly number[] = PERIODOS.map((p) => p.dias);
const RESULTADOS_VALIDOS: readonly string[] = [
	"con_fuente",
	"sin_respuesta_segura",
	"no_le_sirvio",
	"fuera_de_tema",
	"pide_aclarar",
];

/** Filtros en la URL (?dias=0&tema=obras&ver=no_le_sirvio): sobreviven a
 * recargar y a volver del detalle de una conversación (PQ-22). */
function consultaFiltros(
	dias: number,
	tema: string,
	resultado: string,
	persona: FiltroPersona = {},
): string {
	const q = new URLSearchParams();
	// Por defecto "Todo": el ejercicio dura 2 semanas (PQ-69).
	if (dias !== 0) q.set("dias", String(dias));
	if (tema) q.set("tema", tema);
	if (resultado) q.set("ver", resultado);
	if (persona.participante) q.set("part", persona.participante);
	if (persona.tipo) q.set("tipo", String(persona.tipo));
	return q.toString();
}

function ResumenConFiltros() {
	const sp = useSearchParams();
	const [dias, setDias] = useState<number>(() => {
		const d = Number(sp.get("dias"));
		return sp.has("dias") && DIAS_VALIDOS.includes(d) ? d : 0;
	});
	const [tema, setTema] = useState<string>(() => {
		const t = sp.get("tema") ?? "";
		return TEMAS_PANEL.some((x) => x.id === t) ? t : "";
	});
	const [resultado, setResultado] = useState<FiltroResultado>(() => {
		const r = sp.get("ver") ?? "";
		return (RESULTADOS_VALIDOS.includes(r) ? r : "") as FiltroResultado;
	});
	// Filtro por persona del ejercicio (número de participante y tipo de playa).
	const [participante, setParticipante] = useState<string>(() =>
		(sp.get("part") ?? "").toUpperCase().slice(0, 20),
	);
	const [borradorPart, setBorradorPart] = useState(participante);
	const [tipo, setTipo] = useState<number>(() => {
		const n = Number(sp.get("tipo"));
		return n >= 1 && n <= 5 ? n : 0;
	});
	const persona = useMemo<FiltroPersona>(
		() => ({ participante: participante || undefined, tipo: tipo || undefined }),
		[participante, tipo],
	);
	const consulta = consultaFiltros(dias, tema, resultado, persona);

	function escribirUrl(d: number, t: string, r: string, p: FiltroPersona = persona) {
		const q = consultaFiltros(d, t, r, p);
		// PQ-119: replaceState (Next lo sincroniza con useSearchParams) no vuelve a
		// resolver los metadatos, así el título del Resumen no se pierde.
		window.history.replaceState(null, "", q ? `/admin?${q}` : "/admin");
	}

	function cambiarParticipante(valor: string) {
		const limpio = valor.trim().toUpperCase().slice(0, 20);
		if (limpio === participante) return;
		setCargando(true);
		setParticipante(limpio);
		escribirUrl(dias, tema, resultado, { participante: limpio || undefined, tipo: tipo || undefined });
	}

	function cambiarTipo(n: number) {
		setCargando(true);
		setTipo(n);
		escribirUrl(dias, tema, resultado, { participante: participante || undefined, tipo: n || undefined });
	}
	const [datos, setDatos] = useState<Resumen | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [cargando, setCargando] = useState(true);
	const [intento, setIntento] = useState(0);
	const [anuncio, setAnuncio] = useState("");
	const [errorCsv, setErrorCsv] = useState<string | null>(null);

	useEffect(() => {
		let vigente = true;
		pedirResumen(dias, tema, persona)
			.then((r) => {
				if (!vigente) return;
				setDatos(r);
				setError(null);
				setAnuncio(`${textoPeriodo(dias)}: ${cuantas(r.cifras.preguntas, "pregunta", "preguntas")}.`);
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudieron cargar las cifras."));
			})
			.finally(() => {
				if (vigente) setCargando(false);
			});
		return () => {
			vigente = false;
		};
	}, [dias, tema, intento, persona]);

	function cambiarDias(d: number) {
		setCargando(true);
		setDias(d);
		escribirUrl(d, tema, resultado);
	}

	function cambiarTema(t: string) {
		setCargando(true);
		setTema(t);
		escribirUrl(dias, t, resultado);
	}

	// PQ-108: la contraria de los filtros (el periodo se queda como está).
	function limpiarFiltros() {
		setCargando(true);
		setTema("");
		setResultado("");
		setParticipante("");
		setBorradorPart("");
		setTipo(0);
		escribirUrl(dias, "", "", {});
	}

	function cambiarResultado(r: FiltroResultado) {
		setResultado(r);
		escribirUrl(dias, tema, r);
	}

	async function csv() {
		setErrorCsv(null);
		try {
			await descargarCsv(dias, tema, "", persona);
		} catch (e) {
			setErrorCsv(mensajeError(e, "No se pudo descargar el archivo."));
		}
	}

	return (
		<div className="pnl-pag">
			<title>Resumen del panel de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Resumen</h1>
					<p className="pnl-sub">{datos ? subtituloPeriodo(datos) : " "}</p>
				</div>
				<div className="pnl-controles">
					<fieldset className="pnl-periodo">
						<legend>Periodo</legend>
						<div className="pnl-seg">
							{PERIODOS.map((p) => (
								<label key={p.dias}>
									<input
										type="radio"
										name="periodo"
										value={p.dias}
										checked={dias === p.dias}
										onChange={() => cambiarDias(p.dias)}
									/>
									<span>{p.texto}</span>
								</label>
							))}
						</div>
					</fieldset>
					<div className="pnl-campo">
						<label htmlFor="pnl-tema">Tema</label>
						<select id="pnl-tema" value={tema} onChange={(e) => cambiarTema(e.target.value)}>
							<option value="">Todos los temas</option>
							{TEMAS_PANEL.map((t) => (
								<option key={t.id} value={t.id}>
									{t.titulo}
								</option>
							))}
						</select>
					</div>
					<div className="pnl-campo">
						<label htmlFor="pnl-part">Participante</label>
						<input
							id="pnl-part"
							placeholder="Ej.: P007"
							className="pnl-input"
							value={borradorPart}
							onChange={(e) => setBorradorPart(e.target.value)}
							onBlur={() => cambiarParticipante(borradorPart)}
							onKeyDown={(e) => {
								if (e.key === "Enter") cambiarParticipante(borradorPart);
							}}
							aria-describedby="pnl-part-ayuda"
						/>
						{/* PQ-52: la ayuda se ve (el placeholder parecía un valor escrito). */}
						<span id="pnl-part-ayuda" className="sr">
							Se aplica al salir del campo o con Enter. Vacío para ver a todos.
						</span>
					</div>
					<div className="pnl-campo">
						<label htmlFor="pnl-tipo">Tipo de usuario de playa</label>
						<select id="pnl-tipo" value={tipo} onChange={(e) => cambiarTipo(Number(e.target.value))}>
							<option value={0}>Todos</option>
							{TIPOS_PLAYA.map((t) => (
								<option key={t.id} value={t.id}>
									{t.id}. {t.nombre}
								</option>
							))}
						</select>
					</div>
					<button type="button" className="pnl-btn-sec" onClick={csv}>
						<IconoDescargar />
						Descargar CSV
					</button>
					<LimpiarFiltros activo={!!(tema || resultado || participante || borradorPart || tipo)} onLimpiar={limpiarFiltros} />
				</div>
			</div>

			<p className="sr" role="status" aria-live="polite">
				{cargando ? "Cargando cifras…" : anuncio}
			</p>

			<AparecerSi valor={errorCsv}>
				{(errorCsv) => (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>No se pudo descargar el CSV.</b>
							<p>{errorCsv} Intente de nuevo en un momento.</p>
						</div>
					</div>
				)}
			</AparecerSi>

			{datos?.demo ? (
				<div className="pnl-aviso" role="note">
					<IconoAviso />
					<p>
						<b>Datos de demostración.</b> Estas cifras salen de preguntas de prueba, no de
						personas reales.
					</p>
				</div>
			) : null}

			<AparecerSi valor={error}>
				{(error) => (
					<div className="pnl-error" role="alert">
						<IconoAviso />
						<div>
							<b>No se pudieron cargar las cifras.</b>
							<p>{error}</p>
							<button
								type="button"
								className="pnl-btn-sec"
								onClick={() => {
									setCargando(true);
									setIntento((n) => n + 1);
								}}
							>
								Intentar otra vez
							</button>
						</div>
					</div>
				)}
			</AparecerSi>

			{!datos && cargando ? <p className="pnl-cargando">Cargando cifras…</p> : null}

			{datos ? (
				<div aria-busy={cargando} style={cargando ? { opacity: 0.6 } : undefined}>
					<Contenido
						datos={datos}
						dias={dias}
						tema={tema}
						onTema={cambiarTema}
						resultado={resultado}
						onResultado={cambiarResultado}
						volver={consulta}
						persona={persona}
					/>
				</div>
			) : null}
		</div>
	);
}

function textoPeriodo(dias: number): string {
	return dias === 0 ? "Todo el tiempo" : `Últimos ${dias} días`;
}

function subtituloPeriodo(d: Resumen): string {
	const hasta = fechaLarga(d.periodo.hasta);
	if (!d.periodo.desde) return `Todas las preguntas hasta el ${hasta}`;
	return `Del ${fechaLarga(d.periodo.desde)} al ${hasta}`;
}

/** PQ-132: "no le sirvió" separado por tipo de respuesta: las de fuera de
 * tema o aclaración no son contenido que falte (ATLAS respondió bien). */
function desgloseNoSirvio(c: Resumen["cifras"]): string {
	const medias = c.calificaciones - c.le_sirvio - c.no_le_sirvio;
	const si = `A ${numero(c.le_sirvio)} sí les sirvió${medias > 0 ? ` y a ${numero(medias)} a medias` : ""}.`;
	if (c.no_le_sirvio_con_fuente === undefined || !c.no_le_sirvio) return `${si} Calificaron ${numero(c.calificaciones)} de ${numero(c.respuestas)} respuestas.`;
	const partes = [
		`${numero(c.no_le_sirvio_con_fuente)} con fuente`,
		`${numero(c.no_le_sirvio_sin_respuesta ?? 0)} sin respuesta segura`,
	];
	if (c.no_le_sirvio_fuera_de_tema) partes.push(`${numero(c.no_le_sirvio_fuera_de_tema)} fuera de tema o aclaración`);
	return `${si} De las ${numero(c.no_le_sirvio)}: ${partes.join(", ")}.`;
}

function Contenido({
	datos,
	dias: diasFiltro,
	tema,
	onTema,
	resultado,
	onResultado,
	volver,
	persona,
}: {
	datos: Resumen;
	dias: number;
	tema: string;
	onTema: (t: string) => void;
	resultado: FiltroResultado;
	onResultado: (r: FiltroResultado) => void;
	volver: string;
	persona: FiltroPersona;
}) {
	// El periodo que vale es el que respondió el servidor, no el del filtro
	// mientras carga: así cifras y textos siempre describen lo mismo.
	const dias = datos.periodo.dias;
	const c = datos.cifras;
	const a = datos.anterior;
	// PQ-129: el % solo con base suficiente; si no, el conteo y "pocos datos".
	const pFuente = tasaConBase(c.con_fuente, c.respuestas);
	const pFuenteAnt = a ? porcentaje(a.con_fuente, a.respuestas) : null;
	const pSinResp = tasaConBase(c.sin_respuesta_segura, c.respuestas);
	const pSinRespAnt = a ? porcentaje(a.sin_respuesta_segura, a.respuestas) : null;
	const pNoSirvio = tasaConBase(c.no_le_sirvio, c.calificaciones);
	const deBase = (n: number, p: number | null) => `de ${numero(n)}${p !== null ? ` (${p} %)` : n ? " · pocos datos" : ""}`;
	// PQ-128: el periodo actual puede ir a medias; los conteos se comparan por día.
	const diasActual = datos.periodo.dias ? (diasTranscurridos(datos.periodo.desde, datos.periodo.hasta) ?? dias) : dias;
	const antes = `los ${dias} días anteriores`;

	// J6-B: cada cifra abre su lista (la de "Pregunta por pregunta", ya filtrada).
	function ver(r: FiltroResultado) {
		onResultado(r);
		requestAnimationFrame(() =>
			document.getElementById("t-recientes")?.scrollIntoView({
				behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
				block: "start",
			}),
		);
	}

	if (c.preguntas === 0) {
		return (
			<section className="pnl-bloque" aria-labelledby="t-vacio">
				<h2 id="t-vacio">
					{persona.participante
						? `No hay preguntas de ${persona.participante} en este periodo`
						: "No hay preguntas en este periodo"}
				</h2>
				<p className="pnl-vacio">
					{persona.participante
						? "Revise que el número exista (en Cuentas) o pruebe con un periodo más largo, por ejemplo Todo."
						: tema
						? "Nadie preguntó sobre este tema en estas fechas. Pruebe con otro tema o con un periodo más largo."
						: "Nadie hizo preguntas en estas fechas. Pruebe con un periodo más largo, por ejemplo 90 días o Todo."}
				</p>
			</section>
		);
	}

	return (
		<>
			<Grupo id="g-vamos" titulo="¿Cuánto vamos?" sub="Toque una cifra para ver esas preguntas abajo">
				<div className="pnl-tb-cifras">
					<CifraBoton
						titulo="Preguntas"
						onVer={() => ver("")}
						verTexto="Ver todas →"
						det={
							a ? (
								<Delta
									cambio={cambioConteo(c.preguntas, a.preguntas, diasActual, dias)}
									mejorSiSube
									sufijo={`${antes} (${numero(a.preguntas)})`}
								/>
							) : (
								"Desde la primera pregunta guardada"
							)
						}
					>
						{numero(c.preguntas)}
					</CifraBoton>
					<CifraBoton
						titulo="Personas que preguntaron"
						det={
							dias === 0
								? `${cuantasDecimal(datos.personas.preguntas_por_persona, "pregunta", "preguntas")} por persona`
								: `${numero(c.personas_nuevas)} por primera vez; ${cuantasDecimal(datos.personas.preguntas_por_persona, "pregunta", "preguntas")} por persona`
						}
					>
						{numero(c.personas)}
					</CifraBoton>
					<CifraBoton
						titulo="Respondidas con fuente citada"
						tono="bien"
						de={deBase(c.respuestas, pFuente)}
						progreso={pFuente ?? undefined}
						onVer={() => ver("con_fuente")}
						verTexto="Ver cuáles →"
						det={
							a ? (
								<Delta
									cambio={cambioTasa(c.con_fuente, c.respuestas, a.con_fuente, a.respuestas)}
									mejorSiSube
									sufijo={pFuenteAnt === null ? "antes" : `${pFuenteAnt} % antes`}
								/>
							) : (
								"Respuestas que citan una norma o sentencia"
							)
						}
					>
						{numero(c.con_fuente)}
					</CifraBoton>
					{/* A12: título, cifra, color y botón dicen lo mismo; la cifra grande
					    es la que abre el botón ("No le sirvió" → esas respuestas). */}
					<CifraBoton
						titulo="No le sirvió"
						tono={c.no_le_sirvio > 0 ? "ojo" : "neutro"}
						de={deBase(c.calificaciones, pNoSirvio)}
						progreso={pNoSirvio ?? undefined}
						onVer={c.no_le_sirvio > 0 ? () => ver("no_le_sirvio") : undefined}
						verTexto="Ver cuáles →"
						det={desgloseNoSirvio(c)}
					>
						{numero(c.no_le_sirvio)}
					</CifraBoton>
					<CifraBoton
						titulo="Sin respuesta segura"
						tono={c.sin_respuesta_segura > 0 ? "ojo" : "neutro"}
						de={deBase(c.respuestas, pSinResp)}
						onVer={c.sin_respuesta_segura > 0 ? () => ver("sin_respuesta_segura") : undefined}
						verTexto="Ver cuáles →"
						det={
							a ? (
								<Delta
									cambio={cambioTasa(c.sin_respuesta_segura, c.respuestas, a.sin_respuesta_segura, a.respuestas)}
									mejorSiSube={false}
									sufijo={pSinRespAnt === null ? "antes" : `${pSinRespAnt} % antes`}
								/>
							) : (
								"ATLAS no encontró respaldo en las normas"
							)
						}
					>
						{numero(c.sin_respuesta_segura)}
					</CifraBoton>
				</div>
			<p className="pnl-desglose">
				{desglose(c)}
			</p>
			{a ? (
				<p className="pnl-nota">
					Las flechas solo aparecen si el cambio supera el margen de error (95 %) y cada periodo tiene al menos 30
					casos; las preguntas se comparan por día porque el periodo actual puede ir a medias. Los porcentajes se
					muestran desde 20 casos.
				</p>
			) : null}


			<div className="pnl-grid">
				<section className="pnl-bloque pnl-c7" aria-labelledby="t-serie">
					<div className="pnl-bloque-cab">
						<div>
							<h2 id="t-serie">Preguntas por {datos.periodo.agrupacion === "dia" ? "día" : "semana"}</h2>
							<p>
								{datos.periodo.agrupacion === "dia"
									? "Cada columna es un día"
									: "Semanas de lunes a domingo; la trama marca una semana incompleta"}
							</p>
						</div>
					</div>
					<Columnas serie={datos.serie} agrupacion={datos.periodo.agrupacion} />
					<NotaSerie datos={datos} />
					<VerComoTabla
						titulo={`preguntas por ${datos.periodo.agrupacion === "dia" ? "día" : "semana"}`}
					>
						<TablaSerie serie={datos.serie} agrupacion={datos.periodo.agrupacion} />
					</VerComoTabla>
				</section>

				<section className="pnl-bloque pnl-c5" aria-labelledby="t-quien">
					<div className="pnl-bloque-cab">
						<div>
							<h2 id="t-quien">Quién pregunta</h2>
							<p>{cuantas(datos.personas.activas, "persona", "personas")} en el periodo</p>
						</div>
					</div>
					<Personas datos={datos} dias={dias} />
				</section>
			</div>
			</Grupo>

			<Grupo id="g-atencion" titulo="¿Qué necesita atención?" sub="Dónde ATLAS no respondió bien">
				<Brechas datos={datos} volver={volver} tema={tema} onTema={onTema} />
			</Grupo>

			<Grupo id="g-resultados" titulo="Resultados" sub="De qué preguntan y qué responde ATLAS">

			<div className="pnl-grid">
				<section className="pnl-bloque pnl-c7" aria-labelledby="t-temas">
					<div className="pnl-bloque-cab">
						<div>
							<h2 id="t-temas">Temas más preguntados</h2>
							<p>Preguntas y qué tanto le sirvió la respuesta</p>
						</div>
					</div>
					<Barras
						etiqueta="Preguntas por tema"
						filas={datos.temas.map<FilaBarra>((t) => ({
							clave: t.id,
							nombre: t.titulo,
							valor: t.preguntas,
							gris: t.id === "otros",
							extra: (
								<EstadoSatisfaccion
									leSirvio={t.le_sirvio}
									calificaciones={t.calificaciones}
									minimo={MINIMO_PARA_PORCENTAJE}
								/>
							),
						}))}
					/>
					<p className="pnl-nota">
						{(() => {
							const n = datos.temas.reduce((s, t) => s + t.preguntas, 0);
							return `${n === 1 ? "Suma" : "Suman"} ${cuantas(n, "pregunta", "preguntas")}.`;
						})()}
					</p>
					<VerComoTabla titulo="temas">
						<table>
							<thead>
								<tr>
									<th scope="col">Tema</th>
									<th scope="col" className="num">Preguntas</th>
									<th scope="col" className="num">Calificaciones</th>
									<th scope="col" className="num">Le sirvió</th>
									<th scope="col" className="num">Brechas</th>
								</tr>
							</thead>
							<tbody>
								{datos.temas.map((t) => (
									<tr key={t.id}>
										<td>{t.titulo}</td>
										<td className="num">{numero(t.preguntas)}</td>
										<td className="num">{numero(t.calificaciones)}</td>
										<td className="num">{numero(t.le_sirvio)}</td>
										<td className="num">{numero(t.brechas)}</td>
									</tr>
								))}
							</tbody>
						</table>
					</VerComoTabla>
				</section>

				<div className="pnl-pila">
				<section className="pnl-bloque" aria-labelledby="t-normas">
					<div className="pnl-bloque-cab">
						<div>
							<h2 id="t-normas">Normas y sentencias más citadas</h2>
							<p>Cuántas respuestas citan cada norma o sentencia</p>
						</div>
					</div>
					<div>
					{datos.normas.length ? (
						<Recortable
							total={datos.normas.length}
							render={(n) => (
								<Barras
									etiqueta="Normas y sentencias más citadas"
									filas={datos.normas.slice(0, n).map<FilaBarra>((x) => ({
										clave: x.nombre,
										largo: true,
										titulo: x.nombre,
										nombre: (
											<>
												<span className={`pnl-etq${x.doc_type === "jurisprudencia" ? "" : " ley"}`}>
													{tipoDocumento(x.doc_type)}
												</span>
												{x.nombre}
											</>
										),
										valor: x.respuestas,
									}))}
								/>
							)}
						/>
					) : (
						<p className="pnl-vacio">Todavía ninguna respuesta cita una norma o sentencia en este periodo.</p>
					)}
					</div>
					{datos.normas.length ? (
						<VerComoTabla titulo="normas y sentencias citadas">
							<table>
								<thead>
									<tr>
										<th scope="col">Documento</th>
										<th scope="col">Tipo</th>
										<th scope="col" className="num">Respuestas</th>
									</tr>
								</thead>
								<tbody>
									{datos.normas.map((x) => (
										<tr key={x.nombre}>
											<td className="preg">{x.nombre}</td>
											<td>{tipoDocumento(x.doc_type)}</td>
											<td className="num">{numero(x.respuestas)}</td>
										</tr>
									))}
								</tbody>
							</table>
						</VerComoTabla>
					) : null}
				</section>

				<section className="pnl-bloque" aria-labelledby="t-playas">
					<div className="pnl-bloque-cab">
						<div>
							<h2 id="t-playas">Playas mencionadas</h2>
							<p>Cuántas preguntas nombran cada playa</p>
						</div>
					</div>
					{datos.playas.length ? (
						<Barras
							etiqueta="Preguntas por playa"
							filas={datos.playas.map<FilaBarra>((p) => ({
								clave: p.nombre,
								nombre: <span className="lugar">{p.nombre}</span>,
								valor: p.preguntas,
							}))}
						/>
					) : (
						<p className="pnl-vacio">
							Todavía ninguna pregunta nombra una playa (0 de {numero(c.preguntas)}).
						</p>
					)}
					{datos.playas.length ? (
						<p className="pnl-nota">
							{datos.sin_playa === 1
								? "1 pregunta no nombra ninguna playa"
								: `${numero(datos.sin_playa)} preguntas no nombran ninguna playa`}{" "}
							({textoPorcentaje(datos.sin_playa, c.preguntas)}).
						</p>
					) : null}
				</section>
				</div>
			</div>

			</Grupo>

			<Grupo id="g-lista" titulo="Pregunta por pregunta" sub="Lo que abren las cifras de arriba">
			<Recientes
				key={`${diasFiltro}-${tema}-${persona.participante ?? ""}-${persona.tipo ?? ""}`}
				dias={diasFiltro}
				tema={tema}
				resultado={resultado}
				onResultado={onResultado}
				volver={volver}
				persona={persona}
			/>
			</Grupo>

			<p className="pnl-pie">
				Las cifras cuentan las preguntas hechas con sesión iniciada (flujo guiado y equipo), en
				hora de Colombia. El tema y la playa se deducen del texto de la pregunta con reglas fijas,
				sin inteligencia artificial: pueden equivocarse en preguntas escritas a mano.
			</p>
		</>
	);
}

function desglose(c: Resumen["cifras"]): string {
	const partes = [`${numero(c.con_fuente)} con fuente citada`, `${numero(c.sin_respuesta_segura)} sin respuesta segura`];
	if (c.fuera_de_tema) partes.push(`${numero(c.fuera_de_tema)} fuera de tema`);
	if (c.pide_aclarar) partes.push(`${numero(c.pide_aclarar)} en que pidió aclarar`);
	const ultima = partes.pop();
	let texto = `${cuantas(c.respuestas, "respuesta", "respuestas")}: ${partes.join(", ")} y ${ultima}.`;
	const aparte: string[] = [];
	if (c.saludos) aparte.push(`${numero(c.saludos)} ${c.saludos === 1 ? "saludo" : "saludos"}`);
	if (c.sin_respuesta_guardada) aparte.push(`${numero(c.sin_respuesta_guardada)} sin respuesta guardada`);
	if (aparte.length) texto += ` Aparte, ${aparte.join(" y ")}, que no cuentan en los porcentajes.`;
	return texto;
}

function NotaSerie({ datos }: { datos: Resumen }) {
	const s = datos.serie;
	if (!s.length) return null;
	const max = s.reduce((m, p) => (p.preguntas > m.preguntas ? p : m), s[0]);
	const brechas = s.reduce((n, p) => n + p.sin_respuesta_segura, 0);
	const unidad = datos.periodo.agrupacion === "dia" ? "El día" : "La semana";
	return (
		<p className="pnl-nota">
			{unidad} con más preguntas: {datos.periodo.agrupacion === "dia" ? diaMes(`${max.fecha}T12:00:00-05:00`) : `la del ${diaMes(`${max.desde}T12:00:00-05:00`)}`}{" "}
			({numero(max.preguntas)}). Sin respuesta segura en el periodo: {numero(brechas)}.
		</p>
	);
}

function Personas({ datos, dias }: { datos: Resumen; dias: number }) {
	const p = datos.personas;
	const mediana = p.mediana_por_persona ? ` (mediana ${decimal(p.mediana_por_persona)})` : "";
	// PQ-141: si el periodo anterior no tiene preguntas, todos saldrían "nuevos":
	// se dice como en "Todo".
	if (dias === 0 || (datos.anterior !== null && datos.anterior.preguntas === 0)) {
		return (
			<p>
				{dias === 0 ? "En todo el tiempo" : "En el periodo"} {p.activas === 1 ? "preguntó" : "preguntaron"}{" "}
				{cuantas(p.activas, "persona", "personas")}, con{" "}
				{cuantasDecimal(p.preguntas_por_persona, "pregunta", "preguntas")} por persona en promedio{mediana}.
				{dias !== 0 ? " Antes de este periodo no hay preguntas para saber quién vuelve." : null}
			</p>
		);
	}
	const total = Math.max(1, p.activas);
	return (
		<>
			<div
				role="img"
				aria-label={`${p.recurrentes} personas que ya habían preguntado antes y ${p.nuevas} nuevas`}
				style={{ display: "flex", height: 40, gap: 2, margin: "6px 0 8px" }}
			>
				{p.recurrentes ? (
					<i style={estiloSegmento(p.recurrentes / total, "var(--p-marino)", true, !p.nuevas)}>
						{p.recurrentes / total > 0.18 ? `${numero(p.recurrentes)} vuelven` : null}
					</i>
				) : null}
				{p.nuevas ? (
					<i style={estiloSegmento(p.nuevas / total, "var(--p-turquesa)", !p.recurrentes, true)}>
						{p.nuevas / total > 0.18 ? `${numero(p.nuevas)} nuevas` : null}
					</i>
				) : null}
			</div>
			<ul style={{ listStyle: "none", padding: 0, margin: "0 0 16px", display: "grid", gap: 4 }}>
				<li>
					<Muestra color="var(--p-marino)" /> {numero(p.recurrentes)} ya habían preguntado antes
				</li>
				<li>
					<Muestra color="var(--p-turquesa)" /> {numero(p.nuevas)} preguntaron por primera vez
				</li>
			</ul>
			<p style={{ margin: 0 }}>
				En promedio, {cuantasDecimal(p.preguntas_por_persona, "pregunta", "preguntas")} por persona{mediana}. La lista de cuentas
				está en <Link href="/admin/cuentas">Cuentas</Link>.
			</p>
		</>
	);
}

function estiloSegmento(fraccion: number, color: string, izq: boolean, der: boolean): React.CSSProperties {
	return {
		flex: fraccion,
		minWidth: 6,
		background: color,
		color: "var(--p-sobre-marino)",
		display: "flex",
		alignItems: "center",
		padding: "0 10px",
		fontStyle: "normal",
		fontWeight: 700,
		whiteSpace: "nowrap",
		overflow: "hidden",
		borderRadius: `${izq ? 4 : 0}px ${der ? 4 : 0}px ${der ? 4 : 0}px ${izq ? 4 : 0}px`,
	};
}

function Muestra({ color }: { color: string }) {
	return (
		<span
			aria-hidden="true"
			style={{ display: "inline-block", width: 14, height: 14, borderRadius: 3, background: color, verticalAlign: -1 }}
		/>
	);
}

/** Muestra los primeros 5 y un botón para ver todos (listas largas en celular). */
function Recortable({ total, render }: { total: number; render: (n: number) => React.ReactNode }) {
	const [todos, setTodos] = useState(false);
	const corto = 5;
	return (
		<>
			{render(todos ? total : corto)}
			{total > corto ? (
				<button type="button" className="pnl-enlace" aria-expanded={todos} onClick={() => setTodos((t) => !t)}>
					{todos ? "Ver menos" : `Ver las ${total}`}
				</button>
			) : null}
		</>
	);
}
