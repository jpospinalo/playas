"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { restErrorMessage } from "@/lib/httpTimeout";
import {
	fechaHora,
	numero,
	pedirPreguntas,
	recortar,
	type FiltroResultado,
	type Preguntas,
} from "@/lib/admin/panel";
import { EstadoCalificacion, EstadoResultado, IconoAviso } from "@/components/admin/panel/Estados";

const OPCIONES: { valor: FiltroResultado; texto: string }[] = [
	{ valor: "", texto: "Todos" },
	{ valor: "con_fuente", texto: "Con norma citada" },
	{ valor: "sin_respuesta_segura", texto: "Sin respuesta segura" },
	{ valor: "no_le_sirvio", texto: "No le sirvió" },
	{ valor: "fuera_de_tema", texto: "Fuera de tema" },
	{ valor: "pide_aclarar", texto: "Pidió aclarar" },
];

const POR_PAGINA = 20;

/** Preguntas del periodo, de la más reciente a la más antigua, paginadas. */
export function Recientes({ dias, tema }: { dias: number; tema: string }) {
	const [resultado, setResultado] = useState<FiltroResultado>("");
	const [pagina, setPagina] = useState(1);
	const [datos, setDatos] = useState<Preguntas | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [intento, setIntento] = useState(0);

	useEffect(() => {
		let vigente = true;
		pedirPreguntas(dias, tema, resultado, pagina, POR_PAGINA)
			.then((r) => {
				if (!vigente) return;
				setDatos(r);
				setError(null);
			})
			.catch((e) => {
				if (vigente) setError(restErrorMessage(e, "No se pudieron cargar las preguntas."));
			});
		return () => {
			vigente = false;
		};
	}, [dias, tema, resultado, pagina, intento]);

	const total = datos?.total ?? 0;
	const desde = total ? (pagina - 1) * POR_PAGINA + 1 : 0;
	const hasta = Math.min(pagina * POR_PAGINA, total);
	const ultimaPagina = Math.max(1, Math.ceil(total / POR_PAGINA));

	return (
		<section className="pnl-bloque" aria-labelledby="t-recientes">
			<div className="pnl-bloque-cab">
				<div>
					<h2 id="t-recientes">Preguntas recientes</h2>
					<p>{datos ? `${numero(total)} en el periodo con este filtro` : " "}</p>
				</div>
				<div className="pnl-campo">
					<label htmlFor="pnl-resultado">Resultado</label>
					<select
						id="pnl-resultado"
						value={resultado}
						onChange={(e) => {
							setResultado(e.target.value as FiltroResultado);
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

			{error ? (
				<div className="pnl-error" role="alert">
					<IconoAviso />
					<div>
						<b>No se pudieron cargar las preguntas.</b>
						<p>{error}</p>
						<button type="button" className="pnl-btn-sec" onClick={() => setIntento((n) => n + 1)}>
							Intentar otra vez
						</button>
					</div>
				</div>
			) : null}

			{datos && datos.items.length === 0 ? (
				<p className="pnl-vacio">
					<b>No hay preguntas con este filtro.</b>
					Pruebe con “Todos” o con un periodo más largo.
				</p>
			) : null}

			{datos && datos.items.length ? (
				<table className="pnl-lista">
					<thead>
						<tr>
							<th scope="col">Fecha</th>
							<th scope="col">Pregunta</th>
							<th scope="col">Tema</th>
							<th scope="col">Resultado</th>
							<th scope="col">Calificación</th>
							<th scope="col">Persona</th>
						</tr>
					</thead>
					<tbody>
						{datos.items.map((p) => (
							<tr key={p.id}>
								<td data-l="Fecha" className="num" style={{ whiteSpace: "nowrap" }}>
									{fechaHora(p.fecha)}
								</td>
								<td className="preg">
									<Link href={`/admin/conversacion?id=${encodeURIComponent(p.conversation_id)}`}>
										{recortar(p.pregunta)}
									</Link>
									{p.esperaba ? <span className="pnl-esperaba">Esperaba: “{p.esperaba}”</span> : null}
								</td>
								<td data-l="Tema">{p.tema_titulo}</td>
								<td data-l="Resultado">
									<EstadoResultado resultado={p.resultado} fuentes={p.fuentes} />
								</td>
								<td data-l="Calificación">
									<EstadoCalificacion calificacion={p.calificacion} />
								</td>
								<td data-l="Persona">{p.persona}</td>
							</tr>
						))}
					</tbody>
				</table>
			) : null}

			{datos && total > POR_PAGINA ? (
				<nav className="pnl-pagin" aria-label="Páginas de preguntas">
					<span>
						Mostrando {numero(desde)} a {numero(hasta)} de {numero(total)}
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
	);
}
