"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";
import { decimal, numero, porcentaje } from "@/lib/admin/panel";
import { NIVELES, RANGOS, type Ct, type EstadoPregunta, type ResumenEjercicio } from "@/lib/admin/evaluacion";
import { TIPOS_PLAYA } from "@/lib/admin/cuentas";
import { diaLargo, pedirCalendario } from "@/lib/admin/calendario";
import { ChipEstado, IconoAviso } from "@/components/admin/panel/Estados";

/**
 * J6-B (mockup-tablero.html, aprobado por Juan): "Resumen y premios" agrupado
 * por pregunta (¿Cuánto vamos? · ¿Qué necesita atención? · Resultados · Por
 * persona), con color de significado (gris sin empezar, azul en proceso,
 * ámbar atención, verde terminado), barras en vez de números sueltos, cada
 * cifra con su contexto ("X de Y") y cada número llevando a su lista.
 */

const BANDEJA = "/admin/evaluacion";
// Sin práctica, igual que las cifras del resumen.
const lista = (q: string) => `${BANDEJA}?${q}&reales=1`;

/** El camino de una pregunta, de lo que falta a lo terminado. */
const PASOS: { k: EstadoPregunta; texto: string; color: string; filtro: string }[] = [
	{ k: "sin_evaluar", texto: "Sin calificar", color: "var(--p-c1)", filtro: "sin_calificar" },
	{ k: "una_evaluacion", texto: "Falta una calificación", color: "var(--p-c2)", filtro: "una_calificacion" },
	{ k: "concordante", texto: "Coinciden: esperan la validación", color: "var(--p-c3)", filtro: "por_validar" },
	{ k: "con_diferencias", texto: "Con diferencias: las revisa el comité", color: "var(--p-c4)", filtro: "con_diferencias" },
	{ k: "validada", texto: "Validadas", color: "var(--p-c5)", filtro: "validadas" },
	{ k: "final", texto: "Revisadas por el comité", color: "var(--p-c6)", filtro: "revisadas" },
];

/** Color propio y fijo de cada nivel en todo el panel. */
export const COLOR_NIVEL: Record<Ct, string> = { S: "var(--p-n-s)", I: "var(--p-n-i)", A: "var(--p-n-a)" };

