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
	{ valor: "", texto: "Todas las preguntas" },
	{ valor: "con_fuente", texto: "Respondió citando normas" },
	{ valor: "sin_respuesta_segura", texto: "Sin norma que la respalde" },
	{ valor: "no_le_sirvio", texto: "No le sirvió" },
	{ valor: "fuera_de_tema", texto: "Fuera del tema de playas" },
	{ valor: "pide_aclarar", texto: "Pidió aclarar la pregunta" },
];

const POR_PAGINA = 20;

/**
 * Preguntas del periodo, de la más reciente a la más antigua. Cada fila se
 * lee de un vistazo: qué preguntó la persona, el tema, cómo respondió ATLAS
 * y si le sirvió (PQ-J2).
 */
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
					<p>Qué preguntó cada persona, cómo respondió ATLAS y si le sirvió.</p>
				</div>
				<div className="pnl-campo">
					<label htmlFor="pnl-resultado">Mostrar</label>
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
					Pruebe con “Todas las preguntas” o con un periodo más largo.
				</p>
			) : null}

			{datos && datos.items.length ? (
				<ol className="pnl-filas" aria-label={`Preguntas ${numero(desde)} a ${numero(hasta)} de ${numero(total)}`}>
					{datos.items.map((p) => (
						<li key={p.id} className="pnl-fila">
							<div className="pnl-fila-q">
								<Link href={`/admin/conversacion?id=${encodeURIComponent(p.conversation_id)}`}>
									{recortar(p.pregunta, 220)}
								</Link>
								<p className="pnl-fila-meta">
									<span className="pnl-etq">{p.tema_titulo}</span>
									{p.playa ? <span className="lugar">{p.playa}</span> : null}
									<span>
										{p.persona}, {fechaHora(p.fecha)}
									</span>
								</p>
								{p.esperaba ? <p className="pnl-esperaba">Esperaba: “{p.esperaba}”</p> : null}
							</div>
							<dl className="pnl-fila-estado">
								<div>
									<dt>ATLAS</dt>
									<dd>
										<EstadoResultado resultado={p.resultado} fuentes={p.fuentes} />
									</dd>
								</div>
								<div>
									<dt>La persona</dt>
									<dd>
										<EstadoCalificacion calificacion={p.calificacion} />
									</dd>
								</div>
							</dl>
						</li>
					))}
				</ol>
			) : null}

			{datos && total > 0 ? (
				<nav className="pnl-pagin" aria-label="Páginas de preguntas">
					<span>
						{numero(desde)} a {numero(hasta)} de {numero(total)} preguntas
					</span>
					{total > POR_PAGINA ? (
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
					) : null}
				</nav>
			) : null}
		</section>
	);
}
