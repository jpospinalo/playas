"use client";

import { useId, useState, type ReactNode } from "react";
import { diaMesCalendario, numero, type Agrupacion, type Punto } from "@/lib/admin/panel";

/**
 * Gráficos del panel en HTML/CSS (sin librerías): una serie por gráfico,
 * etiqueta directa con el número, nada que dependa del mouse. Cada gráfico
 * tiene su tabla equivalente ("Ver como tabla").
 */

export function VerComoTabla({ children, titulo }: { children: ReactNode; titulo: string }) {
	const [abierta, setAbierta] = useState(false);
	const id = useId();
	return (
		<>
			<button
				type="button"
				className="pnl-enlace"
				aria-expanded={abierta}
				aria-controls={id}
				onClick={() => setAbierta((a) => !a)}
			>
				{abierta ? "Ocultar tabla" : "Ver como tabla"}
				<span className="sr"> de {titulo}</span>
			</button>
			{/* Región con foco: si la tabla es más ancha que la pantalla, se desplaza con el teclado. */}
			<div
				id={id}
				hidden={!abierta}
				className="pnl-tabla-datos"
				role="region"
				aria-label={`Tabla de ${titulo}`}
				tabIndex={abierta ? 0 : -1}
			>
				{abierta ? children : null}
			</div>
		</>
	);
}

/** Escala "redonda" para el eje: 0, mitad y tope (≥ máximo + 15 % de aire). */
export function tope(max: number): number {
	if (max <= 0) return 4;
	const bruto = max * 1.15;
	const paso = 10 ** Math.floor(Math.log10(bruto));
	for (const m of [1, 2, 4, 5, 6, 8, 10]) {
		const t = m * paso;
		// La mitad también debe ser entera: es la otra marca del eje.
		if (t >= bruto && Number.isInteger(t / 2)) return t;
	}
	return 10 * paso;
}

export function etiquetaPunto(p: Punto, agrupacion: Agrupacion): string {
	if (agrupacion === "dia") return diaMesCalendario(p.fecha);
	return diaMesCalendario(p.desde);
}

function descripcionPunto(p: Punto, agrupacion: Agrupacion): string {
	if (agrupacion === "dia") return `${diaMesCalendario(p.fecha)}${p.en_curso ? " (hoy, a medias)" : ""}`;
	const rango =
		p.desde === p.hasta
			? diaMesCalendario(p.desde)
			: `${diaMesCalendario(p.desde)} al ${diaMesCalendario(p.hasta)}`;
	return p.parcial || p.en_curso ? `${rango} (semana incompleta)` : rango;
}

/** Cada cuántas columnas se escribe la fecha para que no se pisen. */
export function pasoEtiquetas(n: number, maximo: number): number {
	return Math.max(1, Math.ceil(n / maximo));
}

export function Columnas({ serie, agrupacion }: { serie: Punto[]; agrupacion: Agrupacion }) {
	const max = Math.max(0, ...serie.map((p) => p.preguntas));
	const t = tope(max);
	const ultimo = serie.length - 1;
	// Fechas visibles: hasta 8 en PC y 4 en celular, siempre la última.
	const pasoPc = pasoEtiquetas(serie.length, 8);
	const pasoCel = pasoEtiquetas(serie.length, 4);
	const resumen = serie
		.map((p) => `${descripcionPunto(p, agrupacion)}: ${numero(p.preguntas)}`)
		.join("; ");
	return (
		<div
			className="pnl-columnas"
			role="img"
			aria-label={`Preguntas por ${agrupacion === "dia" ? "día" : "semana"}. ${resumen}.`}
		>
			<div className="pnl-eje-y" aria-hidden="true">
				<span style={{ top: "0%" }}>{numero(t)}</span>
				<span style={{ top: "50%" }}>{numero(t / 2)}</span>
				<span style={{ top: "100%" }}>0</span>
			</div>
			<div className="pnl-plot" aria-hidden="true">
				{serie.map((p) => {
					const alto = (p.preguntas / t) * 100;
					// PQ-134: cifra en todas las columnas o en ninguna (con muchas, se leen
					// en "Ver como tabla"); hoy y las semanas cortadas llevan trama.
					const conEtiqueta = max > 0 && serie.length <= 14;
					return (
						<div className="pnl-col" key={p.fecha}>
							<i className={p.parcial || p.en_curso ? "parcial" : undefined} style={{ height: `${alto}%` }}>
								{conEtiqueta ? <b className="num">{numero(p.preguntas)}</b> : null}
							</i>
						</div>
					);
				})}
			</div>
			<div className="pnl-eje-x" aria-hidden="true">
				{serie.map((p, i) => {
					const desdeFin = ultimo - i;
					const pc = desdeFin % pasoPc === 0;
					const cel = desdeFin % pasoCel === 0;
					return (
						<span key={p.fecha} className={`${pc ? "" : "no-pc"} ${cel ? "" : "no-cel"}`.trim() || undefined}>
							{pc || cel ? <em>{etiquetaPunto(p, agrupacion)}</em> : null}
						</span>
					);
				})}
			</div>
		</div>
	);
}

export function TablaSerie({ serie, agrupacion }: { serie: Punto[]; agrupacion: Agrupacion }) {
	return (
		<table>
			<thead>
				<tr>
					<th scope="col">{agrupacion === "dia" ? "Día" : "Semana"}</th>
					<th scope="col" className="num">
						Preguntas
					</th>
					<th scope="col" className="num">
						Sin respuesta segura
					</th>
				</tr>
			</thead>
			<tbody>
				{serie.map((p) => (
					<tr key={p.fecha}>
						<td>{descripcionPunto(p, agrupacion)}</td>
						<td className="num">{numero(p.preguntas)}</td>
						<td className="num">{numero(p.sin_respuesta_segura)}</td>
					</tr>
				))}
			</tbody>
		</table>
	);
}

export interface FilaBarra {
	clave: string;
	nombre: ReactNode;
	valor: number;
	largo?: boolean;
	gris?: boolean;
	extra?: ReactNode;
	titulo?: string;
}

export function Barras({ filas, etiqueta }: { filas: FilaBarra[]; etiqueta: string }) {
	const max = Math.max(1, ...filas.map((f) => f.valor));
	return (
		<ul className="pnl-barras" aria-label={etiqueta}>
			{filas.map((f) => (
				<li className="pnl-barra" key={f.clave}>
					<span className={`nom${f.largo ? " largo" : ""}`} title={f.titulo}>
						{f.nombre}
					</span>
					<span className="val num">{numero(f.valor)}</span>
					<span className="riel" aria-hidden="true">
						<i className={f.gris ? "gris" : undefined} style={{ width: `${(f.valor / max) * 100}%` }} />
					</span>
					{f.extra ? <span className="extra">{f.extra}</span> : null}
				</li>
			))}
		</ul>
	);
}