export function Tablero({
	resumen,
	comite,
	ganadores,
}: {
	resumen: ResumenEjercicio;
	comite: boolean;
	/** PQ-113: los ganadores van dentro de "Resultados". */
	ganadores?: ReactNode;
}) {
	const e = resumen.estados;
	const total = resumen.preguntas_registradas;
	const pctOficial = porcentaje(resumen.evaluadas, total) ?? 0;
	const pendVal = (resumen.avance_validadores ?? []).reduce((s, v) => s + v.pendientes, 0);

	return (
		<>
			<Grupo id="g-vamos" titulo="¿Cuánto vamos?" sub="Lo principal, de un vistazo">
				<div className="pnl-tb-cifras">
					<Cifra href={lista("estado=todas")} titulo="Preguntas registradas" det="Hechas por los participantes del ejercicio">
						{numero(total)}
					</Cifra>
					<Cifra
						href={lista("estado=finalizadas")}
						titulo="Con calificación oficial"
						det={resumen.solo_revisadas ? "Validadas por el comité" : "Final del comité o calificaciones que coinciden"}
						de={`de ${numero(total)} (${pctOficial} %)`}
						progreso={pctOficial}
					>
						{numero(resumen.evaluadas)}
					</Cifra>
					<Cifra
						href={lista("estado=con_diferencias")}
						titulo="Con diferencias"
						det={`Las dos calificaciones no coinciden (${resumen.umbral_diferencia} puntos o más, o distinto nivel)`}
						ojo={resumen.estados.con_diferencias > 0}
						ir="Ver cuáles →"
					>
						{numero(e.con_diferencias)}
					</Cifra>
					<Cifra href={lista("estado=finalizadas")} titulo="Promedio del puntaje total" det="Solo preguntas válidas" de="de 21">
						{decimal(resumen.promedio_total)}
					</Cifra>
					<Cifra href={lista("estado=no_validas")} titulo="No válidas" det="No cuentan para premios">
						{numero(resumen.no_validas)}
					</Cifra>
				</div>
				<Camino estados={e} total={total} />
			</Grupo>

			<Grupo id="g-atencion" titulo="¿Qué necesita atención?" sub="Solo lo que pide hacer algo">
				<ul className="pnl-bloque pnl-tb-atencion">
					<FilaAtencion
						n={e.con_diferencias}
						texto={e.con_diferencias === 1 ? "pregunta con diferencias espera al comité" : "preguntas con diferencias esperan al comité"}
						href={lista("estado=con_diferencias")}
						accion="Revisar ahora"
						ojo
					/>
					{comite ? (
						<FilaAtencion
							n={pendVal}
							texto={pendVal === 1 ? "evaluación espera la validación jurídica" : "evaluaciones esperan la validación jurídica"}
							href="/admin/evaluacion/validar"
							accion="Ir a Validar"
						/>
					) : null}
					<FilaAtencion
						n={e.sin_evaluar}
						texto={e.sin_evaluar === 1 ? "pregunta todavía sin calificar" : "preguntas todavía sin calificar"}
						href={lista("estado=sin_calificar")}
						accion="Ver cuáles"
					/>
				</ul>
			</Grupo>

			<Grupo id="g-resultados" titulo="Resultados" sub="Solo preguntas válidas con calificación oficial">
				<div className="pnl-tb-dos">
					<section className="pnl-bloque" aria-labelledby="t-niveles">
						<h3 id="t-niveles">Casos por nivel</h3>
						<p className="pnl-sub">Cada nivel con su color, el mismo en todo el panel.</p>
						<Barras
							filas={(Object.keys(NIVELES) as Ct[]).map((k) => ({
								texto: `Casos ${NIVELES[k].toLowerCase()}s`,
								ayuda: `valor de fondo ${RANGOS[k][0]} a ${RANGOS[k][1]}`,
								n: resumen.por_nivel[k],
								color: COLOR_NIVEL[k],
								href: lista(`estado=finalizadas&ct=${k}`),
							}))}
						/>
					</section>
					<section className="pnl-bloque" aria-labelledby="t-tipos">
						<h3 id="t-tipos">Preguntas por tipo de usuario de playa</h3>
						<p className="pnl-sub">Todas las preguntas registradas.</p>
						<Barras
							filas={resumen.por_tipo_playa.map((t) => ({
								texto: TIPOS_PLAYA.find((x) => x.id === t.tipo)?.nombre ?? t.nombre,
								n: t.preguntas,
								color: "var(--p-uno)",
								href: lista(`estado=todas&tipo=${t.tipo}`),
							}))}
						/>
					</section>
				</div>
				{ganadores ? <div className="pnl-ganadores-w">{ganadores}</div> : null}
			</Grupo>

			<PorPersona resumen={resumen} />
		</>
	);
}

export function Grupo({ id, titulo, sub, children }: { id: string; titulo: string; sub: string; children: ReactNode }) {
	return (
		<section className="pnl-tb-grupo" aria-labelledby={id}>
			<header>
				<h2 id={id}>{titulo}</h2>
				<span>{sub}</span>
			</header>
			{children}
		</section>
	);
}

function Cifra({
	href,
	titulo,
	det,
	de,
	progreso,
	ojo = false,
	ir,
	children,
}: {
	href: string;
	titulo: string;
	det: string;
	de?: string;
	progreso?: number;
	ojo?: boolean;
	ir?: string;
	children: ReactNode;
}) {
	return (
		<Link href={href} className={ojo ? "pnl-tb-cifra ojo" : "pnl-tb-cifra"}>
			<span className="pnl-tb-titulo">
				{ojo ? <IconoAviso /> : null}
				{titulo}
			</span>
			<span className="pnl-tb-valor num">
				{children}
				{de ? <small> {de}</small> : null}
			</span>
			{progreso !== undefined ? (
				<span className="pnl-tb-prog" aria-hidden="true">
					<i style={{ width: `${progreso}%` }} />
				</span>
			) : null}
			<span className="pnl-tb-det">{det}</span>
			{ir ? <span className="pnl-tb-ir">{ir}</span> : null}
		</Link>
	);
}

