"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
	cuantas,
	deCinco,
	decimal,
	medianaEscala,
	MINIMO_PARA_PORCENTAJE,
	descargarEncuestasCsv,
	enlaceConversacion,
	fechaHora,
	mensajeError,
	numero,
	pedirEncuestas,
	porcentaje,
	textoLargo,
	type Encuestas,
	type FiltroEncuesta,
} from "@/lib/admin/panel";
import { IconoAviso, IconoDescargar } from "@/components/admin/panel/Estados";
import { Periodo } from "@/components/admin/panel/Periodo";
import { AparecerSi } from "@/components/admin/panel/Aparece";
import { LimpiarFiltros } from "@/components/admin/panel/LimpiarFiltros";

const OPCIONES: { valor: FiltroEncuesta; texto: string }[] = [
	{ valor: "", texto: "Todas las encuestas" },
	{ valor: "buenas", texto: "Buenas (4 o 5)" },
	{ valor: "malas", texto: "Malas (1 o 2)" },
	{ valor: "con_comentario", texto: "Con comentario" },
];

// Qué mide cada nota de la encuesta (1 = muy mal, 5 = muy bien), PQ-47.
const DIMENSIONES = [
	{ clave: "general", texto: "General", mide: "Qué tan bien le fue en general" },
	{ clave: "claridad", texto: "Claridad", mide: "Qué tan claras fueron las respuestas" },
	{ clave: "tono", texto: "Tono", mide: "Trato y lenguaje de la respuesta" },
	{ clave: "largo", texto: "Largo", mide: "1 muy corta, 3 adecuada, 5 muy larga" },
	{ clave: "facilidad", texto: "Facilidad", mide: "Qué tan fácil fue usar ATLAS" },
] as const;

const POR_PAGINA = 10;

/**
 * PQ-130: una dimensión de la encuesta. Cifra principal: % que puso 4 o 5
 * (Largo: adecuada / corta / larga), con la mediana y las barras 1 a 5 con su
 * conteo; el promedio queda como dato secundario. Sin conteos (API vieja), el
 * promedio como antes.
 */
function CifraEncuesta({
	texto,
	mide,
	largo,
	promedio,
	conteos,
}: {
	texto: string;
	mide: string;
	largo: boolean;
	promedio: number;
	conteos?: number[];
}) {
	const n = conteos ? conteos.reduce((a, b) => a + b, 0) : 0;
	let principal: React.ReactNode;
	let det: string = mide;
	if (!conteos) {
		if (largo && promedio) det = `Promedio ${decimal(promedio)}; ${mide}`;
		principal = !promedio ? (
			<small>Sin datos</small>
		) : largo ? (
			<small>{textoLargo(promedio)}</small>
		) : (
			<>
				{decimal(promedio)}
				<small>&nbsp;de 5</small>
			</>
		);
	} else if (!n) {
		principal = <small>Sin datos</small>;
	} else if (n < MINIMO_PARA_PORCENTAJE) {
		principal = <small>Pocos datos</small>;
		det = `${cuantas(n, "encuesta", "encuestas")}; ${mide}`;
	} else if (largo) {
		const [c1, c2, c3, c4, c5] = conteos;
		principal = <>{porcentaje(c3, n)}&nbsp;%</>;
		det = `de ${numero(n)} la vio adecuada; ${porcentaje(c1 + c2, n)} % corta y ${porcentaje(c4 + c5, n)} % larga. Promedio ${decimal(promedio)}.`;
	} else {
		const altas = conteos[3] + conteos[4];
		const med = medianaEscala(conteos);
		principal = <>{porcentaje(altas, n)}&nbsp;%</>;
		det = `de ${numero(n)} puso 4 o 5. Mediana ${med === null ? "—" : decimal(med)}; promedio ${decimal(promedio)}.`;
	}
	const max = conteos ? Math.max(1, ...conteos) : 1;
	return (
		<div className="pnl-cifra">
			<dt>{texto}</dt>
			<dd>
				<span className="pnl-valor num">{principal}</span>
				<span className="pnl-det">{det}</span>
				{conteos && n ? (
					<span className="pnl-escala" role="img" aria-label={`Notas de 1 a 5: ${conteos.join(", ")}`}>
						{conteos.map((c, i) => (
							<span key={i} className="pnl-escala-col">
								<i style={{ height: `${Math.round((c / max) * 40)}px` }} />
								<b className="num">{numero(c)}</b>
								<small>{i + 1}</small>
							</span>
						))}
					</span>
				) : null}
			</dd>
		</div>
	);
}

/**
 * Encuestas que se llenan al terminar una conversación (tono, largo,
 * facilidad y nota general de 1 a 5, con comentario). Cada una en una fila
 * con el comentario completo a la vista (PQ-25), legible en celular (PQ-26),
 * promedios en formato colombiano "3,4 de 5" (PQ-37) y filtro simple (PQ-38).
 */
export default function PaginaEncuestas() {
	const [dias, setDias] = useState(0); // "Todo" por defecto (PQ-69)
	const [filtro, setFiltro] = useState<FiltroEncuesta>("");
	const [pagina, setPagina] = useState(1);
	const [datos, setDatos] = useState<Encuestas | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [intento, setIntento] = useState(0);
	const [errorCsv, setErrorCsv] = useState<string | null>(null);

	async function csv() {
		setErrorCsv(null);
		try {
			await descargarEncuestasCsv(dias);
		} catch (e) {
			setErrorCsv(mensajeError(e, "No se pudo descargar el archivo."));
		}
	}

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
						bien); arriba, la cifra grande es el porcentaje que puso 4 o 5 (en Largo, cuántas la vieron
						adecuada), con las notas de 1 a 5 debajo.
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
					<button type="button" className="pnl-btn-sec" onClick={csv}>
						<IconoDescargar />
						Descargar CSV con comentarios
					</button>
				</div>
			</div>

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

			<AparecerSi valor={error}>
				{(error) => (
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
				)}
			</AparecerSi>

			{datos ? (
				<dl className="pnl-cifras pnl-cifras-5">
					{DIMENSIONES.map((d) => (
						<CifraEncuesta
							key={d.clave}
							texto={d.texto}
							mide={d.mide}
							largo={d.clave === "largo"}
							promedio={datos.promedios[d.clave]}
							conteos={datos.distribucion?.[d.clave]}
						/>
					))}
				</dl>
			) : null}
			{datos?.distribucion ? (
				<p className="pnl-nota">
					La cifra grande es el porcentaje que puso 4 o 5 (en Largo, cuántas la vieron adecuada, corta o larga); el
					promedio va aparte porque esconde respuestas opuestas. Con menos de {MINIMO_PARA_PORCENTAJE} encuestas se
					muestra el conteo. Sin cuentas de práctica.
				</p>
			) : null}

			<section className="pnl-bloque" aria-labelledby="t-encuestas">
				<div className="pnl-bloque-cab">
					<div>
						<h2 id="t-encuestas">Encuestas</h2>
						<p>{datos ? `${numero(total)} en el periodo con este filtro` : " "}</p>
					</div>
					<div className="pnl-controles">
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
					<LimpiarFiltros
						activo={filtro !== ""}
						onLimpiar={() => {
							setFiltro("");
							setPagina(1);
						}}
					/>
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
									{DIMENSIONES.filter((d) => e[d.clave] !== null).map((d) => (
										<div key={d.clave}>
											<dt>{d.texto}</dt>
											<dd className={d.clave === "general" ? "pnl-veces" : undefined}>
												{d.clave === "largo" ? textoLargo(e.largo ?? 0) : deCinco(e[d.clave] ?? 0)}
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
