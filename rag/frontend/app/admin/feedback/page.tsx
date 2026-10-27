"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
	deCinco,
	decimal,
	enlaceConversacion,
	fechaHora,
	mensajeError,
	numero,
	pedirEncuestas,
	type Encuestas,
	type FiltroEncuesta,
} from "@/lib/admin/panel";
import { IconoAviso } from "@/components/admin/panel/Estados";
import { Periodo } from "@/components/admin/panel/Periodo";

const OPCIONES: { valor: FiltroEncuesta; texto: string }[] = [
	{ valor: "", texto: "Todas las encuestas" },
	{ valor: "buenas", texto: "Buenas (4 o 5)" },
	{ valor: "malas", texto: "Malas (1 o 2)" },
	{ valor: "con_comentario", texto: "Con comentario" },
];

// Qué mide cada nota de la encuesta (1 = muy mal, 5 = muy bien), PQ-47.
const DIMENSIONES = [
	{ clave: "general", texto: "General", mide: "Qué tan bien le fue en general" },
	{ clave: "tono", texto: "Tono", mide: "Trato y lenguaje de la respuesta" },
	{ clave: "largo", texto: "Largo", mide: "Si el largo de la respuesta fue el adecuado" },
	{ clave: "facilidad", texto: "Facilidad", mide: "Qué tan fácil fue usar ATLAS" },
] as const;

const POR_PAGINA = 10;

/**
 * Encuestas que se llenan al terminar una conversación (tono, largo,
 * facilidad y nota general de 1 a 5, con comentario). Cada una en una fila
 * con el comentario completo a la vista (PQ-25), legible en celular (PQ-26),
 * promedios en formato colombiano "3,4 de 5" (PQ-37) y filtro simple (PQ-38).
 */
export default function PaginaEncuestas() {
	const [dias, setDias] = useState(30);
	const [filtro, setFiltro] = useState<FiltroEncuesta>("");
	const [pagina, setPagina] = useState(1);
	const [datos, setDatos] = useState<Encuestas | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [intento, setIntento] = useState(0);

	useEffect(() => {
		let vigente = true;
		pedirEncuestas(dias, filtro, pagina, POR_PAGINA)
			.then((r) => {
				if (vigente) {
					setDatos(r);
					setError(null);
				}
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudieron cargar las encuestas."));
			});
		return () => {
			vigente = false;
		};
	}, [dias, filtro, pagina, intento]);

	const total = datos?.total ?? 0;
	const ultimaPagina = Math.max(1, Math.ceil(total / POR_PAGINA));
	const desde = total ? (pagina - 1) * POR_PAGINA + 1 : 0;
	const hasta = Math.min(pagina * POR_PAGINA, total);

	return (
		<div className="pnl-pag">
			<title>Encuestas de satisfacción: panel de ATLAS</title>
			<div className="pnl-cabeza">
				<div>
					<h1>Encuestas de satisfacción</h1>
					<p className="pnl-sub">
						Lo que respondió cada persona al terminar una conversación. Cada nota va de 1 (muy mal) a 5 (muy
						bien); arriba, el promedio del periodo.
					</p>
				</div>
				<div className="pnl-controles">
					<Periodo
						dias={dias}
						onCambio={(d) => {
							setDias(d);
							setPagina(1);
						}}
					/>
				</div>
			</div>

			{error ? (
				<div className="pnl-error" role="alert">
					<IconoAviso />
					<div>
						<b>No se pudieron cargar las encuestas.</b>
						<p>{error}</p>
						<button type="button" className="pnl-btn-sec" onClick={() => setIntento((n) => n + 1)}>
							Intentar otra vez
						</button>
					</div>
				</div>
			) : null}

			{datos ? (
				<dl className="pnl-cifras pnl-cifras-4">
					{DIMENSIONES.map((d) => (
						<div className="pnl-cifra" key={d.clave}>
							<dt>{d.texto}</dt>
							<dd>
								<span className="pnl-valor num">
									{total || filtro ? decimal(datos.promedios[d.clave]) : "—"}
									<small>&nbsp;de 5</small>
								</span>
								<span className="pnl-det">{d.mide}</span>
							</dd>
						</div>
					))}
				</dl>
			) : null}

			<section className="pnl-bloque" aria-labelledby="t-encuestas">
				<div className="pnl-bloque-cab">
					<div>
						<h2 id="t-encuestas">Encuestas</h2>
						<p>{datos ? `${numero(total)} en el periodo con este filtro` : " "}</p>
					</div>
					<div className="pnl-campo">
						<label htmlFor="pnl-filtro-encuesta">Mostrar</label>
						<select
							id="pnl-filtro-encuesta"
							value={filtro}
							onChange={(e) => {
								setFiltro(e.target.value as FiltroEncuesta);
								setPagina(1);
							}}
						>
							{OPCIONES.map((o) => (
								<option key={o.valor} value={o.valor}>
									{o.texto}
								</option>
							))}
						</select>
					</div>
				</div>

				{datos && datos.items.length === 0 ? (
					<p className="pnl-vacio">
						<b>No hay encuestas con este filtro.</b>
						Pruebe con otra opción en “Mostrar” o con un periodo más largo.
					</p>
				) : null}

				{datos && datos.items.length ? (
					<ol className="pnl-filas" aria-label="Encuestas">
						{datos.items.map((e) => (
							<li key={e.id} className="pnl-fila">
								<div className="pnl-fila-q">
									{e.conversation_id ? (
										<Link href={enlaceConversacion(e.conversation_id, "/admin/feedback")}>
											{e.titulo || "Conversación sin título"}
										</Link>
									) : (
										<span className="pnl-fila-titulo">{e.titulo || "Conversación sin título"}</span>
									)}
									<p className="pnl-fila-meta">
										<span>
											{e.persona}, {fechaHora(e.fecha)}
										</span>
									</p>
									{e.comentario ? (
										<p className="pnl-esperaba">Comentó: “{e.comentario}”</p>
									) : (
										<p className="pnl-fila-meta">Sin comentario</p>
									)}
								</div>
								<dl className="pnl-fila-estado">
									{DIMENSIONES.map((d) => (
										<div key={d.clave}>
											<dt>{d.texto}</dt>
											<dd className={d.clave === "general" ? "pnl-veces" : undefined}>
												{deCinco(e[d.clave])}
											</dd>
										</div>
									))}
								</dl>
							</li>
						))}
					</ol>
				) : null}

				{datos && total > POR_PAGINA ? (
					<nav className="pnl-pagin" aria-label="Páginas de encuestas">
						<span>
							{numero(desde)} a {numero(hasta)} de {numero(total)} encuestas
						</span>
						<div>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={pagina <= 1}
								onClick={() => setPagina((p) => p - 1)}
							>
								Anteriores
							</button>
							<button
								type="button"
								className="pnl-btn-sec"
								disabled={pagina >= ultimaPagina}
								onClick={() => setPagina((p) => p + 1)}
							>
								Siguientes
							</button>
						</div>
					</nav>
				) : null}
			</section>
		</div>
	);
}