function Camino({ estados, total }: { estados: Record<EstadoPregunta, number>; total: number }) {
	return (
		<section className="pnl-bloque pnl-tb-camino" aria-labelledby="t-camino">
			<h3 id="t-camino">El camino de cada pregunta</h3>
			<p className="pnl-sub">De izquierda a derecha: lo que falta y lo que ya terminó. Toque un paso para ver esas preguntas.</p>
			<div className="pnl-tb-apilada" aria-hidden="true">
				{PASOS.map((p) =>
					estados[p.k] ? (
						<span key={p.k} style={{ width: `${(estados[p.k] / Math.max(1, total)) * 100}%`, background: p.color }} />
					) : null,
				)}
			</div>
			<ol className="pnl-tb-leyenda">
				{PASOS.map((p, i) => (
					<li key={p.k}>
						<Link href={lista(`estado=${p.filtro}`)}>
							<span className="paso">{i + 1}.</span>
							<span className="muestra" style={{ background: p.color }} aria-hidden="true" />
							<span>{p.texto}</span>
							<b className="num">{numero(estados[p.k])}</b>
						</Link>
					</li>
				))}
			</ol>
		</section>
	);
}

function FilaAtencion({
	n,
	texto,
	href,
	accion,
	ojo = false,
}: {
	n: number;
	texto: string;
	href: string;
	accion: string;
	ojo?: boolean;
}) {
	const atencion = ojo && n > 0;
	return (
		<li>
			<span className="que">
				{atencion ? (
					<ChipEstado tono="ojo">
						<IconoAviso />
						Atención
					</ChipEstado>
				) : n > 0 ? (
					<ChipEstado tono="espera">En proceso</ChipEstado>
				) : (
					<ChipEstado tono="bien">Al día</ChipEstado>
				)}
				<b className="num">{numero(n)}</b>
				<span>{texto}</span>
			</span>
			{n > 0 ? (
				<Link className="pnl-btn-sec" href={href}>
					{accion}
				</Link>
			) : null}
		</li>
	);
}

function Barras({
	filas,
}: {
	filas: { texto: string; ayuda?: string; n: number; color: string; href: string }[];
}) {
	const max = Math.max(1, ...filas.map((f) => f.n));
	return (
		<ul className="pnl-tb-barras">
			{filas.map((f) => (
				<li key={f.texto}>
					<Link href={f.href}>
						<span>
							{f.texto}
							{f.ayuda ? <small> ({f.ayuda})</small> : null}
						</span>
						<span className="riel" aria-hidden="true">
							<i style={{ width: `${(f.n / max) * 100}%`, background: f.color }} />
						</span>
						<b className="num">{numero(f.n)}</b>
					</Link>
				</li>
			))}
		</ul>
	);
}

/** Cuánto debería llevar hoy, según el calendario (0 antes de empezar, 1 al vencer). */
function esperado(hoy: string, inicio: string | undefined, fin: string | undefined): number {
	if (!inicio || !fin) return 0;
	const a = Date.parse(inicio), b = Date.parse(fin), h = Date.parse(hoy);
	if (!(b > a)) return 0;
	return Math.max(0, Math.min(1, (h - a) / (b - a)));
}

function PorPersona({ resumen }: { resumen: ResumenEjercicio }) {
	const [cal, setCal] = useState<{ hoy: string; inicio?: string } | null>(null);
	useEffect(() => {
		let vigente = true;
		pedirCalendario()
			.then((c) => {
				if (vigente) setCal({ hoy: c.hoy, inicio: c.fechas.find((f) => f.clave === "inicio")?.fecha });
			})
			.catch(() => {
				// Sin calendario no se marca a nadie como atrasado.
			});
		return () => {
			vigente = false;
		};
	}, []);
	const sem = resumen.avance_evaluadores.filter((a) => a.asignadas !== undefined);
	const val = resumen.avance_validadores ?? [];
	if (!sem.length && !val.length) return null;
	const eSem = cal ? esperado(cal.hoy, cal.inicio, resumen.fin_evaluacion) : 0;
	const eVal = cal ? esperado(cal.hoy, cal.inicio, resumen.fin_validacion ?? resumen.fin_evaluacion) : 0;

	return (
		<Grupo id="g-personas" titulo="Por persona" sub="Lo hecho frente a lo asignado">
			<p className="pnl-sub pnl-mb">
				{/* PQ-114: la raya se explica solo cuando se ve. */}
				{eSem === 0 && eVal === 0
					? "El ejercicio todavía no empieza: nadie va atrasado."
					: `Según el calendario, hoy deberían llevar el ${Math.round(eSem * 100)} % (semilleristas) y el ${Math.round(eVal * 100)} % (validación): es la raya oscura de cada barra. En ámbar, quien va por debajo.`}
			</p>
			<div className="pnl-tb-dos">
				{sem.length ? (
					<section className="pnl-bloque" aria-labelledby="t-sem">
						<h3 id="t-sem">Semilleristas</h3>
						{resumen.fin_evaluacion ? <p className="pnl-sub">Fecha límite: {diaLargo(resumen.fin_evaluacion)}.</p> : null}
						{sem.map((a) => (
							<Persona
								key={`${a.evaluador}-${a.sede}`}
								nombre={a.evaluador}
								sede={a.sede}
								hechas={a.evaluadas}
								de={a.asignadas ?? 0}
								esperado={eSem}
								falta="por calificar"
							/>
						))}
					</section>
				) : null}
				{val.length ? (
					<section className="pnl-bloque" aria-labelledby="t-val">
						<h3 id="t-val">Validación jurídica</h3>
						{resumen.fin_validacion ? <p className="pnl-sub">Fecha límite: {diaLargo(resumen.fin_validacion)}.</p> : null}
						{val.map((v) => (
							<Persona
								key={v.validador}
								nombre={v.validador}
								sede={v.sede}
								hechas={v.validadas}
								de={v.evaluaciones}
								esperado={eVal}
								falta="por validar"
								href="/admin/evaluacion/validar"
							/>
						))}
					</section>
				) : null}
			</div>
		</Grupo>
	);
}

