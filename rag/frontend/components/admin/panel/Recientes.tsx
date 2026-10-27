"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Link from "next/link";
import {
	enlaceConversacion,
	fechaHora,
	mensajeError,
	numero,
	pedirPreguntas,
	recortar,
	type FiltroPersona,
	type FiltroResultado,
	type Preguntas,
} from "@/lib/admin/panel";
import { EstadoCalificacion, EstadoResultado, IconoAviso } from "@/components/admin/panel/Estados";

export type OpcionFiltro = { valor: FiltroResultado; texto: string };

export const OPCIONES_PREGUNTAS: OpcionFiltro[] = [
	{ valor: "", texto: "Todas las preguntas" },
	{ valor: "con_fuente", texto: "Respondió citando fuentes" },
	{ valor: "sin_respuesta_segura", texto: "Sin respuesta segura" },
	{ valor: "no_le_sirvio", texto: "No le sirvió" },
	{ valor: "fuera_de_tema", texto: "Fuera del tema de playas" },
	{ valor: "pide_aclarar", texto: "Pidió aclarar la pregunta" },
];

/** 20 por página en PC y 10 en celular, para que la página no sea eterna (PQ-41). */
const consultaCelular = "(max-width: 600px)";
function suscribirCelular(avisar: () => void) {
	if (typeof window === "undefined" || !window.matchMedia) return () => {};
	const mq = window.matchMedia(consultaCelular);
	mq.addEventListener("change", avisar);
	return () => mq.removeEventListener("change", avisar);
}
function usePorPagina(): number {
	return useSyncExternalStore(
		suscribirCelular,
		() => (window.matchMedia?.(consultaCelular).matches ? 10 : 20),
		() => 20,
	);
}

/**
 * Preguntas del periodo, de la más reciente a la más antigua. Cada fila se
 * lee de un vistazo: qué preguntó la persona, el tema, cómo respondió ATLAS
 * y si le sirvió (PQ-J2).
 */
export function Recientes({
	dias,
	tema,
	resultado,
	onResultado,
	volver,
	titulo = "Preguntas recientes",
	descripcion = "Qué preguntó cada persona, cómo respondió ATLAS y si le sirvió.",
	opciones = OPCIONES_PREGUNTAS,
	persona,
}: {
	dias: number;
	tema: string;
	resultado: FiltroResultado;
	onResultado: (r: FiltroResultado) => void;
	volver: string;
	titulo?: string;
	descripcion?: string;
	opciones?: OpcionFiltro[];
	persona?: FiltroPersona;
}) {
	const POR_PAGINA = usePorPagina();
	const [pagina, setPagina] = useState(1);
	const [datos, setDatos] = useState<Preguntas | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [intento, setIntento] = useState(0);

	useEffect(() => {
		let vigente = true;
		pedirPreguntas(dias, tema, resultado, pagina, POR_PAGINA, persona)
			.then((r) => {
				if (!vigente) return;
				setDatos(r);
				setError(null);
			})
			.catch((e) => {
				if (vigente) setError(mensajeError(e, "No se pudieron cargar las preguntas."));
			});
		return () => {
			vigente = false;
		};
	}, [dias, tema, resultado, pagina, intento, POR_PAGINA, persona]);

	const total = datos?.total ?? 0;
	const desde = total ? (pagina - 1) * POR_PAGINA + 1 : 0;
	const hasta = Math.min(pagina * POR_PAGINA, total);
	const ultimaPagina = Math.max(1, Math.ceil(total / POR_PAGINA));

	return (
		<section className="pnl-bloque" aria-labelledby="t-recientes">
			<div className="pnl-bloque-cab">
				<div>
					<h2 id="t-recientes">{titulo}</h2>
					<p>{descripcion}</p>
				</div>
				<div className="pnl-campo">
					<label htmlFor="pnl-resultado">Mostrar</label>
					<select
						id="pnl-resultado"
						value={resultado}
						onChange={(e) => {
							onResultado(e.target.value as FiltroResultado);
							setPagina(1);
						}}
					>
						{opciones.map((o) => (
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
					Pruebe con otra opción en “Mostrar” o con un periodo más largo.
				</p>
			) : null}

			{datos && datos.items.length ? (
				<ol className="pnl-filas" aria-label={`Preguntas ${numero(desde)} a ${numero(hasta)} de ${numero(total)}`}>
					{datos.items.map((p) => (
						<li key={p.id} className="pnl-fila">
							<div className="pnl-fila-q">
								<Link href={enlaceConversacion(p.conversation_id, volver)}>
									{recortar(p.pregunta, 220)}
								</Link>
								<p className="pnl-fila-meta">
									<span className="pnl-etq">{p.tema_titulo}</span>
									{p.playa ? <span className="lugar">{p.playa}</span> : null}
									<span>
										{p.participante ? `${p.participante}: ` : ""}
										{p.persona}, {fechaHora(p.fecha)}
									</span>
								</p>
								{p.esperaba ? <p className="pnl-esperaba">Esperaba: “{p.esperaba}”</p> : null}
							</div>
							<dl className="pnl-fila-estado">
								<div>
									<dt>ATLAS</dt>
									<dd>
										<EstadoResultado
											resultado={p.resultado}
											fuentes={p.fuentes}
											sentencias={p.fuentes_sentencias}
										/>
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