function Persona({
	nombre,
	sede,
	hechas,
	de,
	esperado: esp,
	falta,
	href,
}: {
	nombre: string;
	sede: string | null;
	hechas: number;
	de: number;
	esperado: number;
	falta: string;
	href?: string;
}) {
	const p = porcentaje(hechas, de) ?? 0;
	const lista = de > 0 && hechas >= de;
	const tarde = !lista && p < Math.round(esp * 100);
	const contenido = (
		<>
			<span className="nom">
				{nombre}
				{sede ? <small>{sede}</small> : null}
			</span>
			<span className="riel" role="img" aria-label={`${p} % hecho`}>
				<i style={{ width: `${p}%` }} />
				{esp > 0 ? <span className="meta" style={{ left: `calc(${esp * 100}% - 1px)` }} /> : null}
			</span>
			<span className="cuanto">
				<b className="num">
					{numero(hechas)} de {numero(de)}
				</b>{" "}
				({p} %)
				<small>
					{lista ? (
						<ChipEstado tono="bien">Terminado</ChipEstado>
					) : tarde ? (
						<ChipEstado tono="ojo">
							<IconoAviso />
							Atrasado
						</ChipEstado>
					) : (
						`${numero(de - hechas)} ${falta}`
					)}
				</small>
			</span>
		</>
	);
	const clase = `pnl-tb-persona${tarde ? " tarde" : ""}${lista ? " lista" : ""}`;
	return href ? (
		<Link className={clase} href={href}>
			{contenido}
		</Link>
	) : (
		<div className={clase}>{contenido}</div>
	);
}

/**
 * Cifra del tablero que, en vez de ir a otra página, filtra la lista de abajo
 * (Resumen del admin): mismo aspecto que `Cifra`, con su contexto "X de Y".
 */
export function CifraBoton({
	titulo,
	det,
	de,
	progreso,
	tono = "neutro",
	onVer,
	verTexto,
	children,
}: {
	titulo: string;
	det: ReactNode;
	de?: string;
	progreso?: number;
	tono?: "neutro" | "ojo" | "bien";
	onVer?: () => void;
	verTexto?: string;
	children: ReactNode;
}) {
	const cuerpo = (
		<>
			<span className="pnl-tb-titulo">
				{tono === "ojo" ? <IconoAviso /> : null}
				{titulo}
			</span>
			<span className="pnl-tb-valor num">
				{children}
				{de ? <small> {de}</small> : null}
			</span>
			{progreso !== undefined ? (
				<span className={tono === "ojo" ? "pnl-tb-prog ojo" : "pnl-tb-prog"} aria-hidden="true">
					<i style={{ width: `${progreso}%` }} />
				</span>
			) : null}
			<span className="pnl-tb-det">{det}</span>
			{onVer && verTexto ? <span className="pnl-tb-ir">{verTexto}</span> : null}
		</>
	);
	const clase = tono === "ojo" ? "pnl-tb-cifra ojo" : "pnl-tb-cifra";
	return onVer ? (
		<button type="button" className={clase} onClick={onVer}>
			{cuerpo}
		</button>
	) : (
		<div className={clase}>{cuerpo}</div>
	);
}
